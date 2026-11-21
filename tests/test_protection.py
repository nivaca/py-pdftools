"""Passwords (core/protection.py, File > Protect with passwords): a document protected to open, restricted
in what may be done, or both; its protection read, changed and removed only with the permissions password;
kept when annotations are saved; and set from the window, which opens the document again."""

from __future__ import annotations

import pikepdf
import pymupdf
import pytest

from py_pdftools.core import protection
from py_pdftools.core.protection import ProtectionError


@pytest.fixture
def plain(tmp_path):
    path = tmp_path / "plain.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Hello", fontsize=12)
    doc.save(path)
    return path


def test_password_to_open(plain, tmp_path):
    out = tmp_path / "o.pdf"
    protection.protect(plain, out, open_password="abc")
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(out)
    p = protection.read(out, "abc")
    assert p.encrypted and p.open_password and p.owner and p.method == "AES-256"
    assert p.allowed == {k for k, _ in protection.PERMISSIONS}  # (todos: no se pidió restricción)


def test_restrictions_only(plain, tmp_path):
    out = tmp_path / "r.pdf"
    protection.protect(plain, out, owner_password="boss", allowed={"print_highres"})
    p = protection.read(out)  # (it opens without a password...)
    assert p.encrypted and not p.open_password and not p.owner
    assert p.allowed == {"print_lowres", "print_highres"}  # (...restricted)
    assert pymupdf.open(out).permissions & pymupdf.PDF_PERM_COPY == 0
    assert protection.read(out, "boss").owner


def test_changing_and_removing_need_the_permissions_password(plain, tmp_path):
    out = tmp_path / "b.pdf"
    protection.protect(plain, out, open_password="user", owner_password="boss", allowed=set())
    with pytest.raises(ProtectionError):
        protection.unprotect(out, out, "user")
    with pytest.raises(ProtectionError):
        protection.protect(out, out, open_password="new", password="user")
    protection.protect(out, out, open_password="new", password="boss")
    assert protection.read(out, "new").open_password
    protection.unprotect(out, out, "new")  # (now the only password: it opens and gives all)
    assert not protection.read(out).encrypted
    assert pymupdf.open(out)[0].get_text().strip() == "Hello"


def test_a_password_is_needed(plain, tmp_path):
    with pytest.raises(ProtectionError):
        protection.protect(plain, tmp_path / "x.pdf")
    with pytest.raises(ProtectionError):
        protection.read(protection.protect(plain, tmp_path / "y.pdf", open_password="a") or tmp_path / "y.pdf")


def test_saving_annotations_keeps_a_permissions_password(plain, tmp_path):
    """A file with only a permissions password opens without asking; saved, it stays protected."""
    from py_pdftools.annotate import annots

    out = tmp_path / "r.pdf"
    protection.protect(plain, out, owner_password="boss", allowed={"modify_annotation"})
    note = annots.Annotation("rect", 0, (100, 100, 120, 120), contents="hi")
    annots.write(out, [note], tmp_path / "saved.pdf")
    p = protection.read(tmp_path / "saved.pdf")
    assert p.encrypted and p.allowed == {"modify_annotation"}


def test_the_dialog_checks_what_is_typed(app):
    from py_pdftools.gui.protect_dialog import ProtectDialog

    d = ProtectDialog(protection.Protection())
    assert not d.b_protect.isEnabled() and not d.b_remove.isVisible()
    d.open_pw.setText("a")
    assert "not the same" in d.problem_text()
    d.open_again.setText("a")
    assert d.b_protect.isEnabled()
    d.restrict.setChecked(True)
    d.owner_pw.setText("a")
    d.owner_again.setText("a")
    assert "must not be" in d.problem_text()
    d.owner_pw.setText("b")
    d.owner_again.setText("b")
    d.allow["extract"].setChecked(False)
    values = d.result_values()
    assert values["open_password"] == "a" and values["owner_password"] == "b"
    assert "extract" not in values["allowed"] and "print_lowres" in values["allowed"]


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_in_the_window(app, plain, tmp_path, monkeypatch):
    from py_pdftools.gui.window import MainWindow

    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(plain)
        w.ask_protection = lambda current: {"open_password": "pw", "owner_password": "boss",
                                            "allowed": {"print_highres"}}
        assert w.protection_dialog()
        assert w.password == "pw" and w.doc is not None and w.count == 1
        assert protection.read(plain, "pw").allowed == {"print_lowres", "print_highres"}
        # abierto con la contraseña de apertura, pide la de permisos para cambiarlos
        w.ask_owner_password = lambda: "wrong"
        assert not w.protection_dialog()
        w.ask_owner_password = lambda: "boss"
        w.ask_protection = lambda current: {"remove": True}
        assert w.protection_dialog()
        assert not protection.read(plain).encrypted and w.password == ""
    finally:
        w.close()
