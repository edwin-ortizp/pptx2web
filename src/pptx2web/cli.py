"""CLI de pptx2web.

Exit codes: 0 ok · 2 input inválido · 3 PowerPoint no disponible · 4 error de render.
"""
from __future__ import annotations

import logging
import shutil
import sys
import tempfile
import webbrowser
from pathlib import Path

import click

from . import config as config_mod
from . import images, media, metadata, packager
from .renderer import (
    PowerPointNotAvailableError,
    RenderError,
    render_slides,
)
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
@click.option("--format", "fmt", type=click.Choice(["webp", "png"]),
              default="webp", show_default=True, help="Formato de los slides")
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
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []

    # 1. Render COM → PNGs intermedios en carpeta temporal
    click.echo(f"Convirtiendo: {pptx_path.name}")
    tmp_dir = Path(tempfile.mkdtemp(prefix="pptx2web-"))
    try:
        click.echo("Renderizando slides con PowerPoint…")
        try:
            rendered = render_slides(pptx_path, tmp_dir, scale=scale)
        except PowerPointNotAvailableError as exc:
            _fail(str(exc), EXIT_NO_POWERPOINT)
        except RenderError as exc:
            _fail(str(exc), EXIT_RENDER_ERROR)

        # 2. Metadatos (python-pptx)
        click.echo("Extrayendo metadatos…")
        deck = metadata.extract(pptx_path)
        warnings.extend(deck.warnings)
        if deck.slide_count != len(rendered):
            # Slides ocultos: COM exporta también los ocultos, así que la
            # cuenta debería coincidir; si no, abortar antes de publicar algo roto.
            _fail(
                f"Inconsistencia: COM exportó {len(rendered)} slides pero "
                f"python-pptx ve {deck.slide_count}.", EXIT_RENDER_ERROR,
            )

        # 3. Media
        media_files, media_warnings = media.process_media(deck, pptx_path, out_dir)
        warnings.extend(media_warnings)

        # 4. Imágenes finales
        click.echo(f"Optimizando imágenes ({fmt})…")
        assets, img_warnings = images.process(rendered, out_dir, quality, fmt)
        warnings.extend(img_warnings)

        # 5. Configuración (tema + secciones, ya con slideCount conocido)
        try:
            player_config, cfg_warnings = config_mod.resolve(
                deck_config, theme_name, deck.slide_count
            )
        except ValidationError as exc:
            _fail(str(exc), EXIT_INVALID_INPUT)
        warnings.extend(cfg_warnings)

        # 6. Empaquetado
        slide_px = (rendered[0].width_px, rendered[0].height_px)
        manifest = packager.build_manifest(deck, assets, slide_px)
        index_path = packager.package(
            manifest, out_dir, player_config,
            config_dir=config_path.parent if config_path else None,
            make_zip=make_zip,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    _summary(manifest, assets, media_files, warnings, out_dir)

    if open_after:
        webbrowser.open(index_path.as_uri())


def _summary(manifest, assets, media_files, warnings, out_dir: Path) -> None:
    total_bytes = sum(a.src_bytes + a.thumb_bytes for a in assets)
    click.echo("")
    click.echo(f"Listo: {out_dir}")
    click.echo(f"  Slides: {manifest['slideCount']}")
    click.echo(f"  Peso de imágenes: {total_bytes / 1024 / 1024:.1f} MB")
    if media_files:
        click.echo(f"  Media: {len(media_files)} archivo(s)")
    click.echo(f"  buildId: {manifest['buildId']}")
    if warnings:
        click.echo(f"\n{len(warnings)} advertencia(s):")
        for w in warnings:
            click.echo(f"  - {w}")


def _fail(message: str, code: int) -> None:
    click.echo(f"Error: {message}", err=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
