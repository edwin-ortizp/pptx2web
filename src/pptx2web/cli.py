"""CLI de pptx2web.

Exit codes: 0 ok · 2 input inválido · 3 PowerPoint no disponible · 4 error de render.
"""
from __future__ import annotations

import logging
import sys
import webbrowser
from pathlib import Path

import click

from . import config as config_mod
from . import pipeline
from .renderer import PowerPointNotAvailableError, RenderError
from .validate import ValidationError, validate_input

log = logging.getLogger("pptx2web")

EXIT_INVALID_INPUT = 2
EXIT_NO_POWERPOINT = 3
EXIT_RENDER_ERROR = 4


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_pptx", type=click.Path(path_type=Path))
@click.option("-o", "--out", "out_dir", type=click.Path(path_type=Path),
              default=None, help="Carpeta de salida (default: ./<nombre>-web/)")
@click.option("--scale", default=2.0, show_default=True,
              help="Factor de resolución del render (máx 3.0)")
@click.option("--quality", default=82, show_default=True,
              help="Calidad WebP (1-100)")
@click.option("--format", "fmt", type=click.Choice(["webp", "avif", "png"]),
              default="webp", show_default=True,
              help="Formato de los slides (avif: más liviano, encode más lento)")
@click.option("--theme", "theme_name", default=None,
              help="Tema visual predefinido (ver carpeta themes/)")
@click.option("--config", "config_path", type=click.Path(path_type=Path),
              default=None,
              help="Config del deck (default: <nombre>.config.json junto al .pptx)")
@click.option("--zip", "make_zip", is_flag=True, help="Genera además <out>.zip")
@click.option("--open", "open_after", is_flag=True,
              help="Abre index.html al terminar")
@click.option("-q", "quiet", is_flag=True, help="Solo errores")
@click.option("-v", "verbose", is_flag=True, help="Salida detallada")
def main(input_pptx: Path, out_dir: Path | None, scale: float, quality: int,
         fmt: str, theme_name: str | None, config_path: Path | None,
         make_zip: bool, open_after: bool, quiet: bool,
         verbose: bool) -> None:
    """Convierte INPUT_PPTX en una carpeta web autocontenida."""
    # Consolas Windows heredadas usan cp1252: forzar UTF-8 en la salida
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    level = logging.ERROR if quiet else (logging.DEBUG if verbose else logging.INFO)
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout)

    scale = min(max(scale, 0.5), 3.0)
    quality = min(max(quality, 1), 100)

    try:
        pptx_path = validate_input(input_pptx)
        if config_path is None:
            config_path = config_mod.find_deck_config(pptx_path)
            if config_path:
                click.echo(f"Config detectado: {config_path.name}")
        deck_config = config_mod.load_deck_config(config_path) if config_path else None
        # Validar tema/estructura temprano (las secciones se validan tras
        # extraer metadatos, cuando se conoce el número de láminas)
        if theme_name:
            config_mod.load_theme(theme_name)
    except ValidationError as exc:
        _fail(str(exc), EXIT_INVALID_INPUT)

    if out_dir is None:
        out_dir = Path.cwd() / f"{pptx_path.stem}-web"

    click.echo(f"Convirtiendo: {pptx_path.name}")
    stages = {
        "render": "Renderizando slides con PowerPoint…",
        "metadata": "Extrayendo metadatos…",
        "media": "Procesando media…",
        "images": f"Optimizando imágenes ({fmt})…",
        "package": "Empaquetando…",
    }
    seen: set[str] = set()

    def on_progress(stage: str, current, total) -> None:
        if stage == "render" and current and total:
            log.info("[%d/%d] slide-%03d", current, total, current)
            return
        if stage in stages and stage not in seen:
            seen.add(stage)
            click.echo(stages[stage])

    try:
        summary = pipeline.convert(
            pptx_path=pptx_path, out_dir=out_dir, scale=scale, quality=quality,
            fmt=fmt, theme=theme_name, deck_config=deck_config,
            config_dir=config_path.parent if config_path else None,
            make_zip=make_zip, on_progress=on_progress,
        )
    except PowerPointNotAvailableError as exc:
        _fail(str(exc), EXIT_NO_POWERPOINT)
    except RenderError as exc:
        _fail(str(exc), EXIT_RENDER_ERROR)
    except ValidationError as exc:
        _fail(str(exc), EXIT_INVALID_INPUT)

    _summary(summary)

    if open_after:
        webbrowser.open(summary.index_path.as_uri())


def _summary(summary) -> None:
    click.echo("")
    click.echo(f"Listo: {summary.out_dir}")
    click.echo(f"  Slides: {summary.slide_count}")
    click.echo(f"  Peso de imágenes: {summary.image_bytes / 1024 / 1024:.1f} MB")
    if summary.media_count:
        click.echo(f"  Media: {summary.media_count} archivo(s)")
    click.echo(f"  buildId: {summary.build_id}")
    if summary.warnings:
        click.echo(f"\n{len(summary.warnings)} advertencia(s):")
        for w in summary.warnings:
            click.echo(f"  - {w}")


def _fail(message: str, code: int) -> None:
    click.echo(f"Error: {message}", err=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
