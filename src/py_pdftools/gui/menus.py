"""The menus File, Edit and View, in groups: each is built where its actions are (window.py and the mixins),
and then put in order here, with submenus, so that no menu is a long list. An action keeps its shortcut
wherever it goes. (The menus of the modes are short, and stay as they are.)"""

from __future__ import annotations

from PySide6.QtWidgets import QMenu

from ..core.interface import tr

SEP = "-"


def _all(menu: QMenu) -> set[int]:
    """The ids of the actions of MENU and of its submenus (a submenu counts by its menu action; separators
    don't count)."""
    found = set()
    for act in menu.actions():
        if act.isSeparator():
            continue
        found.add(id(act))
        if act.menu() is not None:
            found |= _all(act.menu())
    return found


def _fill(window, menu: QMenu, layout: list):
    """MENU emptied (its actions are not deleted: they belong to the window) and filled with LAYOUT: names
    of actions (a_...) or of menus (m_...) of WINDOW, SEP, and (title, layout) for a submenu."""
    before = [a for a in menu.actions() if not a.isSeparator()]
    for act in list(menu.actions()):
        menu.removeAction(act)
    for item in layout:
        if item == SEP:
            menu.addSeparator()
        elif isinstance(item, tuple):
            title, inner = item
            sub = QMenu(title, window)
            sub.setToolTipsVisible(True)
            _fill(window, sub, inner)
            menu.addMenu(sub)
        else:
            thing = getattr(window, item, None)
            if thing is None:
                continue
            if isinstance(thing, QMenu):
                menu.addMenu(thing)
            else:
                menu.addAction(thing)
    # Lo que el arreglo no nombra no se pierde: va al final (una acción nueva que aún no tiene su lugar).
    placed = _all(menu)
    # (un submenú cuyas acciones están todas en otro lugar ya está puesto)
    rest = [a for a in before if id(a) not in placed and not (a.menu() is not None and _all(a.menu()) <= placed)]
    if rest:
        menu.addSeparator()
        for act in rest:
            menu.addAction(act)


def regroup(window):
    """File, Edit and View in groups (see the module's text)."""
    window.m_export_annots.setTitle(tr("Annotations"))
    window.m_import_annots.setTitle(tr("Annotations"))
    window.m_export = QMenu(tr("Export"), window)
    window.m_export.setToolTipsVisible(True)
    _fill(window, window.m_export, ["a_export_pages", "a_export_images", "a_export_text", SEP,
                                    "m_export_annots"])
    window.m_import = QMenu(tr("Import"), window)
    window.m_import.setToolTipsVisible(True)
    _fill(window, window.m_import, ["m_import_annots"])
    _fill(window, window.m_file, [
        "a_open", "a_open_tab", "a_reopen_tab", "m_recent", (tr("New"), ["a_images", "a_combine"]), SEP,
        "a_save", "a_save_as", "m_save_copy", "m_export", "m_import", SEP,
        (tr("Security"), ["a_protect", SEP, "a_sign", "a_check_signatures", "a_make_id"]),
        "a_compare", "a_doc_props", "a_print", SEP, "a_close", "a_quit"])
    _fill(window, window.m_edit, [
        "a_undo", "a_redo", SEP, "a_copy", "a_copy_unwrapped", "a_paste", "a_duplicate", SEP,
        "a_props", "a_comment", "a_delete", SEP,
        (tr("Select"), ["a_select_all", "a_select_kind", "a_select_none"]),
        (tr("Arrange"), ["a_group", "a_ungroup", "a_lock", SEP, "m_align"]),
        (tr("Remove annotations"), ["a_clear_page", "a_clear_all"]), SEP, "m_links", "a_word_index"])
    _fill(window, window.m_view, [
        (tr("Panels"), ["a_thumbs", "a_panel", "a_outline", "a_form"]),
        (tr("Annotations"), ["a_show", "a_only_listed", SEP, "a_next_annot", "a_prev_annot"]),
        (tr("Go to"), ["a_prev", "a_next", "a_first", "a_last", SEP, "a_back", "a_forward", SEP,
                       "a_add_bookmark", "a_next_bookmark", "a_prev_bookmark"]),
        (tr("Zoom"), ["a_fit", "a_fit_width", "a_fit_height", "a_fit_visible", "a_actual", SEP,
                      "a_zoom_in", "a_zoom_out"]),
        (tr("Page layout"), ["a_continuous", "a_spread", "a_cover", "a_gaps", SEP, "a_turn_right",
                             "a_turn_left"]),
        "m_reading", SEP, "a_split", "a_detach", "a_present"])
