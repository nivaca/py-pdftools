"""The menus in groups (gui/menus.py): File, Edit and View have submenus, no action of them is lost, and the
shortcuts of the actions in submenus still work."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui.window import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.show()
    yield w
    w.close()


def reachable(menu) -> set[int]:
    found = set()
    for act in menu.actions():
        found.add(id(act))
        if act.menu() is not None:
            found |= reachable(act.menu())
    return found


def test_grouped_and_nothing_lost(window):
    for menu, most in ((window.m_file, 16), (window.m_edit, 16), (window.m_view, 12)):
        assert len([a for a in menu.actions() if not a.isSeparator()]) <= most
    inside = set()
    for menu in (window.m_file, window.m_edit, window.m_view):
        inside |= reachable(menu)
    for name in ("a_open", "a_images", "a_combine", "a_flat", "a_export_md", "a_import_json", "a_protect",
                 "a_sign", "a_make_id", "a_close", "a_quit", "a_group", "a_select_none", "a_clear_all",
                 "a_links_from_text", "a_thumbs", "a_form", "a_last", "a_fit_visible", "a_gaps", "a_present"):
        assert id(getattr(window, name)) in inside, name
    titles = [a.text() for a in window.m_view.actions() if a.menu() is not None]
    assert titles[:5] == ["Panels", "Annotations", "Go to", "Zoom", "Page layout"]


def test_shortcuts_kept(window):
    """Every action with a shortcut that was in File, Edit or View is still in a menu of the bar (where Qt
    finds its shortcut), with its keys."""
    inside = set()
    for menu in (window.m_file, window.m_edit, window.m_view):
        inside |= reachable(menu)
    assert window.a_thumbs.shortcut().toString() == "F3" and id(window.a_thumbs) in inside
    for name in ("a_open", "a_save", "a_print", "a_undo", "a_props", "a_select_none", "a_fit", "a_first",
                 "a_spread", "a_present", "a_turn_left"):
        act = getattr(window, name)
        assert id(act) in inside and not act.shortcut().isEmpty(), name
