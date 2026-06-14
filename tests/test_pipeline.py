"""La orquestación compartida (pipeline.convert) que usan CLI y GUI.

No requiere COM: se mockea render_slides para no depender de PowerPoint, de modo
que corre en CI. La fidelidad del render ya se valida aparte (manual/COM).
"""
from pathlib import Path

import pytest
from PIL import Image

from pptx2web import pipeline
from pptx2web.models import RenderedSlide


@pytest.fixture
def fake_render(monkeypatch):
    """Sustituye render_slides por un generador de PNGs sintéticos."""
    def _render(pptx_path, out_dir, scale=2.0, on_slide=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered = []
        total = 5  # coincide con el fixture demo de conftest
        for i in range(1, total + 1):
            png = out_dir / f"slide-{i:03d}.png"
            Image.new("RGB", (640, 360), (30 * i, 60, 120)).save(png)
            if on_slide:
                on_slide(i, total)
            rendered.append(RenderedSlide(index=i, png_path=png,
                                          width_px=640, height_px=360))
        return rendered
    monkeypatch.setattr(pipeline, "render_slides", _render)


def test_convert_produces_autocontained_output(deck_path: Path, tmp_path: Path, fake_render):
    out = tmp_path / "salida"
    summary = pipeline.convert(pptx_path=deck_path, out_dir=out)

    assert summary.slide_count == 5
    assert (out / "index.html").exists()
    assert (out / "config.json").exists()
    assert list(out.glob("player.*.js")) and list(out.glob("player.*.css"))
    assert len(list((out / "slides").glob("*.webp"))) == 5
    assert summary.build_id and summary.image_bytes > 0


def test_convert_reports_progress(deck_path: Path, tmp_path: Path, fake_render):
    stages = []
    pipeline.convert(
        pptx_path=deck_path, out_dir=tmp_path / "o",
        on_progress=lambda stage, c, t: stages.append(stage),
    )
    # se ven las etapas principales y al menos un tick de render por lámina
    assert {"render", "metadata", "images", "package", "done"} <= set(stages)
    assert stages.count("render") >= 5


def test_convert_avif_format(deck_path: Path, tmp_path: Path, fake_render):
    out = tmp_path / "o"
    pipeline.convert(pptx_path=deck_path, out_dir=out, fmt="avif")
    assert len(list((out / "slides").glob("*.avif"))) == 5
    # miniaturas siguen en webp
    assert len(list((out / "thumbs").glob("*.webp"))) == 5


def test_convert_applies_theme_and_sections(deck_path: Path, tmp_path: Path, fake_render):
    out = tmp_path / "o"
    import json
    summary = pipeline.convert(
        pptx_path=deck_path, out_dir=out, theme="certmind",
        deck_config={"sections": [{"title": "Intro", "from": 1, "to": 5}]},
    )
    cfg = json.loads((out / "config.json").read_text(encoding="utf-8"))
    assert cfg["theme"] == "certmind"
    assert cfg["sections"][0]["title"] == "Intro"
    assert summary.warnings == []  # sección cubre todo el deck, sin huecos
