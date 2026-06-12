"""Extracción de media del .pptx y transcodificación de formatos legacy."""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from .models import Deck

log = logging.getLogger("pptx2web")

# Formatos que los navegadores no reproducen → transcodificar
_LEGACY_VIDEO = {".wmv", ".avi", ".mpg", ".mpeg", ".asf"}
_LEGACY_AUDIO = {".wma", ".wav"}


def find_ffmpeg() -> Path | None:
    """bin/ffmpeg.exe junto a la instalación; si no, el del PATH."""
    bundled = _install_root() / "bin" / "ffmpeg.exe"
    if bundled.exists():
        return bundled
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def _install_root() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def process_media(
    deck: Deck, pptx_path: Path, out_dir: Path
) -> tuple[list[str], list[str]]:
    """Copia/transcodifica cada media part referenciado por el deck a out_dir/media/.

    Asigna MediaItem.src (ruta relativa con content-hash).
    Devuelve (archivos_generados, warnings).
    """
    referenced = {
        item.source_part
        for slide in deck.slides
        for item in slide.media
    }
    if not referenced:
        return [], []

    media_dir = out_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    warnings: list[str] = []
    generated: list[str] = []
    # Un mismo part puede aparecer en varios slides: procesar una sola vez
    resolved: dict[str, str] = {}

    with zipfile.ZipFile(pptx_path) as zf:
        for part_name in sorted(referenced):
            zip_entry = f"ppt/media/{part_name}"
            try:
                data = zf.read(zip_entry)
            except KeyError:
                warnings.append(f"Media no encontrado en el .pptx: {zip_entry}")
                continue

            ext = Path(part_name).suffix.lower()
            raw_path = media_dir / f"_raw{ext}"
            raw_path.write_bytes(data)

            target_ext, needs_transcode = _target_format(ext)
            if needs_transcode and ffmpeg is None:
                warnings.append(
                    f"{part_name}: formato legacy ({ext}) y ffmpeg no disponible; "
                    "se copia el original (puede no reproducirse en el navegador)"
                )
                needs_transcode = False
                target_ext = ext

            if needs_transcode:
                tmp_out = media_dir / f"_transcoded{target_ext}"
                ok = _transcode(ffmpeg, raw_path, tmp_out, target_ext)
                if ok:
                    raw_path.unlink()
                    raw_path = tmp_out
                else:
                    warnings.append(
                        f"{part_name}: la transcodificación falló; se copia el original"
                    )
                    target_ext = ext

            final_name = _hashed_name(part_name, raw_path, target_ext)
            final_path = media_dir / final_name
            raw_path.replace(final_path)
            rel = f"media/{final_name}"
            resolved[part_name] = rel
            generated.append(rel)
            log.info("media: %s -> %s", part_name, rel)

    for slide in deck.slides:
        slide.media = [m for m in slide.media if m.source_part in resolved]
        for item in slide.media:
            item.src = resolved[item.source_part]

    return generated, warnings


def _target_format(ext: str) -> tuple[str, bool]:
    if ext in _LEGACY_VIDEO:
        return ".mp4", True
    if ext in _LEGACY_AUDIO:
        return ".mp3", True
    return ext, False


def _transcode(ffmpeg: Path, src: Path, dst: Path, target_ext: str) -> bool:
    if target_ext == ".mp4":
        codec_args = ["-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
                      "-c:a", "aac", "-movflags", "+faststart"]
    else:  # .mp3
        codec_args = ["-c:a", "libmp3lame", "-q:a", "4"]
    cmd = [str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(src), *codec_args, str(dst)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("ffmpeg falló sobre %s: %s", src.name, exc)
        return False
    if result.returncode != 0:
        log.warning("ffmpeg (%s): %s", src.name, result.stderr.strip()[:300])
        return False
    return dst.exists() and dst.stat().st_size > 0


def _hashed_name(part_name: str, path: Path, ext: str) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    stem = Path(part_name).stem
    # Nombres internos normalizados (ASCII) por si el part trae caracteres raros
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in stem) or "media"
    return f"{safe}.{digest}{ext}"
