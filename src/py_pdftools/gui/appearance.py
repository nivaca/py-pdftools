"""How the program looks and behaves, as Settings > Appearance and Settings > Documents say (the settings in
the configuration file, with their defaults in core/config.py): the colours of the interface (as the system
has them, light, dark or of high contrast), its size (the size of its letters, from 90 to 150 %), and what the windows read
when they need it (see value)."""

from __future__ import annotations

import os
import pathlib

from ..core import config
from ..core.interface import N_

THEMES = ("system", "light", "dark", "contrast", "nord", "solarized-light", "solarized-dark", "sepia")
# (their names, in the View menu and in Settings, in this order)
THEME_NAMES = {"system": N_("As the system"), "light": N_("Light"), "dark": N_("Dark"), "contrast": N_("High contrast"),
               "nord": N_("Nord"), "solarized-light": N_("Solarized light"), "solarized-dark": N_("Solarized dark"),
               "sepia": N_("Sepia")}
DARK_THEMES = {"dark", "contrast", "nord", "solarized-dark"}  # (with the dark variant of the icons)
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
              "Highlight": "#3374c9", "HighlightedText": "#ffffff", "ToolTipBase": "#ffffdc",
              "ToolTipText": "#1e1e1e", "Link": "#0b57d0", "LinkVisited": "#7b3fb0", "PlaceholderText": "#7a7a7a",
              "Light": "#ffffff", "Midlight": "#f5f5f5", "Mid": "#b8b8b8", "Dark": "#9f9f9f", "Shadow": "#767676"},
    "dark": {"Window": "#2b2d30", "WindowText": "#e6e6e6", "Base": "#1e1f22", "AlternateBase": "#2b2d30",
             "Text": "#e6e6e6", "Button": "#3c3f41", "ButtonText": "#e6e6e6", "BrightText": "#ff6b6b",
             "Highlight": "#3d6fb4", "HighlightedText": "#ffffff", "ToolTipBase": "#3c3f41",
             "ToolTipText": "#e6e6e6", "Link": "#6ea8fe", "LinkVisited": "#b392f0", "PlaceholderText": "#8c8f94",
             "Light": "#4a4d50", "Midlight": "#3f4245", "Mid": "#2f3134", "Dark": "#18191b", "Shadow": "#000000"},
    # Alto contraste: blanco sobre negro, lo elegido en amarillo con texto negro, los enlaces en cian; los bordes
    # (Light, Mid, Dark) claros, para que cada botón y casilla se distinga del fondo.
    "contrast": {"Window": "#000000", "WindowText": "#ffffff", "Base": "#000000", "AlternateBase": "#1a1a1a",
                 "Text": "#ffffff", "Button": "#000000", "ButtonText": "#ffffff", "BrightText": "#ffff00",
                 "Highlight": "#ffff00", "HighlightedText": "#000000", "ToolTipBase": "#000000",
                 "ToolTipText": "#ffffff", "Link": "#00ffff", "LinkVisited": "#ff80ff", "PlaceholderText": "#c8c8c8",
                 "Light": "#ffffff", "Midlight": "#c8c8c8", "Mid": "#ffffff", "Dark": "#ffffff", "Shadow": "#ffffff"},
    # Nord: gris azulado oscuro, con el azul y el cian de su paleta (nordtheme.com)
    "nord": {"Window": "#2e3440", "WindowText": "#e5e9f0", "Base": "#272b33", "AlternateBase": "#2e3440",
             "Text": "#e5e9f0", "Button": "#3b4252", "ButtonText": "#e5e9f0", "BrightText": "#bf616a",
             "Highlight": "#4c6a91", "HighlightedText": "#eceff4", "ToolTipBase": "#3b4252",
             "ToolTipText": "#e5e9f0", "Link": "#88c0d0", "LinkVisited": "#b48ead", "PlaceholderText": "#7b88a1",
             "Light": "#4c566a", "Midlight": "#434c5e", "Mid": "#3b4252", "Dark": "#1f232b", "Shadow": "#000000"},
    # Solarized (ethanschoonover.com/solarized): its text, a little darker on the light one than the original
    # grey, which is faint on its cream.
    "solarized-light": {"Window": "#eee8d5", "WindowText": "#3c4f56", "Base": "#fdf6e3", "AlternateBase": "#f5efdc",
                        "Text": "#3c4f56", "Button": "#e6dfcb", "ButtonText": "#3c4f56", "BrightText": "#fdf6e3",
                        "Highlight": "#1f6fa8", "HighlightedText": "#fdf6e3", "ToolTipBase": "#fdf6e3",
                        "ToolTipText": "#3c4f56", "Link": "#1f6fa8", "LinkVisited": "#6c71c4",
                        "PlaceholderText": "#8a9696", "Light": "#fdf6e3", "Midlight": "#f5efdc", "Mid": "#c9c2ad",
                        "Dark": "#a8a290", "Shadow": "#7a7564"},
    "solarized-dark": {"Window": "#073642", "WindowText": "#a7b4b4", "Base": "#002b36", "AlternateBase": "#073642",
                       "Text": "#a7b4b4", "Button": "#0b4352", "ButtonText": "#a7b4b4", "BrightText": "#dc322f",
                       "Highlight": "#1f6fa8", "HighlightedText": "#fdf6e3", "ToolTipBase": "#073642",
                       "ToolTipText": "#a7b4b4", "Link": "#2aa198", "LinkVisited": "#6c71c4",
                       "PlaceholderText": "#657b83", "Light": "#2c5a66", "Midlight": "#1b4a55", "Mid": "#073642",
                       "Dark": "#001e26", "Shadow": "#000000"},
    # Sepia: papel cálido y tinta parda, para leer largo rato con poca luz
    "sepia": {"Window": "#f1e7d0", "WindowText": "#3b2f20", "Base": "#fbf4e4", "AlternateBase": "#f4ead4",
              "Text": "#3b2f20", "Button": "#e8dcc0", "ButtonText": "#3b2f20", "BrightText": "#ffffff",
              "Highlight": "#9c6b30", "HighlightedText": "#ffffff", "ToolTipBase": "#fbf4e4",
              "ToolTipText": "#3b2f20", "Link": "#8a4b0f", "LinkVisited": "#6b3e75", "PlaceholderText": "#8c7b62",
              "Light": "#fffaf0", "Midlight": "#f4ead4", "Mid": "#c4b496", "Dark": "#a39274", "Shadow": "#6f604a"},
}
DISABLED = {"light": "#a0a0a0", "dark": "#7a7d80", "contrast": "#9a9a9a",  # (the text of what can't be used)
            "nord": "#6c7790", "solarized-light": "#a8a89c", "solarized-dark": "#4f6a72", "sepia": "#ab9c80"}
