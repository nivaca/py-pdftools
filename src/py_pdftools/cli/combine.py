"""py-pdftools combine and py-pdftools from-images: several PDFs made one, and a PDF made of pictures. See
pages/combine.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core.interface import tr
from ..pages import combine
from ..pages.combine import CombineError


def _part(text: str) -> combine.Part:
    """'book.pdf' or 'book.pdf:1-3,7' (the pages chosen, after the last ':' if what is before it is a file)."""
    head, sep, pages = text.rpartition(":")
    if sep and head and not Path(text).is_file() and Path(head).is_file():
        return combine.Part(Path(head), pages)
    return combine.Part(Path(text))


def build_combine_parser(prog: str = "py-pdftools combine") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog, description=tr("Combine PDFs into one: their pages one file after another, with their "
                                  "links, annotations and form fields. FILE:PAGES takes only those pages, in "
                                  "that order (book.pdf:1-3,7)."))
    p.add_argument("inputs", nargs="+", metavar=tr("FILE"), help=tr("a PDF, or PDF:PAGES"))
    p.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FILE"), help=tr("the PDF made"))
    p.add_argument("--bookmarks", choices=combine.BOOKMARKS, default="files",
                   help=tr("one for each file, with its own under it (default); those of the files as they are; "
                           "or none"))
    p.add_argument("--labels", action="store_true", help=tr("keep the page labels of each file"))
    p.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    return p


def build_images_parser(prog: str = "py-pdftools from-images") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog, description=tr("Make a PDF of pictures (photographs, scans): a page for each, in the order "
                                  "given, as big as the picture or on paper of a size."))
    p.add_argument("inputs", nargs="+", type=Path, metavar=tr("PICTURE"), help=tr("a picture (PNG, JPEG, TIFF…)"))
    p.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FILE"), help=tr("the PDF made"))
    p.add_argument("--paper", choices=list(combine.PAPERS), help=tr("put each picture on paper of this size"))
    g = p.add_mutually_exclusive_group()
    g.add_argument("--portrait", dest="landscape", action="store_false", default=None,
                   help=tr("the paper standing (else as each picture is)"))
    g.add_argument("--landscape", dest="landscape", action="store_true", help=tr("the paper lying"))
    p.add_argument("--margin", type=float, default=0, metavar="MM", help=tr("a margin, in millimetres"))
    return p


def main_combine(argv: list[str] | None = None, prog: str = "py-pdftools combine") -> int:
    a = build_combine_parser(prog).parse_args(argv)
    parts = [combine.Part(p.path, p.pages, a.password) for p in map(_part, a.inputs)]
    try:
        count = combine.combine(parts, a.output, a.bookmarks, a.labels)
    except CombineError as e:
        print(f"{prog}: {e}", file=sys.stderr)
        return 1
    print(tr("Wrote {path} ({count} pages)", path=a.output, count=count))
    return 0


def main_images(argv: list[str] | None = None, prog: str = "py-pdftools from-images") -> int:
    a = build_images_parser(prog).parse_args(argv)
    try:
        count = combine.from_images(a.inputs, a.output, a.paper or "", a.landscape, a.margin)
    except CombineError as e:
        print(f"{prog}: {e}", file=sys.stderr)
        return 1
    print(tr("Wrote {path} ({count} pages)", path=a.output, count=count))
    return 0
