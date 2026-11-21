"""The command line of py-pdftools.

    py-pdftools labels show | set | clear | copy   the page labels ('labels FILE.pdf': show)
    py-pdftools view                               how a PDF opens in a viewer
    py-pdftools header-footer | watermark          headers, footers and watermarks
    py-pdftools pages                              move, delete, rotate, insert or split pages
    py-pdftools impose COMMAND                     imposition (booklet, nup, step-repeat ...)
    py-pdftools pdf2iso                            PDF/A and PDF/X (the author's pdf2iso, included)
    py-pdftools ocr                                the text of scanned pages, read by tesseract
    py-pdftools combine                            several PDFs made one
    py-pdftools from-images                        a PDF made of pictures
    py-pdftools completion | interface

The commands come from py-foliation (pages/cli.py) and py-imposition
(impose/), and each runs there, as it did in those programs. Here their
parsers are put together into one tree, which gives the help of the whole
and its completion scripts (completion.py).

The commands of imposition stay together under ``impose``, although some of
them also move, delete or rotate pages: the sequences of ``impose run`` and
the history ``impose replay`` reads name them as they are. ``pages`` arranges
the pages of a document keeping its labels, bookmarks and links;
``impose delete`` and the like are steps of an imposition.
"""

from __future__ import annotations

import argparse
import sys

from ..core import interface
from ..core.interface import tr

TOP = ("view", "header-footer", "watermark", "pages")  # commands of pages/cli.py at the top
LABELS = ("show", "set", "clear", "copy")  # and those under 'labels'
OWN = ("completion", "interface")
PROG = "py-pdftools"


def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    # argparse no ofrece una manera pública de llegar a sus subparsers: se usa _actions.
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))


def _graft(dst: argparse._SubParsersAction, src: argparse._SubParsersAction, names) -> None:
    """Put the commands NAMES of SRC under DST, as they are."""
    for name in names:
        # Two private structures must agree: the map of names (for parsing) and the choices (for the help).
        dst._name_parser_map[name] = src.choices[name]
        dst._choices_actions.append(next(c for c in src._choices_actions if c.dest == name))


def build_parser() -> argparse.ArgumentParser:
    # Importaciones diferidas: los analizadores de imposición y de páginas solo hacen falta aquí.
    from .. import __version__
    from ..impose.runner import build_parser as impose_parser
    from ..pages.cli import build_parser as pages_parser

    pages = _subparsers(pages_parser(PROG))
    impose = impose_parser(f"{PROG} impose")
    isub = _subparsers(impose)  # (its 'interface' is the one here)
    # La orden 'interface' de la imposición se retira para que no aparezca dos veces.
    isub._name_parser_map.pop("interface", None)
    isub._choices_actions[:] = [c for c in isub._choices_actions if c.dest != "interface"]

    parser = argparse.ArgumentParser(
        prog=PROG,
        description=tr("Edit PDF documents from the command line: their page labels, how they open, "
                       "headers, footers and watermarks, the order of their pages, and their imposition "
                       "for printing. The window (py-pdftools-gui) also annotates and redacts them."),
        epilog=tr("Run '%(prog)s COMMAND -h' for help on a command."),
    )
    parser.add_argument("--interface", choices=sorted(interface.names()), default=argparse.SUPPRESS,
                        help=tr("the language of the interface, for this run only (to keep a choice, use the "
                                "'interface' command)"))
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="group", metavar=tr("COMMAND"))
    labels = sub.add_parser("labels", help=tr("show, set, clear or copy the page labels of PDFs"),
                            description=tr("Change the page labels of a PDF: the numbering a PDF viewer shows "
                                           "for its pages (i, ii, iii ... 1, 2, 3 ... A-1, A-2 ...)."))
    _graft(_subparsers_of(labels, tr("COMMAND")), pages, LABELS)
    _graft(sub, pages, TOP)
    # 'impose' entra como un analizador entero, con sus órdenes; la pseudoacción solo sirve para la ayuda.
    sub._name_parser_map["impose"] = impose
    sub._choices_actions.append(sub._ChoicesPseudoAction(
        "impose", (), tr("impose pages for printing: booklets, n-up, step and repeat, bleeds, stamps, "
                         "sequences and hot folders")))
    from ..core import pdf2iso

    sub._name_parser_map["pdf2iso"] = pdf2iso.build_parser(f"{PROG} pdf2iso")
    sub._choices_actions.append(sub._ChoicesPseudoAction(
        "pdf2iso", (), tr("convert PDFs to PDF/A or PDF/X-4 (pdf2iso, which is included; it needs Ghostscript)")))
    from . import ocr as ocr_cli

    sub._name_parser_map["ocr"] = ocr_cli.build_parser(f"{PROG} ocr")
    sub._choices_actions.append(sub._ChoicesPseudoAction(
        "ocr", (), tr("read the text of scanned pages with tesseract, and write it under them (OCR)")))
    from . import combine as combine_cli

    sub._name_parser_map["combine"] = combine_cli.build_combine_parser(f"{PROG} combine")
    sub._choices_actions.append(sub._ChoicesPseudoAction(
        "combine", (), tr("combine PDFs into one, or some of their pages")))
    sub._name_parser_map["from-images"] = combine_cli.build_images_parser(f"{PROG} from-images")
    sub._choices_actions.append(sub._ChoicesPseudoAction(
        "from-images", (), tr("make a PDF of pictures (photographs, scans)")))
    _graft(sub, pages, OWN)
    return parser


