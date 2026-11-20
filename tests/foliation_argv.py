"""The command lines of py-foliation's tests, as those of py-pdftools: its
commands of labels go under 'labels' ('py-foliation FILE.pdf' is 'py-pdftools
labels FILE.pdf'); the others are the same."""

from py_pdftools.cli import LABELS
from py_pdftools.cli import main as pdftools_main


def as_pdftools(argv: list[str]) -> list[str]:
    words = [(i, t) for i, t in enumerate(argv) if not t.startswith("-") and (i == 0 or argv[i - 1] != "--interface")]
    if words and (words[0][1] in LABELS or words[0][1].lower().endswith(".pdf")):
        return argv[:words[0][0]] + ["labels"] + argv[words[0][0]:]
    return argv


def main(argv: list[str]) -> int:
    return pdftools_main(as_pdftools(argv))
