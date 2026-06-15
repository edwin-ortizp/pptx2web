"""Actualizaciones OTA contra GitHub Releases (dos canales: temas y app).

Sin dependencias nuevas: usa solo la stdlib (`urllib`, `json`, `hashlib`,
`subprocess`). Pensado para la app *congelada* (PyInstaller `--onedir`) instalada
por-usuario en `%LOCALAPPDATA%`, donde la carpeta es escribible sin admin.

Dos canales independientes:

* **Temas** (`check_themes`): descarga un `themes-manifest.json` (asset del
  release) con `{nombre.json: sha256}` y sincroniza solo los temas nuevos o
  cambiados dentro de `config.themes_dir()`. No requiere reconstruir el `.exe`.
* **App** (`check_app`): compara la versión del último release con
  `pptx2web.__version__`; si hay una nueva, avisa. `apply_app_update` descarga el
  instalador (`pptx2web-setup-<v>.exe`), lo lanza en silencio y cierra la app para
  que Inno Setup reemplace los archivos y relance.

Configuración del repositorio de distribución: por defecto se leen las constantes
de abajo, pero pueden sobreescribirse —sin reconstruir— con un
`%LOCALAPPDATA%\\pptx2web\\update.json` o variables de entorno
(`PPTX2WEB_OTA_OWNER`, `PPTX2WEB_OTA_REPO`, `PPTX2WEB_OTA_TOKEN`).

Recomendación de seguridad: usar un **repo de distribución público aparte** (solo
instalador + temas; el código fuente sigue privado) para no embeber ningún token.
Si el repo es privado, define un token *fine-grained* de **solo lectura** acotado
a ese repo; aun así es extraíble del binario.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__, config as config_mod

log = logging.getLogger("pptx2web")

# ── coordenadas del repo de distribución (editar antes de compilar) ──────────
GITHUB_OWNER = "novapixel-org"
GITHUB_REPO = "pptx2web-dist"
GITHUB_TOKEN = ""  # vacío para repo público (recomendado). Ver docstring.

THEMES_MANIFEST_ASSET = "themes-manifest.json"
INSTALLER_PREFIX = "pptx2web-setup-"
API_ROOT = "https://api.github.com"
_TIMEOUT = 15  # s


# ── configuración (overridable sin recompilar) ──────────────────────────────

def _user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(base) / "pptx2web"


def _settings() -> dict[str, str]:
    """Coordenadas efectivas: constantes < update.json < variables de entorno."""
    cfg = {"owner": GITHUB_OWNER, "repo": GITHUB_REPO, "token": GITHUB_TOKEN}
    override = _user_data_dir() / "update.json"
    if override.exists():
        try:
            data = json.loads(override.read_text(encoding="utf-8"))
            for key in ("owner", "repo", "token"):
                if data.get(key):
                    cfg[key] = str(data[key])
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("update.json ilegible: %s", exc)
    cfg["owner"] = os.environ.get("PPTX2WEB_OTA_OWNER", cfg["owner"])
    cfg["repo"] = os.environ.get("PPTX2WEB_OTA_REPO", cfg["repo"])
    cfg["token"] = os.environ.get("PPTX2WEB_OTA_TOKEN", cfg["token"])
    return cfg


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _request(url: str, token: str, accept: str) -> urllib.request.Request:
    headers = {"User-Agent": "pptx2web-updater", "Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _fetch_json(url: str, token: str):
    with urllib.request.urlopen(
        _request(url, token, "application/vnd.github+json"), timeout=_TIMEOUT
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_bytes(url: str, token: str) -> bytes:
    # Para assets de release: octet-stream resuelve la descarga incluso en repos
    # privados (la API redirige al blob firmado).
    with urllib.request.urlopen(
        _request(url, token, "application/octet-stream"), timeout=_TIMEOUT * 4
    ) as resp:
        return resp.read()


def _latest_release(cfg: dict[str, str]) -> dict | None:
    url = f"{API_ROOT}/repos/{cfg['owner']}/{cfg['repo']}/releases/latest"
    try:
        return _fetch_json(url, cfg["token"])
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.info("OTA: no se pudo consultar el último release: %s", exc)
        return None


def _asset(release: dict, name: str) -> dict | None:
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return asset
    return None


def _asset_starting(release: dict, prefix: str) -> dict | None:
    for asset in release.get("assets", []):
        if str(asset.get("name", "")).startswith(prefix):
            return asset
    return None


def _asset_download(asset: dict, token: str) -> bytes:
    # En repos privados hay que usar la URL de la API (con auth); en públicos
    # `browser_download_url` también sirve. Preferimos la de la API si hay token.
    url = asset["url"] if token else asset.get("browser_download_url", asset["url"])
    return _fetch_bytes(url, token)


# ── versionado ───────────────────────────────────────────────────────────────

def _version_tuple(text: str) -> tuple[int, ...]:
    text = (text or "").strip().lstrip("vV")
    parts: list[int] = []
    for chunk in text.split("."):
        num = "".join(ch for ch in chunk if ch.isdigit())
        if not num:
            break
        parts.append(int(num))
    return tuple(parts) or (0,)


def _is_newer(remote: str, local: str) -> bool:
    return _version_tuple(remote) > _version_tuple(local)


# ── canal de temas ───────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def check_themes() -> list[str]:
    """Sincroniza los temas con el manifiesto del último release.

    Devuelve los nombres (`<tema>.json`) creados o actualizados. Silencioso ante
    errores de red: nunca bloquea el arranque.
    """
    cfg = _settings()
    release = _latest_release(cfg)
    if not release:
        return []

    manifest_asset = _asset(release, THEMES_MANIFEST_ASSET)
    if not manifest_asset:
        return []
    try:
        manifest = json.loads(_asset_download(manifest_asset, cfg["token"]).decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.info("OTA temas: manifiesto ilegible: %s", exc)
        return []

    wanted: dict[str, str] = manifest.get("themes", {})
    dest = config_mod.themes_dir()
    updated: list[str] = []
    for name, want_sha in wanted.items():
        if not name.endswith(".json"):
            continue
        local = dest / name
        if local.exists() and _sha256(local.read_bytes()) == want_sha:
            continue
        asset = _asset(release, name)
        if not asset:
            log.info("OTA temas: %s en manifiesto pero sin asset", name)
            continue
        try:
            data = _asset_download(asset, cfg["token"])
        except (urllib.error.URLError, OSError) as exc:
            log.info("OTA temas: fallo al bajar %s: %s", name, exc)
            continue
        if want_sha and _sha256(data) != want_sha:
            log.warning("OTA temas: sha256 no coincide para %s; se ignora", name)
            continue
        _atomic_write(local, data)
        updated.append(name)
        log.info("OTA temas: actualizado %s", name)
    return updated


# ── canal de app ─────────────────────────────────────────────────────────────

def check_app() -> dict | None:
    """Si hay una versión más nueva publicada, devuelve datos del update.

    Estructura: `{version, assetUrl, assetName}`. No descarga nada todavía.
    Devuelve None si no hay novedad o ante errores.
    """
    cfg = _settings()
    release = _latest_release(cfg)
    if not release:
        return None
    remote = release.get("tag_name") or release.get("name") or ""
    if not _is_newer(remote, __version__):
        return None
    asset = _asset_starting(release, INSTALLER_PREFIX)
    if not asset:
        log.info("OTA app: release %s sin instalador (%s*)", remote, INSTALLER_PREFIX)
        return None
    return {
        "version": remote.lstrip("vV"),
        "assetUrl": asset["url"] if cfg["token"] else asset.get("browser_download_url", asset["url"]),
        "assetName": asset["name"],
    }


def apply_app_update(update: dict) -> bool:
    """Descarga el instalador y lo lanza en silencio; el llamador debe cerrar la
    app a continuación para que Inno Setup pueda reemplazar los archivos.

    Devuelve True si el instalador se lanzó. Solo opera en modo congelado.
    """
    if not is_frozen():
        log.info("OTA app: ignorado en modo desarrollo")
        return False
    cfg = _settings()
    try:
        data = _fetch_bytes(update["assetUrl"], cfg["token"])
    except (urllib.error.URLError, OSError, KeyError) as exc:
        log.warning("OTA app: fallo al descargar instalador: %s", exc)
        return False

    setup_path = Path(tempfile.gettempdir()) / update.get("assetName", "pptx2web-setup.exe")
    try:
        setup_path.write_bytes(data)
    except OSError as exc:
        log.warning("OTA app: no se pudo guardar el instalador: %s", exc)
        return False

    # /SILENT muestra solo la barra de progreso; el instalador relanza la app.
    try:
        subprocess.Popen(
            [str(setup_path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            close_fds=True,
        )
    except OSError as exc:
        log.warning("OTA app: no se pudo lanzar el instalador: %s", exc)
        return False
    return True
