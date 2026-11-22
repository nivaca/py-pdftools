"""How the program looks and behaves, as Settings > Appearance and Settings > Documents say (the settings in
the configuration file, with their defaults in core/config.py): the colours of the interface (as the system
has them, light or dark), its size (the size of its letters, from 90 to 150 %), and what the windows read
when they need it (see value)."""

from __future__ import annotations

import pathlib

from ..core import config

THEMES = ("system", "light", "dark")
SCALES = (90, 100, 110, 125, 150)
OPENINGS = ("document", "page", "width", "actual")  # (how a document opens, without a place remembered)
_BASE_POINTS: float | None = None  # (the size of the letters before any scale: that of the system)


def value(name: str):
    """The setting NAME (its default, if the configuration file hasn't it or can't be read)."""
    return config.get(name)


_SYSTEM_ICONS: str | None = None  # (the icon theme of the desktop, before any theme of the program changed it)

# Los colores de cada tema, todos los papeles: con una paleta entera, el estilo del escritorio (Breeze,
# Fusion...) no tiene nada que completar con los suyos, que serían los del tema contrario.
PALETTES = {
    "light": {"Window": "#efefef", "WindowText": "#1e1e1e", "Base": "#ffffff", "AlternateBase": "#f5f5f5",
              "Text": "#1e1e1e", "Button": "#e6e6e6", "ButtonText": "#1e1e1e", "BrightText": "#ffffff",
              "Highlight": "#3d7fd6", "HighlightedText": "#ffffff", "ToolTipBase": "#ffffdc",
              "ToolTipText": "#1e1e1e", "Link": "#0b57d0", "LinkVisited": "#7b3fb0", "PlaceholderText": "#7a7a7a",
              "Light": "#ffffff", "Midlight": "#f5f5f5", "Mid": "#b8b8b8", "Dark": "#9f9f9f", "Shadow": "#767676"},
    "dark": {"Window": "#2b2d30", "WindowText": "#e6e6e6", "Base": "#1e1f22", "AlternateBase": "#2b2d30",
             "Text": "#e6e6e6", "Button": "#3c3f41", "ButtonText": "#e6e6e6", "BrightText": "#ff6b6b",
             "Highlight": "#3d6fb4", "HighlightedText": "#ffffff", "ToolTipBase": "#3c3f41",
             "ToolTipText": "#e6e6e6", "Link": "#6ea8fe", "LinkVisited": "#b392f0", "PlaceholderText": "#8c8f94",
             "Light": "#4a4d50", "Midlight": "#3f4245", "Mid": "#2f3134", "Dark": "#18191b", "Shadow": "#000000"},
}
DISABLED = {"light": "#a0a0a0", "dark": "#7a7d80"}  # (the text of what can't be used)


def palette(name: str):
    """The palette of the theme NAME ('light' or 'dark'), with every role set."""
    from PySide6.QtGui import QColor, QPalette

    out = QPalette()
    for role, colour in PALETTES[name].items():
        out.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
    if hasattr(QPalette.ColorRole, "Accent"):  # (Qt 6.6 or later)
        out.setColor(QPalette.ColorRole.Accent, QColor(PALETTES[name]["Highlight"]))
    off = QColor(DISABLED[name])
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        out.setColor(QPalette.ColorGroup.Disabled, role, off)
    out.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(PALETTES[name]["Mid"]))
    return out


def _icon_theme_exists(name: str) -> bool:
    from PySide6.QtGui import QIcon

    return any(pathlib.Path(folder, name, "index.theme").is_file() for folder in QIcon.themeSearchPaths()
               if not folder.startswith(":"))


def icon_theme(name: str, dark: bool) -> str:
    """The variant of the icon theme NAME for a DARK interface (or a light one), if it is installed: breeze
    and breeze-dark, Papirus-Light and Papirus-Dark... else NAME itself."""
    lower = name.lower()
    # (un tema sin sufijo, como breeze o Papirus, es el claro)
    if lower.endswith("-dark"):
        base, now_dark = name[: -len("-dark")], True
    elif lower.endswith("-light"):
        base, now_dark = name[: -len("-light")], False
    else:
        base, now_dark = name, False
    if now_dark == dark:
        return name
    wanted = [base + "-Dark", base + "-dark"] if dark else [base, base + "-Light", base + "-light"]
    return next((n for n in wanted if _icon_theme_exists(n)), name)


def apply_theme(name: str | None = None):
    """The colours of the interface: as the system has them, light or dark. Light and dark set a whole
    palette of the program's own, and the matching variant of the icon theme: asking Qt for a scheme of
    colours alone isn't enough, since the desktop's own theme (the portal of KDE, for one) may keep its
    colours over it. 'system' gives the desktop its colours and icons back."""
    global _SYSTEM_ICONS
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QIcon, QPalette
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    name = name or value("theme")
    if _SYSTEM_ICONS is None:
        _SYSTEM_ICONS = QIcon.themeName()
    hints = QGuiApplication.styleHints()
    if name in ("light", "dark"):
        dark = name == "dark"
        # (also the scheme, for what reads it: the style, the dialogs of the system, where they follow it)
        if hasattr(hints, "setColorScheme"):  # (Qt 6.8 or later)
            hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        app.setPalette(palette(name))
        if _SYSTEM_ICONS:
            QIcon.setThemeName(icon_theme(_SYSTEM_ICONS, dark))
        return
    if hasattr(hints, "unsetColorScheme"):
        hints.unsetColorScheme()
    # Una paleta vacía (sin ningún papel fijado) devuelve la de la plataforma
    app.setPalette(QPalette())
    if _SYSTEM_ICONS:
        QIcon.setThemeName(_SYSTEM_ICONS)


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
