"""OCR with the tesseract program (core/ocr.py): the words of a scan, read in other processes, with
their place and confidence; written as invisible text; pages lying sideways turned; the languages,
those installed and those downloaded."""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import pymupdf
import pytest

from py_pdftools.core import ocr

needs_tesseract = pytest.mark.skipif(not ocr.available() or "eng" not in ocr.languages(),
                                     reason="needs tesseract, with English")
LINES = ["The quick brown fox jumps over the lazy dog.", "Pack my box with five dozen liquor jugs.",
         "How vexingly quick daft zebras jump.", "Sphinx of black quartz, judge my vow."]


def scan(path: Path, rotation: int = 0, pages: int = 1) -> Path:
    """A PDF whose pages are pictures of text (as scanned), shown turned ROTATION degrees."""
    text = pymupdf.open()
    page = text.new_page()
    for i, line in enumerate(LINES * 3):
        page.insert_text((60, 90 + i * 34), line, fontsize=15)
    picture = page.get_pixmap(dpi=200)
    doc = pymupdf.open()
    for _ in range(pages):
        p = doc.new_page()
        p.insert_image(p.rect, pixmap=picture)
        p.set_rotation(rotation)
    doc.save(path)
    return path


@pytest.fixture
def own(tmp_path, monkeypatch):
    """py-pdftools' own folder of models, empty, in a folder of the test."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    return ocr.own_tessdata()


@needs_tesseract
def test_a_scan_read_and_written(tmp_path, own):
    path = scan(tmp_path / "scan.pdf", pages=2)
    seen = []
    results = ocr.run(path, "", [0, 1], "eng", progress=lambda done, of: seen.append((done, of)) or True)
    assert [r.number for r in results] == [0, 1] and seen[-1] == (2, 2)
    words = [w.text.strip(".,") for w in results[0].words]
    assert {"quick", "brown", "zebras", "quartz"} <= set(words)
    fox = next(w for w in results[0].words if w.text == "fox")
    assert 0 < fox.rect[0] < fox.rect[2] < 612 and 60 < fox.rect[1] < 120 and fox.confidence > ocr.DOUBTFUL
    doc = pymupdf.open(path)
    assert ocr.scanned(doc[0])
    assert ocr.write_words(doc[0], results[0], corrections={0: ""}) == len(results[0].words) - 1
    text = doc[0].get_text()
    assert not ocr.scanned(doc[0]) and "zebras" in text and "Sphinx" in text
    # (where the picture shows it: the word found is under the fox)
    found = doc[0].search_for("fox")[0]
    assert abs(found.x0 - fox.rect[0]) < 6 and abs(found.y1 - fox.rect[3]) < 6


@needs_tesseract
def test_doubtful_words_come_with_their_picture(tmp_path):
    """(read in this process: everything is doubtful below 101)"""
    path = scan(tmp_path / "scan.pdf")
    with __import__("tempfile").TemporaryDirectory() as folder:
        tessdata = str(ocr.tessdata_for(["eng"], Path(folder)))
        result = ocr.read_page(str(path), "", 0, "eng", tessdata, doubtful=101)
    assert result.doubtful(101) == list(result.words)
    picture = pymupdf.Pixmap(result.words[0].crop)
    assert picture.width > 10 and picture.height > 10


@needs_tesseract
@pytest.mark.skipif(not ocr.has_osd(), reason="needs tesseract's osd model")
@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_a_page_lying_sideways_is_turned(tmp_path, rotation):
    path = scan(tmp_path / "turned.pdf", rotation=rotation)
    (result,) = ocr.run(path, "", [0], "eng", rotate=True)
    assert result.rotate == (360 - rotation) % 360 and "quick" in [w.text for w in result.words]
    doc = pymupdf.open(path)
    ocr.write_words(doc[0], result)
    assert doc[0].rotation == 0 and "zebras" in doc[0].get_text()


def test_languages_installed_and_downloaded(tmp_path, own, monkeypatch):
    own.mkdir(parents=True)
    (own / "xyz.traineddata").write_bytes(b"model")
    assert "xyz" in ocr.languages() and ocr.better("xyz") and not ocr.better("nothing")
    assert ocr.parse_languages("xyz") == ["xyz"]
    for wrong in ("", "osd", "x y", "nothing"):
        with pytest.raises(ocr.OcrError):
            ocr.parse_languages(wrong)
    folder = ocr.tessdata_for(["xyz"], tmp_path / "run")
    assert (folder / "xyz.traineddata").read_bytes() == b"model"
    if ocr.system_tessdata() is not None and "eng" in ocr.languages():
        # (a downloaded model goes before the installed one of the same language)
        (own / "eng.traineddata").write_bytes(b"better")
        assert ocr.models()["eng"] == own / "eng.traineddata"


def test_download(own, monkeypatch):
    class Answer(io.BytesIO):
        headers = {"Content-Length": "11"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    asked = []

    def urlopen(request, timeout=0):
        asked.append(request.full_url)
        if "nope" in request.full_url:
            raise OSError("HTTP Error 404: Not Found")
        return Answer(b"model bytes")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    sizes = []
    (made,) = ocr.download(["lat"], progress=lambda done, total: sizes.append((done, total)) or True)
    assert made == own / "lat.traineddata" and made.read_bytes() == b"model bytes" and sizes[-1] == (11, 11)
    assert asked == [ocr.BEST_URL.format(name="lat")] and ocr.better("lat")
    with pytest.raises(ocr.OcrError, match="no such language"):
        ocr.download(["nope"])
    assert not (own / "nope.part").exists() and not (own / "nope.traineddata").exists()
    with pytest.raises(ocr.OcrError):
        ocr.download(["../x"])


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
    w.drop_work()
    w.close()


@needs_tesseract
def test_text_recognised_into_the_document(window, tmp_path):
    """The text read goes into the document as a change of it: undone and redone like the others, and
    corrected where the review said so."""
    path = scan(tmp_path / "scan.pdf", pages=2)
    assert window.open_path(path)
    results = window.recognise([0, 1], "eng")
    assert [r.number for r in results] == [0, 1]
    first = results[0].words[0].text
    assert window.write_recognised(results, {0: {0: "CORRECTED"}})
    assert window.work is not None and "CORRECTED" in window.doc[0].get_text() and "zebras" in window.doc[1].get_text()
    assert first not in window.doc[0].get_text().split()[:1]
    window.undo()
    assert window.doc[0].get_text().strip() == ""
    window.redo()
    assert "zebras" in window.doc[0].get_text()
    # (read again: those pages have text now, and are left out)
    assert window.recognise([0, 1], "eng") is None


@needs_tesseract
def test_the_mode_ocr(window, tmp_path, monkeypatch):
    """The dialog of the menu of the thumbnails, and the mode OCR: its panel chooses the pages and the
    languages, reads them, and writes the text after the doubtful words were checked."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from py_pdftools.gui import ocr_dialog

    path = scan(tmp_path / "scan.pdf", pages=3)
    assert window.open_path(path)
    dialog = ocr_dialog.OcrDialog(window, 3, [0, 1, 2], [], 1, "eng")
    o = dialog.options
    assert o.all.isChecked() and not o.chosen.isEnabled() and o.page_list() == [0, 1, 2]
    assert o.language() == "eng" and o.languages.item(0).data(Qt.ItemDataRole.UserRole) == "eng"
    o.pages.setText("2-")
    o.listed.setChecked(True)
    assert o.page_list() == [1, 2]
    o.pages.setText("9")
    dialog.accept()
    assert dialog.result() == 0 and "out of range" in o.problem.text()
    o.pages.setText("1")
    o.languages.item(0).setCheckState(Qt.CheckState.Unchecked)
    dialog.accept()
    assert dialog.result() == 0 and "no language" in o.problem.text()
    dialog.reject()

    # (the mode: pages 1 and 3, every word under 100 % doubtful, one corrected in the review)
    window.set_mode("ocr")
    panel = window.ocr_options
    assert "3 pages are scans" in window.ocr_summary.text() and panel.all.isChecked()
    panel.listed.setChecked(True)
    panel.pages.setText("1, 3")
    panel.doubtful.setValue(100)

    def review(self):
        assert self.fields and all(page in (0, 2) for page, *_ in self.fields)
        self.fields[0][3].setText("FIXED")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ocr_dialog.ReviewDialog, "exec", review)
    assert window.recognise_from_panel()
    assert window.doc[0].get_text().split()[0] == "FIXED" and window.doc[1].get_text().strip() == ""
    assert "zebras" in window.doc[2].get_text()
    assert "1 page is a scan" in window.ocr_summary.text()


