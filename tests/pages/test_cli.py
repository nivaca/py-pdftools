"""Tests of the command line (cli.py)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pikepdf
import pytest

from py_pdftools.core import config, interface

from py_pdftools.pages import labels

from py_pdftools.pages.cli import main
from py_pdftools.pages.labels import Range

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "example" / "numbers-100.pdf"


@pytest.fixture(autouse=True)
def english(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV, str(tmp_path / "cfg"))
    yield
    interface.use("en")
    interface.translate_argparse()


@pytest.fixture()
def book(tmp_path) -> Path:
    path = tmp_path / "book.pdf"
    shutil.copyfile(EXAMPLE, path)
    return path


def ranges_of(path: Path) -> list[Range]:
    with pikepdf.open(path) as pdf:
        return labels.read_labels(pdf)


def test_set_both_syntaxes(book, capsys):
    assert main(["set", str(book), "1:r", "9:D", "--range", "90-95", "style=A", "prefix=App-",
                 "LAST:-::Cover"]) == 0
    out = book.with_name("book-labelled.pdf")
    assert ranges_of(out) == [Range(1, "r"), Range(9, "D"), Range(90, "A", "App-"), Range(96, "D", "", 88),
                              Range(100, "", "Cover")]
    assert ranges_of(book) == []  # (the input is left alone)
    text = capsys.readouterr().out
    assert text.startswith(f"Wrote {out} (100 pages)") and "pages 90-95: App-A … App-F" in text


def test_set_replaces_or_keeps(book):
    assert main(["set", str(book), "1:r", "9:D", "-i"]) == 0
    assert main(["set", str(book), "50:A", "-i"]) == 0  # (replaced: pages 1-49 are 1, 2, 3 ...)
    assert ranges_of(book) == [Range(1), Range(50, "A")]
    assert main(["set", str(book), "1:r", "9:D", "-i"]) == 0
    assert main(["set", str(book), "--keep", "50:A", "-i"]) == 0
    assert ranges_of(book) == [Range(1, "r"), Range(9, "D"), Range(50, "A")]
    assert main(["set", str(book), "--remove", "50", "-i"]) == 0  # (--remove implies --keep)
    assert ranges_of(book) == [Range(1, "r"), Range(9, "D")]


def test_show(book, capsys):
    main(["set", str(book), "1:r", "9:D", "-i"])
    capsys.readouterr()
    assert main([str(book)]) == 0  # ("py-foliation file.pdf": show)
    out = capsys.readouterr().out
    assert "pages 1-8" in out and "i … viii" in out and "py-foliation set FILE.pdf 1:r 9:D" in out
    assert main(["show", "--all", str(book)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 100 and lines[8].split() == ["9", "1"]


def test_clear(book, capsys):
    main(["set", str(book), "1:r", "-i"])
    assert main(["clear", str(book), "-o", str(book.with_name("c.pdf"))]) == 0
    assert ranges_of(book.with_name("c.pdf")) == [] and ranges_of(book) == [Range(1, "r")]
    with pikepdf.open(book.with_name("c.pdf")) as pdf:
        assert "/PageLabels" not in pdf.Root


@pytest.mark.parametrize("args, message", [
    (["set", "{book}"], "no ranges given"),
    (["set", "{book}", "0:D"], "page 0 is not in the document"),
    (["set", "{book}", "9:Q"], "unknown style"),
    (["set", "{book}", "--range", "9", "colour=red"], "is not one of"),
    (["set", "{book}", "--remove", "5"], "no range starts at page 5"),
    (["set", "{book}", "1:D", "-o", "{book}"], "the output is the input file"),
    (["show", "missing.pdf"], "not found"),
])
def test_errors(book, capsys, args, message):
    assert main([a.replace("{book}", str(book)) for a in args]) == 1
    assert message in capsys.readouterr().err


def test_not_a_pdf(tmp_path, capsys):
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a PDF")
    assert main(["show", str(bad)]) == 1
    assert "cannot be read as a PDF" in capsys.readouterr().err


def test_interface_before_the_file(book, capsys):
    assert main(["--interface", "es", str(book)]) == 0  # (es is not taken for the file)
    assert "Sin etiquetas de página" in capsys.readouterr().out


def test_folios_and_suffixes(book, capsys):
    assert main(["set", str(book), "--range", "1-4", "style=roman", "prefix=[", "suffix=]", "5:D", "60:f:12v",
                 "-i"]) == 0
    assert ranges_of(book) == [Range(1, "r", "[", 1, "]"), Range(5), Range(60, "f", "", 24)]
    capsys.readouterr()
    main(["show", str(book)])
    out = capsys.readouterr().out
    assert "12v … 32v" in out and "60:f:12v" in out
    command = out.splitlines()[-1].split()  # (the command it prints gives the same labels)
    copy = book.with_name("again.pdf")
    shutil.copyfile(EXAMPLE, copy)
    assert main([t.strip("'").replace("FILE.pdf", str(copy)) for t in command[1:]] + ["-i"]) == 0
    assert ranges_of(copy) == ranges_of(book)


def test_from_file(book, tmp_path, capsys, monkeypatch):
    main(["set", str(book), "1:r", "9:D", "-i"])
    capsys.readouterr()
    main(["show", "--all", str(book)])
    listed = capsys.readouterr().out.splitlines()
    listed[49] = "    50  Map"
    (tmp_path / "list.txt").write_text("\n".join(listed) + "\n")  # (as show --all writes it)
    assert main(["set", str(book), "--from-file", str(tmp_path / "list.txt"), "-i"]) == 0
    assert ranges_of(book) == [Range(1, "r"), Range(9), Range(50, "", "Map"), Range(51, "D", "", 43)]
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(["x"] * 100)))  # (- : the standard input)
    assert main(["set", str(book), "-f", "-", "LAST:-::Cover", "-i"]) == 0
    assert ranges_of(book) == [Range(1, "", "x"), Range(100, "", "Cover")]
    (tmp_path / "short.txt").write_text("a\nb\n")
    assert main(["set", str(book), "-f", str(tmp_path / "short.txt"), "-i"]) == 1
    assert "the list has 2 labels, but the document has 100 pages" in capsys.readouterr().err


def test_copy_several_files_and_dry_run(book, tmp_path, capsys):
    main(["set", str(book), "1:r", "9:D", "-i"])
    others = [tmp_path / f"o{i}.pdf" for i in range(2)]
    for o in others:
        shutil.copyfile(EXAMPLE, o)
    assert main(["copy", str(book), *map(str, others), "--dry-run"]) == 0
    assert "would get (100 pages)" in capsys.readouterr().out
    assert all(not o.with_name(o.stem + "-labelled.pdf").exists() for o in others)
    assert main(["copy", str(book), *map(str, others)]) == 0
    assert all(ranges_of(o.with_name(o.stem + "-labelled.pdf")) == ranges_of(book) for o in others)
    assert main(["clear", *map(str, others), "-o", "x.pdf"]) == 1  # (-o: one input only)
    assert main(["set", *map(str, others), "LAST:R", "-i"]) == 0
    assert all(ranges_of(o) == [Range(1), Range(100, "R")] for o in others)
    assert main(["set", "1:r"]) == 1 and "no PDF given" in capsys.readouterr().err


def test_show_label(book, capsys):
    main(["set", str(book), "1:r", "9:D", "-i"])
    capsys.readouterr()
    assert main(["show", "--label", "IV", str(book)]) == 0
    assert capsys.readouterr().out.strip() == "4"
    assert main(["show", "-l", "xcix", str(book)]) == 1
    assert "no page is labelled 'xcix'" in capsys.readouterr().err


def test_password_keeps_the_protection(book, capsys):
    locked = book.with_name("locked.pdf")
    with pikepdf.open(book) as pdf:
        pdf.save(locked, encryption=pikepdf.Encryption(owner="o", user="u"))
    assert main(["set", str(locked), "1:r", "-i"]) == 1
    assert "--password" in capsys.readouterr().err
    assert main(["set", str(locked), "1:r", "-i", "--password", "u"]) == 0
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(locked)
    with pikepdf.open(locked, password="u") as pdf:
        assert pdf.is_encrypted and labels.read_labels(pdf) == [Range(1, "r")]


@pytest.mark.parametrize("shell", ["bash", "fish", "zsh"])
def test_completion(shell, capsys):
    assert main(["completion", shell]) == 0
    script = capsys.readouterr().out
    for word in ("show", "set", "copy", "from-file", "dry-run"):
        assert word in script
    tool = shutil.which("zsh" if shell == "zsh" else shell)
    if tool:
        import subprocess
        r = subprocess.run([tool, "-n"], input=script, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
