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
    from py_pdftools.gui.state import State

    State("window").setValue("toolbar_labels", "true")
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


def test_a_spacer_on_a_toolbar(window):
    """Customize the toolbars offers an expanding spacer (as KDE's toolbars do), kept as '<->' and back."""
    from py_pdftools.gui.toolbars import SPACER, ToolbarsDialog

    before = window.bar_ids(bar(window, "file"))
    d = ToolbarsDialog(window)
    d.bar.setCurrentIndex(d.bar.findData("file"))
    d.chosen.setCurrentRow(0)
    d.add_spacer()
    d.add_spacer()  # (as many as wished, as separators)
    layout = d.layout_chosen()
    assert layout["bars"]["file"] == [before[0], SPACER, SPACER, *before[1:]]
    window.apply_toolbar_layout(layout)
    assert window.bar_ids(bar(window, "file")) == layout["bars"]["file"]
    other = MainWindow()  # (kept: a new window has them too)
    try:
        assert other.bar_ids(bar(other, "file")) == layout["bars"]["file"]
    finally:
        other.close()


def test_the_rows_of_toolbars_are_packed(window):
    """A toolbar dragged along its row leaves no empty space: once it is let go, the toolbars of the row go
    side by side again, in their order (Qt keeps the place where it was let go, and stretches the one before
    it up to there); their handle is wide enough to take hold of."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStyle

    from py_pdftools.gui.toolbars import HANDLE

    window.resize(1400, 800)
    window.show()
    QApplication.processEvents()
    find = bar(window, "find")
    assert find.style().pixelMetric(QStyle.PixelMetric.PM_ToolBarHandleExtent, None, find) >= HANDLE
    row = sorted((b for b in window.toolbars() if b.isVisible() and b.geometry().y() == find.geometry().y()),
                 key=lambda b: b.x())
    order = [b.objectName() for b in row]
    press = QPoint(4, find.height() // 2)
    QTest.mousePress(find, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, press)
    for dx in range(0, 201, 20):
        QTest.mouseMove(find, press + QPoint(dx, 0))
        QApplication.processEvents()
    QTest.mouseRelease(find, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, press + QPoint(200, 0))
    for _ in range(5):
        QApplication.processEvents()
    row = sorted((b for b in window.toolbars() if b.isVisible() and b.geometry().y() == find.geometry().y()),
                 key=lambda b: b.x())
    assert [b.objectName() for b in row] == order
    assert not window._gaps(row, True)


def top_rows(w):
    """The names of the toolbars shown at the top, row by row, from left to right."""
    from PySide6.QtCore import Qt

    rows = {}
    for b in w.toolbars():
        if b.isVisible() and w.toolBarArea(b) == Qt.ToolBarArea.TopToolBarArea:
            rows.setdefault(b.geometry().y(), []).append((b.geometry().x(), b.objectName()))
    return [[n for _, n in sorted(r)] for _, r in sorted(rows.items())]


NEW = ["modes", "file", "edit", "mousetools", "navigation", "pagenav", "zoom", "pagezoom", "find", "tools"]


def test_the_order_of_the_toolbars(window, app):
    """By kinds of work: the file, editing, what the mouse does, moving, zooming, finding, and the tools
    that work on the whole document (Word index there, not beside Find)."""
    w = window
    w.resize(1900, 900)
    w.show()
    w.set_mode("annotate")
    app.processEvents()
    assert top_rows(w)[0] == NEW
    assert w.bar_ids(bar(w, "find")) == ["a_find", "a_find_bar"]
    assert w.bar_ids(bar(w, "tools")) == ["a_sorter", "a_word_index"]
    assert w.bar_ids(bar(w, "navigation")) == ["a_back", "a_forward"]
    assert w.bar_ids(bar(w, "mousetools")) == ["tool:selecttext", "tool:hand", "tool:zoomarea", "tool:magnifier"]


def test_an_old_arrangement_in_the_new_order(app, tmp_path, monkeypatch):
    """An arrangement kept by an older version, its toolbars in another order and a panel on the right, comes
    in the new order once, the panel where it was."""
    from PySide6.QtCore import Qt

    monkeypatch.setenv("HOME", str(tmp_path))
    old = MainWindow()
    try:
        old.resize(1900, 900)
        old.show()
        old.set_mode("annotate")
        top = Qt.ToolBarArea.TopToolBarArea
        # (the order of before: Find after Edit, Tools nowhere yet)
        old.insertToolBar(bar(old, "mousetools"), bar(old, "find"))
        old.removeToolBar(bar(old, "tools"))
        old.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, old.attach_dock)
        old.attach_dock.show()
        app.processEvents()
        assert top_rows(old)[0][:5] == ["modes", "file", "edit", "find", "mousetools"]
        old.keep_arrangement()
        old.save_settings()
        old.settings.setValue("toolbar_order", 1)
        old.settings.sync()
    finally:
        old.close()
    new = MainWindow()
    try:
        new.resize(1900, 900)
        new.show()
        new.set_mode("annotate")
        app.processEvents()
        assert top_rows(new)[0] == NEW and new.settings.value("toolbar_order", type=int) == 2
        assert new.attach_dock.isVisible() and new.dockWidgetArea(new.attach_dock) == Qt.DockWidgetArea.RightDockWidgetArea
        assert top in (new.toolBarArea(bar(new, "tools")),)
    finally:
        new.close()


def test_reset_the_toolbars(window, app, monkeypatch):
    """Settings > Toolbars > Reset the toolbars: buttons, places and looks as at first, in every mode's
    arrangement; the panels stay; it asks first."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    w = window
    w.resize(1900, 900)
    w.show()
    w.set_mode("annotate")
    # Everything changed: a toolbar of one's own, a button taken off, Find on the left, Zoom hidden, big icons
    d = ToolbarsDialog(w)
    d.new_bar("Mine")
    d.add(["a_save"])
    d.bar.setCurrentIndex(d.bar.findData("edit"))
    d.chosen.setCurrentRow(0)
    d.remove()
    w.apply_toolbar_layout(d.layout_chosen())
    w.addToolBar(Qt.ToolBarArea.LeftToolBarArea, bar(w, "find"))
    bar(w, "zoom").hide()
    w.set_bar_look(None, size=32)
    w.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, w.attach_dock)
    w.attach_dock.show()
    w.keep_arrangement()
    w.set_mode("redact")
    w.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bar(w, "file"))
    w.keep_arrangement()
    # Asked, and No: nothing changes
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    assert not w.reset_toolbars()
    assert w.toolBarArea(bar(w, "file")) == Qt.ToolBarArea.BottomToolBarArea
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert w.reset_toolbars()
    app.processEvents()
    assert top_rows(w)[0] == NEW and w.toolbar_layout() == {"bars": {}, "custom": []}
    assert w.bar_ids(bar(w, "edit")) == ["a_undo", "a_redo", "a_delete"] and w.looks()["size"] == 16
    assert top_rows(w)[1] == ["redaction", "redacted-copy"]  # (the bars of the mode on, below)
    # The other mode's arrangement too; the panel where it was
    w.set_mode("annotate")
    app.processEvents()
    assert top_rows(w)[0] == NEW and bar(w, "zoom").isVisible()
    assert w.attach_dock.isVisible() and w.dockWidgetArea(w.attach_dock) == Qt.DockWidgetArea.RightDockWidgetArea
