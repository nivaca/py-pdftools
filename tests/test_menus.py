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


def test_the_menu_tools(window):
    """Tools, in every mode, between View and Settings: what works on the document as a whole or on several,
    each action in one menu only; the mode Annotate's own menu is called Annotate."""
    bar = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert "Annotate" in bar and bar.index("Tools") == bar.index("View") + 1 == bar.index("Settings") - 1
    tools = reachable(window.m_utils)
    for name in ("a_sorter", "a_word_index", "a_steps", "a_compare", "a_visual_compare"):
        assert id(getattr(window, name)) in tools, name
    elsewhere = set()
    for menu in (window.m_file, window.m_edit, window.m_view, window.m_find):
        elsewhere |= reachable(menu)
    assert not (tools & elsewhere)
    for mode in window.modes:
        window.set_mode(mode)
        assert window.m_utils.menuAction().isVisible(), mode


def test_the_menu_find(window):
    """Find, in every mode, right after Edit: every search, each in that menu only (they were in the menu of
    the mode Annotate, which the other modes don't show, in Tools and in Edit)."""
    bar = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert bar.index("Find") == bar.index("Edit") + 1
    found = reachable(window.m_find)
    names = ("a_find", "a_find_next", "a_find_previous", "a_find_bar", "a_find_all")
    for name in names:
        assert id(getattr(window, name)) in found, name
    for menu in (window.m_file, window.m_edit, window.m_view, window.m_utils, window.m_tools):
        assert not (reachable(menu) & found), menu.title()
    for mode in window.modes:
        window.set_mode(mode)
        assert window.m_find.menuAction().isVisible(), mode
    assert window.a_find.shortcut().toString() == "Ctrl+Shift+F" and window.a_find_bar.shortcut().toString() == "Ctrl+F"


def test_shortcuts_kept(window):
    """Every action with a shortcut that was in File, Edit or View is still in a menu of the bar (where Qt
    finds its shortcut), with its keys."""
    inside = set()
    for menu in (window.m_file, window.m_edit, window.m_view):
        inside |= reachable(menu)
    assert window.a_thumbs.shortcut().toString() == "F7" and id(window.a_thumbs) in inside
    for name in ("a_open", "a_save", "a_print", "a_undo", "a_props", "a_select_none", "a_fit", "a_first",
                 "a_spread", "a_present", "a_turn_left"):
        act = getattr(window, name)
        assert id(act) in inside and not act.shortcut().isEmpty(), name


def test_the_command_palette(window, monkeypatch):
    """Ayuda > Buscar una orden (Ctrl+Shift+P, o Ctrl+Alt+I): las acciones de los menús por cualquier palabra de
    su camino, sin acentos ni mayúsculas; la elegida se ejecuta, después de cerrarse la paleta."""
    from py_pdftools.gui import palette

    assert [k.toString() for k in window.a_palette.shortcuts()] == ["Ctrl+Shift+P", "Ctrl+Alt+I"]
    found = palette.commands(window)
    paths = [p for p, _ in found]
    assert "View › Panels › Page thumbnails" in paths
    assert not any(p.endswith("Fit width") for p in paths)  # (no document: it can't be used, so it isn't there)
    assert all(a.isEnabled() for _, a in found) and len({id(a) for _, a in found}) == len(found)
    hits = palette.matching(found, "THUMBNAILS page")
    assert hits and hits[0][1] is window.a_thumbs
    assert palette.matching(found, "zzzz qqq") == []
    assert palette._plain("&Vista Rápida") == "vista rapida"
    before = window.a_thumbs.isChecked()

    def choose(self):
        self.box.setText("page thumb")
        assert "☑" in self.list.currentItem().text() or "☐" in self.list.currentItem().text()
        self.run(self.list.currentItem())
        return 1

    monkeypatch.setattr(palette.Palette, "exec", choose)
    assert window.command_palette() is window.a_thumbs and window.a_thumbs.isChecked() != before


def test_the_menu_annotate_in_submenus(window):
    w = window
    titles = [a.text() for a in w.m_tools.actions() if a.menu() is not None]
    assert titles == ["Selection", "Text markup", "Notes and text", "Shapes", "Drawing"]
    notes = w.m_tool_groups["notes"]
    assert w.tool_actions["link"] in notes.actions() and w.tool_actions["stamp"] in notes.actions()
    assert w.tool_actions["rect"] in w.m_tool_groups["shapes"].actions()
    # Every tool of the mode Annotate in one submenu (Mark for redaction is the mode Redact's), its key as before
    from py_pdftools.gui.window import TOOLS

    placed = [a for sub in w.m_tool_groups.values() for a in sub.actions()]
    annotate = [w.tool_actions[t] for group in TOOLS for t, _, _ in group] + [w.tool_actions["link"]]
    assert set(annotate) == set(placed) and len(placed) == len(set(placed))
    assert w.tool_actions["rect"].shortcut().toString() == "R" and w.tool_actions["highlight"].shortcut().toString() == "H"
