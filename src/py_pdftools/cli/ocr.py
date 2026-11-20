"""py-pdftools ocr: the text of the scanned pages of PDFs, read by tesseract (see core/ocr.py) and
written under their pictures, invisible, so that it can be found and copied; with --languages, the
languages tesseract has here; with --download, its more accurate models."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core import ocr, pagesel
from ..core.interface import ntr, tr


def build_parser(prog: str = "py-pdftools ocr") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description=tr("Read the text of the scanned pages of PDFs with tesseract, and write it under their "
                       "pictures, invisible, so that it can be found, copied and marked. Pages that have text "
                       "already are left as they are. Each PDF is written as NAME-ocr.pdf beside it, unless "
                       "-o, -i or --output-dir say otherwise."))
    p.add_argument("inputs", nargs="*", type=Path, metavar=tr("PDF"), help=tr("the PDFs to read"))
    p.add_argument("-l", "--lang", metavar=tr("LANGUAGES"),
                   help=tr("the languages of the text, as tesseract names them, several with +, the main one "
                           "first: lat+spa (by default, those of the settings)"))
    p.add_argument("--pages", metavar=tr("PAGES"),
                   help=tr("the pages to read: 1-5,9, LAST ... (by default, all the scanned pages)"))
    p.add_argument("--rotate", action="store_true",
                   help=tr("turn the pages lying sideways or upside down before reading them (needs "
                           "tesseract's osd model: --download osd)"))
    where = p.add_mutually_exclusive_group()
    where.add_argument("-o", "--output", type=Path, metavar=tr("FILE"), help=tr("the PDF to write (one input only)"))
    where.add_argument("-i", "--in-place", action="store_true", help=tr("write each PDF over itself"))
    where.add_argument("--output-dir", type=Path, metavar=tr("FOLDER"),
                       help=tr("write the PDFs into FOLDER, with the same names"))
    p.add_argument("--report", action="store_true",
                   help=tr("list the doubtful words (page, confidence, word), to be checked"))
    p.add_argument("--doubtful", type=float, default=ocr.DOUBTFUL, metavar=tr("CONFIDENCE"),
                   help=tr("words read with a confidence below this (0 to 100) are doubtful (default: %(default)s)"))
    p.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    p.add_argument("--languages", action="store_true",
                   help=tr("show tesseract's version and its languages here (★: a better model), and stop"))
    p.add_argument("--download", nargs="+", metavar=tr("NAME"),
                   help=tr("download tesseract's most accurate models of these languages (and osd, to turn "
                           "pages) into py-pdftools' own folder, and stop"))
    return p


def _target(a, source: Path) -> Path:
    if a.output is not None:
        return a.output
    if a.in_place:
        return source
    folder = a.output_dir if a.output_dir is not None else source.parent
    return folder / (source.name if a.output_dir is not None else f"{source.stem}-ocr.pdf")


def _language(a) -> str:
    if a.lang:
        return a.lang
    from ..annotate import settings

    try:
        return settings.load().ocr_language
    except (OSError, ValueError):
        return "eng"


def _read(a, source: Path) -> None:
    """Read the scanned pages of SOURCE and write the result (see _target); raises OcrError."""
    from ..annotate import annots

    try:
        doc = annots.open_pdf(source, a.password)
    except annots.AnnotateError as e:
        raise ocr.OcrError(str(e)) from None
    try:
        try:
            chosen = pagesel.parse_pages(a.pages, doc.page_count)
        except pagesel.PageError as e:
            raise ocr.OcrError(str(e)) from None
        pages = [n for n in chosen if ocr.scanned(doc[n])]
        target = _target(a, source)
        if not pages:
            print(tr("{path}: no page of those chosen is a scan without text", path=source))
            return
        results = ocr.run(source, a.password, pages, _language(a), rotate=a.rotate, doubtful=a.doubtful)
        words = sum(ocr.write_words(doc[r.number], r) for r in results)
        if a.report:
            for r in results:
                for w in r.doubtful(a.doubtful):
                    print(f"{r.number + 1}\t{w.confidence:.0f}\t{w.text}")
        target.parent.mkdir(parents=True, exist_ok=True)
        annots.save_doc(doc, target)
        doubtful = sum(len(r.doubtful(a.doubtful)) for r in results)
        turned = sum(1 for r in results if r.rotate)
        print(tr("Wrote {path}", path=target) + ": " + ", ".join(
            [ntr("{count} page read", "{count} pages read", len(results)),
             ntr("{count} word", "{count} words", words),
             ntr("{count} doubtful word", "{count} doubtful words", doubtful),
             *([ntr("{count} page turned", "{count} pages turned", turned)] if turned else [])]))
    except (OSError, RuntimeError, ValueError) as e:
        raise ocr.OcrError(tr("{path} cannot be written: {error}", path=_target(a, source), error=e)) from None
    finally:
        if not doc.is_closed:
            doc.close()


def main(argv: list[str] | None = None, prog: str = "py-pdftools ocr") -> int:
    parser = build_parser(prog)
    a = parser.parse_args(argv)

    def fail(message: str) -> int:
        print(f"{prog}: {message}", file=sys.stderr)
        return 1

    if a.languages:
        if not ocr.available():
            return fail(tr("tesseract is not installed: there is no OCR"))
        names = [f"{n}{' ★' if ocr.better(n) else ''}" for n in ocr.languages()]
        print(tr("Tesseract {version}: {languages}", version=ocr.version(), languages=", ".join(names)))
        print(tr("Orientation of pages (osd): {state}", state=tr("yes") if ocr.has_osd() else tr("no")))
        print(tr("Better models: {path}", path=ocr.own_tessdata()))
        return 0
    if a.download:
        try:
            for path in ocr.download(a.download):
                print(tr("Downloaded {path}", path=path))
        except ocr.OcrError as e:
            return fail(str(e))
        return 0
    if not a.inputs:
        parser.print_usage(sys.stderr)
        return fail(tr("no PDF given"))
    if a.output is not None and len(a.inputs) > 1:
        return fail(tr("-o names one file: with several PDFs, use --output-dir or -i"))
    # (tesseract and the languages, checked once, before any file is read)
    if not ocr.available():
        return fail(tr("tesseract is not installed: there is no OCR"))
    try:
        ocr.parse_languages(_language(a))
    except ocr.OcrError as e:
        return fail(str(e))
    failed = False
    for source in a.inputs:
        try:
            _read(a, source)
        except ocr.OcrError as e:
            print(f"{prog}: {source}: {e}", file=sys.stderr)
            failed = True
    return 1 if failed else 0
