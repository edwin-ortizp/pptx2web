"""Configuración del deck (temas, layout, curso, secciones).

El config del deck vive en un JSON junto al .pptx (`<nombre>.config.json`,
autodetectado, o ruta explícita con --config). Aquí se carga, valida y
resuelve contra un tema de `themes/` para producir el `playerConfig` que el
packager embebe en index.html y escribe como config.json editable.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from .validate import ValidationError

log = logging.getLogger("pptx2web")

VALID_SIDES = {"left", "right"}
VALID_PANELS = {"sections", "thumbnails"}

DEFAULT_LAYOUT = {
    "sidebarSide": "left",
    "panels": ["thumbnails"],
    "defaultPanel": "thumbnails",
}

DEFAULT_POINTER = {"size": 18, "color": "#ff3b30"}
POINTER_MIN = 8
POINTER_MAX = 80

DEFAULT_PEN = {
    "colors": ["#e3342f", "#ffd60a", "#39b54a", "#2f6fed", "#ffffff"],
    "penSize": 3,
    "highlighterSize": 18,
    "eraserSize": 28,
}
PEN_SIZE_RANGE = {"penSize": (1, 40), "highlighterSize": (4, 60), "eraserSize": (4, 60)}


def themes_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).parent / "themes"
    return Path(__file__).resolve().parents[2] / "themes"


def available_themes() -> list[str]:
    return sorted(p.stem for p in themes_dir().glob("*.json"))


def load_theme(name: str) -> dict:
    path = themes_dir() / f"{name}.json"
    if not path.exists():
        raise ValidationError(
            f"Tema '{name}' no encontrado. Disponibles: "
            + ", ".join(available_themes())
        )
    try:
        theme = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Tema '{name}' con JSON inválido: {exc}") from exc
    if not isinstance(theme.get("colors"), dict):
        raise ValidationError(f"Tema '{name}': falta el objeto 'colors'")
    return theme


def find_deck_config(pptx_path: Path) -> Path | None:
    """Autodetecta `<stem>.config.json` junto al .pptx."""
    candidate = pptx_path.with_name(f"{pptx_path.stem}.config.json")
    return candidate if candidate.exists() else None


def load_deck_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise ValidationError(f"Config no encontrado: {config_path}")
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Config con JSON inválido ({config_path}): {exc}") from exc
    if not isinstance(cfg, dict):
        raise ValidationError(f"Config debe ser un objeto JSON: {config_path}")
    return cfg


def resolve(
    deck_config: dict | None,
    theme_override: str | None,
    slide_count: int,
) -> tuple[dict, list[str]]:
    """Combina tema + config del deck → playerConfig listo para embeber.

    Precedencia: --theme CLI > config del deck > 'default'.
    Devuelve (playerConfig, warnings).
    """
    cfg = deck_config or {}
    warnings: list[str] = []

    theme_name = theme_override or cfg.get("theme") or "default"
    theme = load_theme(theme_name)

    colors = dict(theme["colors"])
    user_colors = cfg.get("colors") or {}
    if not isinstance(user_colors, dict):
        raise ValidationError("'colors' debe ser un objeto de variables CSS")
    for key, value in user_colors.items():
        if not key.startswith("--"):
            warnings.append(f"colors: clave ignorada '{key}' (debe empezar por --)")
            continue
        colors[key] = str(value)

    layout = {**DEFAULT_LAYOUT, **(theme.get("layout") or {}), **(cfg.get("layout") or {})}
    layout = _validate_layout(layout, warnings)

    explicit_default = any(
        "defaultPanel" in (src or {})
        for src in (theme.get("layout"), cfg.get("layout"))
    )
    sections = _validate_sections(cfg.get("sections"), slide_count, warnings)
    if sections and "sections" not in layout["panels"]:
        layout["panels"] = ["sections", *layout["panels"]]
    if sections and not explicit_default:
        layout["defaultPanel"] = "sections"
    if not sections and "sections" in layout["panels"]:
        layout["panels"] = [p for p in layout["panels"] if p != "sections"]
        if layout["defaultPanel"] == "sections":
            layout["defaultPanel"] = layout["panels"][0] if layout["panels"] else "thumbnails"

    course = cfg.get("course") or {}
    if not isinstance(course, dict):
        raise ValidationError("'course' debe ser un objeto {title, logo}")

    pointer = {**DEFAULT_POINTER, **(theme.get("pointer") or {}), **(cfg.get("pointer") or {})}
    pointer = _validate_pointer(pointer, warnings)

    pen = {**DEFAULT_PEN, **(theme.get("pen") or {}), **(cfg.get("pen") or {})}
    pen = _validate_pen(pen, warnings)

    player_config = {
        "theme": theme_name,
        "colors": colors,
        "layout": layout,
        "course": {
            "title": course.get("title"),
            "logo": course.get("logo"),  # el packager la reescribe al copiar
        },
        "sections": sections,
        "links": _validate_links(cfg.get("links"), slide_count),
        "quizzes": _validate_quizzes(cfg.get("quizzes"), slide_count),
        "pointer": pointer,
        "pen": pen,
    }
    return player_config, warnings


def _validate_pointer(pointer: dict, warnings: list[str]) -> dict:
    """Puntero láser: {size (px, 8-80), color (CSS)}."""
    if not isinstance(pointer, dict):
        raise ValidationError("'pointer' debe ser un objeto {size, color}")
    try:
        size = int(pointer.get("size", DEFAULT_POINTER["size"]))
    except (TypeError, ValueError):
        warnings.append(
            f"pointer.size inválido; se usa {DEFAULT_POINTER['size']}"
        )
        size = DEFAULT_POINTER["size"]
    clamped = max(POINTER_MIN, min(POINTER_MAX, size))
    if clamped != size:
        warnings.append(
            f"pointer.size {size} fuera de rango ({POINTER_MIN}-{POINTER_MAX}); "
            f"ajustado a {clamped}"
        )
    color = str(pointer.get("color", DEFAULT_POINTER["color"]))
    return {"size": clamped, "color": color}


def _validate_pen(pen: dict, warnings: list[str]) -> dict:
    """Anotaciones a mano alzada: {colors[], penSize, highlighterSize, eraserSize}."""
    if not isinstance(pen, dict):
        raise ValidationError("'pen' debe ser un objeto {colors, penSize, …}")

    raw_colors = pen.get("colors")
    if isinstance(raw_colors, list):
        colors = [str(c) for c in raw_colors if isinstance(c, str) and c.strip()]
    else:
        colors = []
    if not colors:
        if raw_colors is not None:
            warnings.append("pen.colors inválido o vacío; se usa la paleta por defecto")
        colors = list(DEFAULT_PEN["colors"])

    out = {"colors": colors}
    for key, (lo, hi) in PEN_SIZE_RANGE.items():
        try:
            size = int(pen.get(key, DEFAULT_PEN[key]))
        except (TypeError, ValueError):
            warnings.append(f"pen.{key} inválido; se usa {DEFAULT_PEN[key]}")
            size = DEFAULT_PEN[key]
        clamped = max(lo, min(hi, size))
        if clamped != size:
            warnings.append(
                f"pen.{key} {size} fuera de rango ({lo}-{hi}); ajustado a {clamped}"
            )
        out[key] = clamped
    return out


def _validate_links(links, slide_count: int) -> list[dict]:
    """Links manuales: {slide, rect{x,y,w,h}, href | slide(destino), tooltip}.
    Se suman a los extraídos del .pptx."""
    if not links:
        return []
    if not isinstance(links, list):
        raise ValidationError("'links' debe ser una lista")
    clean: list[dict] = []
    for i, l in enumerate(links, start=1):
        if not isinstance(l, dict):
            raise ValidationError(f"links[{i}]: debe ser un objeto")
        slide = _slide_number(l.get("slide"), slide_count, f"links[{i}].slide")
        rect = _validate_rect(l.get("rect"), f"links[{i}].rect")
        href = l.get("href")
        target = l.get("to")
        if not href and not target:
            raise ValidationError(
                f"links[{i}]: requiere 'href' (URL) o 'to' (número de lámina destino)"
            )
        if target is not None:
            target = _slide_number(target, slide_count, f"links[{i}].to")
        clean.append({
            "slide": slide,
            "kind": "manual",
            "rect": rect,
            "href": str(href) if href else None,
            "to": target,
            "tooltip": l.get("tooltip"),
        })
    return clean


def _validate_quizzes(quizzes, slide_count: int) -> list[dict]:
    """Quizzes del config: reemplazan al quiz de notas de esa lámina."""
    if not quizzes:
        return []
    if not isinstance(quizzes, list):
        raise ValidationError("'quizzes' debe ser una lista")
    clean: list[dict] = []
    seen_slides: set[int] = set()
    for i, q in enumerate(quizzes, start=1):
        if not isinstance(q, dict):
            raise ValidationError(f"quizzes[{i}]: debe ser un objeto")
        slide = _slide_number(q.get("slide"), slide_count, f"quizzes[{i}].slide")
        if slide in seen_slides:
            raise ValidationError(f"quizzes[{i}]: lámina {slide} repetida")
        seen_slides.add(slide)
        options = q.get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise ValidationError(f"quizzes[{i}]: requiere ≥2 'options'")
        opts = []
        for j, o in enumerate(options, start=1):
            if not isinstance(o, dict) or not o.get("text"):
                raise ValidationError(f"quizzes[{i}].options[{j}]: requiere 'text'")
            opts.append({"text": str(o["text"]), "correct": bool(o.get("correct"))})
        correct = sum(1 for o in opts if o["correct"])
        if correct != 1:
            raise ValidationError(
                f"quizzes[{i}]: debe haber exactamente 1 opción correcta, hay {correct}"
            )
        clean.append({
            "slide": slide,
            "question": q.get("question"),
            "options": opts,
            "feedbackOk": q.get("feedbackOk"),
            "feedbackKo": q.get("feedbackKo"),
        })
    return clean


def _slide_number(value, slide_count: int, where: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{where}: debe ser un número de lámina") from exc
    if not 1 <= n <= slide_count:
        raise ValidationError(f"{where}: {n} fuera del deck (1-{slide_count})")
    return n


def _validate_rect(rect, where: str) -> dict:
    if not isinstance(rect, dict):
        raise ValidationError(f"{where}: requiere un objeto {{x, y, w, h}}")
    out = {}
    for key in ("x", "y", "w", "h"):
        try:
            v = float(rect[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"{where}.{key}: requerido, fracción 0..1") from exc
        if not 0 <= v <= 1:
            raise ValidationError(f"{where}.{key}: {v} fuera de rango 0..1")
        out[key] = v
    if out["w"] <= 0 or out["h"] <= 0:
        raise ValidationError(f"{where}: w y h deben ser > 0")
    return out


def _validate_layout(layout: dict, warnings: list[str]) -> dict:
    if layout["sidebarSide"] not in VALID_SIDES:
        warnings.append(
            f"layout.sidebarSide '{layout['sidebarSide']}' inválido (left|right); se usa left"
        )
        layout["sidebarSide"] = "left"

    panels = layout.get("panels")
    if not isinstance(panels, list):
        panels = list(DEFAULT_LAYOUT["panels"])
    clean = [p for p in panels if p in VALID_PANELS]
    for p in panels:
        if p not in VALID_PANELS:
            warnings.append(f"layout.panels: panel desconocido '{p}' ignorado")
    layout["panels"] = clean or list(DEFAULT_LAYOUT["panels"])

    if layout.get("defaultPanel") not in layout["panels"]:
        layout["defaultPanel"] = layout["panels"][0]
    return layout


def _validate_sections(
    sections, slide_count: int, warnings: list[str]
) -> list[dict]:
    if not sections:
        return []
    if not isinstance(sections, list):
        raise ValidationError("'sections' debe ser una lista")

    clean: list[dict] = []
    for i, s in enumerate(sections, start=1):
        if not isinstance(s, dict) or not s.get("title"):
            raise ValidationError(f"sections[{i}]: requiere 'title'")
        try:
            start = int(s["from"])
            end = int(s["to"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(
                f"sections[{i}] ('{s.get('title')}'): 'from' y 'to' deben ser números de lámina"
            ) from exc
        if start > end:
            raise ValidationError(
                f"sections[{i}] ('{s['title']}'): from ({start}) > to ({end})"
            )
        if start < 1 or end > slide_count:
            raise ValidationError(
                f"sections[{i}] ('{s['title']}'): rango {start}-{end} fuera del deck "
                f"(1-{slide_count})"
            )
        clean.append({"title": str(s["title"]), "from": start, "to": end})

    clean.sort(key=lambda s: s["from"])
    prev_end = 0
    for s in clean:
        if s["from"] <= prev_end:
            warnings.append(
                f"Secciones solapadas alrededor de la lámina {s['from']} ('{s['title']}')"
            )
        elif s["from"] > prev_end + 1:
            warnings.append(
                f"Láminas {prev_end + 1}-{s['from'] - 1} sin sección asignada"
            )
        prev_end = max(prev_end, s["to"])
    if prev_end < slide_count:
        warnings.append(f"Láminas {prev_end + 1}-{slide_count} sin sección asignada")

    return clean
