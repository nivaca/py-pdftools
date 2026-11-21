"""The PDF version (pages/version.py, File > Save a copy > With another PDF version, py-pdftools
pdf-version): read from the header and the catalog; what the document uses since which version; a copy
lowered (without object streams below 1.5) or raised; AES-256 kept at 1.7 or above."""

from __future__ import annotations

import pikepdf
import pymupdf
import pytest

from py_pdftools.pages import version as V


@pytest.fixture
def doc(tmp_path):
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 72), "Hello", fontsize=12)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 1)
    pix.clear_with(100)
    p.insert_image(pymupdf.Rect(72, 100, 92, 120), pixmap=pix)  # (con transparencia)
    d.add_ocg("A layer", on=True)
    d.save(tmp_path / "d.pdf", use_objstms=1)
    return tmp_path / "d.pdf"


def test_read_and_features(doc, tmp_path):
    assert V.version_of(doc) == "1.7"
    assert V.features(doc) == {"transparency": "1.4", "object_streams": "1.5", "layers": "1.5"}
    assert V.newer_than(doc, "1.3") == ["Transparency (soft masks, transparency groups)", "Layers (optional content)"]
    assert V.newer_than(doc, "1.5") == []
    with pikepdf.open(doc) as pdf:  # (the catalog may say more than the header)
        pdf.Root.Version = pikepdf.Name("/2.0")
        pdf.save(tmp_path / "c.pdf", force_version="1.4")
    assert V.version_of(tmp_path / "c.pdf") == "2.0"


def test_lower_and_raise(doc, tmp_path):
    out = tmp_path / "o.pdf"
    assert V.set_version(doc, out, "1.4") == "1.7"
    assert out.read_bytes()[:8] == b"%PDF-1.4" and V.version_of(out) == "1.4"
    assert "object_streams" not in V.features(out)  # (written plainly)
    assert pymupdf.open(out)[0].get_text().strip() == "Hello"
    V.set_version(doc, out, "2.0")
    assert V.version_of(out) == "2.0"
    with pytest.raises(V.VersionError):
        V.set_version(doc, out, "3.1")


def test_aes256(doc, tmp_path):
    from py_pdftools.core import protection

    protection.protect(doc, tmp_path / "p.pdf", open_password="pw")
    with pytest.raises(V.VersionError):
        V.set_version(tmp_path / "p.pdf", tmp_path / "x.pdf", "1.6", "pw")
    V.set_version(tmp_path / "p.pdf", tmp_path / "y.pdf", "2.0", "pw")
    assert protection.read(tmp_path / "y.pdf", "pw").encrypted


def test_command_line(doc, tmp_path, capsys):
    from py_pdftools.cli import main

    assert main(["pdf-version", str(doc)]) == 0
    assert "PDF 1.7" in capsys.readouterr().out
    assert main(["pdf-version", str(doc), "--set", "1.4", "-o", str(tmp_path / "o.pdf")]) == 0
    assert "Layers" in capsys.readouterr().err and V.version_of(tmp_path / "o.pdf") == "1.4"
    assert main(["pdf-version", str(doc), "--set", "1.4"]) == 1


def test_in_the_window(doc, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.version_dialog import VersionDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    d = VersionDialog("1.7", lambda v: V.newer_than(doc, v))
    assert d.chosen() == "1.7" and d.warning.text() == ""
    d.version.setCurrentIndex(d.version.findData("1.3"))
    assert "Layers" in d.warning.text() and d.b_ok.isEnabled()
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(doc)
        w.ask_version = lambda current: "1.5"
        w.ask_new_pdf = lambda title, name: tmp_path / name
        assert w.save_version_dialog()
        assert V.version_of(tmp_path / "d-pdf15.pdf") == "1.5"
    finally:
        w.close()
