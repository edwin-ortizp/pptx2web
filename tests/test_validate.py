import zipfile
from pathlib import Path

import pytest

from pptx2web.validate import ValidationError, validate_input


def test_accepts_valid_pptx(deck_path: Path):
    assert validate_input(deck_path) == deck_path.resolve()


def test_rejects_missing_file(tmp_path: Path):
    with pytest.raises(ValidationError, match="no existe"):
        validate_input(tmp_path / "nope.pptx")


def test_rejects_wrong_extension(tmp_path: Path):
    f = tmp_path / "deck.ppt"
    f.write_bytes(b"x")
    with pytest.raises(ValidationError, match="solo .pptx"):
        validate_input(f)


def test_rejects_empty_file(tmp_path: Path):
    f = tmp_path / "deck.pptx"
    f.write_bytes(b"")
    with pytest.raises(ValidationError, match="vacío"):
        validate_input(f)


def test_rejects_non_zip(tmp_path: Path):
    f = tmp_path / "deck.pptx"
    f.write_bytes(b"esto no es un zip" * 10)
    with pytest.raises(ValidationError, match="contenedor ZIP"):
        validate_input(f)


def test_rejects_zip_without_presentation(tmp_path: Path):
    f = tmp_path / "deck.pptx"
    with zipfile.ZipFile(f, "w") as zf:
        zf.writestr("hola.txt", "x")
    with pytest.raises(ValidationError, match="presentation.xml"):
        validate_input(f)
