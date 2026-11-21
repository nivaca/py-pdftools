"""py-pdftools find-words: on which pages each word, phrase or pattern appears, by the labels of the pages (see
pages/wordfinder.py; it comes from the author's pdf-word-finder, with its options).

    py-pdftools find-words book.pdf amor virtus "de rerum natura"
    py-pdftools find-words book.pdf --words-file terms.txt --csv hits.csv
    py-pdftools find-words book.pdf "re:virtu(s|tem|tis)" --ignore-accents --context
    py-pdftools find-words book.pdf --words-file names.txt --txt index.txt

The report goes to the standard output; the notes (no labels, pages without text, terms not found) to the
standard error, so that the list can be sent to a file or another program as it is."""

from __future__ import annotations

import argparse
import sys

from ..core.interface import ntr, tr


def build_parser(prog: str = "py-pdftools find-words") -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=prog,
        description=tr("Find words, phrases or patterns in a PDF, and give, on a line for each term, the "
                       "labelled (printed) pages where it appears: lines ready for an index."),
        epilog=tr("For instance: {prog} book.pdf amor \"re:virtu(s|tem|tis)\" --ignore-accents --context",
                  prog=prog))
    ap.add_argument("--interface", choices=("en", "es"),
                    help=tr("the language of the interface, for this run only (to keep a choice, use the "
                            "'interface' command)"))
    ap.add_argument("pdf", metavar="FILE", help=tr("the PDF"))
    ap.add_argument("words", nargs="*", metavar="TERM",
                    help=tr("the words or phrases to find; a term that begins with 're:' is a regular "
                            "expression"))
    ap.add_argument("--words-file", metavar="FILE",
                    help=tr("a file with a term on each line ('#' begins a comment)"))
    ap.add_argument("--regex", action="store_true",
                    help=tr("every term is a regular expression (or put 're:' before each)"))
    ap.add_argument("--regex-word", action="store_true",
                    help=tr("regular expressions, too, only match whole words"))
    ap.add_argument("--substring", action="store_true",
                    help=tr("find the terms inside words too (by default, only whole words)"))
    ap.add_argument("--case-sensitive", action="store_true", help=tr("match case"))
    ap.add_argument("--ignore-accents", action="store_true", help=tr("ignore accents"))
    ap.add_argument("--no-dehyphenate", action="store_true",
                    help=tr("don't join the words split by a hyphen at the end of a line"))
    ap.add_argument("--show-logical", action="store_true",
                    help=tr("also give the sequential page (its place in the file), in brackets, where it "
                            "differs from the label"))
    ap.add_argument("--detailed", action="store_true",
                    help=tr("a detailed report: how many times each term appears, and a page on each line"))
    ap.add_argument("--context", action="store_true",
                    help=tr("a fragment of text around each place (implies --detailed)"))
    ap.add_argument("--context-width", type=int, default=60, metavar="N",
                    help=tr("characters of context on each side (default: 60)"))
    ap.add_argument("--sort", action="store_true",
                    help=tr("the list in alphabetical order (by default, in the order of the terms)"))
    ap.add_argument("--txt", metavar="FILE", help=tr("also write the list, in alphabetical order, to a text file"))
    ap.add_argument("--csv", metavar="FILE", help=tr("also write the results to a CSV file"))
    ap.add_argument("--password", metavar="PASSWORD", help=tr("the password to open the PDF"))
    return ap


def main(argv: list[str] | None = None, prog: str = "py-pdftools find-words") -> int:
    import pymupdf

    from ..pages import wordfinder as wf

    ap = build_parser(prog)
    args = ap.parse_args(argv)
    terms: list[str] = list(args.words)
    if args.words_file:
        try:
            with open(args.words_file, encoding="utf-8") as fh:
                terms += wf.read_terms(fh)
        except OSError as exc:
            print(tr("Error: {path} could not be read: {error}", path=args.words_file, error=exc), file=sys.stderr)
            return 1
    if not terms:
        ap.error(tr("no term to find was given"))
    opts = wf.Options(regex=args.regex, regex_word=args.regex_word, substring=args.substring,
                      case_sensitive=args.case_sensitive, ignore_accents=args.ignore_accents,
                      dehyphenate=not args.no_dehyphenate,
                      context_width=args.context_width if args.context else None)
    try:
        doc = pymupdf.open(args.pdf)
    except (pymupdf.FileDataError, pymupdf.FileNotFoundError, RuntimeError) as exc:
        print(tr("Error: {path} could not be opened: {error}", path=args.pdf, error=exc), file=sys.stderr)
        return 1
    if doc.needs_pass and not doc.authenticate(args.password or ""):
        print(tr("Error: {path} is protected: give its password with --password", path=args.pdf), file=sys.stderr)
        return 1
    try:
        result = wf.search(wf.pages_of(doc), terms, opts)
    except wf.PatternError as exc:
        print(tr("Error: {error}", error=exc), file=sys.stderr)
        return 1
    report, notes = wf.build_report(result, show_logical=args.show_logical, detailed=args.detailed or args.context,
                                    alphabetical=args.sort)
    # (las notas, al canal de error: la salida ordinaria queda limpia para redirigirla)
    if notes:
        print(notes, file=sys.stderr)
    if report:
        print(report)
    try:
        if args.txt:
            n = wf.write_txt(args.txt, result, args.show_logical)
            print(ntr("A list of {count} entry written to {path}", "A list of {count} entries written to {path}", n,
                      path=args.txt), file=sys.stderr)
        if args.csv:
            wf.write_csv(args.csv, result)
            print(tr("CSV written to {path}", path=args.csv), file=sys.stderr)
    except OSError as exc:
        print(tr("Error: {error}", error=exc), file=sys.stderr)
        return 1
    return 0
