"""Restricción del PO: la GUI es de administración; NADA suyo llega al export.

Garantiza que la carpeta exportada queda idéntica al pipeline normal y no
contiene assets del paquete `gui/`.
"""
from pathlib import Path

import pytest
from PIL import Image

from pptx2web import pipeline
from pptx2web.models import RenderedSlide


@pytest.fixture
def fake_render(monkeypatch):
    def _render(pptx_path, out_dir, scale=2.0, on_slide=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered = []
        for i in range(1, 6):
            png = out_dir / f"slide-{i:03d}.png"
            Image.new("RGB", (640, 360), (20 * i, 50, 90)).save(png)
            rendered.append(RenderedSlide(index=i, png_path=png,
                                          width_px=640, height_px=360))
        return rendered
    monkeypatch.setattr(pipeline, "render_slides", _render)


def test_export_has_no_gui_assets(deck_path: Path, tmp_path: Path, fake_render):
    out = tmp_path / "salida"
    pipeline.convert(pptx_path=deck_path, out_dir=out)

    files = {p.name for p in out.rglob("*") if p.is_file()}

    # nombres de los assets de la GUI: no deben aparecer jamás en el export
    gui_assets = {"app.js", "app.css"}  # gui/assets/index.html también
    assert not (files & gui_assets)
    # el index.html del export es el del player, no el de la GUI:
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'id="manifest"' in html  # marca del player
    assert "pywebview" not in html  # ni rastro de la GUI

    # el paquete gui/ no es referenciado por el packager
    from pptx2web import packager
    assert "gui" not in str(packager.player_dir()).replace("\\", "/").split("/")[-1]


def test_top_level_export_files_are_expected(deck_path: Path, tmp_path: Path, fake_render):
    out = tmp_path / "salida"
    pipeline.convert(pptx_path=deck_path, out_dir=out)
    top = {p.name for p in out.iterdir() if p.is_file()}
    # exactamente: index.html, manifest.json, config.json, player.<hash>.js/css
    assert "index.html" in top and "manifest.json" in top and "config.json" in top
    assert sum(n.startswith("player.") and n.endswith(".js") for n in top) == 1
    assert sum(n.startswith("player.") and n.endswith(".css") for n in top) == 1
    # nada inesperado en la raíz (solo los conocidos)
    allowed = {"index.html", "manifest.json", "config.json"}
    extras = {n for n in top if n not in allowed and not n.startswith("player.")}
    assert not extras, f"archivos inesperados en la raíz del export: {extras}"
