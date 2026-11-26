"""El panel Archivos adjuntos (gui/attachments.py): los archivos del documento y de sus páginas, abiertos,
guardados, añadidos y quitados; añadir y quitar se deshacen como los otros cambios."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.gui import attachments
from py_pdftools.gui.window import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "carrier.pdf"
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    doc.embfile_add("data.csv", b"a,b\n1,2\n", filename="data.csv", desc="The numbers")
    doc[2].add_file_annot((100, 100), b"note text", "note.txt")
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1400, 900)
    w.show()
    assert w.open_path(path)
    QApplication.processEvents()
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def names(window) -> list[tuple[str, str]]:
    tree = window.attach_list
    return [(tree.topLevelItem(i).text(0), tree.topLevelItem(i).text(2)) for i in range(tree.topLevelItemCount())]


def test_the_panel_of_the_attached_files(window, tmp_path, monkeypatch):
    assert window.a_attachments.shortcut().toString() == "F9" and window.attach_dock.isHidden()
    window.a_attachments.trigger()
    QApplication.processEvents()
    assert names(window) == [("data.csv", "Document"), ("note.txt", "Page 3")]
    tree = window.attach_list
    assert tree.topLevelItem(0).text(1) == "8 B" and tree.topLevelItem(0).text(3) == "The numbers"
    assert window.attach_count.text() == "2 attached files"
    # Abrir: una copia en una carpeta propia, abierta por el escritorio
    opened = []
    monkeypatch.setattr(attachments.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    path = window.open_attached(tree.topLevelItem(0))
    # (como rutas: en Windows, Qt da C:/... y Python C:\\...)
    assert path.read_bytes() == b"a,b\n1,2\n" and [Path(p) for p in opened] == [path]
    # Guardar los dos en una carpeta; otra vez, sin pisar los que ya están
    tree.selectAll()
    out = tmp_path / "out"
    out.mkdir()
    saved = window.save_attached(out)
    assert sorted(p.name for p in saved) == ["data.csv", "note.txt"]
    again = window.save_attached(out)
    assert sorted(p.name for p in again) == ["data (2).csv", "note (2).txt"]
    assert (out / "note.txt").read_bytes() == b"note text"
    # Añadir uno al documento (con un nombre que ya está), deshacer
    extra = tmp_path / "data.csv"
    extra.write_bytes(b"other")
    assert window.add_attached([extra])
    assert [n for n, w in names(window) if w == "Document"] == ["data.csv", "data (2).csv"]
    window.undo()
    assert names(window) == [("data.csv", "Document"), ("note.txt", "Page 3")]
    # Quitar los dos: el del documento y la anotación de la página
    tree.selectAll()
    assert window.remove_attached()
    assert names(window) == [] and window.attach_count.text() == "No attached files"
    assert window.doc.embfile_count() == 0 and not [a for a in window.annotations if a.kind == "attachment"]


def test_sizes():
    assert attachments.size_text(512) == "512 B"
    assert attachments.size_text(3500) == "3.4 KB"
    assert attachments.size_text(5 * 1024 * 1024) == "5.0 MB"


def test_old_opened_copies_are_deleted(tmp_path, monkeypatch):
    """The copies of attached files opened go in a folder of the program's own; at a start, those of more than
    two days ago are deleted (not when the window closes: another program may have one open, or changed); a file
    changed since counts from then."""
    import os
    import time

    monkeypatch.setattr(attachments.tempfile, "tempdir", str(tmp_path))
    old, recent, touched = (attachments.opened_folder() for _ in range(3))
    assert old.parent == recent.parent and old.parent.parent == tmp_path and old != recent
    for folder in (old, recent, touched):
        (folder / "data.csv").write_text("a,b\n")
    then = time.time() - 3 * 86400
    for path in (old / "data.csv", old, touched / "data.csv", touched):
        os.utime(path, (then, then))
    (touched / "data.csv").write_text("changed today\n")  # (saved there by the program that opened it)
    assert attachments.forget_opened() == 1
    assert not old.exists() and recent.exists() and touched.exists()
