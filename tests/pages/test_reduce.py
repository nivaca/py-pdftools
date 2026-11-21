"""A smaller copy (pages/reduce.py, File > Save a copy > Smaller, py-pdftools reduce): pictures drawn again
at a lower resolution only when they are shown above it; the text kept; nothing made bigger; protection
kept; where the bytes go; and the window and the command line."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.pages import reduce
from py_pdftools.pages.reduce import Options


def noisy(w, h, seed=1):
    import random

    rnd = random.Random(seed)
    data = bytes(rnd.randrange(256) for _ in range(w * h * 3))
    return pymupdf.Pixmap(pymupdf.csRGB, w, h, data, 0)


@pytest.fixture
def heavy(tmp_path):
    """Two pages, each with a picture of 1200 × 800 pixels shown 2 inches wide (600 dpi), and text."""
    path = tmp_path / "heavy.pdf"
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page()
        page.insert_text((72, 72), f"Words on page {i + 1}", fontsize=12)
        page.insert_image(pymupdf.Rect(72, 100, 216, 196), pixmap=noisy(1200, 800, i))
    doc.save(path)
    return path


def widths(path):
    doc = pymupdf.open(path)
    return [img[2] for page in doc for img in page.get_images()]


def test_levels(heavy, tmp_path):
    sizes = {}
    for key, *_ in reduce.LEVELS:
        out = tmp_path / f"{key}.pdf"
        before, after = reduce.reduce(heavy, out, reduce.options_of(key))
        assert before == heavy.stat().st_size and after == out.stat().st_size
        sizes[key] = after
        assert [p.get_text().strip() for p in pymupdf.open(out)] == ["Words on page 1", "Words on page 2"]
    assert sizes["small"] < sizes["medium"] < sizes["high"] < heavy.stat().st_size
    assert sizes["lossless"] <= heavy.stat().st_size
    assert widths(tmp_path / "medium.pdf") == [300, 300]  # (2 pulgadas a 150 ppp)
    assert widths(tmp_path / "lossless.pdf") == [1200, 1200]


def test_pictures_already_small_are_left(tmp_path):
    path = tmp_path / "s.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_image(pymupdf.Rect(72, 72, 360, 264), pixmap=noisy(400, 266))  # (100 dpi)
    doc.save(path)
    reduce.reduce(path, tmp_path / "o.pdf", reduce.options_of("medium"))
    assert widths(tmp_path / "o.pdf") == [400]


def test_never_bigger_and_in_place(tmp_path, heavy):
    plain = tmp_path / "plain.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "x")
    doc.save(plain, garbage=4, deflate=True, use_objstms=1)
    before, after = reduce.reduce(plain, tmp_path / "o.pdf", Options(0, 0, False, False))
    assert after <= before and (tmp_path / "o.pdf").stat().st_size <= before
    size = heavy.stat().st_size
    reduce.reduce(heavy, heavy, reduce.options_of("small"))
    assert heavy.stat().st_size < size


def test_grey_and_protected(heavy, tmp_path):
    from py_pdftools.core import protection

    locked = tmp_path / "locked.pdf"
    protection.protect(heavy, locked, open_password="pw")
    out = tmp_path / "o.pdf"
    reduce.reduce(locked, out, Options(150, 75, True), "pw")
    assert pymupdf.open(out).needs_pass
    doc = pymupdf.open(out)
    doc.authenticate("pw")
    assert doc[0].get_images()[0][5] in ("DeviceGray", "ICCBased") and pymupdf.Pixmap(
        doc, doc[0].get_images()[0][0]).n == 1
    with pytest.raises(reduce.ReduceError):
        reduce.reduce(locked, out, Options())


def test_where_the_bytes_go(heavy):
    found = reduce.where(heavy)
    assert set(found) == {k for k, _ in reduce.KINDS}
    assert sum(found.values()) == heavy.stat().st_size
    assert found["images"] > 0.9 * heavy.stat().st_size


def test_command_line(heavy, tmp_path):
    from py_pdftools.cli import main

    out = tmp_path / "c.pdf"
    assert main(["reduce", str(heavy), "-o", str(out), "--dpi", "100"]) == 0
    assert widths(out) == [200, 200]
    assert main(["reduce", str(tmp_path / "missing.pdf"), "-o", str(out)]) == 1


def test_in_the_window(heavy, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.reduce_dialog import ReduceDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    try:
        assert w.open_path(heavy)
        d = ReduceDialog(reduce.where(heavy))
        d.buttons["small"].setChecked(True)
        d.gray.setChecked(True)
        assert d.options() == Options(96, 60, True, True)
        out = tmp_path / "o.pdf"
        w.ask_reduce = lambda found: Options(150, 75)
        w.ask_new_pdf = lambda title, name: out
        assert w.save_smaller_dialog()
        assert out.stat().st_size < heavy.stat().st_size and "% less" in w.statusBar().currentMessage()
    finally:
        w.close()
