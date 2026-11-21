"""Digital IDs (signatures/ids.py, File > Digital signatures > Create a digital ID): a self-signed ID made and
read back with its password, its certificate beside it, what it says of its owner; and trusted
certificates kept. (They need pyHanko and cryptography: without them, the tests are skipped.)"""

from __future__ import annotations

import pytest

pytest.importorskip("pyhanko")

from py_pdftools.signatures import ids  # noqa: E402

WHO = ids.Identity("Ana Pérez", "ana@example.org", "Universidad", "co")


def test_make_and_read(tmp_path):
    cer = ids.make_id(WHO, "secret1", tmp_path / "ana.p12", years=2)
    assert cer == tmp_path / "ana.cer" and cer.read_bytes().startswith(b"-----BEGIN CERTIFICATE")
    key, cert = ids.read_id(tmp_path / "ana.p12", "secret1")
    assert ids.describe(cert) == "Ana Pérez <ana@example.org>"
    assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days in (729, 730)
    assert cert.issuer == cert.subject  # (self-signed)
    with pytest.raises(ids.IdError):
        ids.read_id(tmp_path / "ana.p12", "wrong")
    with pytest.raises(ids.IdError):
        ids.read_id(tmp_path / "missing.p12", "x")


@pytest.mark.parametrize("who, password", [(ids.Identity(" "), "secret1"), (WHO, "short"),
                                           (ids.Identity("A", country="COL"), "secret1")])
def test_refused(tmp_path, who, password):
    with pytest.raises(ids.IdError):
        ids.make_id(who, password, tmp_path / "x.p12")


def test_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("PY_PDFTOOLS_CONFIG", str(tmp_path / "config"))
    assert ids.trusted() == []
    cer = ids.make_id(WHO, "secret1", tmp_path / "ana.p12")
    first = ids.trust(cer.read_bytes(), "Ana Pérez")
    assert ids.trusted() == [first] and ids.trust(cer.read_bytes(), "Ana Pérez") == first  # (not twice)


def test_in_the_window(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.signing import IdDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    d = IdDialog(author="Ana")
    assert not d.b_ok.isEnabled()
    d.password.setText("secret1")
    assert "not the same" in d.problem.text()
    d.again.setText("secret1")
    assert d.b_ok.isEnabled() and d.identity().name == "Ana"
    w = MainWindow()
    try:
        assert w.a_make_id.isEnabled()
        w.ask_id = lambda: (WHO, 1, "secret1", tmp_path / "ana.p12")
        assert w.make_id_dialog() == tmp_path / "ana.p12"
        assert (tmp_path / "ana.cer").is_file() and "ana.cer" in w.statusBar().currentMessage()
    finally:
        w.close()
