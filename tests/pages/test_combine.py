"""Combining PDFs (pages/combine.py, File > Combine files, py-pdftools combine): the pages of each file, all
or some in an order, one after another; links, bookmarks (one for each file, as they are, or none), page
labels, protected files, and the window that makes and opens the result."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.pages import combine
from py_pdftools.pages.combine import CombineError, Part


def book(path, name, n, labels=None, password=""):
    doc = pymupdf.open()
    for i in range(n):
        doc.new_page().insert_text((72, 72), f"{name} page {i + 1}", fontsize=12)
    doc[0].insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(72, 60, 150, 75), "page": n - 1})
    doc.set_toc([[1, f"{name} start", 1], [2, f"{name} more", 2], [1, f"{name} end", n]])
    if labels:
        doc.set_page_labels(labels)
    doc.set_metadata({"title": f"Book {name}"})
    if password:
        doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    else:
        doc.save(path)
    return path


def texts(path):
    return [p.get_text().strip() for p in pymupdf.open(path)]


@pytest.fixture
def two(tmp_path):
    return book(tmp_path / "a.pdf", "A", 3, [{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1}]), \
        book(tmp_path / "b.pdf", "B", 4)


def test_all_pages_with_bookmarks_for_each_file(two, tmp_path):
    a, b = two
    out = tmp_path / "out.pdf"
    assert combine.combine([Part(a), Part(b)], out) == 7
    assert texts(out) == [f"A page {i}" for i in (1, 2, 3)] + [f"B page {i}" for i in (1, 2, 3, 4)]
    doc = pymupdf.open(out)
    assert doc.get_toc()[:4] == [[1, "Book A", 1], [2, "A start", 1], [3, "A more", 2], [2, "A end", 3]]
    assert doc.get_toc()[4] == [1, "Book B", 4]
    # (el enlace de cada primera página sigue yendo a la última página de su archivo)
    assert [lk["page"] for lk in doc[0].get_links()] == [2] and [lk["page"] for lk in doc[3].get_links()] == [6]
    assert doc.get_page_labels() == []  # (numeradas desde el principio)


def test_some_pages_in_an_order_and_labels(two, tmp_path):
    a, b = two
    out = tmp_path / "out.pdf"
    assert combine.combine([Part(a), Part(b, "4, 1-2")], out, bookmarks="keep", labels=True) == 6
    assert texts(out)[3:] == ["B page 4", "B page 1", "B page 2"]
    doc = pymupdf.open(out)
    assert [p.get_label() for p in doc] == ["i", "ii", "iii", "4", "1", "2"]
    # (los marcadores de las páginas que quedan fuera se van; los otros siguen a sus páginas)
    assert [t[1:] for t in doc.get_toc()][3:] == [["B start", 5], ["B more", 6], ["B end", 4]]
    doc.close()  # (before writing over it: Windows doesn't let a file open be replaced)
    combine.combine([Part(a), Part(b)], out, bookmarks="none")
    assert pymupdf.open(out).get_toc() == []


def test_protected_and_wrong(two, tmp_path):
    a, _ = two
    locked = book(tmp_path / "l.pdf", "L", 2, password="pw")
    out = tmp_path / "out.pdf"
    with pytest.raises(combine.PasswordNeeded):
        combine.combine([Part(a), Part(locked)], out)
    assert combine.combine([Part(a), Part(locked, "", "pw")], out) == 5
    assert not pymupdf.open(out).needs_pass  # (the result is not protected)
    with pytest.raises(CombineError):
        combine.combine([Part(a, "9")], out)
    with pytest.raises(CombineError):
        combine.combine([], out)
    (tmp_path / "x.pdf").write_text("not a pdf")
    with pytest.raises(CombineError):
        combine.combine([Part(tmp_path / "x.pdf")], out)


def test_into_one_of_the_files(two):
    a, b = two
    combine.combine([Part(a), Part(b)], a)  # (se escribe al lado y se renombra: puede ser uno de los leídos)
    assert len(texts(a)) == 7


def test_label_rules():
    rules = combine.label_rules(["i", "ii", "iii", "1", "2", "A-1", "5", "6", "IV"])
    doc = pymupdf.open()
    for _ in range(9):
        doc.new_page()
    doc.set_page_labels(rules)
    assert [p.get_label() for p in doc] == ["i", "ii", "iii", "1", "2", "A-1", "5", "6", "IV"]
    assert len(rules) == 5


def test_command_line(two, tmp_path, capsys):
    from py_pdftools.cli import main

    a, b = two
    out = tmp_path / "c.pdf"
    assert main(["combine", str(a), f"{b}:2-3", "-o", str(out), "--bookmarks", "none"]) == 0
    assert texts(out) == ["A page 1", "A page 2", "A page 3", "B page 2", "B page 3"]
    assert main(["combine", str(tmp_path / "missing.pdf"), "-o", str(out)]) == 1


def test_in_the_window(two, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.combine_dialog import CombineDialog
    from py_pdftools.gui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    a, b = two
    locked = book(tmp_path / "l.pdf", "L", 2, password="pw")
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(a)
        d = CombineDialog(w, (w.path, w.password))
        d.ask_password = lambda path: "pw"
        d.add_paths([b, locked])
        assert [p.name for p in d.paths()] == ["a.pdf", "b.pdf", "l.pdf"]
        d.tree.topLevelItem(1).setText(1, "9")
        assert "9" in d.problem.text() or d.problem.text() and not d.b_ok.isEnabled()
        d.tree.topLevelItem(1).setText(1, "last")
        assert d.b_ok.isEnabled()
        d.tree.setCurrentItem(d.tree.topLevelItem(2))
        d.tree.topLevelItem(2).setSelected(True)
        d.move(-1)
        assert [p.path.name for p in d.parts()] == ["a.pdf", "l.pdf", "b.pdf"]
        assert d.parts()[1].password == "pw"
        out = tmp_path / "out.pdf"
        w.ask_combine = lambda: (d.parts(), d.options())
        w.ask_new_pdf = lambda title, name: out
        before = len(QApplication.topLevelWidgets())
        made = w.combine_dialog()
        assert made is not None and made.path == out
        assert texts(out) == ["A page 1", "A page 2", "A page 3", "L page 1", "L page 2", "B page 4"]
        made.close()
        app.processEvents()
        assert len(QApplication.topLevelWidgets()) >= before - 1
    finally:
        w.close()
