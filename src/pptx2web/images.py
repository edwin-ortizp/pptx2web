"""PNG → WebP + miniaturas + content-hash (D3: raster, D6: peso, D7: caché)."""
from __future__ import annotations

from .diagnostics import timed

import hashlib
import io
import time
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path

from PIL import Image

from .models import RenderedSlide, SlideAssets

log = logging.getLogger("pptx2web")

THUMB_WIDTH = 240
THUMB_QUALITY = 70
SLIDE_WEIGHT_WARNING_BYTES = 1024 * 1024  # presupuesto §6


@timed("images.process")
def process(
    rendered: list[RenderedSlide],
    out: Path,
    quality: int = 82,
    fmt: str = "webp",
    on_image=None,
) -> tuple[list[SlideAssets], list[str]]:
    """Convierte los PNG intermedios a assets finales hasheados.

    Devuelve (assets, warnings). Borra los PNG intermedios al terminar.
    `on_image(i, total)` (opcional) reporta progreso tras cada lámina.
    """
    # AVIF: two workers exceeded the 10% benchmark gate with identical output.
    # Other formats have not been benchmarked for concurrency.
    return _process_images(rendered, out, quality, fmt, on_image, workers=2 if fmt == "avif" else 1)


def _process_images(rendered, out, quality=82, fmt="webp", on_image=None, workers=1):
    """Internal worker-count override for reproducible benchmarks."""
    if workers not in (1, 2):
        raise ValueError("workers must be 1 or 2")
    (out / "slides").mkdir(parents=True, exist_ok=True)
    (out / "thumbs").mkdir(parents=True, exist_ok=True)
    assets, warnings = [], []
    def run(rs):
        return _process_slide(rs, out, quality, fmt)
    executor = ThreadPoolExecutor(max_workers=2) if workers == 2 else None
    try:
        results = executor.map(run, rendered) if executor else map(run, rendered)
        for current, (asset, slide_warnings) in enumerate(results, 1):
            assets.append(asset)
            warnings.extend(slide_warnings)
            log.info("[%d/%d] %s", current, len(rendered), Path(asset.src).name)
            if on_image:
                on_image(current, len(rendered))
    finally:
        if executor:
            executor.shutdown(wait=True, cancel_futures=True)
    return assets, warnings


def _process_slide(rs, out, quality, fmt):
    start = time.monotonic()
    phase = "read"
    durations = {}
    try:
        with Image.open(rs.png_path) as source:
            source.load()
            im = source.convert("RGB") if fmt in ("webp", "avif") else source.copy()
        durations["read"] = time.monotonic() - start
        with im:
            width, height = im.size
            phase = "encode"
            mark = time.monotonic()
            with io.BytesIO() as buffer:
                if fmt == "webp":
                    im.save(buffer, "WEBP", quality=quality, method=6)
                    ext = ".webp"
                elif fmt == "avif":
                    _save_avif(im, buffer, quality)
                    ext = ".avif"
                else:
                    im.save(buffer, "PNG", optimize=True)
                    ext = ".png"
                slide_data = buffer.getvalue()
            durations["encode"] = time.monotonic() - mark
            phase = "thumbnail"
            mark = time.monotonic()
            thumb_h = max(1, round(height * THUMB_WIDTH / width))
            with im.resize((THUMB_WIDTH, thumb_h), Image.LANCZOS) as thumb:
                with thumb.convert("RGB") as rgb, io.BytesIO() as buffer:
                    rgb.save(buffer, "WEBP", quality=THUMB_QUALITY, method=6)
                    thumb_data = buffer.getvalue()
            durations["thumbnail"] = time.monotonic() - mark
        phase = "write_finalize"
        mark = time.monotonic()
        tmp_slide = out / "slides" / f"_slide-{rs.index:03d}{ext}"
        tmp_thumb = out / "thumbs" / f"_thumb-{rs.index:03d}.webp"
        tmp_slide.write_bytes(slide_data)
        tmp_thumb.write_bytes(thumb_data)
        slide_name = _finalize(tmp_slide, f"slide-{rs.index:03d}", ext)
        thumb_name = _finalize(tmp_thumb, f"thumb-{rs.index:03d}", ".webp")
        rs.png_path.unlink(missing_ok=True)
        durations["write_finalize"] = time.monotonic() - mark
        log.info("image.result slide=%s width=%s height=%s format=%s quality=%s bytes=%s thumb_bytes=%s "
                 "read_ms=%.1f encode_ms=%.1f thumbnail_ms=%.1f write_finalize_ms=%.1f total_ms=%.1f",
                 rs.index, width, height, fmt, quality, len(slide_data), len(thumb_data),
                 durations["read"] * 1000, durations["encode"] * 1000,
                 durations["thumbnail"] * 1000, durations["write_finalize"] * 1000,
                 (time.monotonic() - start) * 1000)
        warnings = []
        if len(slide_data) > SLIDE_WEIGHT_WARNING_BYTES:
            warnings.append(f"Slide {rs.index}: {len(slide_data) / 1024:.0f} KB supera el "
                            "presupuesto de 1 MB (¿imagen fotográfica a pantalla completa? "
                            "considera --quality menor)")
        return SlideAssets(index=rs.index, src=f"slides/{slide_name}", thumb=f"thumbs/{thumb_name}",
                           src_bytes=len(slide_data), thumb_bytes=len(thumb_data)), warnings
    except Exception:
        log.exception("image.error slide=%s phase=%s format=%s quality=%s elapsed_ms=%.1f",
                      rs.index, phase, fmt, quality, (time.monotonic() - start) * 1000)
        raise


def _save_avif(im, path, quality: int) -> None:
    """AVIF con un `speed` moderado para que el encode no sea lento; si la
    versión de Pillow no acepta ese parámetro, cae a solo quality."""
    try:
        im.save(path, "AVIF", quality=quality, speed=6)
    except (TypeError, ValueError):
        if hasattr(path, "seek"):
            path.seek(0)
            path.truncate()
        im.save(path, "AVIF", quality=quality)


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
