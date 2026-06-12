"""Modelo de datos interno del pipeline.

Las dataclasses fluyen entre módulos: renderer produce RenderedSlide,
metadata produce Deck/SlideMeta, images produce SlideAssets y packager
las consolida en el manifest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

TRANSITION_TYPES = {"fade", "push", "wipe", "split", "cut"}
DEFAULT_TRANSITION_DURATION_MS = 500


@dataclass
class Transition:
    type: str = "fade"
    duration: int = DEFAULT_TRANSITION_DURATION_MS

    def as_dict(self) -> dict:
        return {"type": self.type, "duration": self.duration}


@dataclass
class Rect:
    """Rectángulo en fracciones 0..1 respecto al lienzo del slide."""

    x: float
    y: float
    w: float
    h: float

    def as_dict(self) -> dict:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "w": round(self.w, 4),
            "h": round(self.h, 4),
        }


@dataclass
class MediaItem:
    type: str  # "video" | "audio"
    source_part: str  # nombre del part dentro de ppt/media/
    rect: Rect
    autoplay: bool = False
    # Rellenado por media.py tras copiar/transcodificar:
    src: str | None = None


@dataclass
class LinkItem:
    kind: str  # "shape" | "text"
    rect: Rect
    href: str | None = None  # link externo
    slide: int | None = None  # link interno: índice 1-based de destino
    tooltip: str | None = None

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "rect": self.rect.as_dict(),
            "href": self.href,
            "slide": self.slide,
            "tooltip": self.tooltip,
        }


@dataclass
class QuizOption:
    text: str
    correct: bool = False


@dataclass
class Quiz:
    question: str | None
    options: list[QuizOption]
    feedback_ok: str | None = None
    feedback_ko: str | None = None

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "options": [{"text": o.text, "correct": o.correct} for o in self.options],
            "feedbackOk": self.feedback_ok,
            "feedbackKo": self.feedback_ko,
        }


@dataclass
class SlideMeta:
    index: int  # 1-based
    title: str
    notes_html: str | None
    search_text: str
    transition: Transition
    media: list[MediaItem] = field(default_factory=list)
    links: list[LinkItem] = field(default_factory=list)
    quiz: Quiz | None = None


@dataclass
class Deck:
    title: str
    slide_width_pt: float
    slide_height_pt: float
    slides: list[SlideMeta] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def slide_count(self) -> int:
        return len(self.slides)


@dataclass
class RenderedSlide:
    index: int  # 1-based
    png_path: Path
    width_px: int
    height_px: int


@dataclass
class SlideAssets:
    index: int  # 1-based
    src: str  # ruta relativa final, ej. slides/slide-001.7be01f3a.webp
    thumb: str  # ruta relativa final, ej. thumbs/thumb-001.c2d401aa.webp
    src_bytes: int = 0
    thumb_bytes: int = 0
