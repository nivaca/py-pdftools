"""py-pdftools combine, from-images, reduce y rasterize: varios PDF hechos uno, un PDF hecho de imágenes (ver
pages/combine.py), un PDF más pequeño (pages/reduce.py) y uno con páginas convertidas en imágenes, sin texto
(pages/rasterize.py)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core.interface import tr
from ..pages import combine, rasterize, reduce
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


def build_reduce_parser(prog: str = "py-pdftools reduce") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog, description=tr("Make a smaller copy of a PDF: its pictures at a lower resolution (those "
                                  "above it, as they are shown) and more compressed, its fonts reduced to the "
                                  "characters used, what nothing uses taken out."))
    p.add_argument("input", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    p.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FILE"), help=tr("the PDF made"))
    p.add_argument("--level", choices=[k for k, *_ in reduce.LEVELS], default="medium",
                   help=tr("high: pictures at 220 dpi; medium (default): 150 dpi; small: 96 dpi, more compressed; "
                           "lossless: the pictures untouched"))
    p.add_argument("--dpi", type=int, help=tr("the resolution of the pictures (instead of that of the level)"))
    p.add_argument("--quality", type=int, help=tr("the JPEG quality of the pictures, 1-100"))
    p.add_argument("--gray", action="store_true", help=tr("pictures in grey"))
    p.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    return p


def main_reduce(argv: list[str] | None = None, prog: str = "py-pdftools reduce") -> int:
    a = build_reduce_parser(prog).parse_args(argv)
    base = reduce.options_of(a.level)
    options = reduce.Options(base.dpi if a.dpi is None else a.dpi,
                             base.quality if a.quality is None else max(1, min(100, a.quality)),
                             a.gray, base.fonts)
    try:
        before, after = reduce.reduce(a.input, a.output, options, a.password)
    except reduce.ReduceError as e:
        print(f"{prog}: {e}", file=sys.stderr)
        return 1
    print(tr("Wrote {path}: {before} → {after}", path=a.output, before=reduce.size_text(before),
             after=reduce.size_text(after)))
    return 0


def build_rasterize_parser(prog: str = "py-pdftools rasterize") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog, description=tr("Make a copy of a PDF with some or all of its pages as pictures: they look "
                                  "the same, but their text (and their annotations and form fields, drawn into "
                                  "the picture) can no longer be found, copied or extracted."))
    p.add_argument("input", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    p.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FILE"), help=tr("the PDF made"))
    p.add_argument("--pages", default="", metavar=tr("PAGES"),
                   help=tr("the pages, e.g. 1-3,7,LAST; odd, even (default: all)"))
    p.add_argument("--dpi", type=int, default=300, help=tr("the resolution of the pictures (default 300)"))
    p.add_argument("--format", choices=("png", "jpg"), default="png",
                   help=tr("png (default): lossless, sharper text; jpg: smaller, for photographs"))
    p.add_argument("--quality", type=int, default=85, help=tr("the JPEG quality of the pictures, 1-100"))
    p.add_argument("--gray", action="store_true", help=tr("pictures in grey"))
    p.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    return p


def main_rasterize(argv: list[str] | None = None, prog: str = "py-pdftools rasterize") -> int:
    a = build_rasterize_parser(prog).parse_args(argv)
    if not 1 <= a.dpi <= 2400:
        print(f"{prog}: " + tr("the resolution must be between 1 and 2400 dpi"), file=sys.stderr)
        return 1
    options = rasterize.Options(a.dpi, a.format, max(1, min(100, a.quality)), a.gray)
    try:
        count = rasterize.rasterize(a.input, a.output, options, a.pages if a.pages.strip() else None, a.password)
    except rasterize.RasterizeError as e:
        print(f"{prog}: {e}", file=sys.stderr)
        return 1
    print(tr("Wrote {path} ({count} pages as pictures)", path=a.output, count=count))
    return 0
