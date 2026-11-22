"""Toolbars made to measure (gui/toolbars.py): buttons added, removed and moved on a toolbar, separators, a
toolbar of one's own, kept for the next window, and each toolbar back to what it had at first; and every
button of the toolbars has an icon, those of the modes too."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidgetAction

from py_pdftools.gui.toolbars import SEPARATOR, ToolbarsDialog
from py_pdftools.gui.window import MainWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))  # (QSettings)
    w = MainWindow()
    yield w
    w.close()


def bar(w, name):
    return next(b for b in w.toolbars() if b.objectName() == name)


def test_every_button_has_an_icon(window):
    for b in window.toolbars():
        for act in b.actions():
            # (the box of the page, a widget, is no button)
            assert act.isSeparator() or isinstance(act, QWidgetAction) or not act.icon().isNull(), (
                b.objectName(), act.text())
    assert window.modes_bar.toolButtonStyle().name == "ToolButtonIconOnly"  # (de entrada, como las demás)


def test_the_dialog_changes_a_toolbar(window):
    d = ToolbarsDialog(window)
    d.bar.setCurrentIndex(d.bar.findData("file"))
    assert d.contents["file"] == ["a_open", "a_save"]  # (Print: in the menu File, not on the bar)
    d.chosen.setCurrentRow(1)
    d.add(["a_print"])
    d.remove()  # (Print, added and taken away)
    d.chosen.setCurrentRow(0)
    d.add(["a_find"])  # (after Open)
    d.add_separator()
    d.chosen.setCurrentRow(0)
    d.move(1)
    assert d.contents["file"] == ["a_find", "a_open", SEPARATOR, "a_save"]
    assert "a_print" in [d.available.item(r).data(256) for r in range(d.available.count())]
    window.apply_toolbar_layout(d.layout_chosen())
    assert window.bar_ids(bar(window, "file")) == ["a_find", "a_open", SEPARATOR, "a_save"]
    # (una herramienta de anotar puesta en otra barra conserva su menú)
    d = ToolbarsDialog(window)
    d.bar.setCurrentIndex(d.bar.findData("zoom"))
    d.add(["tool:rect"])
    window.apply_toolbar_layout(d.layout_chosen())
    button = bar(window, "zoom").widgetForAction(window.tool_actions["rect"])
    assert button.contextMenuPolicy().name == "CustomContextMenu"


def test_kept_for_the_next_window_and_reset(window, app):
    d = ToolbarsDialog(window)
    d.new_bar("Mine")
    assert d.current() == "custom-1" and d.b_delete.isEnabled()
    d.add(["a_save", "a_print"])
    d.bar.setCurrentIndex(d.bar.findData("edit"))
    d.chosen.setCurrentRow(0)
    d.remove()
    window.ask_toolbars = lambda: d.layout_chosen()
    assert window.customize_toolbars()
    mine = bar(window, "custom-1")
    assert mine.windowTitle() == "Mine" and window.bar_ids(mine) == ["a_save", "a_print"]
    window.settings.sync()

    other = MainWindow()  # (sus barras como quedaron)
    try:
        assert other.bar_ids(bar(other, "custom-1")) == ["a_save", "a_print"]
        assert other.bar_ids(bar(other, "edit")) == ["a_redo", "a_delete"]
        d = ToolbarsDialog(other)
        d.bar.setCurrentIndex(d.bar.findData("edit"))
        d.reset()
        d.bar.setCurrentIndex(d.bar.findData("custom-1"))
        d.delete_bar()
        other.apply_toolbar_layout(d.layout_chosen())
        assert other.bar_ids(bar(other, "edit")) == ["a_undo", "a_redo", "a_delete"]
        assert "custom-1" not in [b.objectName() for b in other.toolbars()]
        assert other.toolbar_layout() == {"bars": {}, "custom": []}
    finally:
        other.close()


def test_the_bar_of_the_modes_is_not_offered(window):
    d = ToolbarsDialog(window)
    assert "modes" not in d.contents
    assert any(d.bar.itemText(i).endswith("(Annotate)") for i in range(d.bar.count()))


def test_text_position_icon_size_and_lock(window, app):
    """As in KDE: the text position and the size of the icons of all the toolbars, or of one (its own then
    wins); the toolbars locked; kept for the next window; and the setting of old (labels under the icons)."""
    file_bar, zoom = bar(window, "file"), bar(window, "zoom")
    assert file_bar.toolButtonStyle().name == "ToolButtonIconOnly" and file_bar.iconSize().width() == 16
    assert window.modes_bar.toolButtonStyle().name == "ToolButtonIconOnly" and window.modes_bar.iconSize().width() == 16
    window.set_bar_look(None, style="beside", size=32)
    assert file_bar.toolButtonStyle().name == "ToolButtonTextBesideIcon" and zoom.iconSize().width() == 32
    assert window.modes_bar.iconSize().width() == 32  # (all, the bar of the modes too)
    window.set_bar_look(zoom, style="text")
    assert zoom.toolButtonStyle().name == "ToolButtonTextOnly" and file_bar.toolButtonStyle().name != "ToolButtonTextOnly"
    window.set_bars_locked(True)
    assert not file_bar.isMovable()
    window.settings.sync()
    other = MainWindow()
    try:
        assert bar(other, "zoom").toolButtonStyle().name == "ToolButtonTextOnly"
        assert bar(other, "file").iconSize().width() == 32 and not bar(other, "file").isMovable()
    finally:
        other.close()
    # the menus that set them: Settings > Toolbars (all), and the right click on a toolbar (that one)
    from PySide6.QtWidgets import QMenu

    menu = QMenu()
    window.looks_menu(menu, file_bar)
    titles = [a.text() for a in menu.actions()]
    assert titles[:3] == ["Text position", "Icon size", "Lock the toolbars"]
    under = next(a for a in menu.actions()[0].menu().actions() if a.text() == "Text under icons")
    under.trigger()
    assert file_bar.toolButtonStyle().name == "ToolButtonTextUnderIcon"
    assert zoom.toolButtonStyle().name == "ToolButtonTextOnly"
    window.show_labels(False)  # (all, icons only: the own styles go)
    assert zoom.toolButtonStyle().name == "ToolButtonIconOnly"


def test_old_setting_read(app, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from PySide6.QtCore import QSettings

    QSettings("py-pdftools", "py-pdftools").setValue("toolbar_labels", "true")
    w = MainWindow()
    try:
        assert bar(w, "file").toolButtonStyle().name == "ToolButtonTextUnderIcon"
    finally:
        w.close()


def test_looks_in_the_dialog(window):
    d = ToolbarsDialog(window)
    d.bar.setCurrentIndex(d.bar.findData("find"))
    assert d.style.currentData() is None and d.size.currentData() is None
    d.style.setCurrentIndex(d.style.findData("under"))
    d._set_look("style", "under")
    d._set_look("size", 48)
    window.ask_toolbars = lambda: d.layout_chosen()
    assert window.customize_toolbars()
    assert bar(window, "find").toolButtonStyle().name == "ToolButtonTextUnderIcon"
    assert bar(window, "find").iconSize().width() == 48


def test_right_click_sets_all_the_toolbars(window, app):
    """The right click on a toolbar sets how all of them look, not that one only."""
    menu = window.createPopupMenu()
    titles = [a.text() for a in menu.actions()]
    assert "Text position" in titles and "Icon size" in titles
    position = next(a for a in menu.actions() if a.text() == "Text position").menu()
    next(a for a in position.actions() if a.text() == "Text only").trigger()
    for name in ("file", "zoom", "find", "navigation"):
        assert bar(window, name).toolButtonStyle().name == "ToolButtonTextOnly", name
    assert window.modes_bar.toolButtonStyle().name == "ToolButtonTextOnly"


def test_a_change_reaches_every_window(app, tmp_path, monkeypatch):
    """The look of the toolbars (a right click on them), their lock and their buttons (Customize the toolbars)
    change in every window open, not only in the one where they were changed: the others would show them as
    they were, until the program started again."""
    from py_pdftools.gui.window import _WINDOWS

    monkeypatch.setenv("HOME", str(tmp_path))
    one, two = MainWindow(), MainWindow()
    _WINDOWS.extend([one, two])
    try:
        menu = one.createPopupMenu()
        sub = next(a.menu() for a in menu.actions() if a.menu() and a.text() == "Text position")
        next(a for a in sub.actions() if a.text() == "Text alongside icons").trigger()
        assert bar(two, "file").toolButtonStyle().name == "ToolButtonTextBesideIcon"
        one.set_bars_locked(True)
        assert not bar(two, "file").isMovable()
        one.ask_toolbars = lambda: {"bars": {"file": ["a_open", "a_save"]}, "custom": []}
        one.customize_toolbars()
        assert two.bar_ids(bar(two, "file")) == ["a_open", "a_save"]
    finally:
        for w in (one, two):
            _WINDOWS.remove(w)
            w.close()