# Con alto contraste, cada casilla, lista y desplegable lleva un borde blanco, y el que tiene el foco uno amarillo
# más grueso: la paleta sola no basta, porque algunos estilos dibujan esos bordes con colores casi del fondo.
CONTRAST_STYLE = (
    "QLineEdit, QComboBox, QAbstractSpinBox, QAbstractItemView, QPlainTextEdit, QTextEdit "
    "{ border: 1px solid #ffffff; }"
    "QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QAbstractItemView:focus, QPlainTextEdit:focus, "
    "QTextEdit:focus, QGraphicsView:focus { border: 2px solid #ffff00; }"
)


def palette(name: str):
    """The palette of the theme NAME ('light', 'dark' or 'contrast'), with every role set."""
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

    # El nombre, con sus mayúsculas: en Windows y macOS, breeze-Dark también hallaría la carpeta breeze-dark
    for folder in QIcon.themeSearchPaths():
        if folder.startswith(":"):
            continue
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        if name in names and pathlib.Path(folder, name, "index.theme").is_file():
            return True
    return False


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


# Estilos nativos que no siguen la paleta del programa (dibujan con los colores del sistema): con un tema del
# programa, Fusion los reemplaza, como hace Calibre; Breeze, en Linux, sí la sigue, y se queda
NATIVE_STYLES = {"windows11", "windowsvista", "macos", "macintosh"}
_SYSTEM_STYLE: str | None = None  # (the style Qt started with, given back with the theme 'system')


