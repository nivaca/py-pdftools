"""El arranque de la ventana: lo que no hace falta para mostrarla se deja para cuando se pida (el espacio de
trabajo de Imponer, la búsqueda de pdf2iso y Ghostscript), o se busca en otro hilo (Tesseract); y abrir un
documento lee adónde van sus enlaces sin recorrer otra vez, por cada enlace, las anotaciones de su página."""

from __future__ import annotations

import threading
import time

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate import annots
from py_pdftools.core import interface, once


@pytest.fixture
def window():
    QApplication.instance() or QApplication([])
    from py_pdftools.gui.window import MainWindow

    w = MainWindow()
    w.ask_recover = lambda when: False
    yield w
    w.close()


def test_impose_workspace_made_when_first_entered(window):
    """The window starts without the workspace of Impose; its menu holds its place, empty, until the mode is
    entered, and is then filled."""
    assert window._workspace is None
    assert window.impose_menu.actions() == []
    assert not window.impose_menu.menuAction().isVisible()
    window.set_mode("impose")
    ws = window._workspace
    assert ws is not None and window.workspace is ws  # (made once)
    assert ws.menu is window.impose_menu and window.impose_menu.actions()
    assert window.central.currentWidget() is ws
    window.set_mode("read")
    assert window.central.currentWidget() is window.splitter


def test_closing_without_the_workspace(window):
    window.close()  # (nothing to close down: it was never made)
    assert window._workspace is None


def test_pdf2iso_looked_for_when_save_as_opens(window, monkeypatch):
    from py_pdftools.core import conform

    asked = []
    monkeypatch.setattr(conform, "available", lambda path=None: asked.append(path) or False)
    window._have_conform = None
    window._enable()
    assert asked == []  # (not at the start, nor at each _enable)
    from PySide6.QtWidgets import QMenu

    save_as = next(m for m in window.standard_actions["a-2b"].associatedObjects() if isinstance(m, QMenu))
    save_as.aboutToShow.emit()  # (the menu Save as opens)
    assert len(asked) == 1 and window._have_conform is False
    assert not any(a.isEnabled() for a in window.standard_actions.values())
    save_as.aboutToShow.emit()
    assert len(asked) == 1  # (once)


def test_interface_names_from_the_root_only(tmp_path, monkeypatch):
    """The name of each language is read from the root of its file; what follows is not parsed (a file
    broken after its root still gives its name)."""
    (tmp_path / "xx.xml").write_text('<interface native="Xxish" name="X"><text>unclosed', encoding="utf-8")
    (tmp_path / "yy.xml").write_text("not xml", encoding="utf-8")
    monkeypatch.setattr(interface, "FOLDER", tmp_path)
    assert interface.names() == {"en": "English", "xx": "Xxish"}


def test_once_runs_once_for_two_threads():
    calls = []

    @once.once
    def slow():
        calls.append(1)
        time.sleep(0.05)
        return 42

    once.ahead(slow)  # (in another thread)
    results = []
    threads = [threading.Thread(target=lambda: results.append(slow())) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [42, 42, 42] and calls == [1]


def test_once_ahead_keeps_no_error():
    """An error looked for ahead is not kept: it comes again, in the thread that asks."""
    tries = []

    @once.once
    def broken():
        tries.append(1)
        raise OSError("no")

    once.ahead(broken)
    for _ in range(100):
        if tries:
            break
        time.sleep(0.01)
    time.sleep(0.02)
    with pytest.raises(OSError):
        broken()
    assert len(tries) == 2


def test_link_targets(tmp_path):
    """Where each link goes, read from its own object: an address, a page (by its object, by a name, or
    through another object), or nothing (another file)."""
    doc = pymupdf.open()
    for _ in range(4):
        doc.new_page()
    doc.xref_set_key(doc.pdf_catalog(), "Dests", f"<</intro [{doc.page_xref(2)} 0 R /XYZ 0 0 0]>>")
    page = doc[0]
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(10, 10, 50, 20), "uri": "https://x.org/a"})
    page.insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(10, 30, 50, 40), "page": 3,
                      "to": pymupdf.Point(0, 0)})
    page.insert_link({"kind": pymupdf.LINK_GOTOR, "from": pymupdf.Rect(10, 50, 50, 60), "file": "other.pdf",
                      "page": 0, "to": pymupdf.Point(0, 0)})
    path = tmp_path / "links.pdf"
    doc.save(path)
    doc = pymupdf.open(path)
    page = doc[0]
    xrefs = [x for x, kind, _ in page.annot_xrefs() if kind == pymupdf.PDF_ANNOT_LINK]
    # Otros dos, a mano: /Dest con nombre, y una acción GoTo cuyo destino está en otro objeto.
    named = doc.get_new_xref()
    doc.update_object(named, "<</Type/Annot/Subtype/Link/Rect[10 70 50 80]/Dest(intro)>>")
    array = doc.get_new_xref()
    doc.update_object(array, f"[{doc.page_xref(1)} 0 R /Fit]")
    indirect = doc.get_new_xref()
    doc.update_object(indirect, f"<</Type/Annot/Subtype/Link/Rect[10 90 50 100]/A<</S/GoTo/D {array} 0 R>>>>")
    annots_key = doc.xref_get_key(page.xref, "Annots")[1].rstrip("]") + f" {named} 0 R {indirect} 0 R]"
    doc.xref_set_key(page.xref, "Annots", annots_key)
    page = doc.reload_page(page)
    found = [a for a in annots.read(doc) if a.kind == annots.OTHER]
    assert [a.contents for a in found] == ["https://x.org/a", "Page 4", "", "Page 3", "Page 2"]
    assert {a.other for a in found} == {"Link"}
    assert [a.xref for a in found[:3]] == xrefs
    # (where they are, as PyMuPDF's get_links says)
    shown = {link["xref"]: link["from"] for link in page.get_links()}
    for a in found[:3]:
        assert a.rect == pytest.approx(tuple(shown[a.xref]), abs=0.01)
