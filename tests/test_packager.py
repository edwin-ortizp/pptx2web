import json
from pathlib import Path

from pptx2web.metadata import extract
from pptx2web.models import SlideAssets
from pptx2web.packager import build_manifest, package


def _assets(n: int) -> list[SlideAssets]:
    return [
        SlideAssets(
            index=i,
            src=f"slides/slide-{i:03d}.deadbeef.webp",
            thumb=f"thumbs/thumb-{i:03d}.cafebabe.webp",
        )
        for i in range(1, n + 1)
    ]


def test_manifest_schema(deck_path: Path):
    deck = extract(deck_path)
    manifest = build_manifest(deck, _assets(5), (2560, 1440))
    assert manifest["version"] == 1
    assert manifest["slideCount"] == 5
    assert manifest["slideSize"] == {"width": 2560, "height": 1440}
    s1 = manifest["slides"][0]
    assert set(s1) == {"index", "title", "src", "thumb", "notes", "text",
                       "transition", "media", "links", "quiz"}
    assert s1["index"] == 1
    assert s1["media"] == []
    assert s1["links"] == [] and s1["quiz"] is None
    assert "buildId" in manifest
    # slide 4 trae link interno; slide 5 trae quiz (del conftest)
    s4 = manifest["slides"][3]
    assert s4["links"][0]["slide"] == 1
    s5 = manifest["slides"][4]
    assert s5["quiz"]["options"][1]["correct"] is True


def test_package_config_inline_and_on_disk(deck_path: Path, tmp_path: Path):
    from pptx2web.config import resolve

    deck = extract(deck_path)
    manifest = build_manifest(deck, _assets(5), (1280, 720))
    player_config, _ = resolve(
        {
            "theme": "certmind",
            "course": {"title": "Curso X"},
            "sections": [{"title": "Todo", "from": 1, "to": 5}],
        },
        None,
        5,
    )
    out = tmp_path / "out"
    out.mkdir()
    html = package(manifest, out, player_config).read_text(encoding="utf-8")

    assert '<script type="application/json" id="config">' in html
    assert "Curso X" in html
    on_disk = json.loads((out / "config.json").read_text(encoding="utf-8"))
    assert on_disk["theme"] == "certmind"
    assert on_disk["sections"][0]["title"] == "Todo"


def test_package_copies_logo_hashed_and_prune_keeps_it(deck_path: Path, tmp_path: Path):
    from pptx2web.config import resolve

    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    deck = extract(deck_path)
    manifest = build_manifest(deck, _assets(5), (1280, 720))
    player_config, _ = resolve(
        {"course": {"title": "C", "logo": "logo.png"}}, None, 5
    )
    out = tmp_path / "out"
    out.mkdir()
    # dos veces: la segunda ejecuta el prune con el logo ya presente
    package(manifest, out, player_config, config_dir=tmp_path)
    package(manifest, out, player_config, config_dir=tmp_path)

    logos = list(out.glob("logo.*.png"))
    assert len(logos) == 1
    cfg = json.loads((out / "config.json").read_text(encoding="utf-8"))
    assert cfg["course"]["logo"] == logos[0].name


def test_package_inlines_manifest(deck_path: Path, tmp_path: Path):
    deck = extract(deck_path)
    manifest = build_manifest(deck, _assets(5), (2560, 1440))
    out = tmp_path / "out"
    out.mkdir()
    index_path = package(manifest, out)

    html = index_path.read_text(encoding="utf-8")
    # manifest embebido, sin fetch separado (D7)
    assert '<script type="application/json" id="manifest">' in html
    assert '"slideCount": 5'.replace(" ", "") in html.replace(" ", "")
    # ningún placeholder sin sustituir
    assert "{{" not in html
    # JS y CSS hasheados y referenciados
    js = list(out.glob("player.*.js"))
    css = list(out.glob("player.*.css"))
    assert len(js) == 1 and len(css) == 1
    assert js[0].name in html and css[0].name in html
    # manifest.json en disco como artefacto de depuración
    on_disk = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["slideCount"] == 5


def test_package_zip(deck_path: Path, tmp_path: Path):
    deck = extract(deck_path)
    manifest = build_manifest(deck, _assets(5), (1280, 720))
    out = tmp_path / "deck-web"
    out.mkdir()
    package(manifest, out, make_zip=True)
    assert (tmp_path / "deck-web.zip").exists()


def test_script_close_tag_escaped(tmp_path: Path, deck_path: Path):
    deck = extract(deck_path)
    deck.slides[0].search_text = "texto con </script> malicioso"
    manifest = build_manifest(deck, _assets(5), (1280, 720))
    out = tmp_path / "out"
    out.mkdir()
    html = package(manifest, out).read_text(encoding="utf-8")
    assert "</script> malicioso" not in html
    assert "<\\/script> malicioso" in html
