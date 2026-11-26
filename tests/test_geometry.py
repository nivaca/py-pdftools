"""El lugar y el tamaño de la ventana guardados de otra sesión, ajustados a las pantallas de ahora: una ventana
que quedó fuera de toda pantalla (en un monitor que ya no está) o más grande que la suya vuelve a una."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget

from py_pdftools.gui.window import fit_on_screen


def test_brought_back_onto_a_screen():
    QApplication.instance() or QApplication([])
    room = QApplication.primaryScreen().availableGeometry()
    w = QWidget()
    try:
        w.setGeometry(room.right() + 3000, room.bottom() + 3000, 400, 300)  # (on a monitor gone)
        fit_on_screen(w)
        assert room.contains(w.geometry().topLeft()) and w.width() == 400
        w.setGeometry(room.left(), room.top(), room.width() + 2000, room.height() + 1000)  # (larger than it)
        fit_on_screen(w)
        assert w.width() <= room.width() and w.height() <= room.height()
        w.setGeometry(room.left() + 10, room.top() + 10, 300, 200)  # (where it fits: left alone)
        fit_on_screen(w)
        assert (w.x(), w.y(), w.width(), w.height()) == (room.left() + 10, room.top() + 10, 300, 200)
    finally:
        w.deleteLater()
