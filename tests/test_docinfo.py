"""File > PDF properties (core/docinfo.py and gui/docprops_dialog.py): what a document is, and its fonts."""

from __future__ import annotations

import pymupdf
from PySide6.QtWidgets import QApplication

from py_pdftools.core import docinfo


def sample(path):
    doc = pymupdf.open()
    for n in range(3):
        page = doc.new_page()  # (PyMuPDF's default, 595 × 842 points: A4)
        page.insert_text((72, 72), f"Page {n + 1}", fontname="helv")
        if n == 2:
            page.insert_text((72, 120), "Times", fontname="tiro")
    doc.set_metadata({"title": "A test", "author": "Ana Gómez", "creationDate": "D:20261121103000-05'00'"})
    doc.set_toc([[1, "One", 1], [1, "Three", 3]])
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="",
             permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_ACCESSIBILITY)
    return path


def test_the_properties(tmp_path):
    path = sample(tmp_path / "t.pdf")
    doc = pymupdf.open(path)
    found = {label: value for _, label, value in docinfo.properties(doc, path)}
    assert found["Title"] == "A test" and found["Author"] == "Ana Gómez"
    assert found["Created"] == "2026-11-21 10:30:00 −05:00"
    assert found["Name"] == "t.pdf" and found["Pages"] == "3" and found["Bookmarks"] == "2"
    assert found["Page size"].startswith("210 × 297 mm")
    assert "AES" in found["Encrypted"] and "Copy text and pictures" in found["Not allowed"]
    assert "Print" not in found["Not allowed"].split(", ")
    fonts = docinfo.fonts(doc)
    assert [(f["name"], f["pages"]) for f in fonts] == [("Helvetica", [1, 2, 3]), ("Times-Roman", [3])]
    assert not fonts[0]["embedded"]
    assert docinfo.page_ranges([1, 2, 3, 7, 9, 10]) == "1-3, 7, 9-10"
    assert docinfo.pdf_date("D:2026") == "2026" and docinfo.file_size(2048) == "2 KB"


def test_the_dialog(tmp_path):
    from py_pdftools.gui.docprops_dialog import DocumentPropertiesDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    path = sample(tmp_path / "t.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert w.a_doc_props.isEnabled() is False  # (no document yet)
    assert w.open_path(path)
    assert w.a_doc_props.isEnabled()
    d = DocumentPropertiesDialog(w.doc, w.path, w)
    assert d.tabs.count() == 2 and d.fonts_tree.topLevelItemCount() == 2
    text = d.as_text()
    assert "Title: A test" in text and "Helvetica" in text and "1-3" in text
    d.close()
    w.drop_work()
    w.close()
