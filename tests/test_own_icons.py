"""Los iconos propios (icons/actions): sobre un fondo oscuro, sus trazos oscuros se aclaran, y el mismo icono
cambia cuando cambia el tema, sin volver a cargarse."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def darkest(icon) -> int:
    """The lightness of the darkest pixel that is drawn (not transparent) of ICON at 32 pixels."""
    image = icon.pixmap(32, 32).toImage()
    return min(QColor(image.pixel(x, y)).lightness() for x in range(image.width()) for y in range(image.height())
               if QColor.fromRgba(image.pixel(x, y)).alpha() > 200)


def test_light_on_a_dark_interface():
    from py_pdftools.gui import appearance
    from py_pdftools.gui.own_icons import for_dark, own_icon
    from py_pdftools.gui.window import ACTIONS

    app = QApplication.instance() or QApplication([])
    before = app.palette()
    try:
        signature = own_icon(ACTIONS / "signature.svg")  # (dark navy, unreadable on a dark background)
        appearance.apply_theme("light")
        assert darkest(signature) < 80
        appearance.apply_theme("dark")
        assert app.palette().color(QPalette.ColorRole.Window).lightness() < 128
        assert darkest(signature) > 110  # (the same icon, light now)
        # (dark letters on the yellow of Highlight stay dark: they are on a light fill)
        assert "#1d1f24" in for_dark((ACTIONS / "draw-highlight.svg").read_text(), "draw-highlight")
        assert "#1d1f24" not in for_dark((ACTIONS / "draw-text.svg").read_text(), "draw-text")
    finally:
        appearance.apply_theme("system")
        app.setPalette(before)
