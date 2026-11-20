"""Tests of PDF/A and PDF/X (conform.py, and --conform on the command line): finding
pdf2iso, and, when it is installed, a conversion that keeps the page labels."""

from __future__ import annotations

import shutil
from pathlib import Path

import pikepdf
import pytest

from py_pdftools.core import config, conform, interface

from py_pdftools.pages import labels

from foliation_argv import main
from py_pdftools.pages.labels import Range

HAVE = shutil.which("pdf2iso") is not None


@pytest.fixture(autouse=True)
def own_config(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV, str(tmp_path / "cfg"))
    yield
    interface.use("en")
    interface.translate_argparse()


@pytest.fixture()
def small(tmp_path) -> Path:
    """A PDF of four pages, without labels."""
    pdf = pikepdf.Pdf.new()
    for _ in range(4):
        pdf.add_blank_page(page_size=(300, 400))
    path = tmp_path / "small.pdf"
    pdf.save(path)
    return path


def ranges_of(path: Path) -> list[Range]:
    with pikepdf.open(path) as pdf:
        return labels.read_labels(pdf)


def test_conform_missing(small, tmp_path, monkeypatch):
    monkeypatch.setattr(conform, "command", lambda path=None: None)
    with pytest.raises(conform.ConformError):
        conform.convert(small, tmp_path / "x.pdf", "a-2b")






def test_cli_conform_missing(small, monkeypatch, capsys):
    monkeypatch.setattr(conform, "command", lambda path=None: None)
    assert main(["set", str(small), "1:r", "3:D", "--conform", "a-2b"]) == 1
    assert "Ghostscript is not installed" in capsys.readouterr().err
    assert not small.with_name("small-labelled.pdf").exists()


def test_cli_conform_choices(small, capsys):
    with pytest.raises(SystemExit):
        main(["set", str(small), "1:r", "--conform", "a-4"])
    assert "a-2b" in capsys.readouterr().err


@pytest.mark.skipif(not HAVE, reason="pdf2iso not installed")
def test_cli_conform_keeps_the_labels(small, capsys):
    assert main(["set", str(small), "1:r", "3:D", "--conform", "a-2b"]) == 0
    out = small.with_name("small-labelled.pdf")
    assert b"pdfaid" in out.read_bytes()
    assert ranges_of(out) == [Range(1, "r"), Range(3, "D")]
    assert "PDF/A-2b" in capsys.readouterr().out
    assert ranges_of(small) == []  # (the input is left alone)


@pytest.mark.skipif(not HAVE, reason="pdf2iso not installed")
def test_convert_in_place_x4(small):
    with pikepdf.open(small, allow_overwriting_input=True) as pdf:
        labels.write_labels(pdf, [Range(1, "A", "Plate ")])
        pdf.save(small)
    conform.convert(small, small, "x-4")
    assert b"GTS_PDFX" in small.read_bytes() and ranges_of(small) == [Range(1, "A", "Plate ")]
