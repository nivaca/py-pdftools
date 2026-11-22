"""Ayuda > Buscar una versión nueva (ver core/updates.py): la pregunta va en otro hilo, con un diálogo que la
puede cancelar, y la respuesta dice si hay una versión nueva y cómo instalarla en esta copia."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from .. import __version__
from ..core import updates
from ..core.interface import tr


def ask_latest(parent) -> updates.Release | None:
    """The latest release, asked in another thread while a dialog waits (None if cancelled). Raises
    UpdateError."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="updates")
    future: Future = pool.submit(updates.latest)
    pool.shutdown(wait=False)  # (el hilo termina por sí solo; cancelar no lo espera)
    wait = QProgressDialog(tr("Asking GitHub for the latest version…"), tr("Cancel"), 0, 0, parent)
    wait.setWindowTitle(tr("Check for a new version"))
    wait.setMinimumDuration(300)  # (una respuesta rápida no hace parpadear el diálogo)
    loop = QEventLoop()
    timer = QTimer(interval=50)
    timer.timeout.connect(lambda: future.done() and loop.quit())
    wait.canceled.connect(loop.quit)
    timer.start()
    if not future.done():
        loop.exec()
    timer.stop()
    cancelled = wait.wasCanceled()
    wait.close()
    if cancelled and not future.done():
        return None
    return future.result()


def check_for_updates(parent) -> str:
    """Help > Check for a new version: what was found is said. Returns 'newer', 'latest', 'ahead' (this one is
    newer than the latest published), 'cancelled' or 'error'."""
    title = tr("Check for a new version")
    try:
        release = ask_latest(parent)
    except updates.UpdateError as e:
        QMessageBox.warning(parent, title, tr("The latest version could not be found out: {error}", error=e))
        return "error"
    if release is None:
        return "cancelled"
    if updates.newer(__version__, release.version):
        box = QMessageBox(QMessageBox.Icon.Information, title,
                          tr("py-pdftools {new} is out; this is {version}.", new=release.version,
                             version=__version__), parent=parent)
        box.setInformativeText(updates.how_to_update(updates.installation(), release.version))
        page = box.addButton(tr("Open the page of the release"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is page:
            QDesktopServices.openUrl(QUrl(release.url))
        return "newer"
    if updates.newer(release.version, __version__):
        QMessageBox.information(parent, title, tr("This version, {version}, is newer than the latest published "
                                                  "({new}).", version=__version__, new=release.version))
        return "ahead"
    QMessageBox.information(parent, title, tr("py-pdftools {version} is the latest version.", version=__version__))
    return "latest"
