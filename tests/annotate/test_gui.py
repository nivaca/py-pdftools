"""The window, driven as the user would: annotations made, moved and resized with the mouse, and saved."""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate import annots, settings
from py_pdftools.gui.window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, sample, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))  # (QSettings)
    w = MainWindow()

    def warn(title, text):  # (a message box would wait for a click for ever)
        raise AssertionError(f"warning shown: {title}: {text}")

    w.warn = warn
    w.typed = "Typed text"  # (what is "written on the page" for a new text box, note...: None gives up)

    def edit_text(annotation, index=-1):
        if w.typed is not None:
            w.canvas.text_done.emit(index, dataclasses.replace(annotation, contents=w.typed))

    w.canvas.edit_text = edit_text

    def ask_recover(when):  # (likewise)
        raise AssertionError("recovery offered")

    w.ask_recover = ask_recover
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    assert w.open_path(sample)
    app.processEvents()
    yield w
    w.annotations = w.saved = []
    w.close()


def mouse(w, kind, point, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier, page=None):
    """A mouse event at POINT (in points) of PAGE (the page in view, if None)."""
    c = w.canvas
    item = c.pages[w.page if page is None else page]
    pos = c.mapFromScene(item.mapToScene(QPointF(*point)))
    handler = {QEvent.Type.MouseButtonPress: c.mousePressEvent, QEvent.Type.MouseMove: c.mouseMoveEvent,
               QEvent.Type.MouseButtonRelease: c.mouseReleaseEvent,
               QEvent.Type.MouseButtonDblClick: c.mouseDoubleClickEvent}[kind]
    buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else button
    handler(QMouseEvent(kind, QPointF(pos), QPointF(c.viewport().mapToGlobal(pos)), buttons, button, mods))


def drag(w, *points, mods=Qt.KeyboardModifier.NoModifier, page=None):
    """Drag with the mouse on the page (PAGE, or the one in view), through POINTS (in points)."""
    mouse(w, QEvent.Type.MouseButtonPress, points[0], mods=mods, page=page)
    for p in points[1:]:
        mouse(w, QEvent.Type.MouseMove, p, mods=mods, page=page)
    mouse(w, QEvent.Type.MouseButtonRelease, points[-1], mods=mods, page=page)
    QApplication.processEvents()


def click(w, point):
    drag(w, point)


def close(a, b, tolerance=2.0):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


def test_highlight_text(window):
    window.set_tool("highlight")
    drag(window, (75, 95), (200, 125))  # (from the first line to the second)
    assert len(window.annotations) == 1
    a = window.annotations[0]
    assert a.kind == "highlight" and len(a.quads) == 2 and a.color == settings.STYLES["highlight"].color
    assert "First line" in window.marked_text(a)
    window.set_tool("underline")
    mouse(window, QEvent.Type.MouseButtonDblClick, (80, 125))  # (a word: "A")
    assert window.annotations[-1].kind == "underline" and len(window.annotations[-1].quads) == 1


def test_draw_move_resize(window):
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    assert len(window.annotations) == 1 and window.selected == [0]
    assert close(window.annotations[0].rect, (100, 300, 250, 400))
    drag(window, (150, 350), (170, 360))  # (inside: moves it)
    assert close(window.annotations[0].rect, (120, 310, 270, 410))
    drag(window, (270, 410), (300, 450))  # (its corner: resizes it)
    assert close(window.annotations[0].rect, (120, 310, 300, 450))
    window.undo()
    window.undo()
    assert close(window.annotations[0].rect, (100, 300, 250, 400))
    window.redo()
    assert close(window.annotations[0].rect, (120, 310, 270, 410))


def test_lines_and_drawings(window):
    window.set_tool("arrow")
    drag(window, (100, 500), (300, 500))
    arrow = window.annotations[0]
    assert arrow.kind == "arrow" and close(arrow.paths[0][0] + arrow.paths[0][1], (100, 500, 300, 500))
    drag(window, (300, 500), (300, 600))  # (its end: moves only that end)
    assert close(window.annotations[0].paths[0][1], (300, 600))
    window.set_tool("ink")
    drag(window, (100, 650), (120, 670), (150, 660), (180, 690))
    ink = window.annotations[1]
    assert ink.kind == "ink" and len(ink.paths[0]) == 4
    window.set_tool("rect")
    drag(window, (400, 700), (401, 701))  # (a click: draws nothing)
    assert len(window.annotations) == 2


def test_note_and_text_box(window):
    window.set_tool("note")
    click(window, (400, 200))
    note = window.annotations[0]
    assert note.kind == "note" and note.contents == "Typed text"
    assert close(note.rect, (400, 200, 400 + annots.NOTE_SIZE, 200 + annots.NOTE_SIZE))
    window.set_tool("freetext")
    click(window, (300, 300))  # (a click: a box of the usual size)
    box = window.annotations[1]
    assert box.kind == "freetext" and box.contents == "Typed text"
    assert close(box.rect[:2], (300, 300))
    window.typed = None  # (given up: nothing is made)
    click(window, (100, 700))
    assert len(window.annotations) == 2


def test_a_box_dragged_shows_a_frame_of_dashes(window):
    """While a box is dragged (a text box, which may have no border, and the other tools that drag a box), a
    frame of dashes shows where it goes, as the one that selects; it is gone on release."""
    from PySide6.QtGui import QImage, QPainter

    from py_pdftools.gui.canvas import SELECTED

    for tool, y in (("freetext", 100), ("typewriter", 300), ("rect", 500)):
        window.set_tool(tool)
        mouse(window, QEvent.Type.MouseButtonPress, (100, y))
        mouse(window, QEvent.Type.MouseMove, (250, y + 80))
        item = window.canvas._drag["item"]
        assert item.outlined
        # (painted alone, the frame's colour is on its edges)
        image = QImage(400, 300, QImage.Format.Format_ARGB32)
        image.fill(0)
        p = QPainter(image)
        p.translate(-50, 50 - y)  # (the page's point (100, Y) at (50, 50))
        item.paint(p, None)
        p.end()
        top = [x for x in range(400) for y in range(48, 52)
               if image.pixelColor(x, y).rgb() == SELECTED.rgb()]  # (its top edge)
        assert len(top) > 50 and 45 <= min(top) and max(top) <= 205, tool
        mouse(window, QEvent.Type.MouseButtonRelease, (250, y + 80))
        assert item.scene() is None


def test_a_note_shows_where_it_goes(window):
    """While the mouse is pressed with Note, a frame of dashes shows where its icon goes, as large as it is seen;
    it doesn't follow a drag (the note goes where the mouse was pressed; a drag gives its pop-up, see below), and
    the note takes its place."""
    from PySide6.QtWidgets import QGraphicsRectItem

    from py_pdftools.annotate.annots import NOTE_SIZE

    window.set_tool("note")
    pixel = 1.2 / window.canvas.transform().m11()  # (a click falls on a whole pixel: so far, in points, at most)
    mouse(window, QEvent.Type.MouseButtonPress, (100, 120))
    frame = window.canvas._drag["item"]
    assert isinstance(frame, QGraphicsRectItem) and frame.scene() is not None
    side = NOTE_SIZE / window.canvas.transform().m11()
    assert close((frame.rect().x(), frame.rect().y(), frame.rect().width()), (100, 120, side), pixel)
    mouse(window, QEvent.Type.MouseMove, (180, 200))
    assert close((frame.rect().x(), frame.rect().y()), (100, 120), pixel)
    mouse(window, QEvent.Type.MouseButtonRelease, (180, 200))
    assert frame.scene() is None
    assert window.annotations[-1].kind == "note" and close(window.annotations[-1].rect[:2], (100, 120), pixel)


