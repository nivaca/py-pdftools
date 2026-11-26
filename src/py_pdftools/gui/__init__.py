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
        print("Usage: py-pdftools-gui [file.pdf]   (the command line: py-pdftools --help)\n"
              "       py-pdftools-gui --background  (in the tray, without a window: documents then open at once)\n"
              "       py-pdftools-gui --no-tray     (this time not in the background, whatever the settings say:\n"
              "                                      a program of its own, which ends with its last window)")
        return 0
    hidden = "--background" in argv  # (started with the session: in the tray, without a window)
    # --no-tray: esta vez, ni en segundo plano ni pasando los archivos a uno que ya corre (para probar una
    # versión desde el código sin cerrar la instalada); la configuración no cambia
    no_tray = "--no-tray" in argv
    if hidden and no_tray:
        print("py-pdftools-gui: --background and --no-tray can't go together", file=sys.stderr)
        return 2
    argv = [a for a in argv if a not in ("--background", "--no-tray")]
    from .navigation import split_place

    # (a file may come with a place: book.pdf#page=12, book.pdf#nameddest=intro)
    files = [a for a in argv if split_place(a)[0].lower().endswith(".pdf")]
    # In the background (the setting): if the program runs already, it opens the files, at once, and this
    # start ends here, before Qt's widgets and the window are loaded.
    from . import instance

    # (a local socket needs no application object: none is made, so the window's can be made after)
    if hidden and instance.running():  # (en segundo plano ya: nada que hacer)
        return 0
    if not hidden and not no_tray and instance.enabled() and instance.send(files):
        return 0
    # Tesseract (sus idiomas) y Ghostscript se buscan ya, en otro hilo, mientras se carga lo demás: buscarlos
    # los ejecuta, y la ventana los necesita (el menú OCR, Guardar como PDF/A).
    from ..core import conform, ocr, once

    once.ahead(ocr.system_tessdata, conform.ghostscript)
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
    from . import errors

    errors.install(app)  # (an error nothing caught: shown in a dialog, not only in the terminal)
    from .attachments import forget_opened

    forget_opened()  # (the copies of attached files opened some days ago)
    install_qt_translations()
    from . import performance

    performance.apply()  # (the memory profile, the transparency, the antialiasing: Settings > Performance)
    from . import appearance

    appearance.apply()  # (the colours and the size of the interface: Settings > Appearance)
    # La hoja de estilo del alto contraste se quita antes de salir: si Qt la destruye después que la aplicación,
    # el programa puede romperse al terminar (un fallo de segmentación, no siempre).
    app.aboutToQuit.connect(lambda: app.setStyleSheet(""))
    if sys.platform == "darwin":  # (los documentos del Finder y el clic en el Dock: ver appevents.py)
        from . import appevents

        appevents.install(app, open_window, any_window_shown, hidden)
    if hidden:
        # Solo el icono de la bandeja; una ventana se prepara, oculta, para el primer documento (ver spare).
        if not background(True):
            print("py-pdftools-gui: it could not start in the background", file=sys.stderr)
            return 1
        return app.exec()
    win = MainWindow()
    # La ventana entra en _WINDOWS como las que se reconstruyen al cambiar de idioma; change_language la saca
    # de ahí.
    _WINDOWS.append(win)
    # Without files, those open when the program was last ended, if the settings say so.
    if not files and _reopen():
        files = [f for f in session() if Path(f).is_file()]
    # Only the first PDF among the arguments is opened here (the others, each in a window of its own).
    if files:
        path, place = split_place(files[0])
        win.open_path(Path(path), place)
    if _setting("tabs"):  # (the window as the first tab of a window of tabs: the others go there too)
        from .tabs import host_for_new_tab

        host_for_new_tab(win).show()
    else:
        win.show()
    for other in files[1:]:
        open_window(other)
    if instance.enabled() and not no_tray:
        background(True)
    return app.exec()


_INSTANCE = None  # (the program in the background, if it is: see instance.py)


def _reopen() -> bool:
    return _setting("reopen")


def _setting(name: str) -> bool:
    from ..core import config

    try:
        return bool(config.get(name))
    except config.ConfigError:
        return False


def session() -> list[str]:
    """The documents open when the program was last ended (see save_session)."""
    from .state import State

    value = State("window").value("session", [])
    return [str(v) for v in (value if isinstance(value, list) else [value] if value else [])]


def save_session(paths: list) -> None:
    from .state import State

    State("window").setValue("session", [str(p) for p in paths if p])


_QUITTING = False  # (while Quit closes the windows: the session was saved before, with all of them)


