"""La señal de comentario (gui/canvas.py, CommentSign): una anotación cuyo comentario no se ve en la página (un recuadro, una línea, un resaltado) lleva un globito junto a su esquina, con
el comentario en su ayuda emergente; una nota o un cuadro de texto, no."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from py_pdftools.annotate.annots import Annotation
from py_pdftools.gui.canvas import has_comment


def test_which_have_the_sign():
    rect = Annotation("rect", 0, (10, 10, 50, 50), "#e53935", contents="Move this")
    assert has_comment(rect)
    assert not has_comment(Annotation("rect", 0, (10, 10, 50, 50), "#e53935"))
    assert not has_comment(Annotation("rect", 0, (10, 10, 50, 50), "#e53935", contents="   "))
    assert has_comment(Annotation("line", 0, (10, 10, 50, 50), "#1e88e5", contents="why?"))
    assert has_comment(Annotation("highlight", 0, (10, 10, 50, 20), "#ffeb3b", contents="see p. 4"))
    # The comment is seen on the page already (a note's own sign, a text box's text), or it is the program's
    for kind in ("note", "freetext", "callout", "stamp"):
        assert not has_comment(Annotation(kind, 0, (10, 10, 50, 50), "#000000", contents="text")), kind
    assert not has_comment(Annotation("ink", 0, (10, 10, 50, 50), "#000000", contents="Signature"))
    assert has_comment(Annotation("ink", 0, (10, 10, 50, 50), "#000000", contents="my drawing"))


@pytest.fixture
def window(tmp_path, monkeypatch):
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "d.pdf")
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(1000, 800)
    w.show()
    assert w.open_path(tmp_path / "d.pdf")
    yield w
    w.annotations = w.saved = []  # (closing with changes would ask whether to save them)
    w.drop_work()
    w.close()


def test_the_sign_on_the_page(window):
    w = window
    w.add(Annotation("rect", 0, (100, 100, 200, 160), "#e53935", contents="Move this paragraph"))
    w.add(Annotation("rect", 0, (100, 300, 200, 360), "#43a047"))
    items = {i.annot.color: i for i in w.canvas.items_}
    sign = items["#e53935"].sign
    assert sign is not None and items["#43a047"].sign is None
    assert "Move this paragraph" in sign.toolTip()  # (pointing at the sign shows the comment)
    # At its corner, and of the same size on the screen whatever the zoom (it ignores the view's transformation)
    from PySide6.QtWidgets import QGraphicsItem

    assert sign.scenePos() == items["#e53935"].mapToScene(200, 100)
    assert sign.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    size = sign.boundingRect().size()
    w.canvas.set_zoom(w.canvas.zoom() * 3)
    QApplication.processEvents()
    sign = next(i for i in w.canvas.items_ if i.annot.color == "#e53935").sign
    assert sign.boundingRect().size() == size
    # The comment taken away: the sign goes
    i = next(n for n, a in enumerate(w.annotations) if a.color == "#e53935")
    w.change([a if n != i else a.__class__(**{**a.__dict__, "contents": ""}) for n, a in enumerate(w.annotations)])
    assert all(item.sign is None for item in w.canvas.items_)