def test_a_note_dragged_has_its_popup_there(window):
    """Dragging with Note: a frame of dashes follows the mouse, the size of the note's pop-up window (where readers
    show its text); the note goes where the mouse was pressed, with that pop-up. A click: no pop-up of its own."""
    window.set_tool("note")
    pixel = 1.2 / window.canvas.transform().m11()  # (a click falls on a whole pixel: so far, in points, at most)
    mouse(window, QEvent.Type.MouseButtonPress, (100, 120))
    mouse(window, QEvent.Type.MouseMove, (300, 260))
    box = window.canvas._drag["box"]
    assert box.scene() is not None and close((box.rect().left(), box.rect().top(), box.rect().right(),
                                              box.rect().bottom()), (100, 120, 300, 260), pixel)
    mouse(window, QEvent.Type.MouseButtonRelease, (300, 260))
    assert box.scene() is None
    note = window.annotations[-1]
    assert note.kind == "note" and close(note.rect[:2], (100, 120), pixel)
    assert note.popup is not None and close(note.popup, (100, 120, 300, 260), pixel)
    click(window, (400, 500))
    assert window.annotations[-1].kind == "note" and window.annotations[-1].popup is None


def test_a_tool_buttons_tip_has_its_name(window):
    """The tooltip of a tool's button on its toolbar: its name, its key and what it does, also after the tool is
    chosen (Qt then gave the button the action's tooltip again: only what it does)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QToolButton, QToolTip

    window.show()
    act = window.tool_actions["note"]
    window.set_tool("note")
    window.set_tool("select")
    button = next(b for b in window.findChildren(QToolButton) if b.defaultAction() is act)
    QApplication.sendEvent(button, QHelpEvent(QEvent.Type.ToolTip, QPoint(2, 2), button.mapToGlobal(QPoint(2, 2))))
    tip = QToolTip.text()
    QToolTip.hideText()
    assert "<b>Note</b>" in tip and act.shortcut().toString() in tip and "Click on the page to add a note" in tip


def test_comment_in_the_panel(window):
    window.set_tool("ellipse")
    drag(window, (100, 300), (250, 400))
    window.comment.setPlainText("Look at this")
    window.keep_comment()
    assert window.annotations[0].contents == "Look at this"
    window.undo()
    assert window.annotations[0].contents == ""


def test_new_colour_is_kept(window):
    window.set_tool("highlight")
    window.set_color("#43a047")
    assert settings.load().style("highlight").color == "#43a047"
    drag(window, (75, 95), (200, 100))
    assert window.annotations[0].color == "#43a047"
    window.set_color("#e53935")  # (selected: only it changes)
    assert window.annotations[0].color == "#e53935" and settings.load().style("highlight").color == "#43a047"


def test_save_and_open_again(window, sample):
    window.set_tool("highlight")
    drag(window, (75, 95), (200, 100))
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    window.show_page(2)  # (the turned page)
    window.set_tool("note")
    click(window, (100, 100))
    assert window.is_modified() and window.save()
    assert not window.is_modified() and len(window.undo_stack) == 3  # (what was done can still be undone)
    kinds = [a.kind for a in annots.read(annots.open_pdf(sample))]
    assert sorted(kinds) == ["highlight", "note", "rect"]
    # the window shows the annotations of the file now, and can delete one of them
    assert all(a.xref for a in window.annotations)
    window.show_page(0)
    rect = next(a for a in window.annotations if a.kind == "rect")
    window.pick([window.annotations.index(rect)], False)
    window.delete_selected()
    before = sample.read_bytes()
    assert window.save()
    assert sample.read_bytes().startswith(before)  # (saved incrementally: added at the end)
    assert sorted(a.kind for a in annots.read(annots.open_pdf(sample))) == ["highlight", "note"]
    # undone after saving, and saved again: the rectangle is back
    window.undo()
    assert sorted(a.kind for a in window.annotations) == ["highlight", "note", "rect"]
    assert window.save()
    assert sorted(a.kind for a in annots.read(annots.open_pdf(sample))) == ["highlight", "note", "rect"]
    window.undo()  # (and the note, made before the first save, goes)
    assert window.save()
    assert sorted(a.kind for a in annots.read(annots.open_pdf(sample))) == ["highlight", "rect"]


def test_save_as(window, tmp_path, sample):
    window.set_tool("line")
    drag(window, (100, 300), (250, 400))
    target = tmp_path / "copy.pdf"
    assert window.save_to(target)
    assert window.path == target
    assert [a.kind for a in annots.read(annots.open_pdf(target))] == ["line"]
    assert annots.read(annots.open_pdf(sample)) == []


def test_pages_rendered_elsewhere(app, sample, tmp_path, monkeypatch):
    """With the pages rendered in other processes, a document with annotations is rendered from the
    file itself, without the annotations the window draws (and the file is left as it was)."""
    import time

    from py_pdftools.gui import renderer

    monkeypatch.setattr(renderer, "ENABLED", True)
    monkeypatch.setenv("HOME", str(tmp_path))
    annots.write(sample, [annots.Annotation("rect", 0, (10, 10, 200, 200), "#000000", fill="#000000")], sample)
    before = sample.read_bytes()
    w = MainWindow()
    assert w.open_path(sample)
    assert w.canvas.source[0] == str(sample.resolve()) and w.canvas.source[3] is True
    got = []
    renderer.renderer().request("view", w.canvas.source, 0, 1.0, got.append, first=True)
    deadline = time.time() + 60
    while not got and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    image = got[0]
    assert image is not None and image.pixelColor(100, 100).lightness() > 200  # (white: the box isn't there)
    assert sample.read_bytes() == before
    w.close()


def test_language(window, sample):
    window.change_language("es")
    from py_pdftools.gui.window import _WINDOWS

    new = _WINDOWS[-1]
    assert new.menuBar().actions()[0].text() == "&Archivo" and new.path == sample
    new.change_language("en")
    _WINDOWS[-1].close()


def test_new_tools(window):
    window.set_tool("area")
    drag(window, (100, 300), (200, 360))
    window.set_tool("cloud")
    drag(window, (300, 300), (400, 360))
    window.set_tool("callout")
    drag(window, (100, 500), (250, 420))  # (from the place pointed at, to where the box goes)
    window.set_tool("caret")
    click(window, (150, 600))
    window.set_tool("stamp")
    click(window, (300, 700))
    kinds = [a.kind for a in window.annotations]
    assert kinds == ["area", "cloud", "callout", "caret", "stamp"]
    area, cloud, callout, caret, stamp = window.annotations
    assert area.opacity == settings.STYLES["area"].opacity and len(cloud.paths[0]) == 4
    assert close(callout.paths[0][0], (100, 500)) and callout.contents == "Typed text"
    assert stamp.stamp == "Approved" and stamp.image and close(((stamp.rect[0] + stamp.rect[2]) / 2,), (300,))
    assert window.save()
    assert [a.kind for a in annots.read(annots.open_pdf(window.path))] == kinds


def test_polygon_by_clicks(window):
    window.set_tool("polygon")
    for p in ((100, 300), (200, 300), (150, 380)):
        click(window, p)
    window.canvas.finish_polygon()
    assert window.annotations[0].kind == "polygon" and len(window.annotations[0].paths[0]) == 3
    window.set_tool("select")
    drag(window, (100, 300), (90, 290))  # (a point of the polygon, selected: moves only that point)
    assert close(window.annotations[0].paths[0][0], (90, 290)) and close(window.annotations[0].paths[0][1], (200, 300))


def test_eraser(window):
    window.set_tool("ink")
    drag(window, (100, 650), (150, 650), (200, 650), (250, 650), (300, 650))
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    window.set_tool("eraser")
    drag(window, (200, 640), (200, 660))  # (across the middle of the stroke: it is cut in two)
    ink = window.annotations[0]
    assert ink.kind == "ink" and len(ink.paths) == 2
    drag(window, (100, 350), (110, 350))  # (on the rectangle: it goes)
    assert [a.kind for a in window.annotations] == ["ink"]
    window.undo()
    assert len(window.annotations) == 2


def test_select_by_frame_copy_paste_align(window):
    window.set_tool("rect")
    drag(window, (100, 300), (150, 340))
    drag(window, (200, 320), (260, 380))
    window.set_tool("select")
    drag(window, (80, 280), (300, 400))  # (a frame around both)
    assert sorted(window.selected) == [0, 1]
    window.align("top")
    assert window.annotations[0].rect[1] == window.annotations[1].rect[1]
    window.copy_selected()
    window.show_page(1)
    window.paste()
    assert [a.page for a in window.annotations] == [0, 0, 1, 1]
    assert window.annotations[2].rect == window.annotations[0].rect  # (another page: in the same place)
    window.duplicate()
    assert len(window.annotations) == 6 and close(window.annotations[4].rect[:2],
                                                  [v + 10 for v in window.annotations[2].rect[:2]])


def test_lock(window):
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    window.toggle_lock()
    assert window.annotations[0].locked
    window.set_tool("select")
    drag(window, (150, 350), (170, 360))  # (locked: it stays)
    assert close(window.annotations[0].rect, (100, 300, 250, 400))
    window.delete_selected()
    assert len(window.annotations) == 1


def test_filters_and_navigation(window):
    window.set_tool("highlight")
    drag(window, (75, 95), (200, 100))
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    window.replace(1, dataclasses.replace(window.annotations[1], contents="about justice", author="B"))
    window.search.setText("justice")
    window.search_timer.timeout.emit()  # (the pause after typing)
    assert window._rows == [1]
    window.search.clear()
    window.f_author.setCurrentIndex(window.f_author.findData("B"))
    window._filter_changed()
    assert window._rows == [1]
    window.f_author.setCurrentIndex(0)
    window._filter_changed()
    window.selected = []
    window.go_annotation(1)
    assert window.selected == [0]
    window.go_annotation(1)
    assert window.selected == [1]
    window.a_show.setChecked(False)
    assert window.canvas.items_ == []


def test_tool_behaviour(window):
    prefs = window.prefs.with_style("rect", dataclasses.replace(window.prefs.style("rect"), sticky=False))
    window.set_prefs(prefs)
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    assert window.canvas.mode == "select"  # (not sticky: back to Select)
    window.set_tool("note")
    window.typed = None  # (its text asked for, and given up: no note)
    click(window, (400, 200))
    assert len(window.annotations) == 1


def test_recovery(window, sample, app):
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    window.keep_recovery()
    kept = list(window.annotations)
    window.annotations = window.saved = []  # (as if the program had stopped)
    other = MainWindow()
    other.ask_recover = lambda when: True
    assert other.open_path(sample)
    assert other.annotations == kept and other.is_modified()
    assert other.save()
    other.close()


def test_export_import(window, tmp_path):
    window.set_tool("highlight")
    drag(window, (75, 95), (200, 100))
    window._ask_target = lambda title, suffix, ext="pdf": tmp_path / f"out.{ext}"
    for kind in ("json", "md", "txt", "csv"):
        assert window.export_dialog(kind)
    assert "First line" in (tmp_path / "out.md").read_text(encoding="utf-8")
    assert "“First line" in (tmp_path / "out.txt").read_text(encoding="utf-8")
    window.annotations = []
    window.refresh()
    assert window.import_from(tmp_path / "out.json", "json")
    assert [a.kind for a in window.annotations] == ["highlight"]
    assert window.import_from(tmp_path / "out.json", "json") and len(window.annotations) == 1  # (already there)
    assert window.save_flattened_dialog()
    flat = annots.open_pdf(tmp_path / "out.pdf")
    assert list(flat[0].annots()) == [] and window.path != tmp_path / "out.pdf"


def test_settings_dialog(window):
    from PySide6.QtGui import QKeySequence

    from py_pdftools.gui.prefs import SettingsDialog

    dialog = SettingsDialog(window.prefs, window)
    dialog.author.setText("  N.   V. ")
    dialog.palette_rows[0][1].setText("Key ideas")
    dialog.key_edits["rect"].setKeySequence(QKeySequence("H"))
    assert dialog.conflicts() == [("H", "highlight", "rect")]
    dialog.key_edits["rect"].setKeySequence(QKeySequence("Ctrl+Alt+R"))
    assert dialog.conflicts() == []
    window.set_prefs(dialog.settings())
    assert window.prefs.author == "N. V." and window.prefs.palette[0] == ("#ffeb3b", "Key ideas")
    assert window.tool_actions["rect"].shortcut().toString() == "Ctrl+Alt+R"
    from py_pdftools.gui.colors import color_name

    assert color_name("#ffeb3b") == "Yellow — Key ideas"


def fake_pdf2iso(folder) -> str:
    """A pdf2iso that copies the file, leaving out polygons, as Ghostscript does."""
    import sys

    script = folder / "pdf2iso"
    # (it gets the tests' own sys.path: on Windows it is run by whatever Python is on the PATH)
    script.write_text(f"""#!{sys.executable}
