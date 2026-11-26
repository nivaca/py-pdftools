"""Los temas de colores (los cuatro de antes y Nord, Solarized claro y oscuro, Sepia) y la elección de los
iconos (los del escritorio, los propios del programa u otro tema instalado), en Ver y en Configuración, al
instante y guardados."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from py_pdftools.core import config
from py_pdftools.gui import appearance, own_icons
from py_pdftools.gui.window import _WINDOWS, ACTIONS, MainWindow


@pytest.fixture
def window():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.ask_recover = lambda when: False
    _WINDOWS.append(w)
    yield w
    w.close()
    if w in _WINDOWS:
        _WINDOWS.remove(w)
    appearance.apply_theme("system")


@pytest.fixture
def icon_themes(tmp_path):
    """Icon themes of the test only: Fake, with a red Signature icon; a theme of cursors; hicolor."""
    paths, name = QIcon.themeSearchPaths(), QIcon.themeName()
    fake = tmp_path / "Fake"
    (fake / "actions" / "scalable").mkdir(parents=True)
    (fake / "index.theme").write_text("[Icon Theme]\nName=Fake icons\nDirectories=actions/scalable\n\n"
                                      "[actions/scalable]\nSize=16\nMinSize=8\nMaxSize=512\nType=Scalable\n"
                                      "Context=Actions\n")
    (fake / "actions" / "scalable" / "signature.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" '
        'fill="#ff0000"/></svg>')
    (tmp_path / "Cursors").mkdir()
    (tmp_path / "Cursors" / "index.theme").write_text("[Icon Theme]\nName=Some cursors\n")
    (tmp_path / "hicolor").mkdir()
    (tmp_path / "hicolor" / "index.theme").write_text("[Icon Theme]\nName=Hicolor\nDirectories=actions/16\n")
    QIcon.setThemeSearchPaths([str(tmp_path)])
    yield
    QIcon.setThemeSearchPaths(paths)
    QIcon.setThemeName(name)
    own_icons.OWN_ONLY = False


def middle(icon) -> QColor:
    image = icon.pixmap(32, 32).toImage()
    return QColor(image.pixel(16, 16))


def contrast(a: str, b: str) -> float:
    def lum(colour):
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
             for x in (QColor(colour).redF(), QColor(colour).greenF(), QColor(colour).blueF())]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_every_theme_is_whole_and_readable():
    for name in appearance.THEMES[1:]:
        colours = appearance.PALETTES[name]
        assert name in appearance.DISABLED and name in appearance.THEME_NAMES
        # (text on its fields, and the text of what is selected, legible: WCAG's 4.5 to 1)
        assert contrast(colours["Text"], colours["Base"]) >= 4.5, name
        assert contrast(colours["WindowText"], colours["Window"]) >= 4.5, name
        assert contrast(colours["HighlightedText"], colours["Highlight"]) >= 4.5, name
        dark = QColor(colours["Window"]).lightness() < 128
        assert dark == (name in appearance.DARK_THEMES), name


def test_installed_icon_themes(icon_themes):
    # (neither the cursors, which have no icons, nor hicolor, which every theme falls back to)
    assert appearance.installed_icon_themes() == [("Fake", "Fake icons")]


def test_the_theme_or_the_programs_own(icon_themes):
    """An icon of the program is the theme's while the theme has it; the program's own with the setting 'own',
    or in a theme without it; the same icon follows each change, without being made again."""
    from py_pdftools.gui.window import icon

    QApplication.instance() or QApplication([])
    signature = icon("signature")
    config.set("icons", "Fake")
    appearance.apply_icons(None)
    assert QIcon.themeName() == "Fake" and middle(signature).name() == "#ff0000"
    config.set("icons", "own")
    appearance.apply_icons(None)
    assert middle(signature).name() != "#ff0000"
    assert not icon("signature").pixmap(32, 32).toImage().isNull()
    config.set("icons", "Gone")  # (a theme no longer installed: the desktop's)
    appearance.apply_icons(None)
    assert not own_icons.OWN_ONLY and QIcon.themeName() != "Gone"
    assert (ACTIONS / "signature.svg").is_file()


def test_from_the_view_menu(window, icon_themes):
    window.m_theme.aboutToShow.emit()
    names = [a.text() for a in window.m_theme.actions()]
    assert names == [appearance.THEME_NAMES[k] for k in appearance.THEMES]
    nord = next(a for a in window.m_theme.actions() if a.data() == "nord")
    nord.trigger()
    assert config.get("theme") == "nord"
    assert QApplication.instance().palette().color(QPalette.ColorRole.Window).name() == "#2e3440"
    window.m_theme.aboutToShow.emit()  # (made again: the one in use ticked)
    assert [a.data() for a in window.m_theme.actions() if a.isChecked()] == ["nord"]
    window.m_icons.aboutToShow.emit()
    keys = [a.data() for a in window.m_icons.actions() if not a.isSeparator()]
    assert keys == ["system", "own", "Fake"]
    next(a for a in window.m_icons.actions() if a.data() == "own").trigger()
    assert config.get("icons") == "own" and own_icons.OWN_ONLY


def test_from_the_settings(window, icon_themes):
    from py_pdftools.gui.prefs import SettingsDialog

    d = SettingsDialog(window.prefs, window)
    assert [d.theme.itemData(i) for i in range(d.theme.count())] == list(appearance.THEMES)
    d.theme.setCurrentIndex(d.theme.findData("sepia"))
    d.icons.setCurrentIndex(d.icons.findData("Fake"))
    d.accept()
    assert config.get("theme") == "sepia" and config.get("icons") == "Fake" and QIcon.themeName() == "Fake"


def test_fusion_where_the_native_style_ignores_the_palette(monkeypatch):
    """On Windows and macOS, whose styles draw with the system's colours, a theme of the program takes Fusion, and
    'system' gives the native style back; elsewhere (Breeze, Fusion) the style stays."""
    QApplication.instance() or QApplication([])
    used = []
    monkeypatch.setattr(appearance, "_use_style", used.append)
    monkeypatch.setattr(appearance, "_SYSTEM_STYLE", "windows11")
    try:
        appearance.apply_theme("nord")
        appearance.apply_theme("system")
        assert used == ["Fusion", "windows11"]
        used.clear()
        monkeypatch.setattr(appearance, "_SYSTEM_STYLE", "Breeze")
        appearance.apply_theme("sepia")
        assert used == []  # (Breeze follows the palette: it stays)
    finally:
        appearance.apply_theme("system")
