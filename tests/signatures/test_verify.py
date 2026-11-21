"""Checking signatures (signatures/verify.py, File > Digital signatures > Check the signatures): a signature
valid but not trusted, then trusted; one with changes after it; one whose document was changed (invalid);
the version a signature signed cut out; and the window. (They need pyHanko: without it, they are skipped.)"""

from __future__ import annotations

import pymupdf
import pytest

pytest.importorskip("pyhanko")

from py_pdftools.signatures import ids, sign, verify  # noqa: E402
from py_pdftools.signatures.sign import Options  # noqa: E402


@pytest.fixture
def signed(tmp_path, monkeypatch):
    monkeypatch.setenv("PY_PDFTOOLS_CONFIG", str(tmp_path / "config"))
    ids.make_id(ids.Identity("Ana Pérez", "ana@example.org"), "secret1", tmp_path / "ana.p12")
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), "Contract", fontsize=12)
    d.save(tmp_path / "c.pdf")
    sign.sign(tmp_path / "c.pdf", tmp_path / "s.pdf", Options(tmp_path / "ana.p12", "secret1", "I agree", "Bogotá",
                                                              page=0, rect=(72, 600, 272, 660)))
    return tmp_path / "s.pdf"


def test_trusted_or_not(signed):
    [r] = verify.check(signed)
    assert (r.intact, r.valid, r.trusted, r.changes, r.whole) == (True, True, False, "NONE", True)
    assert r.signer == "Ana Pérez <ana@example.org>" and r.reason == "I agree" and r.location == "Bogotá"
    assert "not among those trusted" in r.verdict and not r.good
    verify.trust(r)
    [r] = verify.check(signed)
    assert r.trusted and r.good and "trusted" in r.verdict


def test_changed_after_and_broken(signed, tmp_path):
    import shutil

    later = tmp_path / "later.pdf"
    shutil.copy(signed, later)
    with pymupdf.open(later) as d:
        d[0].insert_text((300, 300), "added")
        d.save(later, incremental=True, encryption=0)
    [r] = verify.check(later)
    assert r.intact and r.valid and not r.whole and r.changes == "OTHER" and not r.good
    version = verify.signed_version(later, r, tmp_path / "v.pdf")
    assert version.read_bytes() == signed.read_bytes()  # (the document as it was signed)
    with pymupdf.open(signed) as d:
        d[0].insert_text((300, 300), "rewritten")
        d.save(tmp_path / "rewritten.pdf", garbage=3)
    [r] = verify.check(tmp_path / "rewritten.pdf")
    assert not r.intact and r.verdict.startswith("Invalid")
    assert verify.check(tmp_path / "c.pdf") == []


def test_in_the_window(signed, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(signed)
        assert "signed once" in w.statusBar().currentMessage()
        d = w.signatures_dialog()
        assert d.tree.topLevelItemCount() == 1 and d.b_trust.isEnabled()
        assert "Ana Pérez" in d.details.toPlainText()
        d.b_trust.click()
        assert d.reports[0].trusted and not d.b_trust.isEnabled()
        other = w._open_signed(d.reports[0])
        assert other is not None and other.path.read_bytes() == signed.read_bytes() and other is not w
        other.close()
        d.close()
        app.processEvents()
    finally:
        w.close()