import sys
sys.path[:0] = {sys.path!r}
import pymupdf
args = sys.argv[1:]
out = args[args.index("-o") + 1]
doc = pymupdf.open(args[-1])
if doc.needs_pass:
    doc.authenticate(args[args.index("-p") + 1])
for page in doc:
    for xref in [a.xref for a in page.annots() if a.type[1] == "Polygon"]:
        page.delete_annot(page.load_annot(xref))
doc.save(out)
print("OK  (veraPDF: PASS) in.pdf -> out.pdf [PDF/A-2b]")
""")
    if sys.platform != "win32":  # (a shell script that runs it: the path of this Python may have spaces,
        # which a #! line can't take, as in the installer's environment on macOS)
        body = folder / "pdf2iso-body.py"
        script.rename(body)
        script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{body}" "$@"\n')
    script.chmod(0o755)
    return str(script)


def test_save_as_pdfa(window, tmp_path):
    window.set_prefs(dataclasses.replace(window.prefs, pdfconform=str(tmp_path / "missing")))
    assert not window.standard_actions["a-2b"].isEnabled()  # (no pdf2iso there)
    window.set_prefs(dataclasses.replace(window.prefs, pdfconform=fake_pdf2iso(tmp_path)))
    assert window.standard_actions["a-2b"].isEnabled()
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    window.set_tool("polygon")
    for p in ((300, 300), (400, 300), (350, 380)):
        click(window, p)
    window.canvas.finish_polygon()
    asked = []
    window.ask_flatten_lost = lambda standard, names: asked.append(names) or True
    target = tmp_path / "copy-pdfa.pdf"
    assert window.save_standard(target, "a-2b")
    assert asked == ["polygon (1)"]  # (left out by Ghostscript: made part of the pages instead)
    doc = annots.open_pdf(target)
    assert [a.kind for a in annots.read(doc)] == ["rect"] and doc[0].get_drawings()
    assert "veraPDF: PASS" in window.statusBar().currentMessage()
    assert window.path != target and window.is_modified()  # (a copy: the document stays as it was)


def test_panel_can_be_hidden(window):
    assert window.panel.isVisible()
    window.a_panel.trigger()
    assert not window.panel.isVisible()
    window.a_panel.trigger()
    assert window.panel.isVisible()
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    window.replace(0, dataclasses.replace(window.annotations[0], author="B"))
    assert window.f_author.itemText(window.f_author.findData("B")) == "B (1)"


def test_text_written_on_the_page(window):
    from py_pdftools.gui.canvas import PageCanvas

    canvas = window.canvas
    del canvas.edit_text  # (the real one: an editor on the page)
    window.set_tool("freetext")
    click(window, (300, 300))
    assert canvas.editing() and window.annotations == []  # (made once its text is written)
    canvas.commit_text("Written here")
    assert [a.contents for a in window.annotations] == ["Written here"]
    # double-clicked: written again, where it is
    window.set_tool("select")
    mouse(window, QEvent.Type.MouseButtonDblClick, (310, 310))
    assert canvas.editing()
    canvas.commit_text("Written again")
    assert window.annotations[0].contents == "Written again" and len(window.undo_stack) == 2
    # a note: Escape gives it up
    window.set_tool("note")
    click(window, (100, 600))
    assert canvas.editing()
    canvas.cancel_text()
    assert len(window.annotations) == 1
    assert isinstance(canvas, PageCanvas)


def test_replies_status_and_tags_in_the_panel(window, sample):
    window.prefs = dataclasses.replace(window.prefs, author="Me")
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    window.listing.reply_edit.setText("Is this right?")
    window.add_reply()
    window.set_status("Accepted")
    a = window.annotations[0]
    assert [(r.author, r.contents, r.state) for r in a.replies] == [("Me", "Is this right?", ""),
                                                                    ("Me", "Status: Accepted", "Accepted")]
    assert a.status() == "Accepted" and window.listing.replies.count() == 2
    window.listing.tags.setText("Ethics, Aristotle")
    window.keep_tags()
    assert window.annotations[0].tags == ("Ethics", "Aristotle")
    window.toggle_category("Definitions")
    assert window.annotations[0].categories == ("Definitions",)
    # the filters: by status, tag, category; and the search finds replies
    window.f_status.setCurrentIndex(window.f_status.findData("Accepted"))
    window.f_tag.setCurrentIndex(window.f_tag.findData("Ethics"))
    window._filter_changed()
    assert window._rows == [0]
    window.f_status.setCurrentIndex(window.f_status.findData("-"))
    window._filter_changed()
    assert window._rows == []
    window.f_status.setCurrentIndex(0)
    window.f_tag.setCurrentIndex(0)
    window.search.setText("right?")
    window.search_timer.timeout.emit()
    assert window._rows == [0]
    window.search.clear()
    assert window.save()
    got = annots.read(annots.open_pdf(sample))[0]
    assert got.status() == "Accepted" and got.tags == ("Ethics", "Aristotle") and len(got.replies) == 2
    window.pick([0], False)
    window.delete_reply(0)
    assert [r.contents for r in window.annotations[0].replies] == ["Status: Accepted"]


def test_find_and_highlight(window):
    window.find_dialog("line of")
    finder = window.finder
    finder.search()
    assert len(finder.matches) == 6
    finder.kind.setCurrentIndex(finder.kind.findData("underline"))
    finder._mark(finder.matches)
    assert [a.kind for a in window.annotations] == ["underline"] * 6
    assert window.marked_text(window.annotations[0]) == "line of"
    finder._mark(finder.matches)  # (not twice over the same place)
    assert len(window.annotations) == 6
    finder.regex.setChecked(True)
    finder.query.setText("page (")
    finder.search()
    assert finder.matches == [] and "not right" in finder.summary.text()
    finder.close()


def test_continuous_and_one_page(window):
    canvas = window.canvas
    assert canvas.continuous and sorted(canvas.pages) == [0, 1, 2]
    window.show_page(2)
    assert window.page == 2 and window.a_page_number.boxes()[0].text() == "3"
    window.a_continuous.setChecked(False)
    assert list(canvas.pages) == [2]
    window.show_page(0)
    assert list(canvas.pages) == [0]
    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    assert window.annotations[0].page == 0
    window.a_continuous.setChecked(True)
    assert sorted(canvas.pages) == [0, 1, 2] and len(canvas.items_) == 1


def test_marker_and_pressure(window):
    from py_pdftools.gui.canvas import PageCanvas

    window.set_tool("marker")
    drag(window, (100, 650), (150, 655), (200, 650))
    a = window.annotations[0]
    assert a.kind == "marker" and a.width == settings.STYLES["marker"].width and a.opacity < 1
    pressed = PageCanvas._pressed(dataclasses.replace(a, width=2), {"pressures": [1.0, 1.0]})
    assert pressed.width == 3.2  # (2 × (0.4 + 1.2))
    assert PageCanvas._pressed(a, {}) == a


def test_thumbnail_size(window):
    window.thumb_slider.setValue(200)
    assert window.thumb.height() == 200 and window.pages.iconSize().height() == 200
    QApplication.processEvents()


def test_print_and_exports(window, tmp_path, sample):
    from PySide6.QtGui import QPdfWriter

    from py_pdftools.gui import printing

    window.set_tool("rect")
    drag(window, (100, 300), (250, 400))
    doc = printing.printable(sample, window.annotations)
    writer = QPdfWriter(str(tmp_path / "printed.pdf"))
    assert printing.render(writer, doc, [0, 1])
    import pymupdf

    assert pymupdf.open(tmp_path / "printed.pdf").page_count == 2
    window._ask_target = lambda title, suffix, ext="pdf": tmp_path / f"out{suffix}.{ext}"
    assert window.export_dialog("xfdf") and window.export_dialog("pdf")
    assert (tmp_path / "out-annotations.xfdf").read_text(encoding="utf-8").count("<square") == 1
    assert pymupdf.open(tmp_path / "out-summary.pdf").page_count == 1


def test_many_annotations_are_listed_at_once(window):
    import time

    many = [annots.Annotation("rect", i % 3, (10 + i % 50, 10, 30 + i % 50, 30), "#000000") for i in range(3000)]
    start = time.perf_counter()
    window.change(many)
    assert window.model.rowCount() == 3000 and time.perf_counter() - start < 5


def test_items_made_again_only_when_changed(window):
    window.set_tool("rect")
    drag(window, (100, 300), (150, 340))
    drag(window, (200, 300), (250, 340))
    first, second = sorted(window.canvas.items_, key=lambda i: i.index)
    window.replace(1, annots.moved(window.annotations[1], 5, 0))
    items = sorted(window.canvas.items_, key=lambda i: i.index)
    assert items[0] is first and items[1] is not second  # (only the one that changed is made again)
    window.set_tool("eraser")
    first.setOpacity(0.2)  # (as the eraser leaves what it is about to erase)
    window.refresh()
    assert first.opacity() == 1.0


def test_file_changed_elsewhere_before_saving(window, sample):
    """If the file changed since it was opened, what it has is read again before saving."""
    window.set_tool("rect")
    drag(window, (100, 300), (150, 340))
    other = annots.Annotation("ellipse", 1, (10, 10, 60, 60), "#000000")
    annots.write(sample, [other], sample)  # (another program adds an ellipse)
    assert window.save()
    kinds = sorted(a.kind for a in annots.read(annots.open_pdf(sample)))
    assert kinds == ["rect"]  # (the window's annotations are what the document has: the ellipse was not known)


def test_formatting_written_on_the_page(window, sample):
    """Bold and a colour given while writing a text box are kept as rich text, saved, painted,
    and shown again when it is written once more; Plain text takes them out."""
    from PySide6.QtGui import QImage, QKeyEvent, QPainter

    canvas = window.canvas
    del canvas.edit_text
    window.set_tool("freetext")
    click(window, (300, 300))
    editor = canvas._editor["item"]
    editor.setPlainText("one two")
    cursor = editor.textCursor()
    cursor.setPosition(4)
    cursor.setPosition(7, cursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier))
    editor._format("look", color="#ff0000")
    canvas.commit_text()
    a = window.annotations[0]
    assert a.contents == "one two"
    assert a.rich == '<p>one <span style="font-weight:bold;color:#ff0000">two</span></p>'
    assert window.save()
    assert annots.read(annots.open_pdf(sample))[0].rich == a.rich
    image = QImage(600, 600, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFF)
    p = QPainter(image)
    from py_pdftools.gui.paint import paint

    paint(p, window.annotations[0])  # (it is drawn: some red where the text is)
    p.end()
    r = window.annotations[0].rect
    reds = [image.pixelColor(x, y) for x in range(int(r[0]), int(r[2])) for y in range(int(r[1]), int(r[3]))]
    assert any(c.red() > 200 and c.green() < 80 for c in reds)
    window.set_tool("select")
    mouse(window, QEvent.Type.MouseButtonDblClick, (305, 305))
    editor = canvas._editor["item"]
    assert editor.toPlainText() == "one two"
    cursor = editor.textCursor()
    cursor.select(cursor.SelectionType.Document)
    editor.setTextCursor(cursor)
    editor._format("plain")
    canvas.commit_text()
    assert window.annotations[0].rich == "" and window.annotations[0].contents == "one two"


def test_border_colour_in_the_properties(window):
    from py_pdftools.gui.props import PropertiesDialog

    window.set_tool("freetext")
    drag(window, (100, 300), (250, 360))
    dialog = PropertiesDialog([window.annotations[0]], window)
    assert dialog.border.text() == "As the text"
    dialog.border.set_color("#00aa00")
    assert dialog.apply(window.annotations[0]).border == "#00aa00"


def test_groups_in_the_window(window, sample):
    """Annotations grouped are selected together by a click, deleted together, kept in the file;
    copies of a group make another group; ungrouped, each is on its own again."""
    window.set_tool("rect")
    drag(window, (100, 300), (150, 340))
    drag(window, (200, 300), (250, 340))
    drag(window, (300, 300), (350, 340))
    window.set_tool("select")
    window.pick([0, 1], False)
    window.group_selected()
    group = window.annotations[0].group
    assert group and window.annotations[1].group == group and not window.annotations[2].group
    window.pick([], False)
    click(window, (125, 320))  # (one of the group: both are selected)
    assert sorted(window.selected) == [0, 1]
    window.duplicate()
    copies = window.annotations[3:]
    assert len(copies) == 2 and copies[0].group == copies[1].group and copies[0].group != group
    assert window.save()
    assert sorted(a.group for a in annots.read(annots.open_pdf(sample))).count(group) == 2
    window.pick([0], False)
    window.delete_selected()
    assert len(window.annotations) == 3 and all(a.group != group for a in window.annotations)
    window.pick([1], False)  # (a copy: its group is selected with it)
    assert sorted(window.selected) == [1, 2]
    window.ungroup_selected()
    window.pick([1], False)
    assert window.selected == [1]


def test_textual_criticism_in_the_window(window):
    from py_pdftools.annotate.annots import Critical
    from py_pdftools.gui.props import PropertiesDialog

    window.set_tool("rect")
    drag(window, (100, 300), (150, 340))
    window.pick([0], False)
    window._critical_for_selected("conjecture")
    assert window.annotations[0].critical == Critical("conjecture")
    dialog = PropertiesDialog([window.annotations[0]], window)
    assert dialog.critical.isChecked()
    # Folded at first: one line that sums up the entry, and a lower dialog; unfolded, the fields.
    assert dialog.c_body.isHidden() and dialog.c_toggle.text() == "Conjecture"
    dialog.show()
    QApplication.processEvents()
    folded = dialog.height()
    dialog.c_toggle.setChecked(True)
    QApplication.processEvents()
    assert not dialog.c_body.isHidden() and dialog.height() > folded
    dialog.c_fields["reading"].setText("  lege   pacem ")
    dialog.c_fields["witness"].setText("A")
    dialog.c_toggle.setChecked(False)
    QApplication.processEvents()
    assert dialog.c_toggle.text() == "Conjecture: ] lege pacem A" and dialog.height() == folded
    dialog.hide()
    a = dialog.apply(window.annotations[0])
    assert a.critical == Critical("conjecture", reading="lege pacem", witness="A")
    window.replace(0, a)
    window.search.setText("pacem")
    window.search_timer.timeout.emit()
    assert window._rows == [0]
    window.search.clear()
    dialog = PropertiesDialog([window.annotations[0]], window)
    dialog.critical.setChecked(False)
    assert dialog.c_body.isHidden()
    dialog.critical.setChecked(True)  # (ticked: unfolded, to be filled)
    assert not dialog.c_body.isHidden()
    dialog.critical.setChecked(False)
    assert dialog.apply(window.annotations[0]).critical is None


def test_other_kinds_listed_not_changed(app, sample, tmp_path, monkeypatch):
    """A link and a watermark annotation are listed, but are neither deleted, changed nor copied; saving
    keeps them as they were. (A redaction mark was such another kind in py-annotate; in py-pdftools it is a
    box of the mode Redact.)"""
    import pymupdf

    monkeypatch.setenv("HOME", str(tmp_path))
    doc = pymupdf.open(sample)
    doc[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(60, 60, 200, 80), "uri": "https://example.org"})
    xref = doc.get_new_xref()
    doc.update_object(xref, "<</Type/Annot/Subtype/Watermark/Rect[300 500 400 520]/F 4>>")
    annots_ = doc.xref_get_key(doc[0].xref, "Annots")[1]
    doc.xref_set_key(doc[0].xref, "Annots", annots_.rstrip("]") + f" {xref} 0 R]")
    path = tmp_path / "linked.pdf"
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert w.open_path(path)
    assert sorted(a.name() for a in w.annotations) == ["Link", "Watermark"]
    assert len(w._rows) == 2
    w.pick([0, 1], False)
    w.delete_selected()
    assert len(w.annotations) == 2
    w.change([dataclasses.replace(a, color="#ff0000", locked=False) for a in w.annotations])
    assert all(a.color == "#808080" and a.locked for a in w.annotations) and not w.undo_stack
    w.copy_selected()
    w.set_tool("rect")
    drag(w, (100, 400), (150, 440))
    assert w.save()
    out = annots.open_pdf(path)
    assert sorted(a.other for a in annots.read(out) if a.kind == "other") == ["Link", "Watermark"]
    assert out[0].get_links()[0]["uri"] == "https://example.org"
    w.annotations = w.saved = []
    w.close()


def test_exports_leave_out_other_kinds(window, sample, tmp_path):
    import pymupdf

    doc = pymupdf.open(sample)
    doc[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(60, 60, 200, 80), "uri": "https://example.org"})
    doc.save(tmp_path / "linked.pdf")
    assert window.open_path(tmp_path / "linked.pdf")
    window.set_tool("rect")
    drag(window, (100, 400), (150, 440))
    window._ask_target = lambda *args: tmp_path / "out.json"
    assert window.export_dialog("json")
    import json

    assert [a["kind"] for a in json.loads((tmp_path / "out.json").read_text())["annotations"]] == ["rect"]


def test_pressure_along_a_stroke(window, sample):
    """A stroke whose pen pressure changes is cut where it goes to another level: drawings of their
    own widths, joined end to end, one group; with one pressure, one drawing."""
    canvas = window.canvas
    canvas.pen_pressure = "along"
    window.set_tool("ink")
    points = [(100 + 10 * i, 300) for i in range(12)]
    pressures = [0.1] * 4 + [0.5] * 4 + [0.95] * 4
    canvas._pressure = pressures[0]
    mouse(window, QEvent.Type.MouseButtonPress, points[0])
    for p, pressure in zip(points[1:], pressures[1:], strict=True):
        canvas._pressure = pressure
        mouse(window, QEvent.Type.MouseMove, p)
    mouse(window, QEvent.Type.MouseButtonRelease, points[-1])
    canvas._pressure = None
    pieces = window.annotations
    assert len(pieces) == 3 and len({a.group for a in pieces}) == 1 and pieces[0].group
    widths = [a.width for a in pieces]
    assert widths == sorted(widths) and widths[0] < widths[-1]
    assert pieces[0].paths[0][-1] == pieces[1].paths[0][0]  # (joined)
    assert window.save()
    assert sorted(a.width for a in annots.read(annots.open_pdf(sample))) == sorted(widths)
    canvas._pressure = 0.5  # (one pressure: one drawing)
    drag(window, (100, 500), (150, 500), (200, 500))
    canvas._pressure = None
    assert len(window.annotations) == 4 and not window.annotations[-1].group


def test_layers_in_the_window(window, sample):
    """New annotations go to the layer chosen; a layer hidden is neither drawn nor listed, and that
    is a change to save; saved, the document has the layers as they were."""
    window.new_layer("Mine")
    window.set_tool("rect")
    drag(window, (100, 300), (150, 340))
    window.layer = ""
    drag(window, (200, 300), (250, 340))
    assert [a.layer for a in window.annotations] == ["Mine", ""]
    window.pick([1], False)
    window.move_to_layer("Other")
    assert [a.layer for a in window.annotations] == ["Mine", "Other"]
    assert window.save() and not window.is_modified()
    window.show_layer("Mine", False)
    assert window.is_modified()
    assert window._rows == [1] and [i.index for i in window.canvas.items_] == [1]
    window.search.setText("other")
    window.search_timer.timeout.emit()
    assert window._rows == [1]
    window.search.clear()
    window.layers_menu()  # (it is made without trouble)
    assert window.save()
    doc = annots.open_pdf(sample)
    assert annots.layers(doc) == {"Mine": False, "Other": True}
    assert window.open_path(sample) and window.layers == {"Mine": False, "Other": True}
    assert window._rows == [1]


def test_searchable_copy(window, tmp_path):
    """File > Save a copy > Searchable (OCR): the copy is made, with the annotations, and opened, and
    its text can be marked."""
    from py_pdftools.annotate import ocr
    from test_exchange import scanned_pdf

    if not ocr.available() or "eng" not in ocr.languages():
        pytest.skip("Tesseract (with English) is not installed")
    assert window.open_path(scanned_pdf(tmp_path / "scan.pdf"))
    window.set_tool("rect")
    drag(window, (100, 600), (150, 640))
    window.ask_open_copy = lambda target: True
    window.maybe_discard = lambda: True
    assert window.save_searchable(tmp_path / "scan-ocr.pdf")
    assert window.path == tmp_path / "scan-ocr.pdf" and len(window.annotations) == 1
    assert any(t == "justice" for _, t in annots.page_text(window.doc[0]))


def tablet(w, kind, point, pressure=0.5, eraser=False, side=False):
    """A tablet's pen event at POINT (in points of the page in view), its eraser end if ERASER."""
    from PySide6.QtGui import QInputDevice, QPointingDevice, QTabletEvent

    pointer = QPointingDevice.PointerType.Eraser if eraser else QPointingDevice.PointerType.Pen
    device = QPointingDevice("pen", 1, QInputDevice.DeviceType.Stylus, pointer,
                             QInputDevice.Capability.Position | QInputDevice.Capability.Pressure, 1, 2)
    w._devices = getattr(w, "_devices", []) + [device]  # (kept alive while the events use it)
    c = w.canvas
    pos = QPointF(c.mapFromScene(c.pages[w.page].mapToScene(QPointF(*point))))
    pos += QPointF(0.37, 0.61)  # (between two pixels: the pen is finer than the mouse)
    button = Qt.MouseButton.RightButton if side else Qt.MouseButton.LeftButton  # (a side button, or the tip)
    buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.TabletRelease else button
    event = QTabletEvent(kind, device, pos, pos, pressure, 0, 0, 0, 0, 0, Qt.KeyboardModifier.NoModifier,
                         button, buttons)
    return c.viewportEvent(event)


