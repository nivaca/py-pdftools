"""Filling forms (forms/fields.py, the panel Form): the fields read with their kinds, values, options and
places; values written, by the panel and by clicks on the page; undo; reset; and saving."""

from __future__ import annotations

import pymupdf
import pytest
from gui_helpers import mouse
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLineEdit
from sample_form import make

from py_pdftools.forms import fields
from py_pdftools.gui.window import MainWindow


@pytest.fixture
def form(tmp_path):
    return make(tmp_path / "form.pdf", scripts=False, pages=2)


def values(path):
    return {f.name: f.value for f in fields.read(pymupdf.open(path))}


def test_read(form):
    found = fields.read(pymupdf.open(form))
    by = {f.name: f for f in found}
    assert [f.name for f in found][:3] == ["name", "qty", "price"] and found[-1].name == "more1"
    assert by["more1"].page == 1
    assert by["agree"].kind == "check" and by["agree"].value == "Off" and by["agree"].states == ("Yes",)
    assert by["size"].kind == "radio" and by["size"].states == ("small", "large") and len(by["size"].widgets) == 2
    assert by["colour"].kind == "combo" and by["colour"].options == ("Red", "Green", "Blue")
    assert by["many"].kind == "list" and by["many"].value == "B"
    assert by["name"].label == "Name" and by["name"].title == "Name"
    assert fields.read(pymupdf.open()) == []


def test_fill_and_reset(form, tmp_path):
    doc = pymupdf.open(form)
    done = fields.fill(doc, {"name": "Ana", "size": "large", "agree": "Yes", "colour": "Blue", "nothing": "x"})
    assert sorted(done) == ["agree", "colour", "name", "size"]
    out = tmp_path / "o.pdf"
    doc.save(out)
    v = values(out)
    assert (v["name"], v["size"], v["agree"], v["colour"]) == ("Ana", "large", "Yes", "Blue")
    assert "Ana" in pymupdf.open(out)[0].get_text()
    doc = pymupdf.open(out)
    fields.fill(doc, fields.reset_values(fields.read(doc)))
    doc.save(tmp_path / "r.pdf")
    v = values(tmp_path / "r.pdf")
    assert (v["name"], v["size"], v["agree"]) == ("", "Off", "Off")


def test_in_the_window(form, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 900)
    w.show()
    try:
        assert w.open_path(form)
        app.processEvents()
        assert w.form_dock.isVisible()  # (opened by itself: the document has a form)
        name = w._form_editors["name"]
        assert isinstance(name, QLineEdit)
        name.setText("Ana")
        name.editingFinished.emit()
        assert w.field("name").value == "Ana" and w.is_modified()
        w._form_editors["agree"].setChecked(True)
        assert w.field("agree").value == "Yes"
        assert isinstance(w._form_editors["size"], QComboBox) and isinstance(w._form_editors["agree"], QCheckBox)
        # on the page: a click on the radio button 'small' sets it; one on a text field takes the panel to it
        w.set_mode("read")
        w.show_page(0)
        w._fit("page")
        app.processEvents()
        small = next(x for x in w.field("size").widgets if x.state == "small")
        cx, cy = (small.rect[0] + small.rect[2]) / 2, (small.rect[1] + small.rect[3]) / 2
        mouse(w, QEvent.Type.MouseButtonPress, (cx, cy), page=0)
        mouse(w, QEvent.Type.MouseButtonRelease, (cx, cy), page=0)
        assert w.field("size").value == "small"
        r = w.field("qty").widgets[0].rect
        mouse(w, QEvent.Type.MouseButtonPress, ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), page=0)
        mouse(w, QEvent.Type.MouseButtonRelease, ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), page=0)
        app.processEvents()
        assert w.focusWidget() is w._form_editors["qty"]
        w.undo()
        assert w.field("size").value == "Off"
        assert w.reset_form()
        assert w.field("name").value == "" and w.field("agree").value == "Off"
        w.undo()
        assert w.save()
        v = values(form)
        assert (v["name"], v["agree"]) == ("Ana", "Yes")
    finally:
        w.drop_work()
        w.close()