@needs_tesseract
def test_the_languages_dialog(window, own, monkeypatch):
    """Every language, with what there is of it here; better models downloaded and removed."""
    from py_pdftools.gui.ocr_languages import LanguagesDialog
    from py_pdftools.gui.prefs import SettingsDialog

    def download(names, progress=None):
        own.mkdir(parents=True, exist_ok=True)
        for n in names:
            (own / f"{n}.traineddata").write_bytes(b"x" * 2_000_000)
            progress(1, 1)
        return []

    monkeypatch.setattr(ocr, "download", download)
    settings = SettingsDialog(window.prefs, window)
    assert ocr.version() in settings.ocr_found.text()
    dialog = LanguagesDialog(window)
    rows = {dialog.table.item(r, 0).text(): r for r in range(dialog.table.rowCount())}
    assert {"eng", "lat", "grc", "osd"} <= set(rows) and dialog.table.item(rows["eng"], 2).text() == "yes"
    assert rows["eng"] < rows["grc"]  # (those there first)
    dialog.filter.setText("greek")
    shown = [dialog.table.item(r, 0).text() for r in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(r)]
    assert set(shown) == {"ell", "grc"}
    dialog.table.selectRow(rows["grc"])
    assert dialog.download.isEnabled() and not dialog.remove.isEnabled()
    assert dialog.download_chosen() and ocr.better("grc") and "grc" in ocr.languages()
    rows = {dialog.table.item(r, 0).text(): r for r in range(dialog.table.rowCount())}
    assert dialog.table.item(rows["grc"], 3).text().startswith("2 MB")
    dialog.table.selectRow(rows["grc"])
    assert dialog.remove.isEnabled() and dialog.remove_chosen() and not ocr.better("grc")
    with pytest.raises(ocr.OcrError):
        ocr.remove("grc")
    dialog.reject()
    settings.reject()


