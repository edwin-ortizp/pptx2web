"""Validación del archivo de entrada antes de tocar COM."""
from __future__ import annotations

import zipfile
from pathlib import Path

MAX_SIZE_BYTES = 2 * 1024**3  # 2 GB: límite de cordura, no técnico


class ValidationError(Exception):
    """Input inválido. El CLI lo traduce a exit code 2."""


def validate_input(pptx_path: Path) -> Path:
    """Valida que el input exista, sea .pptx y sea un ZIP OOXML legible.

    Devuelve la ruta resuelta (absoluta).
    """
    path = pptx_path.resolve()

    if not path.exists():
        raise ValidationError(f"El archivo no existe: {path}")
    if not path.is_file():
        raise ValidationError(f"No es un archivo: {path}")
    if path.suffix.lower() != ".pptx":
        raise ValidationError(
            f"Extensión no soportada '{path.suffix}': solo .pptx "
            "(guarda el .ppt como .pptx desde PowerPoint)"
        )

    size = path.stat().st_size
    if size == 0:
        raise ValidationError(f"El archivo está vacío: {path}")
    if size > MAX_SIZE_BYTES:
        raise ValidationError(
            f"El archivo pesa {size / 1024**3:.1f} GB y supera el límite de 2 GB"
        )

    if not zipfile.is_zipfile(path):
        raise ValidationError(
            f"El archivo no es un .pptx válido (no es un contenedor ZIP): {path}. "
            "Si está protegido con contraseña, quítala antes de convertir."
        )

    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile as exc:
        raise ValidationError(f".pptx corrupto (ZIP ilegible): {exc}") from exc

    if "ppt/presentation.xml" not in names:
        raise ValidationError(
            "El ZIP no contiene ppt/presentation.xml: no es una presentación PowerPoint"
        )

    return path
