"""Ensamblado final: manifest, player hasheado, index.html y ZIP opcional."""
from __future__ import annotations

import datetime as _dt
import json
import logging
import secrets
import shutil
import sys
import zipfile
from pathlib import Path

from .images import content_hash
from .models import Deck, SlideAssets

log = logging.getLogger("pptx2web")


def player_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).parent / "player"
    return Path(__file__).resolve().parents[2] / "player"


def build_manifest(
    deck: Deck, assets: list[SlideAssets], slide_px: tuple[int, int]
) -> dict:
    by_index = {a.index: a for a in assets}
    slides = []
    for meta in deck.slides:
        a = by_index[meta.index]
        slides.append(
            {
                "index": meta.index,
                "title": meta.title,
                "src": a.src,
                "thumb": a.thumb,
                "notes": meta.notes_html,
                "text": meta.search_text,
                "transition": meta.transition.as_dict(),
                "media": [
                    {
                        "type": m.type,
                        "src": m.src,
                        "rect": m.rect.as_dict(),
                        "autoplay": m.autoplay,
                    }
                    for m in meta.media
                    if m.src
                ],
                "links": [link.as_dict() for link in meta.links],
                "quiz": meta.quiz.as_dict() if meta.quiz else None,
            }
        )
    return {
        "version": 1,
        "buildId": _build_id(),
        "title": deck.title,
        "slideSize": {"width": slide_px[0], "height": slide_px[1]},
        "slideCount": deck.slide_count,
        "slides": slides,
    }


def package(
    manifest: dict,
    out_dir: Path,
    player_config: dict | None = None,
    config_dir: Path | None = None,
    make_zip: bool = False,
) -> Path:
    """Escribe manifest.json (depuración), copia player hasheado y genera
    index.html con manifest y config embebidos (D7). Devuelve la ruta del index.

    `config_dir` es la carpeta del config del deck: el logo se resuelve
    relativo a ella y se copia hasheado a la salida.
    """
    src = player_dir()
    template = (src / "index.template.html").read_text(encoding="utf-8")

    if player_config is None:
        from .config import resolve
        player_config, _ = resolve(None, None, manifest["slideCount"])
    else:
        # copia profunda: _copy_logo reescribe course.logo y el dict es del caller
        player_config = json.loads(json.dumps(player_config))

    # manifest.json en disco solo como artefacto de depuración; el player
    # nunca lo pide por red (el JSON viaja inline en el HTML).
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    js_name = _copy_hashed(src / "player.js", out_dir)
    css_name = _copy_hashed(src / "player.css", out_dir)

    logo_name = _copy_logo(player_config, config_dir, out_dir)

    # config.json en la raíz: editable post-export sin reconvertir (el player
    # lo lee en segundo plano por HTTP y sobrescribe lo embebido)
    (out_dir / "config.json").write_text(
        json.dumps(player_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    html_out = (
        template.replace("{{TITLE}}", _escape_html(manifest["title"]))
        .replace("{{BUILD_ID}}", manifest["buildId"])
        .replace("{{PLAYER_JS}}", js_name)
        .replace("{{PLAYER_CSS}}", css_name)
        .replace("{{MANIFEST_INLINE}}", _inline_json(manifest))
        .replace("{{CONFIG_INLINE}}", _inline_json(player_config))
    )
    index_path = out_dir / "index.html"
    index_path.write_text(html_out, encoding="utf-8")

    keep = {js_name, css_name}
    if logo_name:
        keep.add(logo_name)
    _prune_orphans(manifest, out_dir, keep=keep)

    if make_zip:
        zip_path = out_dir.parent / f"{out_dir.name}.zip"
        _zip_dir(out_dir, zip_path)
        log.info("ZIP generado: %s", zip_path)

    return index_path


def _inline_json(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False)
    # </script> dentro de strings del JSON rompería el bloque inline
    return text.replace("</", "<\\/")


def _copy_logo(
    player_config: dict, config_dir: Path | None, out_dir: Path
) -> str | None:
    """Copia el logo del curso (relativo al config) con content-hash y
    reescribe la referencia en player_config."""
    logo_ref = (player_config.get("course") or {}).get("logo")
    if not logo_ref:
        return None
    logo_path = Path(logo_ref)
    if not logo_path.is_absolute():
        logo_path = (config_dir or Path.cwd()) / logo_path
    if not logo_path.exists():
        log.warning("Logo no encontrado, se omite: %s", logo_path)
        player_config["course"]["logo"] = None
        return None
    digest = content_hash(logo_path)
    name = f"logo.{digest}{logo_path.suffix.lower()}"
    shutil.copy2(logo_path, out_dir / name)
    player_config["course"]["logo"] = name
    return name


def _prune_orphans(manifest: dict, out_dir: Path, keep: set[str]) -> None:
    """Al republicar sobre la misma carpeta, elimina assets de versiones
    anteriores que el manifest actual ya no referencia."""
    referenced = set(keep)
    for s in manifest["slides"]:
        referenced.add(s["src"])
        referenced.add(s["thumb"])
        referenced.update(m["src"] for m in s["media"])

    for sub in ("slides", "thumbs", "media"):
        folder = out_dir / sub
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            rel = f"{sub}/{f.name}"
            if f.is_file() and rel not in referenced:
                f.unlink()
                log.debug("huérfano eliminado: %s", rel)

    for f in out_dir.glob("player.*.js"):
        if f.name not in referenced:
            f.unlink()
    for f in out_dir.glob("player.*.css"):
        if f.name not in referenced:
            f.unlink()
    for f in out_dir.glob("logo.*"):
        if f.name not in referenced:
            f.unlink()


def _copy_hashed(src_file: Path, out_dir: Path) -> str:
    digest = content_hash(src_file)
    name = f"{src_file.stem}.{digest}{src_file.suffix}"
    shutil.copy2(src_file, out_dir / name)
    return name


def _build_id() -> str:
    now = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{now}-{secrets.token_hex(3)}"


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _zip_dir(folder: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(folder))
