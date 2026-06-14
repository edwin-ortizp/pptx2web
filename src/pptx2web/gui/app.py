"""Backend de la GUI: ventana pywebview + clase Api (puente JS↔Python).

Cada método de `Api` es una capa fina sobre módulos ya probados del núcleo
(`validate`, `metadata`, `config`, `images`, `packager`, `pipeline`). No duplica
lógica de conversión ni de validación.
"""
from __future__ import annotations

import functools
import json
import shutil
import tempfile
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview

from .. import config as config_mod
from .. import images, metadata, packager, pipeline
from ..renderer import PowerPointNotAvailableError, RenderError, render_slides
from ..validate import ValidationError, validate_input

ASSETS = Path(__file__).resolve().parent / "assets"
PREVIEW_SCALE = 0.4   # render liviano solo para previsualizar
PREVIEW_QUALITY = 70


def _file_dialog(kind: str):
    """Constante de tipo de diálogo compatible con pywebview nuevo y viejo."""
    fd = getattr(webview, "FileDialog", None)
    if fd is not None:  # pywebview ≥ 5.x
        return fd.OPEN if kind == "open" else fd.FOLDER
    return webview.OPEN_DIALOG if kind == "open" else webview.FOLDER_DIALOG


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # sin ruido en consola
        pass


