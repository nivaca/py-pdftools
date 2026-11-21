"""The data of forms (forms/data.py, the panel's Export and Import, py-pdftools form): values written as
JSON, CSV, XFDF and FDF and read back; a form filled from a file, checked and summed; many forms in one
table; fields flattened."""

from __future__ import annotations

import json

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication
from sample_form import make

from py_pdftools.forms import data
from py_pdftools.forms.formats import Refused
from py_pdftools.gui.window import MainWindow

VALUES = {"name": "Añá (x)\\y", "price": "12.5", "agree": "Yes", "size": "large", "colour": "Blue"}


@pytest.fixture
def form(tmp_path):
    return make(tmp_path / "form.pdf")


@pytest.mark.parametrize("fmt", data.FORMATS)
def test_round_trip(fmt, tmp_path):
    path = tmp_path / f"v.{fmt}"
    path.write_text(data.dumps(VALUES, fmt, "form.pdf", {"agree", "size"}), encoding="utf-8")
    assert data.load(path) == VALUES
    if fmt == "fdf":
        assert "/V /Yes" in path.read_text() and "/V /large" in path.read_text()


def test_load_errors(tmp_path):
    for name, text in (("a.json", "[1]"), ("b.csv", "only,a,header\n"), ("c.xfdf", "<xfdf><fields>")):
        (tmp_path / name).write_text(text)
        with pytest.raises(data.DataError):
            data.load(tmp_path / name)
    with pytest.raises(data.DataError):
        data.load(tmp_path / "missing.json")


def test_fill_flatten_and_table(form, tmp_path):
    out = tmp_path / "filled.pdf"
    done = data.fill_file(form, VALUES | {"nothing": "x"}, out)
    assert "total" in done  # (summed from the price)
    with pymupdf.open(out) as doc:
        v = data.values_of(doc)
        assert (v["name"], v["total"], v["size"]) == (VALUES["name"], "12.5", "large")
        assert "$12.50" in doc[0].get_text()
    with pytest.raises(Refused):
        data.fill_file(form, {"price": "lots"}, tmp_path / "x.pdf")
    assert data.fill_file(form, {"price": "lots"}, tmp_path / "raw.pdf", formatted=False) == ["price"]
    flat = tmp_path / "flat.pdf"
    assert data.flatten_file(out, flat) == 12
    with pymupdf.open(flat) as doc:
        assert list(doc[0].widgets()) == [] and "Añá" in doc[0].get_text()
    rows = []
    for p in (form, out):
        with pymupdf.open(p) as doc:
            rows.append((p.name, data.values_of(doc)))
    lines = data.table(rows).splitlines()
    assert lines[0].startswith("file,name,qty") and lines[2].startswith("filled.pdf,")


def test_command_line(form, tmp_path, capsys):
    from py_pdftools.cli import main

    (tmp_path / "v.json").write_text(json.dumps(VALUES))
    out = tmp_path / "o.pdf"
    assert main(["form", "fill", str(form), str(tmp_path / "v.json"), "-o", str(out), "--flatten"]) == 0
    assert list(pymupdf.open(out)[0].widgets()) == []
    assert main(["form", "fill", str(form), str(tmp_path / "v.json"), "-o", str(out)]) == 0
    capsys.readouterr()
    assert main(["form", "show", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["colour"] == "Blue"
    assert main(["form", "table", str(form), str(out), "-o", str(tmp_path / "t.csv")]) == 0
    assert len((tmp_path / "t.csv").read_text().splitlines()) == 3
    (tmp_path / "bad.json").write_text('{"price": "lots"}')
    assert main(["form", "fill", str(form), str(tmp_path / "bad.json"), "-o", str(out)]) == 1


def test_in_the_window(form, tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(form)
        source = tmp_path / "v.xfdf"
        source.write_text(data.dumps(VALUES | {"when": "not a date"}, "xfdf"), encoding="utf-8")
        assert w.import_form_dialog(source)
        assert w.field("price").value == "12.5" and w.field("total").value == "12.5"
        assert "Date" in w.statusBar().currentMessage()  # (refused, and said)
        w.undo()
        assert w.field("price").value == ""
        w.redo()
        w.ask_form_file = lambda saving: tmp_path / "out.csv"
        assert w.export_form_dialog()
        assert data.load(tmp_path / "out.csv")["colour"] == "Blue"
        w.ask_new_pdf = lambda title, name: tmp_path / "flat.pdf"
        assert w.save_flat_form_dialog()
        with pymupdf.open(tmp_path / "flat.pdf") as doc:
            assert list(doc[0].widgets()) == [] and "$12.50" in doc[0].get_text()
    finally:
        w.drop_work()
        w.close()


def test_csv_lines_end_plainly():
    """The CSVs are saved as text, which ends their lines as the system does (\\r\\n on Windows): they must not
    have csv's own \\r\\n, which would become \\r\\r\\n there, an empty line after each row."""
    from py_pdftools.forms import data

    assert "\r" not in data.dumps({"a": "1", "b": "2"}, "csv")
    assert "\r" not in data.table([("x.pdf", {"a": "1"}), ("y.pdf", {"b": "2"})])