def test_pen_eraser_end(window):
    """Turned over, the pen erases whatever tool is chosen, and the tool comes back after."""
    window.set_tool("rect")
    drag(window, (100, 300), (200, 400))
    assert len(window.annotations) == 1
    tablet(window, QEvent.Type.TabletPress, (110, 300), eraser=True)
    assert window.canvas.mode == "eraser"
    drag(window, (90, 350), (150, 350), (210, 350))
    tablet(window, QEvent.Type.TabletRelease, (210, 350), eraser=True)
    QApplication.processEvents()
    assert window.annotations == [] and window.canvas.mode == "rect"


def test_pen_strokes(window):
    """The pen's own moves draw (finer than the mouse's, and smoothed); with the pressure counted once
    per stroke, a stroke of changing pressure is one drawing."""
    canvas = window.canvas
    canvas.pen_pressure = "along"
    window.set_tool("ink")
    points = [(100 + 8 * i, 300 + (i % 2)) for i in range(15)]
    tablet(window, QEvent.Type.TabletPress, points[0], 0.1)
    mouse(window, QEvent.Type.MouseButtonPress, points[0])
    for i, p in enumerate(points[1:]):
        assert tablet(window, QEvent.Type.TabletMove, p, 0.1 if i < 7 else 0.9)  # (taken: no mouse move made)
    tablet(window, QEvent.Type.TabletRelease, points[-1])
    mouse(window, QEvent.Type.MouseButtonRelease, points[-1])
    drawn = window.annotations
    assert len(drawn) == 2 and drawn[0].group == drawn[1].group  # (along the stroke: two widths)
    xs = [x for a in drawn for x, _ in a.paths[0]]
    assert any(abs(x - round(x)) > 0.05 for x in xs)  # (not on whole pixels)
    ys = [y for _, y in drawn[0].paths[0][1:-1]]
    assert max(ys) - min(ys) < 1.0  # (the zigzag of one point, smoothed)
    canvas.pen_pressure = "stroke"
    tablet(window, QEvent.Type.TabletPress, (100, 500), 0.1)
    mouse(window, QEvent.Type.MouseButtonPress, (100, 500))
    for i in range(1, 12):
        tablet(window, QEvent.Type.TabletMove, (100 + 8 * i, 500), 0.1 if i < 6 else 0.9)
    tablet(window, QEvent.Type.TabletRelease, (188, 500))
    mouse(window, QEvent.Type.MouseButtonRelease, (188, 500))
    assert len(window.annotations) == 3 and not window.annotations[-1].group