class Api:
    """Expuesta a la UI como `window.pywebview.api.*`."""

    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self._deck_path: Path | None = None
        self._deck = None
        self._assets: list = []
        self._slide_px: tuple[int, int] = (0, 0)
        self._preview_dir: Path | None = None
        self._server_port: int | None = None

    # ── selección de archivos (diálogos nativos) ──────────────────────────

    def pick_pptx(self) -> str | None:
        res = self.window.create_file_dialog(
            _file_dialog("open"), file_types=("PowerPoint (*.pptx)",)
        )
        return res[0] if res else None

    def pick_logo(self) -> str | None:
        res = self.window.create_file_dialog(
            _file_dialog("open"),
            file_types=("Imágenes (*.png;*.jpg;*.jpeg;*.svg;*.webp)",),
        )
        return res[0] if res else None

    def pick_output_dir(self) -> str | None:
        res = self.window.create_file_dialog(_file_dialog("folder"))
        return res[0] if res else None

    # ── temas y validación ────────────────────────────────────────────────

    def list_themes(self) -> list[dict]:
        out = []
        for name in config_mod.available_themes():
            theme = config_mod.load_theme(name)
            out.append({
                "name": name,
                "description": theme.get("description", ""),
                "colors": theme.get("colors", {}),
            })
        return out

    def validate_config(self, cfg: dict) -> dict:
        """Corre la MISMA validación que la CLI; errores/warnings estructurados."""
        slide_count = self._deck.slide_count if self._deck else 0
        try:
            resolved, warnings = config_mod.resolve(
                cfg, cfg.get("theme"), slide_count
            )
            return {"ok": True, "warnings": warnings, "resolved": resolved}
        except ValidationError as exc:
            return {"ok": False, "error": str(exc), "warnings": []}

    # ── carga del deck + pre-render para preview ──────────────────────────

    def load_deck(self, path: str) -> dict:
        """Valida, extrae metadatos y pre-renderiza a baja resolución para el
        preview. Devuelve info del deck + config existente si la hay."""
        try:
            pptx_path = validate_input(Path(path))
        except ValidationError as exc:
            return {"ok": False, "error": str(exc)}

        self._deck_path = pptx_path
        self._deck = metadata.extract(pptx_path)
        self._reset_preview()

        try:
            self._prerender_preview()
        except PowerPointNotAvailableError as exc:
            return {"ok": False, "error": str(exc)}
        except RenderError as exc:
            return {"ok": False, "error": str(exc)}

        existing = config_mod.find_deck_config(pptx_path)
        cfg = config_mod.load_deck_config(existing) if existing else None

        return {
            "ok": True,
            "title": self._deck.title,
            "slideCount": self._deck.slide_count,
            "slides": [
                {
                    "index": s.index,
                    "title": s.title,
                    "quiz": s.quiz.as_dict() if s.quiz else None,
                    "links": [link.as_dict() for link in s.links],
                }
                for s in self._deck.slides
            ],
            "configPath": str(existing) if existing else None,
            "config": cfg,
            "deckPath": str(pptx_path),
        }

    def _prerender_preview(self) -> None:
        tmp_png = Path(tempfile.mkdtemp(prefix="pptx2web-prev-png-"))
        try:
            rendered = render_slides(self._deck_path, tmp_png, scale=PREVIEW_SCALE)
            self._slide_px = (rendered[0].width_px, rendered[0].height_px)
            self._assets, _ = images.process(
                rendered, self._preview_dir, PREVIEW_QUALITY, "webp"
            )
        finally:
            shutil.rmtree(tmp_png, ignore_errors=True)

    def build_preview(self, cfg: dict) -> dict:
        """Re-empaqueta el preview con la config actual (sin re-renderizar) y
        devuelve una URL HTTP local para el iframe. Se sirve por http (no file://)
        porque WebView2 no carga archivos locales en subframes ni respeta el
        cache-buster en file://."""
        if not self._assets:
            return {"ok": False, "error": "No hay deck cargado"}
        try:
            player_config, _ = config_mod.resolve(
                cfg, cfg.get("theme"), self._deck.slide_count
            )
        except ValidationError as exc:
            return {"ok": False, "error": str(exc)}
        manifest = packager.build_manifest(self._deck, self._assets, self._slide_px)
        packager.package(
            manifest, self._preview_dir, player_config,
            config_dir=self._deck_path.parent,
        )
        port = self._ensure_server()
        return {"ok": True, "url": f"http://127.0.0.1:{port}/index.html?v={manifest['buildId']}"}

    def _ensure_server(self) -> int:
        """Servidor HTTP local (una vez por sesión) que sirve la carpeta de
        preview. Sirve siempre el `_preview_dir` actual."""
        if self._server_port:
            return self._server_port
        handler = functools.partial(_QuietHandler, directory=str(self._preview_dir))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server_port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return self._server_port

    # ── persistencia del config junto al .pptx ────────────────────────────

    def save_config(self, cfg: dict) -> dict:
        if not self._deck_path:
            return {"ok": False, "error": "No hay deck cargado"}
        path = self._deck_path.with_name(f"{self._deck_path.stem}.config.json")
        path.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"ok": True, "path": str(path)}

    # ── conversión real (en hilo, con progreso por eventos) ───────────────

    def convert(self, opts: dict) -> dict:
        if not self._deck_path:
            return {"ok": False, "error": "No hay deck cargado"}
        threading.Thread(
            target=self._convert_worker, args=(opts,), daemon=True
        ).start()
        return {"started": True}

    def _convert_worker(self, opts: dict) -> None:
        cfg = opts.get("config") or {}
        out = opts.get("outDir")
        out_dir = Path(out) if out else self._deck_path.parent / f"{self._deck_path.stem}-web"
        try:
            summary = pipeline.convert(
                pptx_path=self._deck_path,
                out_dir=out_dir,
                scale=float(opts.get("scale", 2.0)),
                quality=int(opts.get("quality", 82)),
                fmt=opts.get("format", "webp"),
                theme=cfg.get("theme"),
                deck_config=cfg,
                config_dir=self._deck_path.parent,
                make_zip=bool(opts.get("zip", False)),
                on_progress=lambda stage, cur, tot: self._emit(
                    "progress", {"stage": stage, "current": cur, "total": tot}
                ),
            )
            # guardar el config para reuso desde la CLI
            self.save_config(cfg)
            self._emit("done", {
                "outDir": str(summary.out_dir),
                "indexPath": str(summary.index_path),
                "indexUrl": summary.index_path.as_uri(),
                "slideCount": summary.slide_count,
                "imageBytes": summary.image_bytes,
                "mediaCount": summary.media_count,
                "buildId": summary.build_id,
                "warnings": summary.warnings,
            })
        except (ValidationError, PowerPointNotAvailableError, RenderError) as exc:
            self._emit("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001 — superficie para la UI
            self._emit("error", {"message": f"Error inesperado: {exc}"})

    # ── abrir resultados ──────────────────────────────────────────────────

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def open_folder(self, path: str) -> None:
        webbrowser.open(Path(path).as_uri())

    # ── internos ──────────────────────────────────────────────────────────

    def _reset_preview(self) -> None:
        # directorio estable por sesión (el servidor HTTP lo sirve); solo se
        # limpia su contenido al cargar un nuevo deck
        if self._preview_dir is None:
            self._preview_dir = Path(tempfile.mkdtemp(prefix="pptx2web-preview-"))
        else:
            for child in self._preview_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        self._assets = []

    def _emit(self, event: str, payload: dict) -> None:
        if self.window:
            self.window.evaluate_js(
                f"window.guiEvent({json.dumps(event)}, {json.dumps(payload)})"
            )


def main() -> None:
    api = Api()
    window = webview.create_window(
        "pptx2web — Asistente de publicación",
        str(ASSETS / "index.html"),
        js_api=api,
        width=1180,
        height=820,
        min_size=(940, 640),
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
