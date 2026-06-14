"""Render de slides vía COM con PowerPoint local (D1).

Slide.Export renderiza todos los shapes en su estado final, por lo que
las animaciones intra-slide quedan resueltas sin lógica adicional (D4).
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import RenderedSlide

log = logging.getLogger("pptx2web")

EMU_PER_PT = 12700
PT_TO_PX = 96 / 72
MAX_EXPORT_WIDTH_PX = 4096  # PowerPoint rechaza exports desmesurados

_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


class PowerPointNotAvailableError(Exception):
    """PowerPoint no instalado o COM no instanciable. Exit code 3."""


class RenderError(Exception):
    """Fallo de render no recuperable. Exit code 4."""


def read_slide_size_pt(pptx_path: Path) -> tuple[float, float]:
    """Lee el tamaño del lienzo desde ppt/presentation.xml (sin COM)."""
    with zipfile.ZipFile(pptx_path) as zf:
        root = ET.fromstring(zf.read("ppt/presentation.xml"))
    sldsz = root.find(f"{{{_NS_P}}}sldSz")
    if sldsz is None:
        # Default OOXML: 10 x 7.5 in (4:3)
        return 720.0, 540.0
    cx = int(sldsz.get("cx"))
    cy = int(sldsz.get("cy"))
    return cx / EMU_PER_PT, cy / EMU_PER_PT


def render_slides(
    pptx_path: Path, out_dir: Path, scale: float = 2.0, on_slide=None
) -> list[RenderedSlide]:
    """Exporta cada slide a PNG en out_dir. Devuelve la lista en orden.

    Abre una instancia COM nueva (DispatchEx) para no interferir con un
    PowerPoint que el usuario tenga abierto, y la cierra en finally.

    `on_slide(i, total)` (opcional) se llama tras exportar cada lámina, para
    reportar progreso a un front-end (CLI/GUI).
    """
    try:
        import pythoncom
        import win32com.client
        from pywintypes import com_error
    except ImportError as exc:
        raise PowerPointNotAvailableError(
            "pywin32 no está instalado (pip install pywin32)"
        ) from exc

    width_pt, height_pt = read_slide_size_pt(pptx_path)
    width_px = round(width_pt * scale * PT_TO_PX)
    height_px = round(height_pt * scale * PT_TO_PX)
    if width_px > MAX_EXPORT_WIDTH_PX:
        factor = MAX_EXPORT_WIDTH_PX / width_px
        width_px = MAX_EXPORT_WIDTH_PX
        height_px = round(height_px * factor)
        log.warning("Ancho de export limitado a %d px", width_px)

    out_dir.mkdir(parents=True, exist_ok=True)

    pythoncom.CoInitialize()
    powerpoint = None
    pres = None
    try:
        try:
            powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
        except com_error as exc:
            raise PowerPointNotAvailableError(
                "No se pudo iniciar PowerPoint vía COM. Verifica que Microsoft "
                "PowerPoint (escritorio) esté instalado en este equipo."
            ) from exc

        try:
            pres = _open_presentation(powerpoint, pptx_path)
        except com_error as exc:
            raise RenderError(
                f"PowerPoint no pudo abrir el archivo: {pptx_path}. "
                "Si está protegido con contraseña, quítala antes de convertir. "
                f"(COM: {_com_msg(exc)})"
            ) from exc

        total = pres.Slides.Count
        if total == 0:
            raise RenderError("La presentación no contiene slides")

        rendered: list[RenderedSlide] = []
        for i in range(1, total + 1):
            png_path = out_dir / f"slide-{i:03d}.png"
            _export_with_retry(pres.Slides(i), png_path, width_px, height_px, i)
            log.info("[%d/%d] %s", i, total, png_path.name)
            if on_slide:
                on_slide(i, total)
            rendered.append(
                RenderedSlide(
                    index=i, png_path=png_path,
                    width_px=width_px, height_px=height_px,
                )
            )
        return rendered
    finally:
        # Cierre garantizado: nunca dejar un POWERPNT.EXE huérfano.
        try:
            if pres is not None:
                pres.Close()
        except Exception:
            pass
        try:
            if powerpoint is not None:
                powerpoint.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def _open_presentation(powerpoint, pptx_path: Path):
    """Abre ReadOnly y sin ventana; si la versión instalada rechaza
    WithWindow=False, reabre con ventana minimizada."""
    from pywintypes import com_error

    try:
        return powerpoint.Presentations.Open(
            str(pptx_path), ReadOnly=True, Untitled=False, WithWindow=False
        )
    except com_error:
        powerpoint.Visible = True
        powerpoint.WindowState = 2  # ppWindowMinimized
        return powerpoint.Presentations.Open(
            str(pptx_path), ReadOnly=True, Untitled=False, WithWindow=True
        )


def _export_with_retry(slide, png_path: Path, w: int, h: int, index: int) -> None:
    from pywintypes import com_error

    for attempt in (1, 2):
        try:
            slide.Export(str(png_path), "PNG", w, h)
            if not png_path.exists() or png_path.stat().st_size == 0:
                raise RenderError(f"Export del slide {index} produjo un PNG vacío")
            return
        except com_error as exc:
            if attempt == 2:
                raise RenderError(
                    f"El slide {index} no pudo exportarse tras reintento "
                    f"(COM: {_com_msg(exc)}). Se aborta: un deck incompleto "
                    "no es publicable."
                ) from exc
            log.warning("Slide %d: error COM transitorio, reintentando…", index)


def _com_msg(exc) -> str:
    try:
        return str(exc.excepinfo[2]) if exc.excepinfo else str(exc)
    except Exception:
        return str(exc)
