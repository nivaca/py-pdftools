"""OCR with the tesseract program (core/ocr.py): the words of a scan, read in other processes, with
their place and confidence; written as invisible text; pages lying sideways turned; the languages,
those installed and those downloaded."""

from __future__ import annotations

import io
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

    monkeypatch.setattr(ocr.urllib.request, "urlopen", urlopen)
    sizes = []
    (made,) = ocr.download(["lat"], progress=lambda done, total: sizes.append((done, total)) or True)
    assert made == own / "lat.traineddata" and made.read_bytes() == b"model bytes" and sizes[-1] == (11, 11)
    assert asked == [ocr.BEST_URL.format(name="lat")] and ocr.better("lat")
    with pytest.raises(ocr.OcrError, match="no such language"):
        ocr.download(["nope"])
    assert not (own / "nope.part").exists() and not (own / "nope.traineddata").exists()
    with pytest.raises(ocr.OcrError):
        ocr.download(["../x"])
