"""Orquestación de la conversión, compartida por la CLI y la GUI.

Es el único lugar que conoce el orden del pipeline (validar → render → metadata
→ media → imágenes → config → empaquetado). Tanto `cli.py` como `gui/app.py` son
front-ends delgados sobre `convert()`.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config as config_mod
from . import images, media, metadata, packager
from .renderer import render_slides
from .validate import ValidationError, validate_input

# on_progress(stage, current, total): stage es un id corto ("render",
# "metadata", "media", "images", "package", "done"); current/total son
# opcionales (p.ej. lámina i de N durante el render).
ProgressCb = Callable[[str, "int | None", "int | None"], None]


@dataclass
class Summary:
    out_dir: Path
    index_path: Path
    slide_count: int
    image_bytes: int
    media_count: int
    build_id: str
    warnings: list[str] = field(default_factory=list)


def convert(
    *,
    pptx_path: Path,
    out_dir: Path,
    scale: float = 2.0,
    quality: int = 82,
    fmt: str = "webp",
    theme: str | None = None,
    deck_config: dict | None = None,
    config_dir: Path | None = None,
    make_zip: bool = False,
    on_progress: ProgressCb | None = None,
) -> Summary:
    """Convierte `pptx_path` en una carpeta web autocontenida en `out_dir`.

    No imprime ni hace sys.exit: propaga ValidationError /
    PowerPointNotAvailableError / RenderError para que el front-end decida.
    """
    def emit(stage: str, current: int | None = None, total: int | None = None) -> None:
        if on_progress:
            on_progress(stage, current, total)

    pptx_path = validate_input(pptx_path)
    scale = min(max(scale, 0.5), 3.0)
    quality = min(max(quality, 1), 100)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="pptx2web-"))
    try:
        emit("render", 0, None)
        rendered = render_slides(
            pptx_path, tmp_dir, scale=scale,
            on_slide=lambda i, total: emit("render", i, total),
        )

        emit("metadata")
        deck = metadata.extract(pptx_path)
        warnings.extend(deck.warnings)
        if deck.slide_count != len(rendered):
            from .renderer import RenderError
            raise RenderError(
                f"Inconsistencia: COM exportó {len(rendered)} slides pero "
                f"python-pptx ve {deck.slide_count}."
            )

        emit("media")
        media_files, media_warnings = media.process_media(deck, pptx_path, out_dir)
        warnings.extend(media_warnings)

        emit("images", 0, len(rendered))
        assets, img_warnings = images.process(
            rendered, out_dir, quality, fmt,
            on_image=lambda i, total: emit("images", i, total),
        )
        warnings.extend(img_warnings)

        player_config, cfg_warnings = config_mod.resolve(
            deck_config, theme, deck.slide_count
        )
        warnings.extend(cfg_warnings)

        emit("package")
        slide_px = (rendered[0].width_px, rendered[0].height_px)
        manifest = packager.build_manifest(deck, assets, slide_px)
        index_path = packager.package(
            manifest, out_dir, player_config,
            config_dir=config_dir, make_zip=make_zip,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    emit("done")
    return Summary(
        out_dir=out_dir,
        index_path=index_path,
        slide_count=manifest["slideCount"],
        image_bytes=sum(a.src_bytes + a.thumb_bytes for a in assets),
        media_count=len(media_files),
        build_id=manifest["buildId"],
        warnings=warnings,
    )
