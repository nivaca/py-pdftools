"""Settings > Appearance and Documents: the colours and the size of the interface, the hints of the modes, the
toolbars of every window; how a document opens, its place remembered or not, links asked about or not, the
recent documents, where the file dialogs start. Each kept in the configuration file and in effect at once."""

from __future__ import annotations

import sys

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from py_pdftools.core import config
from py_pdftools.gui import appearance
from py_pdftools.gui.prefs import SettingsDialog
from py_pdftools.gui.window import _WINDOWS, MainWindow


@pytest.fixture
def window(tmp_path):
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.ask_recover = lambda when: False
    _WINDOWS.append(w)
    yield w
    w.close()
    if w in _WINDOWS:
        _WINDOWS.remove(w)


def doc(path, pages=3):
    d = pymupdf.open()
    for _ in range(pages):
        d.new_page()
    d.save(path)
    return path


def test_defaults():
    # (the hints of the modes and the tooltips: off at first)
    assert [appearance.value(k) for k in ("theme", "scale", "hints", "tooltips", "opening", "places", "ask_links",
                                          "recent", "dialogs")] == ["system", 100, False, False, "document", True,
                                                                    True, 10, "last"]


def test_tooltips(window):
    """Settings > Appearance > Show tooltips: without it (at first), the events that ask for a tooltip are
    dropped; with it, they reach the widgets."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent

    from PySide6.QtCore import QObject

    class Got(QObject):  # (a filter of the widget's own: it runs after the application's, if that one lets it)
        def __init__(self):
            super().__init__()
            self.got = []

        def eventFilter(self, obj, event):
            self.got.append(event.type())
            return False

    def asks(button=None):  # (whether a widget gets the event that asks for its tooltip)
        button = button if button is not None else window.outline_filter
        spy = Got()
        button.installEventFilter(spy)
        QApplication.sendEvent(button, QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5), QPoint(5, 5)))
        button.removeEventFilter(spy)
        return QEvent.Type.ToolTip in spy.got

    try:
        appearance.apply_tooltips()
        assert not asks()
        # (those of the toolbars show all the same)
        bar = window.toolbars()[0]
        assert asks(bar) and asks(bar.widgetForAction(bar.actions()[0]))
        d = SettingsDialog(window.prefs, window)
        assert not d.tooltips.isChecked()
        d.tooltips.setChecked(True)
        d.accept()
        assert config.get("tooltips") is True and asks()
    finally:
        appearance.apply_tooltips(True)


def test_appearance(window):
    app = QApplication.instance()
    points = app.font().pointSizeF()
    d = SettingsDialog(window.prefs, window)
    d.scale.setCurrentIndex(d.scale.findData(125))
    d.theme.setCurrentIndex(d.theme.findData("dark"))
    d.hints.setChecked(True)
    d.bar_style.setCurrentIndex(d.bar_style.findData("beside"))
    d.bar_size.setCurrentIndex(d.bar_size.findData(32))
    d.accept()
    assert config.get("scale") == 125 and config.get("theme") == "dark" and config.get("hints") is True
    assert abs(app.font().pointSizeF() - points * 1.25) < 0.2
    bar = next(b for b in window.toolbars() if b.objectName() == "file")
    assert bar.toolButtonStyle().name == "ToolButtonTextBesideIcon" and bar.iconSize().width() == 32
    window.set_mode("redact")
    assert not window.hint.isHidden() and window.hint.text()  # (the hint of the mode: the setting says so)
    d = SettingsDialog(window.prefs, window)
    d.hints.setChecked(False)
    d.accept()
    window.hint.show_text("")
    window.hint.hide()
    window.set_mode("read")
    assert window.hint.isHidden()  # (no hint: the setting says so)
    appearance.apply_scale(100)
    appearance.apply_theme("system")


def test_light_and_dark_whatever_the_desktop(window):
    """Light and dark set the program's own palette, whatever colours the desktop's theme keeps (asking Qt
    for a scheme alone did nothing under KDE's portal); the view behind the pages follows; System gives the
    desktop's palette back."""
    from PySide6.QtGui import QPalette

    app = QApplication.instance()
    before = app.palette().color(QPalette.ColorRole.Window).name()
    window_colour = lambda: window.palette().color(QPalette.ColorRole.Window).lightness()
    try:
        appearance.apply_theme("dark")
        QApplication.processEvents()
        assert window_colour() < 80 and window.canvas.backgroundBrush().color().lightness() < 80
        appearance.apply_theme("light")
        QApplication.processEvents()
        assert window_colour() > 200 and window.canvas.backgroundBrush().color().lightness() > 120
        # (disabled text, too: of the theme, not left to the style)
        disabled = app.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        assert disabled.name() == appearance.DISABLED["light"]
    finally:
        appearance.apply_theme("system")
        QApplication.processEvents()
    assert app.palette().color(QPalette.ColorRole.Window).name() == before


def test_icon_theme_variants(tmp_path, monkeypatch):
    """The icons follow light and dark: the variant of the desktop's icon theme, where it is installed."""
    from PySide6.QtGui import QIcon

    for name in ("breeze", "breeze-dark", "Papirus-Colors", "Papirus-Colors-Dark", "Papirus-Light", "Papirus-Dark",
                 "Adwaita"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "index.theme").write_text("[Icon Theme]\n")
    monkeypatch.setattr(QIcon, "themeSearchPaths", staticmethod(lambda: [str(tmp_path), ":/icons"]))
    assert appearance.icon_theme("breeze", dark=True) == "breeze-dark"
    assert appearance.icon_theme("breeze-dark", dark=False) == "breeze"
    assert appearance.icon_theme("breeze-dark", dark=True) == "breeze-dark"
    assert appearance.icon_theme("Papirus-Colors-Dark", dark=False) == "Papirus-Colors"
    assert appearance.icon_theme("Papirus-Light", dark=True) == "Papirus-Dark"
    assert appearance.icon_theme("Papirus-Dark", dark=False) == "Papirus-Light"  # (Papirus itself isn't here)
    assert appearance.icon_theme("Adwaita", dark=True) == "Adwaita"  # (no variant: as it is)


def test_documents(window, tmp_path, monkeypatch):
    first = doc(tmp_path / "a.pdf", 5)
    d = SettingsDialog(window.prefs, window)
    d.opening.setCurrentIndex(d.opening.findData("actual"))
    d.places.setChecked(False)
    d.ask_links.setChecked(False)
    d.recent.setValue(2)
    d.dialogs.setCurrentIndex(d.dialogs.findData("document"))
    d.accept()
    assert window.open_path(first)
    assert abs(window.canvas.zoom() - 1.0) < 0.01  # (opened at actual size)
    window.show_page(3)
    window.remember_file_place()
    assert window._places() == {}  # (places not remembered)
    assert window.last_dir() == str(tmp_path)  # (the document's folder)
    for name in ("b.pdf", "c.pdf"):
        window.open_path(doc(tmp_path / name))
    assert [p.name for p in window.recent_files()] == ["c.pdf", "b.pdf"]
    assert len([a for a in window.m_recent.actions() if a.text().startswith("&")]) == 2
    opened = []
    monkeypatch.setattr("py_pdftools.gui.navigation.QDesktopServices.openUrl", lambda url: opened.append(url) or True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: pytest.fail("not asked: the setting says so"))
    assert window.open_address("https://example.org") and len(opened) == 1
    d = SettingsDialog(window.prefs, window)
    d._clear_recent()
    assert window.recent_files() == []


def test_language_from_settings(window, monkeypatch):
    changed = []
    monkeypatch.setattr(window, "change_language", changed.append)
    d = SettingsDialog(window.prefs, window)
    d.language.setCurrentIndex(d.language.findData("es"))
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: (self.language.setCurrentIndex(
        self.language.findData("es")), self.accept(), 1)[2])
    window.settings_dialog()
    for _ in range(5):
        QApplication.processEvents()
    assert changed == ["es"]