def test_pen_settings_kept(tmp_path, monkeypatch):
    prefs = dataclasses.replace(settings.Settings(), pen_pressure="off", pen_curve="firm", pen_button="menu",
                                ocr_language="lat+eng")
    settings.save(prefs)
    got = settings.load()
    assert (got.pen_pressure, got.pen_curve, got.pen_button, got.ocr_language) == ("off", "firm", "menu", "lat+eng")


def test_pen_side_button_moves_the_page(window):
    """Held, the side button of the pen moves the page with the pen, and draws nothing, nor opens the
    menu; with the setting 'menu', it is a right click again."""
    canvas = window.canvas
    canvas.set_zoom(3.0)  # (so that there is room to move)
    QApplication.processEvents()
    window.set_tool("ink")
    menus = []
    canvas.menu_asked.connect(lambda *args: menus.append(args))
    bar = canvas.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    before = bar.value()
    assert tablet(window, QEvent.Type.TabletPress, (200, 300), side=True)
    assert tablet(window, QEvent.Type.TabletMove, (200, 250), side=True)
    assert bar.value() > before  # (the pen went up: the page follows it up, so the view goes down)
    assert tablet(window, QEvent.Type.TabletRelease, (200, 250), side=True)
    assert window.annotations == [] and menus == [] and canvas._pen_pan is None
    canvas.pen_button = "menu"
    assert not tablet(window, QEvent.Type.TabletPress, (200, 300), side=True)  # (left to Qt: a right click)


