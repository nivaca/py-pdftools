"""El clasificador de páginas (Ver > Clasificador de páginas): la operación arrange.Sort, el diálogo, y el paso
único del historial que hace en el documento."""

from __future__ import annotations

import io

import pikepdf
import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QDialog

from py_pdftools.pages import arrange


def book(path, pages=5):
    """PAGES pages, each with its number as text (P1, P2...), labelled i, ii, then 1, 2, 3..."""
    doc = pymupdf.open()
    for n in range(pages):
        doc.new_page().insert_text((72, 72), f"P{n + 1}", fontsize=20)
    doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
                         {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1}])
    doc.save(path)
    return path


def texts(doc) -> list[str]:
    return [page.get_text().strip() for page in doc]


def test_the_operation(tmp_path):
    """A new order (pages left out are deleted, repeated ones duplicated), then turns by the new places."""
    pdf = pikepdf.open(book(tmp_path / "b.pdf"))
    op = arrange.Sort((3, 1, 5, 5), ((1, 90), (4, 270)), count=5)
    assert op.moves_pages() and op.items(5) == [3, 1, 5, 5]
    op.apply(pdf)
    out = io.BytesIO()
    pdf.save(out)
    doc = pymupdf.open(stream=out.getvalue())
    assert texts(doc) == ["P3", "P1", "P5", "P5"] and [p.rotation for p in doc] == [90, 0, 0, 270]
    # (only turns: the pages don't move, and the labels are not asked about)
    assert not arrange.Sort((1, 2, 3), ((2, 180),), count=3).moves_pages()
    # (one left out of three: it is deleted, and so the pages move)
    assert arrange.Sort((1, 2), count=3).moves_pages()
    # the labels follow their pages
    assert arrange.labels_after(arrange.Sort((3, 1), count=5), ["i", "ii", "1", "2", "3"], 5) == ["1", "i"]
    with pytest.raises(Exception):
        arrange.Sort((7,), count=5).items(5)


@pytest.fixture
def window(tmp_path, monkeypatch):
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1200, 800)
    assert w.open_path(book(tmp_path / "book.pdf"))
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def test_the_dialog(window):
    from py_pdftools.gui.pages.sorter_dialog import PAGE, TURN, SorterDialog

    d = SorterDialog(window)
    assert d.grid.count() == 5 and d.operation() is None  # (nothing changed yet)
    assert d.grid.item(0).text() == "1  (i)" and d.grid.item(2).text() == "3  (1)"
    d.grid.item(1).setSelected(True)
    d.turn(90)
    d.turn(90)
    assert d.grid.item(1).data(TURN) == 180
    d.duplicate()
    assert [d.grid.item(r).data(PAGE) for r in range(d.grid.count())] == [1, 2, 2, 3, 4, 5]
    d.grid.clearSelection()
    d.grid.item(0).setSelected(True)
    d.delete()
    op = d.operation()
    assert op.order == (2, 2, 3, 4, 5) and op.turns == ((1, 180), (2, 180)) and op.count == 5
    d.grid.selectAll()
    d.delete()  # (not every page: the document needs one)
    assert d.grid.count() == 5 and "one page at least" in d.state.text()
    d.reset()
    assert d.operation() is None and d.grid.count() == 5
    d.close()


def test_one_step_of_the_history(window, monkeypatch):
    """OK makes everything as one change of the document, which one Undo takes back."""
    from py_pdftools.gui.pages import sorter_dialog

    def sorted_dialog(self):
        for r in (4, 0):  # (pages 5 and 1 left out: 2, 3, 4 remain)
            self.grid.takeItem(r)
        self.grid.item(0).setSelected(True)
        self.turn(90)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(sorter_dialog.SorterDialog, "exec", sorted_dialog)
    monkeypatch.setattr(window, "labels_choice", lambda: arrange.FOLLOW)
    assert window.page_sorter()
    assert texts(window.doc) == ["P2", "P3", "P4"] and window.doc[0].rotation == 90
    assert window.page_labels() == ["ii", "1", "2"]
    window.undo()
    assert texts(window.doc) == ["P1", "P2", "P3", "P4", "P5"] and window.doc[1].rotation == 0
    # Cancel, or OK without a change: nothing done
    monkeypatch.setattr(sorter_dialog.SorterDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    assert not window.page_sorter()
    monkeypatch.setattr(sorter_dialog.SorterDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    assert not window.page_sorter()