def _subparsers_of(parser: argparse.ArgumentParser, metavar: str) -> argparse._SubParsersAction:
    return parser.add_subparsers(dest="command", metavar=metavar)


def _words(argv: list[str]) -> list[tuple[int, str]]:
    """The words of ARGV that are not options (with their places), leaving out the value of --interface."""
    return [(i, t) for i, t in enumerate(argv)
            if not t.startswith("-") and (i == 0 or argv[i - 1] != "--interface")]


def main(argv: list[str] | None = None) -> int:
    from ..pages import cli as pages_cli

    argv = list(sys.argv[1:] if argv is None else argv)
    # The language is set before any parser is built, so that its help and argparse's own messages are translated.
    interface.use_configured(interface.option(argv))
    interface.translate_argparse()
    words = _words(argv)
    first = words[0] if words else None
    # Cada grupo de órdenes conserva su propio main, como en los programas de donde viene.
    if first and first[1] == "pdf2iso":
        from ..core import pdf2iso

        return pdf2iso.main(argv[:first[0]] + argv[first[0] + 1:], prog=f"{PROG} pdf2iso")
    if first and first[1] == "ocr":
        from . import ocr as ocr_cli

        return ocr_cli.main(argv[:first[0]] + argv[first[0] + 1:], prog=f"{PROG} ocr")
    if first and first[1] == "combine":
        from . import combine as combine_cli

        return combine_cli.main_combine(argv[:first[0]] + argv[first[0] + 1:], prog=f"{PROG} combine")
    if first and first[1] == "from-images":
        from . import combine as combine_cli

        return combine_cli.main_images(argv[:first[0]] + argv[first[0] + 1:], prog=f"{PROG} from-images")
    if first and first[1] == "impose":
        from ..impose import main as impose_main

        # Se quita la palabra 'impose' y el resto se pasa tal cual al programa de imposición.
        return impose_main(argv[:first[0]] + argv[first[0] + 1:])
    if first and first[1] == "labels":
        second = words[1][1] if len(words) > 1 else None
        if second in LABELS or (second or "").lower().endswith(".pdf"):  # ('labels FILE.pdf': show)
            return pages_cli.main(argv[:first[0]] + argv[first[0] + 1:])
    elif first and first[1] in TOP + OWN:
        return pages_cli.main(argv)
    parser = build_parser()
    a = parser.parse_args(argv)  # (the help, the version, or a command that does not exist)
    # 'labels' sin orden muestra la ayuda de ese grupo, no la general.
    if a.group == "labels":
        _subparsers(parser).choices["labels"].print_help()
    else:
        parser.print_help()
    return 1
