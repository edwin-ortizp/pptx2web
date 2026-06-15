# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para pptx2web-gui (onedir, sin consola).

Construir desde la raíz del proyecto:
    python -m PyInstaller packaging/pptx2web.spec

Notas de empaquetado:
* `gui/assets/` se embebe como dato del paquete (lo busca por ruta de módulo:
  `Path(__file__).parent / "assets"` → queda en `_internal/pptx2web/gui/assets`).
* `player/`, `themes/` y `bin/ffmpeg.exe` NO se embeben aquí: el código los busca
  JUNTO al ejecutable (`Path(sys.executable).parent / ...`). `build.ps1` los copia
  a la carpeta del dist tras compilar, y el instalador los reparte igual.
* Los hooks de WebView2/clr (pywebview) y pywin32 los aporta PyInstaller
  automáticamente (pywebview registra su carpeta `__pyinstaller`).
"""
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.dirname(os.path.abspath(SPECPATH))  # raíz del repo (padre de packaging/)
SRC = os.path.join(ROOT, "src")
ICON = os.path.join(ROOT, "packaging", "pptx2web.ico")

datas = [
    (os.path.join(SRC, "pptx2web", "gui", "assets"), "pptx2web/gui/assets"),
]

hiddenimports = [
    "win32com.client",
    "win32timezone",   # pywin32 lo carga de forma tardía en algunos equipos
    "pythoncom",
    "pywintypes",
    *collect_submodules("pptx"),
]

a = Analysis(
    [os.path.join(ROOT, "packaging", "run_gui.py")],
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "PyInstaller"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pptx2web-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                # sin ventana de consola
    icon=ICON if os.path.exists(ICON) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="pptx2web-gui",
)
