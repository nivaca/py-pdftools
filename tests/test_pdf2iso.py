"""pdf2iso, included in py-pdftools (core/pdf2iso.py), and how conform.py runs it: the one of
py-pdftools by default, another one only if the settings name it; PDF/A and PDF/X with
Ghostscript, whose absence is said, not hidden."""

from __future__ import annotations

import sys
from pathlib import Path

import pikepdf
import pymupdf
import pytest

from py_pdftools.cli import main
from py_pdftools.core import config, conform, pdf2iso

GHOSTSCRIPT = pytest.mark.skipif(bool(conform.ghostscript()), reason="Ghostscript is not installed")


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    for i in range(2):
        doc.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=14)
    doc.save(path)
    return path


def test_the_own_one_by_default(tmp_path, monkeypatch):
    """With nothing in the settings, the pdf2iso of py-pdftools: not one found on the PATH or in ~/bin
    (as before it was part of py-pdftools)."""
    home = tmp_path / "home"
    (home / "bin").mkdir(parents=True)
    script = home / "bin" / "pdf2iso"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{home / 'bin'}:/usr/bin:/bin")
    assert conform.find() == Path(pdf2iso.__file__)
    assert conform.command() == [sys.executable, "-m", "py_pdftools.core.pdf2iso"] == conform.builtin()


def test_another_one_from_the_settings(tmp_path, monkeypatch):
    script = tmp_path / "my-pdf2iso"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    config.set("pdfconform", str(script))
    assert sys.platform == "win32" or conform.command() == [str(script)]
    assert conform.available()
    other = tmp_path / "elsewhere.py"  # (a script that can't be run by itself: run with a Python)
    other.write_text("print()\n")
    config.set("pdfconform", str(other))
    cmd = conform.command()
    assert cmd[-1] == str(other) and Path(cmd[0]).stem.startswith(("python", "py"))
    config.set("pdfconform", str(tmp_path / "missing"))
    assert conform.command() is None and not conform.available()


def test_without_ghostscript(sample, tmp_path, monkeypatch):
    """Without Ghostscript, PDF/A and PDF/X can't be made, and the error says why."""
    monkeypatch.setattr(conform, "ghostscript", lambda: "Ghostscript not found")
    assert not conform.available()
    with pytest.raises(conform.ConformError, match="Ghostscript not found"):
        conform.convert(sample, tmp_path / "out.pdf", "a-2b")
    assert not (tmp_path / "out.pdf").exists()


@GHOSTSCRIPT
@pytest.mark.parametrize("standard", ["a-2b", "x-4"])
def test_conversion(sample, tmp_path, standard):
    """The own pdf2iso, run as the window and the command line run it, makes the standard."""
    out = tmp_path / "out.pdf"
    check = conform.convert(sample, out, standard)
    with pikepdf.open(out) as pdf:
        meta = str(pdf.open_metadata())
        assert len(pdf.pages) == 2
        if standard == "x-4":
            assert "/GTS_PDFX" in str(pdf.Root.OutputIntents[0].S)
        else:
            assert "pdfaid" in meta
    assert standard != "x-4" or "PASS" in check  # (PDF/X-4: its own structural check)


@GHOSTSCRIPT
def test_command_line(sample, tmp_path, capsys):
    out = tmp_path / "archived.pdf"
    assert main(["pdf2iso", str(sample), "-t", "a-1b", "-o", str(out)]) == 0
    assert out.is_file() and "[PDF/A-1b]" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["pdf2iso", "--help"])
    assert "usage: py-pdftools pdf2iso" in capsys.readouterr().out


def test_the_module_does_not_stop_the_program():
    """As a script, pdf2iso stopped when pikepdf was missing or too old; as a module it must never call
    sys.exit when it is imported."""
    source = Path(pdf2iso.__file__).read_text()
    head = source[:source.index("def main(")]
    assert "sys.exit(" not in head.split("class Target")[0]
