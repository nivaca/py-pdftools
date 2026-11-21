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


def apply():
    """The theme and the size, as the settings say (at the start, and when they change)."""
    apply_theme()
    apply_scale()