def open_window(path=None):
    """A window (with the document at PATH, a path or 'book.pdf#page=3'): an empty one shown already takes
    it, else a new one."""
    from .navigation import split_place
    from .window import _WINDOWS, MainWindow

    if _setting("tabs"):  # (in a tab of the last window of tabs: see tabs.py)
        from .tabs import open_in_tab

        return open_in_tab(path)
    empty = next((w for w in _WINDOWS if w.is_open() and w.host is None and w.path is None), None)
    win = empty
    if win is None:
        win = take_spare() or MainWindow()
        _WINDOWS.append(win)
    if path is not None:
        file, place = split_place(str(path))
        win.open_path(Path(file), place)
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def any_window_shown() -> bool:
    """Whether a window of the program (or of tabs) is on the screen."""
    from .tabs import _HOSTS
    from .window import _WINDOWS

    return any(w.isVisible() for w in (*_WINDOWS, *_HOSTS))


def quit_all() -> bool:
    """Close every window (each asks about what is not saved), then end the program. False if one stayed."""
    from PySide6.QtWidgets import QApplication

    from .window import _WINDOWS

    global _QUITTING
    # (the documents open now are those to open again next time, if the settings say so)
    save_session([w.path for w in _WINDOWS if w.is_open() and w.path is not None])
    _QUITTING = True
    try:
        for win in list(_WINDOWS):
            if win.is_open() and not win.close():
                return False
    finally:
        _QUITTING = False
    if _INSTANCE is not None:
        _INSTANCE.stop()
    QApplication.instance().quit()
    return True


def reset_settings():
    """Close every window (each asks about what is not saved; they write what they keep of themselves as they
    close), then move the settings aside (core/config.reset). The copy of the old settings, None if there were
    none; False if a window stayed open (nothing is reset then). The caller then ends the program (end())."""
    from ..core import config
    from .window import _WINDOWS

    global _QUITTING
    _QUITTING = True
    try:
        for win in list(_WINDOWS):
            if win.is_open() and not win.close():
                return False
    finally:
        _QUITTING = False
    # Ya con todo cerrado: lo que las ventanas escribieron al cerrarse va también a la copia.
    return config.reset()


def end() -> None:
    """End the program, also if it was running in the background."""
    from PySide6.QtWidgets import QApplication

    if _INSTANCE is not None:
        _INSTANCE.stop()
    QApplication.instance().quit()


def background(on: bool) -> bool:
    """Keep running in the background (ON), or not, from now on. Whether it could. In the background, a
    window is kept ready (see spare)."""
    global _INSTANCE, _SPARE
    from .instance import Instance

    if on:
        if _INSTANCE is None:
            _INSTANCE = Instance(open_window, quit_all)
        started = _INSTANCE.start()
        if started:
            _later_spare()
        return started
    if _INSTANCE is not None:
        _INSTANCE.stop()
    if _SPARE is not None:
        _SPARE[0].deleteLater()
        _SPARE = None
    return True


# ----------------------------------------------------------------- a window kept ready

# A window made beforehand, hidden, while the program waits in the background: the next document opened from
# outside (or New window in the tray) takes it, instead of making one then (about a third of a second, and
# more on a slow machine). It is made again after. A window made before the settings changed is not used: it
# would show them as they were (see _looks).
_SPARE: tuple | None = None  # (the window, the settings it was made with)
SPARE_DELAY_MS = 1500  # (made a moment after the program is idle, not while the user waits)


def _looks() -> tuple:
    """What a window takes from the settings when it is made: the settings, and the language, toolbars and
    mode the windows keep (see state.py)."""
    from ..core import config, interface
    from .state import State

    # (solo los ajustes: lo que la ventana guarda de sí misma va en el mismo archivo y cambia a menudo)
    try:
        conf = repr(sorted(config.read().get("parameters", {}).items()))
    except config.ConfigError:
        conf = ""
    qs = State("window")
    keys = ("toolbar_contents", "toolbar_looks", "toolbars", "mode", "reading", "thumbnails", "gaps", "spread")
    return conf, interface.code(), tuple(str(qs.value(k, "")) for k in keys)


def _later_spare():
    from PySide6.QtCore import QTimer

    QTimer.singleShot(SPARE_DELAY_MS, prepare_spare)


def prepare_spare():
    """Make the window kept ready, if the program is in the background and has none."""
    global _SPARE
    if _INSTANCE is None or _INSTANCE.server is None or _SPARE is not None:
        return
    from .window import MainWindow

    win = MainWindow()
    _SPARE = (win, _looks())


def take_spare():
    """The window kept ready (and another one made, a moment later); None if there is none, or it was made
    with settings that changed since."""
    global _SPARE
    if _SPARE is None:
        return None
    win, looks = _SPARE
    _SPARE = None
    _later_spare()
    if looks != _looks():
        win.deleteLater()
        return None
    return win
