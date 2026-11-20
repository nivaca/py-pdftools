"""The window of py-pdftools (PySide6 / Qt 6). Start it with ``py-pdftools-gui [file.pdf]``."""

from __future__ import annotations

import sys
from pathlib import Path


def app_icon():
    from PySide6.QtGui import QIcon

    icon = QIcon()
    # Los PNG de hicolor, de todos los tamaños: Qt elige el que corresponda a cada uso.
    hicolor = Path(__file__).resolve().parent.parent / "icons" / "linux" / "hicolor"
    for png in sorted(hicolor.glob("*/apps/py-pdftools.png")):
        icon.addFile(str(png))
    return icon


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # --version and --help are answered before Qt is imported, so they work without a display.
    if argv and argv[0] in ("--version", "-V"):
        from .. import __version__

        print(f"py-pdftools {__version__}")
        return 0
    if argv and argv[0] in ("--help", "-h"):
        print("Usage: py-pdftools-gui [file.pdf]   (the command line: py-pdftools --help)")
        return 0
    # El idioma configurado se fija antes de crear la ventana: sus textos se traducen al construirse.
    from ..core import interface

    interface.use_configured()
    from PySide6.QtWidgets import QApplication

    from .window import _WINDOWS, MainWindow, install_qt_translations

    # An application may exist already (the tests make one): it is reused.
    app = QApplication.instance() or QApplication([sys.argv[0]] + argv)
    app.setApplicationName("py-pdftools")
    app.setOrganizationName("py-pdftools")
    app.setDesktopFileName("py-pdftools")
    app.setWindowIcon(app_icon())
    install_qt_translations()
    win = MainWindow()
    # La ventana entra en _WINDOWS como las que se reconstruyen al cambiar de idioma; change_language la saca
    # de ahí.
    _WINDOWS.append(win)
    # Only the first PDF among the arguments is opened.
    files = [a for a in argv if a.lower().endswith(".pdf")]
    if files:
        win.open_path(Path(files[0]))
    win.show()
    return app.exec()
