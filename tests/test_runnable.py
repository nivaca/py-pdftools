"""Los archivos que correrían en lugar de abrirse (programas, guiones, instaladores: core/runnable.py): un PDF
puede traerlos adjuntos, o enlazarlos con una dirección file:. No se abren; el usuario sabe por qué, y puede
guardarlos para decidir él."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate.annots import Annotation
from py_pdftools.core.runnable import could_run
from py_pdftools.gui import attachments
from py_pdftools.gui.window import MainWindow


def test_which_files_would_run():
    for name in ("invoice.exe", "INVOICE.EXE", "bill.pdf.exe", "bill.exe.", "bill.exe ", "setup.msi", "run.sh",
                 "x.js", "x.vbs", "Thing.app", "a.desktop", "tool.AppImage", "script.py", "link.lnk", "/tmp/a/b.bat"):
        assert could_run(name), name
    for name in ("data.csv", "note.txt", "paper.pdf", "photo.JPG", "exe", "notes.exe.txt", "README", ""):
        assert not could_run(name), name


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "carrier.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.embfile_add("invoice.exe", b"MZ...", filename="invoice.exe")
    doc.embfile_add("data.csv", b"a,b\n", filename="data.csv")
    doc.save(path)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1400, 900)
    w.show()
    assert w.open_path(path)
    QApplication.processEvents()
    opened, asked = [], []
    monkeypatch.setattr(attachments.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    w.ask_save_runnable = lambda name, can_save=True: asked.append((name, can_save)) or False
    w.opened, w.asked = opened, asked
    yield w
    w.annotations = w.saved = []
    w.drop_work()
    w.close()


def test_an_attached_program_is_not_opened(window):
    window.a_attachments.trigger()
    QApplication.processEvents()
    tree = window.attach_list
    item = {tree.topLevelItem(i).text(0): tree.topLevelItem(i) for i in range(tree.topLevelItemCount())}
    assert window.open_attached(item["invoice.exe"]) is None
    assert window.asked == [("invoice.exe", True)] and window.opened == []
    assert window.open_attached(item["data.csv"]) is not None and len(window.opened) == 1  # (the others open)


def test_nor_from_its_annotation(window, monkeypatch):
    saved = []
    monkeypatch.setattr(window, "save_attachment", lambda a, target=None: saved.append(target))
    window.ask_save_runnable = lambda name, can_save=True: window.asked.append(name) or True  # (save it)
    window.open_attachment(Annotation("attachment", 0, (10, 10, 26, 26), data=b"#!/bin/sh", filename="run.sh"))
    assert window.asked == ["run.sh"] and window.opened == [] and saved == [None]  # (saved where the user says)


def test_nor_a_link_to_one(window, tmp_path):
    from py_pdftools.core import config

    config.set("ask_links", False)
    assert not window.open_address(Path(tmp_path / "evil.sh").as_uri())
    assert window.asked == [("evil.sh", False)] and window.opened == []  # (nothing to save: it is there already)
    assert window.open_address("https://example.org")
    assert window.opened == ["https://example.org"]
