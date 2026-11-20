"""Tests of the command line of py-pdftools as a whole (cli/): its groups,
where each command goes, and the completion scripts."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pikepdf
import pytest

from py_pdftools.cli import build_parser, main
from py_pdftools.cli.completion import script, tree

EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "example" / "numbers-100.pdf"


@pytest.fixture
def book(tmp_path):
    path = tmp_path / "book.pdf"
    shutil.copy(EXAMPLE, path)
    return path


def test_help_lists_the_groups(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for word in ("labels", "view", "header-footer", "watermark", "pages", "impose", "completion", "interface"):
        assert f"\n    {word} " in out
    assert main([]) == 1


def test_labels(book, capsys):
    assert main(["labels", "set", str(book), "1:r", "9:D", "-i"]) == 0
    assert main(["labels", str(book)]) == 0  # (labels FILE.pdf: show)
    assert "py-pdftools labels set FILE.pdf 1:r 9:D" in capsys.readouterr().out
    assert main(["labels"]) == 1 and "show" in capsys.readouterr().out  # (the help of the group)
    with pytest.raises(SystemExit):
        main(["labels", "nothing"])
    with pytest.raises(SystemExit):
        main(["labels", "set", "-h"])
    assert "usage: py-pdftools labels set" in capsys.readouterr().out


def test_other_commands_of_pages(book):
    assert main(["pages", str(book), "--delete", "LAST", "-i"]) == 0
    assert main(["view", str(book), "--open-at", "9", "-i"]) == 0
    with pikepdf.open(book) as pdf:
        assert len(pdf.pages) == 99


def test_impose(book, capsys):
    out = book.with_name("booklet.pdf")
    assert main(["--interface", "es", "impose", "booklet", str(book), "-o", str(out)]) == 0
    assert "Se escribió" in capsys.readouterr().out
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 50
    with pytest.raises(SystemExit):
        main(["impose", "-h"])
    assert "usage: py-pdftools impose" in capsys.readouterr().out


def test_unknown_command():
    with pytest.raises(SystemExit):
        main(["bogus"])


def test_the_tree():
    paths = tree(build_parser())
    assert ("labels", "set") in paths and ("impose", "booklet") in paths and ("impose", "impose") in paths
    assert ("impose", "interface") not in paths  # (there is one 'interface', at the top)
    assert ("set",) not in paths


def test_bash_completion(tmp_path):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("no bash")
    (tmp_path / "c.bash").write_text(script("bash", build_parser()))
    (tmp_path / "a.pdf").write_bytes(b"")

    def complete(*words: str) -> list[str]:
        test = f"""complete() {{ :; }}
source c.bash
COMP_WORDS=({' '.join(repr(w) for w in words)}); COMP_CWORD={len(words) - 1}; COMPREPLY=()
_py_pdftools; echo "${{COMPREPLY[*]}}"
"""
        result = subprocess.run([bash, "-c", test], cwd=tmp_path, capture_output=True, text=True, check=True)
        return result.stdout.split()

    assert "labels" in complete("py-pdftools", "") and "impose" in complete("py-pdftools", "")
    assert complete("py-pdftools", "labels", "") == ["show", "set", "clear", "copy"]
    assert complete("py-pdftools", "labels", "set", "a") == ["a.pdf"]
    assert complete("py-pdftools", "labels", "set", "a.pdf", "--ra") == ["--range"]
    assert complete("py-pdftools", "--interface", "es", "imp") == ["impose"]
    assert complete("py-pdftools", "impose", "nu") == ["nup"]
    assert complete("py-pdftools", "completion", "") == ["bash", "fish", "zsh"]


def test_fish_completion(tmp_path):
    fish = shutil.which("fish")
    if not fish:
        pytest.skip("no fish")
    path = tmp_path / "c.fish"
    path.write_text(script("fish", build_parser()))

    def complete(line: str) -> list[str]:
        result = subprocess.run([fish, "-c", f"source {path}; complete -C '{line}'"], capture_output=True,
                                text=True, check=True)
        return [row.split("\t")[0] for row in result.stdout.splitlines()]

    assert sorted(complete("py-pdftools labels ")) == ["clear", "copy", "set", "show"]
    assert complete("py-pdftools impose nu") == ["nup"]
    assert "--sheets-per-fold" in complete("py-pdftools impose impose --she")  # (a command named as its group)
    assert complete("py-pdftools --interface es labels set --ke") == ["--keep"]


def test_zsh_completion():
    text = script("zsh", build_parser())
    assert text.startswith("#compdef py-pdftools") and "bashcompinit" in text