def test_thumbnails_hidden(window, sample):
    """View > The thumbnails of the pages hides them (and they are not drawn meanwhile), and the
    window remembers it."""
    window.a_thumbs.setChecked(False)
    assert window.thumbs_box.isHidden()
    window._thumbs.clear()
    window.thumb_timer.start()
    window._draw_thumbnails()
    assert not window.thumb_timer.isActive() and window._thumbs == {}
    window.save_settings()
    other = MainWindow()
    assert not other.a_thumbs.isChecked() and other.thumbs_box.isHidden()
    other.a_thumbs.setChecked(True)
    assert not other.thumbs_box.isHidden()
    other.save_settings()
    other.close()
    window.a_thumbs.setChecked(True)
    assert not window.thumbs_box.isHidden() and window.thumb_timer.isActive()


def test_writing_by_hand(window, monkeypatch):
    """Strokes made one soon after the other, near each other, are one drawing (a word written stroke
    by stroke), each undone on its own; a stroke far away, or after a pause, is another drawing. A pen
    draws even over an annotation (selected or not), never moving it."""
    from py_pdftools.gui import canvas as canvas_module

    clock = [1000.0]
    monkeypatch.setattr(canvas_module.time, "monotonic", lambda: clock[0])
    window.set_tool("ink")
    drag(window, (100, 300), (110, 320), (120, 300))
    clock[0] += 0.4
    drag(window, (112, 305), (125, 315), (135, 305))  # (starts over the first stroke, which is selected)
    clock[0] += 0.4
    drag(window, (140, 300), (150, 320))
    assert len(window.annotations) == 1 and len(window.annotations[0].paths) == 3
    first = window.annotations[0].paths[0]
    assert close(first[0], (100, 300))  # (not moved by the strokes over it)
    window.undo()
    assert len(window.annotations) == 1 and len(window.annotations[0].paths) == 2
    clock[0] += 0.4
    drag(window, (400, 600), (420, 620))  # (far away: another drawing)
    clock[0] += 3.0
    drag(window, (410, 605), (430, 625))  # (after a pause: another one)
    assert [len(a.paths) for a in window.annotations] == [2, 1, 1]


