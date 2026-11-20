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
    files = [a for a in argv if a.lower().endswith(".pdf")]
    # In the background (the setting): if the program runs already, it opens the files, at once, and this
    # start ends here, before Qt's widgets and the window are loaded.
    from . import instance

    # (a local socket needs no application object: none is made, so the window's can be made after)
    if instance.enabled() and instance.send(files):
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
    # Only the first PDF among the arguments is opened here (the others, each in a window of its own).
    if files:
        win.open_path(Path(files[0]))
    win.show()
    for other in files[1:]:
        open_window(Path(other))
    if instance.enabled():
        background(True)
    return app.exec()


_INSTANCE = None  # (the program in the background, if it is: see instance.py)


def open_window(path: Path | None = None):
    """A window (with the document at PATH): an empty one shown already takes it, else a new one."""
    from .window import _WINDOWS, MainWindow

    empty = next((w for w in _WINDOWS if w.isVisible() and w.path is None), None)
    win = empty
    if win is None:
        win = MainWindow()
        _WINDOWS.append(win)
    if path is not None:
        win.open_path(path)
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def quit_all() -> bool:
    """Close every window (each asks about what is not saved), then end the program. False if one stayed."""
    from PySide6.QtWidgets import QApplication

    from .window import _WINDOWS

    for win in list(_WINDOWS):
        if win.isVisible() and not win.close():
            return False
    if _INSTANCE is not None:
        _INSTANCE.stop()
    QApplication.instance().quit()
    return True


def background(on: bool) -> bool:
    """Keep running in the background (ON), or not, from now on. Whether it could."""
    global _INSTANCE
    from .instance import Instance

    if on:
        if _INSTANCE is None:
            _INSTANCE = Instance(open_window, quit_all)
        return _INSTANCE.start()
    if _INSTANCE is not None:
        _INSTANCE.stop()
    return True
