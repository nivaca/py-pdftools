"""The engines that draw the pages (core/backends.py): MuPDF, PDFium (Qt PDF or pypdfium2) and Poppler (pdftoppm)
draw each page and each tile at the size and in the place MuPDF does, also turned and cropped; the annotations
the window draws itself are left out, the others kept; an engine that fails leaves the page to MuPDF; and, in the
window, the setting, the question on opening and the change of engine."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.core import backends, rendering

OTHERS = [b for b in (backends.PDFIUM, backends.POPPLER) if not backends.why_not(b)]


@pytest.fixture
def pdf(tmp_path):
    """Three pages: plain, turned 90 degrees, and with a crop box apart from the media box."""
    path = tmp_path / "engines.pdf"
    d = pymupdf.open()
    for i in range(3):
        p = d.new_page(width=595, height=842)
        p.insert_text((72, 100), f"Page {i + 1}: the quick brown fox", fontsize=24)
        p.draw_rect(pymupdf.Rect(100, 300, 300, 500), color=(1, 0, 0), fill=(0, 0, 1), width=4)
    d[1].set_rotation(90)
    d[2].set_cropbox(pymupdf.Rect(50, 60, 500, 760))
    d.save(path)
    return path


def mean_difference(a: pymupdf.Pixmap, b: pymupdf.Pixmap) -> float:
    sa, sb = a.samples, b.samples
    step = max(1, len(sa) // 100000)
    return sum(abs(sa[i] - sb[i]) for i in range(0, len(sa), step)) / (len(sa) / step)


@pytest.mark.skipif(not OTHERS, reason="neither PDFium nor Poppler is here")
@pytest.mark.parametrize("backend", OTHERS)
@pytest.mark.parametrize("number", [0, 1, 2])
@pytest.mark.parametrize("clip", [None, (100, 250, 350, 550)])
def test_same_size_and_place(pdf, backend, number, clip):
    page = pymupdf.open(pdf)[number]
    mupdf = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False,
                            clip=pymupdf.Rect(clip) if clip else None)
    other = backends._other(page, 1.5, clip, backend)
    assert (other.width, other.height) == (mupdf.width, mupdf.height)
    # (otro motor suaviza los bordes a su manera: solo eso difiere, no el lugar de lo dibujado)
    assert mean_difference(mupdf, other) < 5


@pytest.mark.skipif(not OTHERS, reason="neither PDFium nor Poppler is here")
@pytest.mark.parametrize("backend", OTHERS)
def test_annotations_of_the_window_left_out(tmp_path, backend):
    """A page drawn bare (the window draws its annotations itself) has none of them, with any engine; drawn whole,
    it has them."""
    path = tmp_path / "annotated.pdf"
    d = pymupdf.open()
    page = d.new_page(width=300, height=300)
    annot = page.add_rect_annot(pymupdf.Rect(50, 50, 250, 250))
    annot.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
    annot.update()
    d.save(path)
    stamp = (path.stat().st_mtime_ns, path.stat().st_size)

    def red(bare: bool) -> int:
        w, h, stride, data = rendering.render(str(path), "", stamp, 0, 1.0, bare=bare, backend=backend)[:4]
        pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, b"".join(data[r * stride: r * stride + w * 3] for r in range(h)),
                             False)
        return sum(1 for y in range(0, h, 10) for x in range(0, w, 10)
                   if pix.pixel(x, y)[0] > 200 and pix.pixel(x, y)[1] < 80)

    assert red(False) > 100 and red(True) == 0


def test_another_engine_that_fails_leaves_it_to_mupdf(pdf, monkeypatch):
    page = pymupdf.open(pdf)[0]

    def broken(*args):
        raise backends.BackendError("broken")

    monkeypatch.setattr(backends, "_other", broken)
    monkeypatch.setattr(backends, "why_not", lambda backend: "")
    pix = backends.draw(page, 1.0, None, backends.POPPLER)
    assert pix.samples == page.get_pixmap(alpha=False).samples


def test_what_each_needs(monkeypatch):
    monkeypatch.setattr(backends, "_pdftoppm", lambda: None)
    monkeypatch.setattr(backends, "_qtpdf", lambda: False)
    monkeypatch.setattr(backends, "_pypdfium2", lambda: False)
    assert backends.available() == [backends.MUPDF]
    assert "pdftoppm" in backends.why_not(backends.POPPLER) and "pypdfium2" in backends.why_not(backends.PDFIUM)
    assert backends.why_not(backends.MUPDF) == "" and backends.why_not("other")


def test_renderer_keeps_engines_apart():
    """The same page asked for with two engines is two drawings, not one."""
    from py_pdftools.gui.renderer import Renderer

    r = Renderer()
    try:
        source = ("/nowhere.pdf", "", (1, 1), False)
        r.request("view", source, 0, 1.0, lambda image: None, backend=backends.MUPDF)
        r.request("view", source, 0, 1.0, lambda image: None, backend=backends.POPPLER)
        keys = list(r.lanes["view"].callbacks)
        assert len(keys) == 2 and {k[-1] for k in keys} == {backends.MUPDF, backends.POPPLER}
    finally:
        r.shutdown()


# ----------------------------------------------------------------- the window

@pytest.fixture
def window(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    yield w
    w.annotations = w.saved = []
    w.close()


def test_the_setting_and_the_question(window, pdf, tmp_path, monkeypatch):
    from py_pdftools.core import config
    from py_pdftools.gui import backend_dialog

    monkeypatch.setattr(backends, "available", lambda: [backends.MUPDF, backends.POPPLER])
    monkeypatch.setattr(backends, "why_not", lambda b: "")
    config.set("backend", backends.POPPLER)
    assert window.open_path(pdf) and window.canvas.backend == backends.POPPLER
    # Preguntando: lo elegido; cancelada la pregunta, el documento de antes sigue abierto, con su motor.
    config.set("ask_backend", True)
    other = tmp_path / "other.pdf"
    other.write_bytes(pdf.read_bytes())
    monkeypatch.setattr(backend_dialog.BackendDialog, "exec", lambda self: 0)
    assert not window.open_path(other) and window.path == pdf and window.canvas.backend == backends.POPPLER

    def chosen(self):
        self.buttons[backends.MUPDF].setChecked(True)
        return 1

    monkeypatch.setattr(backend_dialog.BackendDialog, "exec", chosen)
    assert window.open_path(other) and window.path == other and window.canvas.backend == backends.MUPDF
    # An engine chosen in the settings that isn't here: MuPDF.
    config.set("ask_backend", False)
    config.set("backend", "nothing")
    assert window.ask_backend(other) == backends.MUPDF


def test_changed_in_the_settings(window, pdf):
    from py_pdftools.core import config
    from py_pdftools.gui.prefs import SettingsDialog
    from py_pdftools.gui.window import _WINDOWS

    assert window.open_path(pdf) and window.canvas.backend == backends.MUPDF
    _WINDOWS.append(window)
    try:
        dialog = SettingsDialog(window.prefs, window)
        index = dialog.backend.findData(backends.POPPLER)
        dialog.backend.setCurrentIndex(index)
        enabled = dialog.backend.model().item(index).isEnabled()
        assert dialog.put_in_effect()
        if enabled:  # (pdftoppm is here: the document is drawn with it now)
            assert config.get("backend") == backends.POPPLER and window.canvas.backend == backends.POPPLER
        dialog.close()
    finally:
        _WINDOWS.remove(window)


def test_system_check():
    from py_pdftools.core import config, health

    check = health.engines()
    assert check.status in (health.OK, health.INFO) and "MuPDF" in check.detail
    config.set("backend", "nothing")
    assert health.engines().status == health.WARNING