def test_pen_dots_and_freehand_highlight(window, monkeypatch):
    """A tap with the freehand tool makes a dot (the dot of an i), part of the word written just
    before; a freehand highlight is drawn in the window."""
    from PySide6.QtGui import QImage, QPainter

    from py_pdftools.gui import canvas as canvas_module
    from py_pdftools.gui.paint import paint

    clock = [1000.0]
    monkeypatch.setattr(canvas_module.time, "monotonic", lambda: clock[0])
    window.set_tool("ink")
    drag(window, (100, 320), (100, 340), (101, 360))
    clock[0] += 0.5
    click(window, (100, 305))
    assert len(window.annotations) == 1
    assert [len(p) for p in window.annotations[0].paths] == [3, 1]
    clock[0] += 5
    click(window, (300, 500))  # (on its own: a drawing of one dot)
    assert len(window.annotations) == 2 and window.annotations[1].paths[0][0] == pytest.approx((300, 500), abs=1)
    window.set_tool("marker")
    drag(window, (100, 600), (200, 600), (300, 605))
    marker = window.annotations[-1]
    assert marker.kind == "marker"
    image = QImage(600, 800, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFF)
    p = QPainter(image)
    paint(p, marker)
    p.end()
    assert image.pixelColor(200, 600) != image.pixelColor(200, 700)  # (it is there, where it was drawn)


def test_replace_text(window, sample):
    """Replace text strikes out what it is dragged over and writes the new text in an insert-text mark
    at its end, the two one group; written as PDF programs write it, and read back so."""
    window.set_tool("replace")
    window.typed = "Primera línea"
    drag(window, (75, 95), (140, 100))
    assert len(window.annotations) == 2
    caret, struck = window.annotations
    assert (caret.kind, caret.intent, caret.contents) == ("caret", "Replace", "Primera línea")
    assert (struck.kind, struck.intent) == ("strikeout", "StrikeOutTextEdit")
    assert caret.group == struck.group and caret.name() == "Replacement"
    assert "First" in window.marked_text(struck)
    assert abs(caret.rect[0] + annots.CARET_SIZE[0] / 2 - struck.quads[-1][2]) < 1  # (at the end of the text)
    assert window.save()
    doc = annots.open_pdf(sample)
    got = annots.read(doc)
    assert sorted((a.kind, a.intent) for a in got) == [("caret", "Replace"), ("strikeout", "StrikeOutTextEdit")]
    first = next(a for a in got if a.kind == "caret")  # (written first: the one the other answers)
    other = next(a for a in got if a.kind == "strikeout")
    assert doc.xref_get_key(other.xref, "IRT")[1] == f"{first.xref} 0 R"
    assert doc.xref_get_key(other.xref, "RT")[1] == "/Group"
    window.typed = None  # (given up: nothing is made)
    drag(window, (75, 120), (140, 125))
    assert len(window.annotations) == 2


def test_compare_in_the_window(window, sample, tmp_path):
    """File > Compare with another version marks the differences here, tagged with the other's name,
    and one undo takes them all back."""
    import pymupdf
    from test_exchange import version

    other = tmp_path / "other.pdf"
    doc = pymupdf.open(sample)
    page_text = doc[0].get_text().split()
    version(other, " ".join(page_text[:2] + ["CHANGED"] + page_text[3:]))
    assert window.compare_with(sample)  # (with itself: nothing)
    assert window.annotations == []
    assert window.compare_with(other)
    marked = window.annotations
    assert marked and all(a.tags == ("Compared with other.pdf",) for a in marked)
    changed = [a for a in marked if a.contents.startswith("In other.pdf: ")]
    assert changed and "CHANGED" in changed[0].contents
    window.undo()
    assert window.annotations == []


