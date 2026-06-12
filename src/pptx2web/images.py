"""PNG → WebP + miniaturas + content-hash (D3: raster, D6: peso, D7: caché)."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from PIL import Image

from .models import RenderedSlide, SlideAssets

log = logging.getLogger("pptx2web")

THUMB_WIDTH = 240
THUMB_QUALITY = 70
SLIDE_WEIGHT_WARNING_BYTES = 1024 * 1024  # presupuesto §6


def process(
    rendered: list[RenderedSlide],
    out: Path,
    quality: int = 82,
    fmt: str = "webp",
) -> tuple[list[SlideAssets], list[str]]:
    """Convierte los PNG intermedios a assets finales hasheados.

    Devuelve (assets, warnings). Borra los PNG intermedios al terminar.
    """
    slides_dir = out / "slides"
    thumbs_dir = out / "thumbs"
    slides_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    ext = ".webp" if fmt == "webp" else ".png"
    assets: list[SlideAssets] = []
    warnings: list[str] = []
    total = len(rendered)

    for rs in rendered:
        with Image.open(rs.png_path) as im:
            im = im.convert("RGB") if fmt == "webp" else im

            if fmt == "webp":
                tmp_slide = slides_dir / f"_slide-{rs.index:03d}.webp"
                im.save(tmp_slide, "WEBP", quality=quality, method=6)
            else:
                tmp_slide = slides_dir / f"_slide-{rs.index:03d}.png"
                im.save(tmp_slide, "PNG", optimize=True)

            thumb_h = max(1, round(im.height * THUMB_WIDTH / im.width))
            thumb = im.resize((THUMB_WIDTH, thumb_h), Image.LANCZOS)
            tmp_thumb = thumbs_dir / f"_thumb-{rs.index:03d}.webp"
            thumb.convert("RGB").save(
                tmp_thumb, "WEBP", quality=THUMB_QUALITY, method=6
            )

        slide_name = _finalize(tmp_slide, f"slide-{rs.index:03d}", ext)
        thumb_name = _finalize(tmp_thumb, f"thumb-{rs.index:03d}", ".webp")

        src_bytes = (slides_dir / slide_name).stat().st_size
        if src_bytes > SLIDE_WEIGHT_WARNING_BYTES:
            warnings.append(
                f"Slide {rs.index}: {src_bytes / 1024:.0f} KB supera el "
                "presupuesto de 1 MB (¿imagen fotográfica a pantalla completa? "
                "considera --quality menor)"
            )

        rs.png_path.unlink(missing_ok=True)
        log.info("[%d/%d] %s", rs.index, total, slide_name)
        assets.append(
            SlideAssets(
                index=rs.index,
                src=f"slides/{slide_name}",
                thumb=f"thumbs/{thumb_name}",
                src_bytes=src_bytes,
                thumb_bytes=(thumbs_dir / thumb_name).stat().st_size,
            )
        )

    return assets, warnings


def content_hash(path: Path) -> str:
    """Primeros 8 hex del SHA-256 del contenido (D7)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:8]


def _finalize(tmp_path: Path, stem: str, ext: str) -> str:
    name = f"{stem}.{content_hash(tmp_path)}{ext}"
    final = tmp_path.with_name(name)
    if final.exists():  # mismo contenido de una corrida anterior: reutilizar
        tmp_path.unlink()
    else:
        tmp_path.replace(final)
    return name
