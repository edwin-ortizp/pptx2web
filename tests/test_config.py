import json
from pathlib import Path

import pytest

from pptx2web.config import (
    available_themes,
    find_deck_config,
    load_deck_config,
    load_theme,
    resolve,
)
from pptx2web.validate import ValidationError


def test_available_themes_includes_defaults():
    themes = available_themes()
    assert "default" in themes
    assert "certmind" in themes


def test_load_theme_unknown_lists_available():
    with pytest.raises(ValidationError, match="default"):
        load_theme("no-existe")


def test_resolve_defaults_without_config():
    cfg, warnings = resolve(None, None, 10)
    assert cfg["theme"] == "default"
    assert cfg["colors"]["--accent"]  # vars del tema presentes
    assert cfg["layout"] == {
        "sidebarSide": "left",
        "panels": ["thumbnails"],
        "defaultPanel": "thumbnails",
    }
    assert cfg["sections"] == []
    assert warnings == []


def test_theme_override_and_color_merge():
    deck_cfg = {"theme": "default", "colors": {"--accent": "#123456", "malo": "x"}}
    cfg, warnings = resolve(deck_cfg, "certmind", 10)
    assert cfg["theme"] == "certmind"  # CLI gana sobre el config
    assert cfg["colors"]["--accent"] == "#123456"  # colors gana sobre el tema
    assert cfg["colors"]["--panel"] == "#000000"  # resto del tema intacto
    assert any("malo" in w for w in warnings)


def test_sections_valid_and_layout_auto_enables_panel():
    deck_cfg = {
        "sections": [
            {"title": "Intro", "from": 1, "to": 3},
            {"title": "Cierre", "from": 4, "to": 10},
        ]
    }
    cfg, warnings = resolve(deck_cfg, None, 10)
    assert [s["title"] for s in cfg["sections"]] == ["Intro", "Cierre"]
    assert "sections" in cfg["layout"]["panels"]
    assert cfg["layout"]["defaultPanel"] == "sections"
    assert warnings == []


def test_sections_gap_and_overlap_warn():
    deck_cfg = {
        "sections": [
            {"title": "A", "from": 1, "to": 5},
            {"title": "B", "from": 4, "to": 8},
        ]
    }
    _, warnings = resolve(deck_cfg, None, 10)
    assert any("solapadas" in w for w in warnings)
    assert any("9-10" in w for w in warnings)


def test_sections_out_of_range_fails():
    with pytest.raises(ValidationError, match="fuera del deck"):
        resolve({"sections": [{"title": "X", "from": 1, "to": 99}]}, None, 10)
    with pytest.raises(ValidationError, match="from"):
        resolve({"sections": [{"title": "X", "from": 5, "to": 2}]}, None, 10)
    with pytest.raises(ValidationError, match="title"):
        resolve({"sections": [{"from": 1, "to": 2}]}, None, 10)


def test_invalid_side_warns_and_falls_back():
    cfg, warnings = resolve({"layout": {"sidebarSide": "top"}}, None, 5)
    assert cfg["layout"]["sidebarSide"] == "left"
    assert any("sidebarSide" in w for w in warnings)


def test_find_and_load_deck_config(tmp_path: Path):
    pptx = tmp_path / "curso.pptx"
    pptx.write_bytes(b"x")
    assert find_deck_config(pptx) is None
    cfg_file = tmp_path / "curso.config.json"
    cfg_file.write_text(json.dumps({"theme": "certmind"}), encoding="utf-8")
    found = find_deck_config(pptx)
    assert found == cfg_file
    assert load_deck_config(found)["theme"] == "certmind"


def test_manual_links_valid():
    cfg, _ = resolve({
        "links": [
            {"slide": 2, "rect": {"x": 0.1, "y": 0.8, "w": 0.3, "h": 0.1},
             "href": "https://x.com", "tooltip": "Ver"},
            {"slide": 3, "rect": {"x": 0, "y": 0, "w": 0.5, "h": 0.5}, "to": 1},
        ]
    }, None, 5)
    assert cfg["links"][0]["href"] == "https://x.com"
    assert cfg["links"][0]["kind"] == "manual"
    assert cfg["links"][1]["to"] == 1


def test_manual_links_invalid():
    base_rect = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
    with pytest.raises(ValidationError, match="fuera del deck"):
        resolve({"links": [{"slide": 99, "rect": base_rect, "href": "x"}]}, None, 5)
    with pytest.raises(ValidationError, match="0..1"):
        resolve({"links": [{"slide": 1, "rect": {"x": 2, "y": 0, "w": 1, "h": 1},
                            "href": "x"}]}, None, 5)
    with pytest.raises(ValidationError, match="'href'.*'to'"):
        resolve({"links": [{"slide": 1, "rect": base_rect}]}, None, 5)


def test_config_quizzes_valid_and_invalid():
    good = {"quizzes": [{"slide": 2, "question": "¿?", "options": [
        {"text": "a"}, {"text": "b", "correct": True}]}]}
    cfg, _ = resolve(good, None, 5)
    assert cfg["quizzes"][0]["slide"] == 2
    assert cfg["quizzes"][0]["options"][1]["correct"] is True

    with pytest.raises(ValidationError, match="1 opción correcta"):
        resolve({"quizzes": [{"slide": 1, "options": [
            {"text": "a"}, {"text": "b"}]}]}, None, 5)
    with pytest.raises(ValidationError, match="repetida"):
        resolve({"quizzes": [
            {"slide": 1, "options": [{"text": "a", "correct": True}, {"text": "b"}]},
            {"slide": 1, "options": [{"text": "c", "correct": True}, {"text": "d"}]},
        ]}, None, 5)


def test_load_deck_config_invalid_json(tmp_path: Path):
    bad = tmp_path / "c.config.json"
    bad.write_text("{rota", encoding="utf-8")
    with pytest.raises(ValidationError, match="JSON inválido"):
        load_deck_config(bad)