def test_typewriter_and_marks(window, sample):
    """The typewriter writes a text box with no border nor fill, kept as one (/IT /FreeTextTypeWriter);
    the check-mark tool puts the mark chosen, and the window remembers it."""
    window.set_tool("typewriter")
    click(window, (100, 400))
    tw = window.annotations[0]
    assert (tw.kind, tw.width, tw.fill, tw.intent, tw.contents) == ("freetext", 0, "", "FreeTextTypeWriter",
                                                                   "Typed text")
    assert tw.name() == "Typewriter"
    window.set_tool("mark")
    click(window, (200, 600))
    check = window.annotations[1]
    assert check.kind == "ink" and len(check.paths) == 1 and len(check.paths[0]) == 3
    x0, y0, x1, y1 = check.rect
    assert x0 < 200 < x1 and y0 < 600 < y1
    window.set_mark("cross")
    click(window, (250, 600))
    assert len(window.annotations[2].paths) == 2
    window.set_mark("dot")
    click(window, (300, 600))
    dot = window.annotations[3]
    assert dot.kind == "ellipse" and dot.fill == dot.color
    window.save_settings()
    assert MainWindow().mark == "dot"
    assert window.save()
    got = annots.read(annots.open_pdf(sample))
    assert got[0].intent == "FreeTextTypeWriter" and got[0].name() == "Typewriter"
    doc = annots.open_pdf(sample)
    assert doc.xref_get_key(got[0].xref, "IT")[1] == "/FreeTextTypeWriter"


def test_attach_a_file(window, sample, tmp_path):
    """The attach tool puts the file chosen where the click was; it can be saved again."""
    source = tmp_path / "notes.txt"
    source.write_bytes(b"my notes")
    window.ask_attachment = lambda: source
    window.set_tool("attachment")
    click(window, (300, 600))
    a = window.annotations[0]
    assert (a.kind, a.data, a.filename, a.contents) == ("attachment", b"my notes", "notes.txt", "notes.txt")
    out = window.save_attachment(a, tmp_path / "copy.txt")
    assert out.read_bytes() == b"my notes"
    window.ask_attachment = lambda: None  # (given up: nothing)
    click(window, (400, 600))
    assert len(window.annotations) == 1
    assert window.save()
    assert annots.read(annots.open_pdf(sample))[0].data == b"my notes"


def test_signature(window):
    """The signature drawn once is kept and put where the Signature tool is clicked, as a drawing
    120 points wide; with none kept yet, it is asked for first (and nothing is put if it is not given)."""
    from PySide6.QtGui import QMouseEvent

    from py_pdftools.gui import signature

    window.settings.setValue(signature.KEPT, "[]")
    window.draw_signature = lambda: False  # (none drawn: nothing)
    window.set_tool("signature")
    click(window, (100, 600))
    assert window.annotations == []

    pad = signature.Pad()
    for kind, x, y in ((QEvent.Type.MouseButtonPress, 10, 50), (QEvent.Type.MouseMove, 60, 20),
                       (QEvent.Type.MouseMove, 110, 60), (QEvent.Type.MouseMove, 210, 30)):
        event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        (pad.mousePressEvent if kind == QEvent.Type.MouseButtonPress else pad.mouseMoveEvent)(event)
    assert len(pad.strokes) == 1 and len(pad.strokes[0]) == 4

    def drawn():
        signature.save(window.settings, [signature.Kept("1", "Signature", strokes=signature.normalized(pad.strokes))],
                       "1")
        return True

    window.draw_signature = drawn
    click(window, (100, 600))
    a = window.annotations[0]
    assert a.kind == "ink" and len(a.paths) == 1 and len(a.paths[0]) == 4
    xs = [x for x, _ in a.paths[0]]
    assert abs(min(xs) - 100) < 1 and abs(max(xs) - min(xs) - window.SIGNATURE_WIDTH) < 1
    window.draw_signature = lambda: (_ for _ in ()).throw(AssertionError("asked again"))
    click(window, (100, 700))  # (kept: not asked again)
    assert len(window.annotations) == 2

    # A drag shows a frame of dashes while the mouse moves (as wide as the signature will be), gone on release
    from PySide6.QtWidgets import QGraphicsRectItem

    mouse(window, QEvent.Type.MouseButtonPress, (100, 300))
    mouse(window, QEvent.Type.MouseMove, (250, 330))
    frame = window.canvas._drag["item"]
    assert isinstance(frame, QGraphicsRectItem) and frame.pen().style() == Qt.PenStyle.DashLine
    assert abs(frame.rect().width() - 150) < 1 and frame.scene() is not None
    mouse(window, QEvent.Type.MouseButtonRelease, (250, 330))
    assert frame.scene() is None and len(window.annotations) == 3
    xs = [x for x, _ in window.annotations[2].paths[0]]
    assert abs(max(xs) - min(xs) - 150) < 1


def test_find_dialog_steps_and_history(window):
    """Previous and Next go round the places found; the searches made are remembered."""
    from py_pdftools.gui.finder import FindDialog

    dialog = FindDialog(window)
    dialog.query.setText("line")
    dialog.search()
    assert len(dialog.matches) == 6
    dialog.step(1)
    assert dialog.results.currentRow() == 0
    dialog.step(-1)
    assert dialog.results.currentRow() == 5  # (round)
    dialog.step(1)
    assert dialog.results.currentRow() == 0
    assert dialog.history[0] == "line"
    again = FindDialog(window)
    assert again.history[0] == "line" and again.accents.isChecked()


def test_a_strikeout_where_the_saved_one_is(app):
    """The line of a strikeout is drawn on the screen where MuPDF draws it in the file saved (3/7 of the line's
    height from its foot), across the small letters: the middle of the words' box was some points too high."""
    from PySide6.QtGui import QImage, QPainter

    import pymupdf

    from py_pdftools.annotate.annots import Annotation
    from py_pdftools.gui.paint import paint

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "example strike text", fontname="helv", fontsize=24)
    words = page.get_text("words")
    box = tuple(pymupdf.Rect(words[0][:4]) | pymupdf.Rect(words[-1][:4]))
    clip = pymupdf.Rect(70, 70, 120, 110)

    def red_rows(image) -> float:  # (the middle of the red line, in points of the page)
        rows = [y for y in range(image.height()) if sum(
            1 for x in range(image.width()) if (lambda c: c.red() > 200 and c.green() < 80)(image.pixelColor(x, y)))
            > image.width() // 3]
        return clip.y0 + (min(rows) + max(rows)) / 2 / 10

    image = QImage(500, 400, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFF)
    painter = QPainter(image)
    painter.scale(10, 10)
    painter.translate(-clip.x0, -clip.y0)
    paint(painter, Annotation("strikeout", 0, box, "#ff0000", quads=(box,)))
    painter.end()
    on_screen = red_rows(image)
    annot = page.add_strikeout_annot(pymupdf.Rect(box).quad)
    annot.set_colors(stroke=(1, 0, 0))
    annot.update()
    pix = page.get_pixmap(matrix=pymupdf.Matrix(10, 10), clip=clip)
    saved = red_rows(QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888))
    assert abs(on_screen - saved) < 0.3
    assert 100 - 0.4 * 24 < on_screen < 100 - 0.2 * 24  # (across the small letters, above the baseline at 100)
