"""Signing (signatures/sign.py, File > Digital signatures > Sign the document): visibly in an area drawn on the
page (also turned and protected), in an empty field of the form, or invisibly; certifying the document;
a second signature after the first; the wrong password refused; and the window, which opens the signed
copy. (They need pyHanko: without it, the tests are skipped.)"""

from __future__ import annotations

import pymupdf
import pytest

pytest.importorskip("pyhanko")

from py_pdftools.signatures import ids, sign  # noqa: E402
from py_pdftools.signatures.sign import Options, SignError  # noqa: E402


@pytest.fixture(scope="module")
def digital_id(tmp_path_factory):
    folder = tmp_path_factory.mktemp("id")
    ids.make_id(ids.Identity("Ana Pérez", "ana@example.org"), "secret1", folder / "ana.p12")
    return folder / "ana.p12"


@pytest.fixture
def doc(tmp_path):
    d = pymupdf.open()
    for i in range(2):
        d.new_page().insert_text((72, 72), f"Contract, page {i + 1}", fontsize=12)
    d.save(tmp_path / "c.pdf")
    return tmp_path / "c.pdf"


def signatures(path, password=""):
    with pymupdf.open(path) as d:
        if d.needs_pass:
            d.authenticate(password)
        return [(w.field_name, n, (pymupdf.Rect(w.rect) * d[n].rotation_matrix).normalize())
                for n in range(d.page_count) for w in d[n].widgets() or []
                if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE]


def test_visible_and_then_another(doc, digital_id, tmp_path):
    out = tmp_path / "s.pdf"
    o = Options(digital_id, "secret1", "I agree", "Bogotá", page=1, rect=(72, 600, 272, 660), certify="forms")
    assert sign.sign(doc, out, o) == "Signature1"
    [(name, page, rect)] = signatures(out)
    assert page == 1 and abs(rect.x0 - 72) < 1 and abs(rect.y1 - 660) < 1
    assert "Ana Pérez" in pymupdf.open(out)[1].get_text()
    assert sign.sign(out, out, Options(digital_id, "secret1")) == "Signature2"  # (invisible; in place)
    assert sorted(s[0] for s in signatures(out)) == ["Signature1", "Signature2"]
    with pytest.raises(SignError):  # (only the first signature certifies)
        sign.sign(out, tmp_path / "x.pdf", Options(digital_id, "secret1", certify="none"))
    with pytest.raises(SignError):
        sign.sign(out, tmp_path / "x.pdf", Options(digital_id, "wrong"))


def test_empty_field_turned_and_protected(digital_id, tmp_path):
    from py_pdftools.core import protection

    d = pymupdf.open()
    page = d.new_page()
    page.set_rotation(90)
    d.save(tmp_path / "t.pdf")
    protection.protect(tmp_path / "t.pdf", tmp_path / "p.pdf", open_password="pw")
    sign.sign(tmp_path / "p.pdf", tmp_path / "ps.pdf", Options(digital_id, "secret1", page=0,
                                                              rect=(100, 100, 300, 160)), "pw")
    [(_, _, rect)] = signatures(tmp_path / "ps.pdf", "pw")
    assert abs(rect.x0 - 100) < 1 and abs(rect.y0 - 100) < 1  # (where it was drawn, as the page is shown)
    # an empty signature field, signed in
    first = tmp_path / "f.pdf"
    sign.sign(tmp_path / "t.pdf", first, Options(digital_id, "secret1", page=0, rect=(100, 100, 300, 160)))
    with pymupdf.open(first) as d2:
        assert sign.empty_fields(d2) == []
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields

    with open(tmp_path / "t.pdf", "rb") as f:
        w = IncrementalPdfFileWriter(f)
        fields.append_signature_field(w, fields.SigFieldSpec("Here", on_page=0, box=(50, 50, 200, 100)))
        with open(tmp_path / "e.pdf", "wb") as out:
            w.write(out)
    with pymupdf.open(tmp_path / "e.pdf") as d3:
        assert sign.empty_fields(d3) == ["Here"]
    assert sign.sign(tmp_path / "e.pdf", tmp_path / "es.pdf", Options(digital_id, "secret1", field="Here")) == "Here"
    with pymupdf.open(tmp_path / "es.pdf") as d4:
        assert sign.empty_fields(d4) == []


def test_in_the_window(doc, digital_id, tmp_path, monkeypatch):
    from gui_helpers import drag
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.signing import SignDialog
    from py_pdftools.gui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    d = SignDialog(None, str(digital_id), ["Here"], signed=True)
    assert not d.b_ok.isEnabled() and not d.certify.isEnabled()
    d.password.setText("secret1")
    assert d.b_ok.isEnabled() and d.chosen()[1] == "field:Here" and d.chosen()[0].field == "Here"
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1100, 800)
    w.show()
    try:
        assert w.open_path(doc)
        w.show_page(0)
        w._fit("page")
        app.processEvents()
        w.ask_sign = lambda empty, signed: (Options(digital_id, "secret1", "Seen"), "draw")
        w.ask_new_pdf = lambda title, name: tmp_path / "signed.pdf"
        assert w.sign_dialog() and w.canvas.mode == "signarea"
        drag(w, (72, 600), (272, 660), page=0)
        assert w.path == tmp_path / "signed.pdf" and w.canvas.mode != "signarea"
        assert signatures(tmp_path / "signed.pdf")[0][1] == 0
        # Escape, while the area is to be drawn: not signed
        w.ask_new_pdf = lambda title, name: tmp_path / "other.pdf"
        assert w.sign_dialog()
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent

        w.canvas.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        assert not (tmp_path / "other.pdf").exists() and w.canvas.mode != "signarea"
    finally:
        w.close()


def test_the_dialog_in_plain_steps(digital_id, tmp_path):
    """Sign digitally says what a digital ID is when there is none, and offers to make one; with one, whose it
    is and until when; the password is checked as it is typed; where the signature goes is said in words."""
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.signing import SignDialog

    QApplication.instance() or QApplication([])
    made = []
    d = SignDialog(None, "", [], on_create=lambda: made.append(1) or digital_id)
    assert not d.has_id() and "digital ID" in d.who.text() and not d.pw_box.isVisibleTo(d)
    assert not d.b_ok.isEnabled() and d.where == "draw"
    d.b_create.click()  # (the window makes it: see SignMixin.make_id_dialog)
    assert made and d.has_id() and d.pw_box.isVisibleTo(d)
    d.password.setText("wrong!")
    assert d.password_said.text() == "wrong password" and not d.b_ok.isEnabled()
    d.password.setText("secret1")
    assert d.password_said.text() == "✓" and d.b_ok.isEnabled()
    # Nowhere: an invisible signature
    d._place_buttons[-1].setChecked(True)
    options, where = d.chosen()
    assert where == "none" and options.password == "secret1" and options.id_path == digital_id