@needs_tesseract
def test_command_line(tmp_path, own, capsys, monkeypatch):
    from py_pdftools.cli import main

    path = scan(tmp_path / "scan.pdf", pages=2)
    assert main(["ocr", str(path), "-l", "eng", "--pages", "2", "--report", "--doubtful", "101"]) == 0
    out = capsys.readouterr().out
    written = tmp_path / "scan-ocr.pdf"
    assert f"Wrote {written}" in out and "1 page read" in out
    assert any(line.startswith("2\t") for line in out.splitlines())  # (the doubtful words of page 2)
    doc = pymupdf.open(written)
    assert doc[0].get_text().strip() == "" and "zebras" in doc[1].get_text()
    # (in place; and a second time, nothing left to read)
    assert main(["ocr", "-i", str(path), "-l", "eng"]) == 0
    assert "zebras" in pymupdf.open(path)[0].get_text()
    assert main(["ocr", "-i", str(path), "-l", "eng"]) == 0
    assert "no page of those chosen" in capsys.readouterr().out
    assert main(["ocr", "--languages"]) == 0 and "Tesseract" in capsys.readouterr().out
    assert main(["ocr", str(path), "-l", "klingon"]) == 1 and "klingon" in capsys.readouterr().err
    assert main(["ocr", str(path), str(written), "-o", str(tmp_path / "x.pdf")]) == 1
    assert main(["ocr"]) == 1
    monkeypatch.setattr(ocr, "download", lambda names, progress=None: [own / f"{n}.traineddata" for n in names])
    assert main(["ocr", "--download", "lat", "osd"]) == 0 and "osd.traineddata" in capsys.readouterr().out
