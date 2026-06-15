"""Punto de entrada para el ejecutable congelado (PyInstaller).

Usa import absoluto (no relativo) porque PyInstaller ejecuta este archivo como
`__main__`, fuera del contexto de paquete. Equivale a `python -m pptx2web.gui`.
"""
from pptx2web.gui.app import main

if __name__ == "__main__":
    main()
