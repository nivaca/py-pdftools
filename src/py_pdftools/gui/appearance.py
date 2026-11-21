"""How the program looks and behaves, as Settings > Appearance and Settings > Documents say (the settings in
the configuration file, with their defaults in core/config.py): the colours of the interface (as the system
has them, light or dark), its size (the size of its letters, from 90 to 150 %), and what the windows read
when they need it (see value)."""

from __future__ import annotations

from ..core import config

THEMES = ("system", "light", "dark")
SCALES = (90, 100, 110, 125, 150)
OPENINGS = ("document", "page", "width", "actual")  # (how a document opens, without a place remembered)
_BASE_POINTS: float | None = None  # (the size of the letters before any scale: that of the system)


def value(name: str):
    """The setting NAME (its default, if the configuration file hasn't it or can't be read)."""
    return config.get(name)


def apply_theme(name: str | None = None):
    """The colours of the interface: as the system has them, light or dark (Qt's own scheme of colours)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    name = name or value("theme")
    scheme = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(name, Qt.ColorScheme.Unknown)
    hints = QGuiApplication.styleHints()
    if hasattr(hints, "setColorScheme"):  # (Qt 6.8 or later)
        hints.setColorScheme(scheme)
        return
    # (un Qt anterior: los colores de Fusion, oscuros o claros; «system» deja los del estilo)
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None or name == "system":
        return
    app.setStyle("Fusion")
    if name == "light":
        app.setPalette(app.style().standardPalette())
        return
    palette = QPalette()
    for role, colour in ((QPalette.ColorRole.Window, "#2b2d30"), (QPalette.ColorRole.WindowText, "#e6e6e6"),
                         (QPalette.ColorRole.Base, "#1e1f22"), (QPalette.ColorRole.AlternateBase, "#2b2d30"),
                         (QPalette.ColorRole.Text, "#e6e6e6"), (QPalette.ColorRole.Button, "#3c3f41"),
                         (QPalette.ColorRole.ButtonText, "#e6e6e6"), (QPalette.ColorRole.Highlight, "#3d6fb4"),
                         (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.ToolTipBase, "#3c3f41"),
                         (QPalette.ColorRole.ToolTipText, "#e6e6e6"), (QPalette.ColorRole.Link, "#6ea8fe")):
        palette.setColor(role, QColor(colour))
    app.setPalette(palette)


def apply_scale(percent: int | None = None):
    """The size of the interface: its letters, PERCENT of the system's (the widgets follow them)."""
    global _BASE_POINTS
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    percent = int(percent or value("scale") or 100)
    font = app.font()
    if _BASE_POINTS is None:
        _BASE_POINTS = font.pointSizeF() if font.pointSizeF() > 0 else 10.0
    font.setPointSizeF(round(_BASE_POINTS * percent / 100, 1))
    app.setFont(font)


def apply_sharpness(name: str | None = None) -> bool:
    """The sharpness of the text of the pages (see reading.SHARPNESS). Whether it changed (the pages are then
    to be drawn again)."""
    from . import reading

    sharpness = reading.SHARPNESS.get(name or value("sharpness"), reading.SHARPNESS["drawn"])
    changed = sharpness != reading.SHARPEN
    reading.SHARPEN = sharpness
    return changed


_NO_TIPS = None  # (the filter that keeps the tooltips from showing, while it is installed: see apply_tooltips)


def apply_tooltips(show: bool | None = None):
    """Whether the tooltips show (the bubbles over buttons, menus and fields when the mouse rests on them):
    without them, an event filter of the application drops the events that ask for them, except those of
    the toolbars, which always show. Tips the program
    shows by itself (the address of a link under the mouse) are not of those, and stay."""
    global _NO_TIPS
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QApplication, QToolBar, QWidget

    app = QApplication.instance()
    if app is None:
        return
    show = bool(value("tooltips")) if show is None else show
    if show and _NO_TIPS is not None:
        app.removeEventFilter(_NO_TIPS)
        _NO_TIPS = None
    elif not show and _NO_TIPS is None:

        class NoTips(QObject):
            def eventFilter(self, obj, event):
                if event.type() != QEvent.Type.ToolTip:
                    return False
                # Las de las barras de herramientas se ven siempre: sus botones casi solo tienen icono
                w = obj if isinstance(obj, QWidget) else None
                while w is not None:
                    if isinstance(w, QToolBar):
                        return False
                    w = w.parentWidget()
                return True  # (tragado: la burbuja no se pide)

        _NO_TIPS = NoTips(app)
        app.installEventFilter(_NO_TIPS)


def apply():
    """The theme, the size, the sharpness of the text and the tooltips, as the settings say (at the start, and
    when they change)."""
    apply_theme()
    apply_scale()
    apply_sharpness()
    apply_tooltips()
