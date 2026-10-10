from pathlib import Path

from PIL import Image

from pptx2web.images import THUMB_WIDTH, content_hash, process
from pptx2web.models import RenderedSlide


def _fake_render(tmp_path: Path, n: int = 2) -> list[RenderedSlide]:
    rendered = []
    for i in range(1, n + 1):
        png = tmp_path / f"slide-{i:03d}.png"
        im = Image.new("RGB", (1280, 720), (40 * i, 80, 160))
        im.save(png)
        rendered.append(RenderedSlide(index=i, png_path=png, width_px=1280, height_px=720))
    return rendered


def test_process_webp(tmp_path: Path):
    out = tmp_path / "out"
    assets, warnings = process(_fake_render(tmp_path), out)
    assert len(assets) == 2 and warnings == []
    for a in assets:
        slide_file = out / a.src
        thumb_file = out / a.thumb
        assert slide_file.exists() and thumb_file.exists()
        assert slide_file.suffix == ".webp"
        # nombre = slide-NNN.<hash8>.webp y el hash corresponde al contenido
        digest = a.src.split(".")[-2]
        assert len(digest) == 8
        assert content_hash(slide_file) == digest
        with Image.open(thumb_file) as t:
            assert t.width == THUMB_WIDTH


def test_intermediate_pngs_deleted(tmp_path: Path):
    rendered = _fake_render(tmp_path)
    process(rendered, tmp_path / "out")
    assert not any(r.png_path.exists() for r in rendered)


def test_png_escape_format(tmp_path: Path):
    assets, _ = process(_fake_render(tmp_path, 1), tmp_path / "out", fmt="png")
    assert assets[0].src.endswith(".png")


def test_avif_format(tmp_path: Path):
    out = tmp_path / "out"
    rendered = _fake_render(tmp_path, 2)
    assets, _ = process(rendered, out, fmt="avif")
    for a in assets:
        assert a.src.endswith(".avif")
        slide_file = out / a.src
        assert slide_file.exists() and slide_file.stat().st_size > 0
        with Image.open(slide_file) as im:  # AVIF legible
            assert im.format == "AVIF"
        # la miniatura sigue en WebP
        assert a.thumb.endswith(".webp")
    # PNG intermedios borrados
    assert not any(r.png_path.exists() for r in rendered)


def test_identical_content_same_hash(tmp_path: Path):
    a1, _ = process(_fake_render(tmp_path, 1), tmp_path / "o1")
    a2, _ = process(_fake_render(tmp_path, 1), tmp_path / "o2")
    assert a1[0].src == a2[0].src  # mismo contenido → misma URL (D7)


def test_two_image_workers_preserve_results_and_progress(tmp_path):
    from PIL import Image
    from pptx2web import images
    from pptx2web.models import RenderedSlide
    all_assets = []
    for workers in (1, 2):
        folder = tmp_path / str(workers)
        folder.mkdir()
        slides = []
        for index in range(1, 5):
            path = folder / f'{index}.png'
            Image.new('RGB', (320, 180), (index * 40, 70, 90)).save(path)
            slides.append(RenderedSlide(index=index, png_path=path, width_px=320, height_px=180))
        progress = []
        assets, warnings = images._process_images(slides, folder, 82, 'avif',
                                                  lambda i, total: progress.append((i, total)), workers=workers)
        assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]
        assert not warnings
        assert all(not slide.png_path.exists() for slide in slides)
        for asset in assets:
            with Image.open(folder / asset.src) as decoded:
                assert decoded.size == (320, 180)
        all_assets.append(assets)
    assert all_assets[0] == all_assets[1]


def test_avif_fallback_resets_memory_buffer():
    import io
    from pptx2web.images import _save_avif
    class Encoder:
        def save(self, target, fmt, **kwargs):
            if 'speed' in kwargs:
                target.write(b'partial-failed-data')
                raise TypeError('unsupported speed')
            target.write(b'valid-avif')
    with io.BytesIO() as buffer:
        _save_avif(Encoder(), buffer, 82)
        assert buffer.getvalue() == b'valid-avif'
