"""Los errores que nada atrapó: además de la terminal, un diálogo con los detalles (y las versiones), desde el
hilo principal aunque el error ocurra en otro."""

from __future__ import annotations

import sys
import threading

from PySide6.QtWidgets import QApplication

from py_pdftools.gui import errors


def test_shown_with_its_details(capsys):
    app = QApplication.instance() or QApplication([])
    reporter = errors.Reporter(app)
    shown = []
    reporter.dialog = lambda what, text: shown.append((what, text, threading.current_thread()))
    try:
        raise ValueError("the page is missing")
    except ValueError:
        reporter.hook(*sys.exc_info())
    QApplication.processEvents()
    assert len(shown) == 1 and shown[0][0] == "ValueError: the page is missing"
    assert "py-pdftools " in shown[0][1] and "PyMuPDF" in shown[0][1] and "Traceback" in shown[0][1]
    assert "the page is missing" in capsys.readouterr().err  # (the terminal, as before)
    # (from another thread: shown by the main one)
    def fail():
        raise RuntimeError("in a thread")

    worker = threading.Thread(target=fail)
    old = threading.excepthook
    threading.excepthook = reporter.thread_hook
    try:
        worker.start()
        worker.join()
    finally:
        threading.excepthook = old
    QApplication.processEvents()
    assert shown[1][0] == "RuntimeError: in a thread" and shown[1][2] is threading.main_thread()
    # (Ctrl+C: no dialog)
    reporter.hook(KeyboardInterrupt, KeyboardInterrupt(), None)
    QApplication.processEvents()
    assert len(shown) == 2
    reporter.deleteLater()
