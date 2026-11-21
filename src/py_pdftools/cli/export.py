"""py-pdftools export: the pages of a PDF as pictures, the pictures it holds, or its text. See
pages/export.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core.interface import tr
from ..core.pagesel import PageError, parse_pages
from ..pages import export


def build_parser(prog: str = "py-pdftools export") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=tr("Export the pages of a PDF as pictures, the pictures "
                                                          "it holds, or its text."))
    sub = p.add_subparsers(dest="command", metavar=tr("COMMAND"), required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("input", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    common.add_argument("--pages", default="", metavar=tr("PAGES"), help=tr("which pages (default: all)"))
    common.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    sp = sub.add_parser("pages", parents=[common], help=tr("the pages drawn as pictures (PNG, JPEG, TIFF)"))
    sp.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FOLDER"),
                    help=tr("the folder of the pictures"))
    sp.add_argument("--format", choices=export.PICTURE_FORMATS, default="png", help=tr("default: png"))
    sp.add_argument("--dpi", type=int, default=150, help=tr("the resolution (default: 150)"))
    sp.add_argument("--gray", action="store_true", help=tr("in grey"))
    sp.add_argument("--quality", type=int, default=90, help=tr("of a JPEG, 1-100 (default: 90)"))
    sp = sub.add_parser("images", parents=[common], help=tr("the pictures the pages show, each in a file"))
    sp.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FOLDER"),
                    help=tr("the folder of the pictures"))
    sp.add_argument("--smallest", type=int, default=32, metavar="PX",
                    help=tr("leave out those smaller than this on a side (default: 32)"))
    sp = sub.add_parser("text", parents=[common], help=tr("the text, as Markdown, HTML or plain text"))
    sp.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FILE"),
                    help=tr("the file made (.md, .html or .txt: its extension says the format)"))
    return p


def main(argv: list[str] | None = None, prog: str = "py-pdftools export") -> int:
    a = build_parser(prog).parse_args(argv)
    try:
        pages = None
        if a.pages.strip():
            import pymupdf

            with pymupdf.open(a.input) as doc:
                count = doc.page_count
            pages = parse_pages(a.pages, count, keep_order=True)
        if a.command == "pages":
            made = export.export_pages(a.input, a.output, pages, a.format, a.dpi, a.gray, a.quality, a.password)
            print(tr("Wrote {count} pictures in {folder}", count=len(made), folder=a.output))
        elif a.command == "images":
            made = export.export_images(a.input, a.output, pages, a.smallest, a.password)
            print(tr("Wrote {count} pictures in {folder}", count=len(made), folder=a.output))
        else:
            export.export_text(a.input, a.output, pages=pages, password=a.password)
            print(tr("Wrote {path}", path=a.output))
    except (export.ExportError, PageError, OSError, RuntimeError) as e:
        print(f"{prog}: {e}", file=sys.stderr)
        return 1
    return 0