def test_text_sharpness(window, tmp_path):
    """Settings > Appearance > Text on the pages: the grey edges of the letters darkened, in the pages drawn
    by the processes of rendering and by the window itself; As drawn leaves them as MuPDF draws them."""
    from py_pdftools.core import rendering
    from py_pdftools.gui import reading
    from py_pdftools.gui.canvas import page_image

    d = pymupdf.open()
    d.new_page().insert_text((40, 60), "Sharp text, or soft", fontsize=11)
    d.save(tmp_path / "t.pdf")
    path = str(tmp_path / "t.pdf")
    stamp = ((tmp_path / "t.pdf").stat().st_mtime_ns, (tmp_path / "t.pdf").stat().st_size)

    def pixels(name):
        w, h, stride, data = rendering.render(path, "", stamp, 0, 1.0, sharpness=reading.SHARPNESS[name])
        return [data[r * stride: r * stride + w * 3] for r in range(h)]

    def ink(name):  # (the darkness of the text: the sum of how far each pixel is from white)
        return sum(255 - b for row in pixels(name) for b in row)

    def edges(name):  # (how steep the edges are: the sum of the differences between neighbours in a row)
        return sum(abs(row[i] - row[i + 3]) for row in pixels(name) for i in range(len(row) - 3))

    assert ink("sharper") > ink("drawn") * 1.1
    assert edges("drawn") < edges("sharper") < edges("sharpest")
    assert config.get("sharpness") == "sharper"  # (the default)
    before = reading.SHARPEN
    try:
        assert window.open_path(tmp_path / "t.pdf")
        d2 = SettingsDialog(window.prefs, window)
        d2.sharpness.setCurrentIndex(d2.sharpness.findData("sharpest"))
        d2.accept()
        assert reading.SHARPEN == reading.SHARPNESS["sharpest"] and config.get("sharpness") == "sharpest"
        darker = page_image(window.doc[0], 1.0)
        plain = page_image(window.doc[0], 1.0, sharpness=reading.SHARPNESS["drawn"])
        assert darker != plain
    finally:
        reading.SHARPEN = before


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads the open files in /proc")
def test_rendering_lets_go_of_the_file_on_windows(tmp_path, monkeypatch):
    """On Windows the processes of rendering read a document into memory, and don't keep its file open: a file
    held open there can't be replaced, so saving the document, or protecting it, would fail."""
    import os

    from py_pdftools.core import rendering

    path = tmp_path / "w.pdf"
    d = pymupdf.open()
    d.new_page().insert_text((40, 60), "Windows")
    d.save(path)
    stamp = (path.stat().st_mtime_ns, path.stat().st_size)

    def held() -> bool:
        return any(os.path.realpath(f"/proc/self/fd/{fd}") == str(path) for fd in os.listdir("/proc/self/fd"))

    monkeypatch.setattr(rendering.sys, "platform", "win32")
    rendering._docs.clear()
    try:
        rendering.render(str(path), "", stamp, 0, 1.0)
        assert not held()
    finally:
        rendering._docs.clear()


def test_the_colours_shown_as_colours(window):
    """Settings > Colours shows each colour as a patch of it, its name in the tip (its meaning is in the field
    beside it), not as its name."""
    d = SettingsDialog(window.prefs, window)
    button, edit = d.palette_rows[0]
    assert button.text() == "" and not button.icon().isNull() and button.toolTip()
    assert button.iconSize().width() > button.iconSize().height()
    button.set_color("#123456")
    assert button.text() == "" and "#123456" in button.toolTip()
