"""Herramientas > Aplicar pasos a varios archivos (pages/steps.py y gui/steps_dialog.py): los pasos en su orden sobre
cada archivo, los errores de uno sin detener los demás, los nombres que nunca escriben encima, las series
guardadas, y el diálogo, que trabaja en un hilo."""

from __future__ import annotations

import threading
import time

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from py_pdftools.pages import steps


def pdf(path, text):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text, fontsize=14)
    doc.save(path)
    return path


def test_the_steps_in_their_order(tmp_path):
    files = [pdf(tmp_path / "a.pdf", "Alpha"), pdf(tmp_path / "b.pdf", "Beta")]
    (tmp_path / "broken.pdf").write_text("not a PDF")
    files.append(tmp_path / "broken.pdf")
    plan = [steps.Step("headfoot", {"footer": "Page $page"}), steps.Step("watermark", {"text": "DRAFT"}),
            steps.Step("reduce", {"level": "lossless"})]
    seen = []
    out = steps.run(files, plan, tmp_path / "out", "-done", progress=lambda d, t, w: seen.append((d, t, w)))
    assert [o.target.name if o.target else None for o in out] == ["a-done.pdf", "b-done.pdf", None]
    assert out[2].error.startswith("Header and footer: ") and "broken.pdf" in out[2].error
    assert "py-pdftools-steps-" not in out[2].error  # (the temporary file is not named)
    assert pymupdf.open(out[0].target)[0].get_text().split() == ["Alpha", "Page", "1", "DRAFT"]
    assert seen[0] == (0, 9, "a.pdf: Header and footer") and seen[-1] == (9, 9, "")
    assert pymupdf.open(files[0])[0].get_text().split() == ["Alpha"]  # (the original untouched)


def test_never_over_a_file(tmp_path):
    source = pdf(tmp_path / "a.pdf", "A")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "a-x.pdf").write_text("there")
    assert steps.target_for(source, tmp_path / "out", "-x").name == "a-x (2).pdf"
    assert steps.target_for(source, tmp_path, "").name == "a (2).pdf"  # (not over itself)


def test_what_cannot_run(tmp_path, monkeypatch):
    with pytest.raises(steps.StepsError):
        steps.Step("watermark", {"text": " "}).argv(tmp_path / "a", tmp_path / "b")
    with pytest.raises(steps.StepsError):
        steps.Step("headfoot", {"header": "", "footer": ""}).argv(tmp_path / "a", tmp_path / "b")
    with pytest.raises(steps.StepsError):
        steps.run([tmp_path / "a.pdf"], [], tmp_path, "")
    from py_pdftools.core import ocr

    monkeypatch.setattr(ocr, "available", lambda: False)
    with pytest.raises(steps.StepsError, match="tesseract"):
        steps.run([tmp_path / "a.pdf"], [steps.Step("ocr")], tmp_path, "")


def test_stopping(tmp_path):
    files = [pdf(tmp_path / f"{n}.pdf", str(n)) for n in range(3)]
    stop = threading.Event()
    stop.set()
    assert steps.run(files, [steps.Step("reduce")], tmp_path / "out", "-s", stop=stop) == []


def test_recipes(tmp_path):
    assert steps.recipes() == {}
    plan = [steps.Step("ocr", {"languages": "lat+spa", "rotate": True}), steps.Step("pdfa", {"standard": "a-3b"})]
    steps.keep_recipe("Scans", plan)
    steps.keep_recipe("Other", [steps.Step("reduce")])
    found = steps.recipes()
    assert sorted(found) == ["Other", "Scans"]
    assert [(s.kind, s.settings) for s in found["Scans"]] == [(s.kind, s.settings) for s in plan]
    steps.keep_recipe("Other", None)
    assert sorted(steps.recipes()) == ["Scans"]
    steps.recipes_path().write_text("{not json")
    assert steps.recipes() == {}  # (a file that can't be read: none, and no error)


def test_the_dialog(tmp_path, monkeypatch):
    from py_pdftools.gui.steps_dialog import StepsDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert w.open_path(pdf(tmp_path / "doc.pdf", "Doc"))
    d = StepsDialog(w)
    try:
        assert [d.files.item(r).text() for r in range(d.files.count())] == ["doc.pdf"]  # (the document open)
        d.add_paths([pdf(tmp_path / "two.pdf", "Two"), tmp_path / "notes.txt"])  # (only PDFs)
        assert d.files.count() == 2
        assert not d.start() and "step" in d.report.toPlainText()  # (no step chosen)
        # Watermark, then Reduced file size, ticked; Reduced first (dragged above)
        for r in range(d.steps.count()):
            if d.steps.item(r).data(Qt.ItemDataRole.UserRole).kind in ("watermark", "reduce"):
                d.steps.item(r).setCheckState(Qt.CheckState.Checked)
        reduce_row = next(r for r in range(d.steps.count())
                          if d.steps.item(r).data(Qt.ItemDataRole.UserRole).kind == "reduce")
        d.steps.insertItem(0, d.steps.takeItem(reduce_row))
        assert [s.kind for s in d.chosen_steps()] == ["reduce", "watermark"]
        d.steps.setCurrentRow(next(r for r in range(d.steps.count())
                                   if d.steps.item(r).data(Qt.ItemDataRole.UserRole).kind == "watermark"))
        d.fields["watermark"]["text"].setText("COPY")
        d.fields["watermark"]["text"].textEdited.emit("COPY")
        d.folder.setText(str(tmp_path / "done"))
        assert d.start()
        end = time.time() + 60
        while d.thread.is_alive() and time.time() < end:
            QApplication.processEvents()
            time.sleep(0.02)
        QApplication.processEvents()
        assert "2 files written" in d.report.toPlainText() and d.b_run.isEnabled()
        made = tmp_path / "done" / "doc-processed.pdf"
        assert "COPY" in pymupdf.open(made)[0].get_text()
        # Kept as a recipe, and read back
        monkeypatch.setattr("PySide6.QtWidgets.QInputDialog.getText", lambda *a, **k: ("Mine", True))
        assert d.keep_recipe()
        d.load_steps([])
        d.load_recipe("Mine")
        assert [s.kind for s in d.chosen_steps()] == ["reduce", "watermark"]
        assert d.chosen_steps()[1].value("text") == "COPY"
    finally:
        d.reject()
        w.drop_work()
        w.close()
