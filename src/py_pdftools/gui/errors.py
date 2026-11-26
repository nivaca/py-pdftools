"""Los errores que nada atrapó (un fallo dentro de la ventana, o de otro hilo): antes solo se escribían en la
terminal, que quien usa el programa instalado nunca ve. Ahora, además, un diálogo dice que algo falló y trae
los detalles (el error, dónde ocurrió, las versiones del programa y de sus bibliotecas), con un botón para
copiarlos y pegarlos en un aviso. Lo de otro hilo llega a la ventana por una señal en cola (un diálogo solo
puede mostrarse desde el hilo principal). Idea tomada de Calibre (ExceptionHandler en gui2/main_window.py)."""

from __future__ import annotations

import platform
import sys
import threading
import traceback

from PySide6.QtCore import QObject, Qt, Signal

from ..core.interface import tr


def versions() -> str:
    """The versions of the program, Python, Qt, PySide6 and PyMuPDF, and the system: for a report."""
    from PySide6 import __version__ as pyside
    from PySide6.QtCore import qVersion

    from .. import __version__

    try:
        import pymupdf

        mupdf = f"PyMuPDF {pymupdf.VersionBind} (MuPDF {pymupdf.VersionFitz})"
    except ImportError:  # (it can't be missing in a working program; but a report should still be made)
        mupdf = "PyMuPDF ?"
    return (f"py-pdftools {__version__}, Python {platform.python_version()}, Qt {qVersion()}, PySide6 {pyside}, "
            f"{mupdf}, {platform.platform()}")


def details(kind, value, tb) -> str:
    """The text of a report of the error (KIND, VALUE, TB): the versions, then the traceback."""
    return versions() + "\n\n" + "".join(traceback.format_exception(kind, value, tb))


class Reporter(QObject):
    """Shows the errors that nothing caught (see install), one dialog at a time: those that come while one is
    shown are only written to the terminal."""

    caught = Signal(str, str)  # what failed (a line), the details

    def __init__(self, parent=None):
        super().__init__(parent)
        self.showing = False
        self.caught.connect(self.show, Qt.ConnectionType.QueuedConnection)

    def hook(self, kind, value, tb):
        """sys.excepthook: written to the terminal, as before, and shown (from the main thread)."""
        text = details(kind, value, tb)
        print(text, file=sys.stderr)
        if issubclass(kind, KeyboardInterrupt):  # (Ctrl+C in the terminal: no dialog)
            return
        self.caught.emit(f"{kind.__name__}: {value}", text)

    def thread_hook(self, args):
        """threading.excepthook: the same, for an error in another thread."""
        if args.exc_type is SystemExit:
            return
        self.hook(args.exc_type, args.exc_value, args.exc_traceback)

    def show(self, what: str, text: str):
        if self.showing:
            return
        self.showing = True
        try:
            self.dialog(what, text)
        finally:
            self.showing = False

    def dialog(self, what: str, text: str):
        """The dialog: what failed, the details to be seen, a button that copies them."""
        from PySide6.QtWidgets import QApplication, QMessageBox

        box = QMessageBox(QMessageBox.Icon.Critical, tr("Something went wrong"),
                          tr("py-pdftools met an error it didn't expect: {error}", error=what[:300]),
                          parent=QApplication.activeWindow())
        box.setInformativeText(tr("What was being done may have been left undone. If it happens again, please "
                                  "report it with the details, which the button copies."))
        box.setDetailedText(text)
        copy = box.addButton(tr("Copy the details"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is copy:
            QApplication.clipboard().setText(text)


_REPORTER: Reporter | None = None


def install(app) -> Reporter:
    """The errors that nothing catches, shown in a dialog (see Reporter), in the main thread and in the others."""
    global _REPORTER
    if _REPORTER is None:
        _REPORTER = Reporter(app)
        sys.excepthook = _REPORTER.hook
        threading.excepthook = _REPORTER.thread_hook
    return _REPORTER