def _use_style(name: str) -> None:
    """The style NAME for the whole application, if it isn't the one in use already."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None and app.style().name().lower() != name.lower():
        app.setStyle(name)


def apply_theme(name: str | None = None):
    """The colours of the interface: as the system has them, or one of the program's themes (THEMES), each a
    whole palette of its own, and the matching variant of the icon theme: asking Qt for a scheme of
    colours alone isn't enough, since the desktop's own theme (the portal of KDE, for one) may keep its
    colours over it. 'system' gives the desktop its colours and icons back."""
    global _SYSTEM_ICONS, _SYSTEM_STYLE, _APPLIED
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QIcon, QPalette
    from PySide6.QtWidgets import QApplication, QToolTip

    app = QApplication.instance()
    if app is None:
        return
    name = name or value("theme")
    _APPLIED = name
    if _SYSTEM_ICONS is None:
        _SYSTEM_ICONS = QIcon.themeName()
    if _SYSTEM_STYLE is None:
        _SYSTEM_STYLE = app.style().name()
    hints = QGuiApplication.styleHints()
    if name in PALETTES:
        dark = name in DARK_THEMES  # (high contrast is white on black: the icons of a dark theme)
        # (also the scheme, for what reads it: the style, the dialogs of the system, where they follow it)
        if hasattr(hints, "setColorScheme"):  # (Qt 6.8 or later)
            hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        # (el estilo antes que la paleta: setStyle puede poner la del estilo)
        if _SYSTEM_STYLE.lower() in NATIVE_STYLES:  # (Windows, macOS: their style would ignore the palette)
            _use_style("Fusion")
        _watch(app)
        app.setPalette(palette(name))
        QToolTip.setPalette(app.palette())  # (los globos de ayuda guardan la suya: quedaban del tema anterior)
        app.setStyleSheet(CONTRAST_STYLE if name == "contrast" else "")
        apply_icons(dark)
        return
    if hasattr(hints, "unsetColorScheme"):
        hints.unsetColorScheme()
    _watch(app)
    if _SYSTEM_STYLE:
        _use_style(_SYSTEM_STYLE)  # (the system's style again, if a theme of the program had changed it)
    # Una paleta vacía (sin ningún papel fijado) devuelve la de la plataforma
    app.setPalette(QPalette())
    QToolTip.setPalette(app.palette())
    app.setStyleSheet("")
    apply_icons(None)


_WATCH = None  # (see _watch)
_APPLIED = "system"  # (the theme apply_theme set last: the one _watch keeps)


def _watch(app) -> None:
    """Once: the theme chosen is kept, and followed. If the desktop changes the palette of the program while it
    runs (KDE does, when its colour scheme is changed), a theme of the program is set again, as Calibre does;
    with 'system', a switch of the system between light and dark draws the icons again, and takes the matching
    variant of the icon theme."""
    global _WATCH
    if _WATCH is not None:
        return
    from PySide6.QtCore import QEvent, QObject, QTimer
    from PySide6.QtGui import QGuiApplication, QPalette

    class Watch(QObject):
        pending = False

        def eventFilter(self, obj, event):
            if obj is app and event.type() == QEvent.Type.ApplicationPaletteChange and not self.pending:
                wanted = PALETTES.get(_APPLIED, {}).get("Window")
                if wanted and app.palette().color(QPalette.ColorRole.Window).name() != wanted:
                    self.pending = True  # (set again once, after the change that came from outside)
                    QTimer.singleShot(0, self.again)
            return False

        def again(self):
            self.pending = False
            if _APPLIED in PALETTES and app.palette().color(QPalette.ColorRole.Window).name() != \
                    PALETTES[_APPLIED]["Window"]:
                apply_theme(_APPLIED)

        def scheme_changed(self, _scheme=None):
            if _APPLIED not in PALETTES:
                apply_icons(None)

    _WATCH = Watch(app)
    app.installEventFilter(_WATCH)
    hints = QGuiApplication.styleHints()
    if hasattr(hints, "colorSchemeChanged"):  # (Qt 6.5 or later)
        hints.colorSchemeChanged.connect(_WATCH.scheme_changed)


ICON_CHOICES = {"system": N_("As the desktop"), "own": N_("The program's own")}  # (and each theme installed)


def installed_icon_themes() -> list[tuple[str, str]]:
    """The icon themes installed, that have icons of actions (not those of cursors, nor hicolor, which every
    theme falls back to): (their folder's name, the name they give themselves), in the order of the names."""
    import configparser

    from PySide6.QtGui import QIcon

    found: dict[str, str] = {}
    for folder in QIcon.themeSearchPaths():
        if folder.startswith(":"):  # (Qt's resources: no theme of the system)
            continue
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for theme in names:
            index = pathlib.Path(folder, theme, "index.theme")
            if theme in found or theme.lower() in ("hicolor", "locolor", "default") or not index.is_file():
                continue
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                parser.read_string(index.read_text(encoding="utf-8", errors="replace"))
                about = parser["Icon Theme"]
            except (configparser.Error, KeyError, OSError):
                continue
            # (un tema de cursores no tiene carpetas de iconos; uno oculto no se ofrece)
            if "actions" not in about.get("Directories", "").lower() or about.get("Hidden", "").lower() == "true":
                continue
            found[theme] = about.get("Name", theme) or theme
    return sorted(found.items(), key=lambda item: (item[1].casefold(), item[0]))


def apply_icons(dark: bool | None = ...):
    """The icons, as the setting 'icons' says: 'system', the desktop's theme (in its light or dark variant,
    with a theme of the program: DARK, whether it is dark; None, as the desktop has it); 'own', the
    program's own SVGs wherever it has one; or the name of an icon theme installed. Every widget is drawn
    again: the icons of the program follow the theme when they are drawn (see own_icons.py)."""
    global _SYSTEM_ICONS
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import own_icons

    if _SYSTEM_ICONS is None:
        _SYSTEM_ICONS = QIcon.themeName()
    if dark is ...:  # (asked by itself: the dark of the theme in use)
        theme = value("theme")
        dark = (theme in DARK_THEMES) if theme in PALETTES else None
    choice = value("icons") or "system"
    own_icons.OWN_ONLY = choice == "own"
    if choice not in ICON_CHOICES and _icon_theme_exists(choice):
        QIcon.setThemeName(choice)
    elif _SYSTEM_ICONS:
        QIcon.setThemeName(icon_theme(_SYSTEM_ICONS, dark) if dark is not None else _SYSTEM_ICONS)
    app = QApplication.instance()
    if app is not None:
        for widget in app.allWidgets():
            widget.update()


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
# ms: at the start, how long the filter waits before it is installed. It sees every event of the application, and
# building the window and drawing its first page send thousands (14 ms more, measured); a tooltip needs the mouse
# still for 700 ms, so none can show before it is there.
TIPS_LATER_MS = 500


def apply_tooltips(show: bool | None = None, later: int = 0):
    """Whether the tooltips show (the bubbles over buttons, menus and fields when the mouse rests on them):
    without them, an event filter of the application drops the events that ask for them, except those of
    the toolbars, which always show. Tips the program
    shows by itself (the address of a link under the mouse) are not of those, and stay. LATER: ms to wait
    before the filter is installed (see TIPS_LATER_MS)."""
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
    elif not show and _NO_TIPS is None and later:
        from PySide6.QtCore import QTimer

        # (asked again then: the setting may have changed meanwhile, and the filter is installed only once)
        QTimer.singleShot(later, apply_tooltips)
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
    apply_tooltips(later=TIPS_LATER_MS)
