"""The commands of page labels, the view, headers and footers, watermarks and pages
(from py-foliation); py_pdftools.cli puts them in the command line of py-pdftools."""

from __future__ import annotations

import argparse
import dataclasses
import io
import sys
from datetime import datetime
from pathlib import Path

import pikepdf

from ..core import conform, config, interface

from . import arrange, headfoot, labels, stamps, view, watermark
from .changes import Change
from .files import open_pdf, read_list, save_pdf
from ..core.interface import N_, ntr, tr
from .labels import LabelError, pages_text, set_command

LABEL_COMMANDS = ("show", "set", "clear", "copy")
COMMANDS = ("show", "set", "clear", "copy", "view", "header-footer", "watermark", "pages", "completion",
            "interface")

SET_EPILOG = N_("""A range is written PAGES:STYLE[:START[:PREFIX]]:

  1:r            pages from 1 on: i, ii, iii ...
  9:D            pages from 9 on: 1, 2, 3 ...
  201-214:A      pages 201 to 214: A ... N (then the old numbering goes on)
  215:D:1:App-   pages from 215 on: App-1, App-2 ...
  5:f:12v        folios from page 5 on: 12v, 13r, 13v ...
  LAST:-::Cover  the last page: Cover

or, with --range, PAGES [style=S] [start=N] [prefix=P] [suffix=X]:

  --range 9-200 style=arabic
  --range 1-4 style=roman prefix=[ suffix=]

PAGES is a first page (9) or a span (9-200, 9..200, 201-); LAST and LAST-N
count from the end. A range without a last page goes on until the next one.

Styles: D or arabic (1, 2, 3), r or roman (i, ii, iii), R or ROMAN (I, II,
III), a or letters (a, b, c), A or LETTERS (A, B, C), f or folio (1r, 1v,
2r: the recto and verso of each leaf; START is a leaf and its side, as
12v), - or none (the prefix only).

Folios and suffixes are not page label styles of PDF: py-pdftools writes
them as one label for each page, and recognises them when it reads the
file.

--from-file takes the labels of all the pages, one on each line (as
'show --all' writes them, with or without the page numbers; - is the
standard input), and finds the fewest ranges that give them.""")


VIEW_EPILOG = N_("""Page layouts: single (one page at a time), single-continuous (all the pages
in one column), facing (two pages at a time, odd pages on the left),
facing-continuous (all the pages in two columns), cover (as facing, but the
first page alone, as the cover of a book), cover-continuous.

Page views: actual-size (the size it would be printed), fit-width, fit-page,
or a percentage (150%).

For instance: py-pdftools view book.pdf --layout cover --page-view fit-page
--open-at 9 -i""")


HEADER_FOOTER_EPILOG = N_("""The text of each place may hold variables, written with $ (put the text in
single quotes, or the shell takes them as its own): $page, $pagelabel,
$bookmark, $totalpages, $author, $filename, $filepath, $date, $shortdate,
$time, $day, $month, $year, $shortyear, $hour, $longhour, $minute, $second,
$ampm and $bates; $$ writes a $. A new line in the text (\\n in --*-left and
the rest) starts another line.

The fonts are the standard fonts of PDF, which every viewer has: they write
Latin script, with its accents and signs, but not Greek or Cyrillic.

Margins are the distances from the edges of the page to the header, the
footer and the text at the sides. --shrink scales the content of the pages
down so that the header and footer don't cover it.

A header and footer added to a page replaces those py-pdftools added
before, unless --add keeps them; --update replaces the last one added, with
its settings and the options given; --remove takes them away (--remove-bates
only those with Bates numbers), putting the pages back as they were. With
several files, the Bates numbers go on from one file to the next, in the
order given. Profiles keep settings to use again (--save-profile NAME, then
--profile NAME); the options given are laid over those of the profile.

For instance: py-pdftools header-footer book.pdf --footer-center 'Page
$pagelabel of $totalpages' --header-right '$date' --pages 9- -i""")


WATERMARK_EPILOG = N_("""A watermark is a text (--text, with the variables of header-footer, such as
$page or $date; put it in single quotes) or a page of another PDF (--file,
--file-page). --scale fills that percent of the page with it (by default,
it keeps its own size); --rotation turns it, counterclockwise; --opacity
goes from 0 (invisible) to 1 (or 0% to 100%).

It goes in the middle of the page unless --horizontal and --vertical say
otherwise, moved by --hoffset and --voffset from there. --behind draws it
behind the content of the pages (where a page painted white would hide it).
--no-print or --no-screen shows it only on the screen or only when
printing, in viewers that follow such settings.

A watermark added to a page replaces those py-pdftools added before,
unless --add keeps them; --update replaces the last one added; --remove
takes them away, putting the pages back as they were.

For instance: py-pdftools watermark book.pdf --text DRAFT --opacity 30%
--scale 60 -i""")


PAGES_EPILOG = N_("""The operations are made in the order they are given, each on the pages as the
ones before left them. PAGES is a list of pages, as 9-20,31 (LAST counts from
the end), 'all', 'even', 'odd', or 1-50,odd; WHERE is a page (the pages go
before it), 'start' or 'end'. --order gives the whole new order: 1-8,20-30,
9-19,31- (pages may be repeated or left out; 10-1 goes backwards).

By default the page labels follow the pages: each page keeps its label, and
pages inserted bring the labels they had. With --labels position, the ranges
of labels stay where they are, and the pages take the labels of their new
places. Bookmarks and links go with their pages; those that went to a page
deleted go to the page after it.

--split-every and --split-at save the result as several files, named as the
input with -1, -2 ... (in --output-dir, if given).

For instance: py-pdftools pages book.pdf --move 201-214 9 --delete LAST
--rotate even 90 -i""")


def interface_option(argv: list[str]) -> str | None:
    """The value of --interface in ARGV (needed before the parser is built)."""
    for i, tok in enumerate(argv):
        if tok == "--interface" and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith("--interface="):
            return tok.split("=", 1)[1]
    return None


def translate_paragraphs(text: str) -> str:
    return "\n\n".join(tr(par) for par in text.split("\n\n"))


def build_parser(prog: str = "py-pdftools") -> argparse.ArgumentParser:
    from .. import __version__

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--interface", choices=sorted(interface.names()), default=argparse.SUPPRESS,
                        help=tr("the language of the interface, for this run only (to keep a choice, use the "
                                "'interface' command)"))
    parser = argparse.ArgumentParser(
        prog=prog, parents=[common],
        description=tr("Change the page labels of a PDF: the numbering a PDF viewer shows for its pages "
                       "(i, ii, iii ... 1, 2, 3 ... A-1, A-2 ...)."),
        epilog=tr("Run '%(prog)s COMMAND -h' for help on a command. "
                  "'%(prog)s file.pdf' on its own shows the page labels of the file."),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar=tr("COMMAND"))

    def password(sp):
        sp.add_argument("--password", default="", metavar=tr("PASSWORD"),
                        help=tr("the password to open the PDFs (their protection is kept when they are saved)"))

    def output_options(sp, dry_run_help: str | None = None):
        g = sp.add_mutually_exclusive_group()
        g.add_argument("-o", "--output", type=Path,
                       help=tr("output PDF, with one input only (default: <input>-labelled.pdf)"))
        g.add_argument("-i", "--in-place", action="store_true", help=tr("change the input files themselves"))
        g.add_argument("--output-dir", type=Path, metavar=tr("FOLDER"),
                       help=tr("save the PDFs in this folder, with their own names unless --name-prefix or "
                               "--name-suffix are given"))
        sp.add_argument("--name-prefix", default="", metavar=tr("TEXT"),
                        help=tr("put this before the names of the PDFs saved"))
        sp.add_argument("--name-suffix", metavar=tr("TEXT"),
                        help=tr("put this after the names of the PDFs saved (default: -labelled, or nothing "
                                "with --output-dir)"))
        sp.add_argument("-n", "--dry-run", action="store_true",
                        help=dry_run_help or tr("show the labels the files would get, without writing anything"))
        sp.add_argument("--conform", choices=[v for v, _ in conform.STANDARDS], metavar=tr("STANDARD"),
                        help=tr("save the PDFs as PDF/A or PDF/X: a-1b, a-2b, a-3b (archiving) or x-4 "
                                "(printing), made by pdf2iso, which must be installed"))
        password(sp)

    def stamp_options(sp, what: str):
        """The options headers and footers share with watermarks."""
        g = sp.add_argument_group(tr("pages"))
        g.add_argument("--pages", metavar=tr("PAGES"),
                       help=tr("the pages, as 9-200 or 1,3,9- (default: all; LAST counts from the end)"))
        parity = g.add_mutually_exclusive_group()
        parity.add_argument("--even", dest="parity", action="store_const", const="even", help=tr("even pages only"))
        parity.add_argument("--odd", dest="parity", action="store_const", const="odd", help=tr("odd pages only"))
        parity.add_argument("--all-pages", dest="parity", action="store_const", const="all",
                            help=tr("even and odd pages (with a profile that has only some)"))
        g = sp.add_argument_group(tr("Bates numbering ($bates)"))
        g.add_argument("--bates-prefix", metavar=tr("TEXT"), help=tr("text before the number"))
        g.add_argument("--bates-start", type=int, metavar="N", help=tr("the first number (default: 1)"))
        g.add_argument("--bates-digits", type=int, metavar="N",
                       help=tr("the digits of the number, at least (default: 6)"))
        g.add_argument("--bates-suffix", metavar=tr("TEXT"), help=tr("text after the number"))
        g.add_argument("--date-format", choices=list(stamps.DATE_FORMATS), metavar=tr("FORMAT"),
                       help=tr("how $date writes the date: {formats} (default: medium, as Nov 28, 2007)",
                               formats=", ".join(stamps.DATE_FORMATS)))
        g = sp.add_argument_group(tr("adding, updating and removing"))
        g.add_argument("--add", action="store_true",
                       help=tr("keep the {what} py-pdftools added to the pages before (else they are replaced)",
                               what=what))
        g.add_argument("--update", action="store_true",
                       help=tr("replace the last {what} added, with its settings and the options given", what=what))
        g.add_argument("--remove", action="store_true",
                       help=tr("take away the {what} py-pdftools added (on --pages, or all)", what=what))
        g = sp.add_argument_group(tr("profiles"))
        g.add_argument("--profile", metavar=tr("NAME"), help=tr("start from the settings of this profile"))
        g.add_argument("--save-profile", metavar=tr("NAME"), help=tr("keep these settings as a profile"))
        g.add_argument("--show-on-menu", action=argparse.BooleanOptionalAction, default=None,
                       help=tr("with --save-profile: list the profile in the window's menu"))
        g.add_argument("--list-profiles", action="store_true", help=tr("list the profiles kept"))
        g.add_argument("--delete-profile", metavar=tr("NAME"), help=tr("forget a profile"))

    sp = sub.add_parser("show", parents=[common], help=tr("show the page labels of PDFs"),
                        description=tr("Show the ranges of page labels of PDFs, and the command that "
                                       "would give them to another file."))
    sp.add_argument("inputs", nargs="+", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    g = sp.add_mutually_exclusive_group()
    g.add_argument("-a", "--all", action="store_true", help=tr("show the label of every page"))
    g.add_argument("-l", "--label", metavar=tr("LABEL"),
                   help=tr("show the pages labelled LABEL (if none, those labelled so but for capitals)"))
    password(sp)

    sp = sub.add_parser("set", parents=[common], help=tr("give PDFs new page labels"),
                        description=tr("Give PDFs new page labels, range by range. The labels they had are "
                                       "replaced, unless --keep is given."),
                        epilog=translate_paragraphs(SET_EPILOG), formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("items", nargs="+", metavar=tr("FILE|RANGE"),
                    help=tr("the PDFs (files ending in .pdf), and the ranges: PAGES:STYLE[:START[:PREFIX]]"))
    sp.add_argument("-r", "--range", dest="named", nargs="+", action="append", default=[],
                    metavar=tr("PAGES [KEY=VALUE]"),
                    help=tr("a range: PAGES [style=S] [start=N] [prefix=P] [suffix=X]"))
    sp.add_argument("-f", "--from-file", metavar=tr("LIST"),
                    help=tr("the labels of all the pages, one on each line (- for the standard input)"))
    sp.add_argument("-k", "--keep", action="store_true",
                    help=tr("keep the labels the PDF has, changing only the pages given"))
    sp.add_argument("--remove", type=int, action="append", default=[], metavar=tr("PAGE"),
                    help=tr("drop the range that starts at PAGE (the one before goes on over its pages); "
                            "implies --keep"))
    output_options(sp)

    sp = sub.add_parser("clear", parents=[common], help=tr("remove the page labels of PDFs"),
                        description=tr("Remove the page labels of PDFs: viewers then number their pages "
                                       "1, 2, 3 ..."))
    sp.add_argument("inputs", nargs="+", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    output_options(sp)

    sp = sub.add_parser("copy", parents=[common], help=tr("give PDFs the page labels of another"),
                        description=tr("Give PDFs the page labels of another PDF, for instance a new export "
                                       "of the same book. If they have fewer pages, the labels of the pages "
                                       "they lack are left out; if they have more, the last range goes on."))
    sp.add_argument("source", type=Path, metavar=tr("FROM"), help=tr("the PDF whose labels are copied"))
    sp.add_argument("inputs", nargs="+", type=Path, metavar=tr("FILE"), help=tr("the PDFs that get them"))
    output_options(sp)

    sp = sub.add_parser("view", parents=[common], help=tr("show or set how PDFs open in a viewer"),
                        description=tr("Show or set the view of PDFs when they are opened: the page "
                                       "layout, the page view and the page they open at. A PDF has one view "
                                       "for the whole document. Without options, the view is shown; the "
                                       "options not given are kept; 'default' leaves that part to the "
                                       "viewer."),
                        epilog=translate_paragraphs(VIEW_EPILOG),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("inputs", nargs="+", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    sp.add_argument("--layout", metavar=tr("LAYOUT"), help=tr("the page layout (see below)"))
    sp.add_argument("--page-view", "--zoom", dest="zoom", metavar=tr("VIEW"),
                    help=tr("the page view (see below), or a percentage, as 150%%"))
    sp.add_argument("--open-at", metavar=tr("PAGE"),
                    help=tr("the page it opens at (the pages of the file, from 1; LAST counts from the end)"))
    output_options(sp, tr("show the view the files would get, without writing anything"))

    sp = sub.add_parser("header-footer", parents=[common], help=tr("add headers and footers to PDFs"),
                        description=tr("Draw text at the top and bottom of the pages of PDFs: a header and "
                                       "a footer, each with a left, center and right place, with variables "
                                       "such as the page label or the date. Unlike the labels, they change "
                                       "the pages themselves."),
                        epilog=translate_paragraphs(HEADER_FOOTER_EPILOG),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("inputs", nargs="*", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    g = sp.add_argument_group(tr("text"))
    for slot in headfoot.SLOTS:
        g.add_argument("--" + slot.replace("_", "-"), dest=slot, metavar=tr("TEXT"),
                       help=tr("the text of the {place}", place=tr(headfoot.SLOT_TITLES[slot]).lower()))
    g = sp.add_argument_group(tr("margins"))
    g.add_argument("--units", choices=list(headfoot.POINTS), help=tr("the units of the margins (default: cm)"))
    for side in ("top", "bottom", "left", "right"):
        g.add_argument("--" + side, type=float, metavar=tr("SIZE"),
                       help=tr("the {side} margin", side=tr(headfoot.SIDES[side])))
    g.add_argument("--shrink", action=argparse.BooleanOptionalAction, default=None,
                   help=tr("scale the content of the pages down to leave room for the header and footer"))
    g = sp.add_argument_group(tr("appearance"))
    g.add_argument("--font", choices=list(headfoot.FAMILIES), help=tr("the font (default: helvetica)"))
    g.add_argument("--size", type=float, metavar=tr("POINTS"), help=tr("the font size (default: 10)"))
    g.add_argument("--color", metavar="#RRGGBB", help=tr("the color of the text"))
    g.add_argument("--bold", action=argparse.BooleanOptionalAction, default=None, help=tr("bold text"))
    g.add_argument("--italic", action=argparse.BooleanOptionalAction, default=None, help=tr("italic text"))
    g.add_argument("--border", action=argparse.BooleanOptionalAction, default=None,
                   help=tr("a border around each text"))
    g.add_argument("--border-color", metavar="#RRGGBB", help=tr("the color of the border"))
    g.add_argument("--border-width", type=float, metavar=tr("POINTS"), help=tr("the width of the border"))
    g.add_argument("--background", metavar="#RRGGBB", help=tr("a background color behind each text ('none': no background)"))
    stamp_options(sp, tr("headers and footers"))
    sp.add_argument("--remove-bates", action="store_true",
                    help=tr("take away only the headers and footers with Bates numbers (on --pages, or all)"))
    output_options(sp, tr("show the header and footer of the first and last pages, without writing anything"))

    sp = sub.add_parser("watermark", parents=[common], help=tr("add watermarks to PDFs"),
                        description=tr("Draw a watermark on the pages of PDFs: a text, such as Draft or Copy, "
                                       "or a page of another PDF, in front of their content or behind it, "
                                       "turned, scaled and with some transparency. Like headers and footers, "
                                       "it changes the pages themselves."),
                        epilog=translate_paragraphs(WATERMARK_EPILOG),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("inputs", nargs="*", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    g = sp.add_argument_group(tr("what"))
    g.add_argument("--text", metavar=tr("TEXT"), help=tr("the text of the watermark (\\n starts another line)"))
    g.add_argument("--file", dest="source", metavar=tr("PDF"), help=tr("a PDF whose page is the watermark"))
    g.add_argument("--file-page", dest="source_page", type=int, metavar="N",
                   help=tr("the page of --file (default: 1)"))
    g = sp.add_argument_group(tr("appearance"))
    g.add_argument("--font", choices=list(headfoot.FAMILIES), help=tr("the font (default: helvetica)"))
    g.add_argument("--size", type=float, metavar=tr("POINTS"), help=tr("the font size (default: 60)"))
    g.add_argument("--color", metavar="#RRGGBB", help=tr("the color of the text (default: #808080)"))
    g.add_argument("--bold", action=argparse.BooleanOptionalAction, default=None, help=tr("bold text"))
    g.add_argument("--italic", action=argparse.BooleanOptionalAction, default=None, help=tr("italic text"))
    g.add_argument("--scale", type=float, metavar=tr("PERCENT"),
                   help=tr("fill this percent of the page (default: 0, its own size)"))
    g.add_argument("--rotation", type=float, metavar=tr("DEGREES"),
                   help=tr("turn it, counterclockwise (default: 45)"))
    g.add_argument("--opacity", metavar=tr("OPACITY"), help=tr("from 0 to 1, or 0%% to 100%% (default: 0.5)"))
    g.add_argument("--behind", action=argparse.BooleanOptionalAction, default=None,
                   help=tr("behind the content of the pages (default: in front of it)"))
    g.add_argument("--print", dest="on_print", action=argparse.BooleanOptionalAction, default=None,
                   help=tr("shown when printing (default: yes)"))
    g.add_argument("--screen", dest="on_screen", action=argparse.BooleanOptionalAction, default=None,
                   help=tr("shown on the screen (default: yes)"))
    g = sp.add_argument_group(tr("position"))
    g.add_argument("--horizontal", dest="halign", choices=list(watermark.HALIGNS),
                   help=tr("left, center or right (default: center)"))
    g.add_argument("--vertical", dest="valign", choices=list(watermark.VALIGNS),
                   help=tr("top, center or bottom (default: center)"))
    g.add_argument("--units", choices=list(headfoot.POINTS), help=tr("the units of the offsets (default: cm)"))
    g.add_argument("--hoffset", type=float, metavar=tr("SIZE"),
                   help=tr("move it across, from the side chosen (or to the right of the center)"))
    g.add_argument("--voffset", type=float, metavar=tr("SIZE"),
                   help=tr("move it up or down, from the edge chosen (or up from the center)"))
    stamp_options(sp, tr("watermarks"))
    output_options(sp, tr("show the watermark of the first and last pages, without writing anything"))

    sp = sub.add_parser("pages", parents=[common], help=tr("move, delete, rotate, insert or split pages of PDFs"),
                        description=tr("Arrange the pages of PDFs: move, delete, duplicate, reverse or rotate "
                                       "them, put them in a new order, insert pages of another PDF or replace "
                                       "pages by them, and save some of them as a new file, or the whole as "
                                       "several."),
                        epilog=translate_paragraphs(PAGES_EPILOG), formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("inputs", nargs="+", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    g = sp.add_argument_group(tr("operations (in the order given)"))
    g.add_argument("--order", action=OperationAction, nargs=1, metavar=tr("PAGES"),
                   help=tr("the pages in this order (repeated: duplicated; left out: deleted)"))
    g.add_argument("--move", action=OperationAction, nargs=2, metavar=(tr("PAGES"), tr("WHERE")),
                   help=tr("move PAGES before page WHERE (or to the start or end)"))
    g.add_argument("--delete", action=OperationAction, nargs=1, metavar=tr("PAGES"), help=tr("delete PAGES"))
    g.add_argument("--duplicate", action=OperationAction, nargs="+", metavar=tr("PAGES [WHERE]"),
                   help=tr("copy PAGES, right after them or before page WHERE"))
    g.add_argument("--reverse", action=OperationAction, nargs="?", const="all", metavar=tr("PAGES"),
                   help=tr("reverse the order of PAGES (default: all)"))
    g.add_argument("--rotate", action=OperationAction, nargs=2, metavar=(tr("PAGES"), tr("DEGREES")),
                   help=tr("turn PAGES clockwise by 90, 180 or 270 degrees (-90: counterclockwise)"))
    g.add_argument("--insert-blank", action=OperationAction, nargs="+", metavar=tr("WHERE [COUNT]"),
                   help=tr("insert COUNT blank pages (default: 1) before page WHERE, as big as the page before "
                           "them (at the start, as the first page)"))
    g.add_argument("--insert", action=OperationAction, nargs="+", metavar=tr("PDF WHERE [PAGES]"),
                   help=tr("insert the pages of another PDF (or some of them) before page WHERE"))
    g.add_argument("--replace", action=OperationAction, nargs="+", metavar=tr("PAGES PDF [FIRST]"),
                   help=tr("replace the content of PAGES by pages of another PDF, from its page FIRST (default: "
                           "1); links and bookmarks stay"))
    g.add_argument("--extract", action=OperationAction, nargs=1, metavar=tr("PAGES"),
                   help=tr("keep only PAGES (with -o, a new file of them)"))
    g = sp.add_argument_group(tr("the labels and the result"))
    g.add_argument("--labels", choices=["follow", "position"], default="follow",
                   help=tr("the page labels follow the pages (default), or stay by position"))
    g.add_argument("--source-password", default="", metavar=tr("PASSWORD"),
                   help=tr("the password of the PDFs of --insert and --replace"))
    g.add_argument("--split-every", type=int, metavar="N", help=tr("save the result as files of N pages each"))
    g.add_argument("--split-at", metavar=tr("PAGES"), help=tr("save the result as files that start at PAGES"))
    output_options(sp, tr("show what the pages would be, without writing anything"))

    sp = sub.add_parser("completion", parents=[common], help=tr("print the completion script of a shell"),
                        description=tr("Print the script that completes py-pdftools's commands, options and "
                                       "files in SHELL. For instance: py-pdftools completion fish > "
                                       "~/.config/fish/completions/py-pdftools.fish"))
    sp.add_argument("shell", choices=["bash", "fish", "zsh"], metavar=tr("SHELL"),
                    help=tr("bash, fish or zsh"))

    sp = sub.add_parser("interface", parents=[common], help=tr("show or choose the language of the interface"),
                        description=tr("The language of the help, the messages and the window. The choice is "
                                       "kept in the configuration file; --interface CODE changes it for one run "
                                       "only."))
    sp.add_argument("language", nargs="?", choices=sorted(interface.names()),
                    help=tr("the language to use from now on; without it, the languages are listed and the "
                            "one in use is marked"))
    for name in LABEL_COMMANDS:  # (in the command line of py-pdftools, they are 'labels show' ...)
        sub.choices[name].prog = f"{prog} labels {name}"
    return parser


# =========================================================================== commands


def report(error: LabelError) -> None:
    print(tr("error: {error}", error=error), file=sys.stderr)


def show(a) -> int:
    failed = False
    for k, path in enumerate(a.inputs):
        if k and not (a.all or a.label is not None):
            print()
        try:
            with open_pdf(path, password=a.password) as pdf:
                n = len(pdf.pages)
                ranges = labels.read_labels(pdf)
                shown = view.read_view(pdf)
                added = stamps.additions(pdf)
        except LabelError as e:
            report(e)
            failed = True
            continue
        prefix = f"{path}: " if len(a.inputs) > 1 else ""
        if a.all:
            for page, label in enumerate(labels.page_labels(ranges, n), 1):
                print(f"{prefix}{page:>6}  {label}")
        elif a.label is not None:
            pages = labels.find_label(ranges, n, a.label)
            if pages:
                print(prefix + ", ".join(map(str, pages)))
            else:
                print(prefix + tr("no page is labelled {label!r}", label=a.label), file=sys.stderr)
                failed = True
        else:
            print_ranges(path, ranges, n, shown)
            print_additions(added)
    return 1 if failed else 0


def print_ranges(path: Path, ranges: list[labels.Range], n: int, shown: view.View = view.View()) -> None:
    """The ranges of a file (and its view when it is opened, if it has one), and the command that gives
    them to another file."""
    print(ntr("{path}: {count} page", "{path}: {count} pages", n, path=path))
    if not ranges:
        print(tr("No page labels: viewers number the pages 1, 2, 3 ..."))
    else:
        rows = [(pages_text(r, last), labels.describe(r, last), r.spec()) for r, last in labels.spans(ranges, n)]
        w1 = max(len(x[0]) for x in rows)
        w2 = max(len(x[1]) for x in rows)
        for pages, desc, spec in rows:
            print(f"  {pages:<{w1}}  {desc:<{w2}}  {spec}")
    if shown:
        print_view(shown)
    if not ranges:
        return
    print(tr("To give these labels to another file:"))
    print("  " + set_command(Path("FILE.pdf"), ranges).replace("FILE.pdf", tr("FILE.pdf")))


def print_additions(added: list[stamps.Addition]) -> None:
    """What py-pdftools added to the pages of a file (its headers and footers, and watermarks)."""
    if not added:
        return
    print(tr("Added to the pages by py-pdftools:"))
    for a in added:
        what = tr("header and footer") if a.kind == stamps.HEADER_FOOTER else tr("watermark")
        if a.bates:
            what += " " + tr("(with Bates numbers)")
        print("  " + ntr("{what}, on {count} page: {pages}", "{what}, on {count} pages: {pages}", len(a.pages),
                         what=what, pages=stamps.compact_pages(a.pages)))


def print_view(v: view.View, title: str | None = None) -> None:
    print(title or tr("When it is opened:"))
    rows = view.describe(v)
    width = max(len(what) for what, _ in rows)
    for what, how in rows:
        print(f"  {what + ':':<{width + 1}}  {how}")


def split_named(groups: list[list[str]]) -> tuple[list[list[str]], list[str]]:
    """The --range groups, and what was given after one of them that is not
    KEY=VALUE (``--range 9-200 style=roman 201:D book.pdf``: argparse gives
    201:D and book.pdf to --range)."""
    named, rest = [], []
    for group in groups:
        named.append([group[0]] + [t for t in group[1:] if "=" in t])
        rest += [t for t in group[1:] if "=" not in t]
    return named, rest


def is_file(item: str) -> bool:
    return item.lower().endswith(".pdf") or (":" not in item and Path(item).is_file())


def output_path(a, path: Path) -> Path:
    """Where the changed PATH is saved: itself (--in-place), --output, or a name made from its own
    (in --output-dir, or next to it), with --name-prefix and --name-suffix."""
    if a.in_place:
        return path
    if a.output:
        return a.output
    folder = getattr(a, "output_dir", None)
    suffix = getattr(a, "name_suffix", None)
    if suffix is None:
        suffix = "" if folder else "-labelled"
    return (folder or path.parent) / f"{getattr(a, 'name_prefix', '')}{path.stem}{suffix}.pdf"


def print_spans(ranges: list[labels.Range], n: int) -> None:
    for r, last in labels.spans(ranges, n):
        print(f"  {pages_text(r, last)}: {labels.describe(r, last)}")


def change(a, inputs: list[Path], make, write=labels.write_labels, describe=print_spans) -> int:
    """Give each of INPUTS what MAKE(pdf, n) returns (with WRITE(pdf, it): page labels
    by default), and save it (or, with --dry-run, only say what it would be);
    then DESCRIBE(it, n)."""
    if a.output is not None and len(inputs) > 1:
        raise LabelError(tr("--output takes one input only; with several, each is saved as "
                            "<input>-labelled.pdf, or changed with --in-place"))
    if (a.in_place or a.output) and (getattr(a, "name_prefix", "") or getattr(a, "name_suffix", None) is not None):
        raise LabelError(tr("--name-prefix and --name-suffix go with --output-dir, or alone"))
    standard = getattr(a, "conform", None)
    if standard and not a.dry_run and not conform.available():
        raise LabelError(tr("{standard} can't be made: {command} is not installed (or not on the PATH, in ~/bin "
                            "or in ~/.local/bin, or where the setting pdfconform says)",
                            standard=conform.label(standard), command=conform.COMMAND))
    if getattr(a, "output_dir", None) is not None and not a.dry_run:
        try:
            a.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise LabelError(tr("{path} cannot be written: {error}", path=a.output_dir, error=e)) from None
    failed = False
    for path in inputs:
        try:
            with open_pdf(path, a.in_place and not a.dry_run, a.password) as pdf:
                n = len(pdf.pages)
                made = make(pdf, n)
                out = output_path(a, path)
                if a.dry_run:
                    print(ntr("{path} would get ({count} page):", "{path} would get ({count} pages):", n,
                              path=out))
                else:
                    if not a.in_place and out.resolve() == path.resolve():
                        raise LabelError(tr("the output is the input file; use --in-place to change it"))
                    write(pdf, made)
                    save_pdf(pdf, out)
                    wrote = ntr("Wrote {path} ({count} page)", "Wrote {path} ({count} pages)", len(pdf.pages),
                                path=out)
                    if not standard:
                        print(wrote)
            if standard and not a.dry_run:  # (once the file is closed: an input changed in place is replaced)
                try:
                    check = conform.convert(out, out, standard, a.password)
                except conform.ConformError as e:
                    raise LabelError(tr("{path} was saved as a plain PDF, but it could not be made {standard}: "
                                        "{error}", path=out, standard=conform.label(standard), error=e)) from None
                print(wrote + " — " + conform.label(standard) + (f" ({check})" if check else ""))
        except LabelError as e:
            report(e)
            failed = True
            continue
        describe(made, n)
    return 1 if failed else 0


def set_labels(a) -> int:
    named, rest = split_named(a.named)
    items = a.items + rest
    inputs = [Path(t) for t in items if is_file(t)]
    compact = [t for t in items if not is_file(t)]
    if not inputs:
        raise LabelError(tr("no PDF given (the files must end in .pdf)"))
    if not (compact or named or a.remove or a.from_file):
        raise LabelError(tr("no ranges given (see py-pdftools labels set -h)"))
    listed = read_list(a.from_file) if a.from_file else None

    def make(pdf, n):
        if listed is not None:
            base = labels.from_list(listed, n)
        else:
            base = labels.read_labels(pdf) if a.keep or a.remove else []
        requests = [labels.parse_compact(s, n) for s in compact] + [labels.parse_named(g, n) for g in named]
        return labels.apply(base, requests, n, a.remove)

    return change(a, inputs, make)


def clear(a) -> int:
    return change(a, a.inputs, lambda pdf, n: [])


def copy(a) -> int:
    with open_pdf(a.source, password=a.password) as pdf:
        source = labels.read_labels(pdf)
    return change(a, a.inputs, lambda pdf, n: [r for r in source if r.page <= n])


class OperationAction(argparse.Action):
    """Keeps the operations of 'pages' in the order they are given (in a.operations)."""

    def __call__(self, parser, namespace, values, option_string=None):
        if not isinstance(values, list):
            values = [values]
        ops = list(getattr(namespace, "operations", None) or [])
        ops.append((self.dest, values))
        namespace.operations = ops


def make_operation(name: str, values: list[str], n: int, labels_choice: str, password: str):
    """An arrange.Operation from an option of 'pages' (NAME, its VALUES), on a document of N pages."""
    kw = {"labels": labels_choice}

    def pages(spec):
        return tuple(arrange.parse_page_list(spec, n))

    if name == "order":
        return arrange.Order(tuple(arrange.parse_order(values[0], n)), **kw)
    if name == "extract":
        return arrange.Order(pages(values[0]), **kw)
    if name == "move":
        return arrange.Move(pages(values[0]), arrange.parse_where(values[1], n), **kw)
    if name == "delete":
        return arrange.Delete(pages(values[0]), **kw)
    if name == "duplicate":
        if len(values) > 2:
            raise LabelError(tr("--duplicate takes PAGES and, if wished, WHERE"))
        return arrange.Duplicate(pages(values[0]), arrange.parse_where(values[1], n) if len(values) > 1 else 0, **kw)
    if name == "reverse":
        return arrange.Reverse(() if values[0] == "all" else pages(values[0]), **kw)
    if name == "rotate":
        try:
            angle = int(values[1])
        except ValueError:
            angle = None
        if angle is None or angle % 360 not in arrange.ANGLES:
            raise LabelError(tr("pages turn by 90, 180 or 270 degrees (not {angle})", angle=values[1]))
        return arrange.Rotate(pages(values[0]), angle, **kw)
    if name == "insert_blank":
        if len(values) > 2 or (len(values) == 2 and not values[1].isdigit()):
            raise LabelError(tr("--insert-blank takes WHERE and, if wished, how many pages"))
        return arrange.InsertBlank(arrange.parse_where(values[0], n), int(values[1]) if len(values) > 1 else 1, **kw)
    if name == "insert":
        if not 2 <= len(values) <= 3:
            raise LabelError(tr("--insert takes a PDF, WHERE and, if wished, its PAGES"))
        source = values[0]
        count = arrange.source_count(source, password)
        chosen = tuple(arrange.parse_page_list(values[2], count)) if len(values) > 2 else ()
        return arrange.Insert(source, chosen, arrange.parse_where(values[1], n), password, **kw)
    if name == "replace":
        if not 2 <= len(values) <= 3:
            raise LabelError(tr("--replace takes PAGES, a PDF and, if wished, its FIRST page"))
        first = int(values[2]) if len(values) > 2 and values[2].isdigit() else 1
        return arrange.Replace(pages(values[0]), values[1], first, password, **kw)
    raise LabelError(name)


def arranged(pdf, a) -> tuple[list, list]:
    """(the operations, the label ranges after them) that the options of 'pages' give for PDF."""
    n = len(pdf.pages)
    ranges = labels.read_labels(pdf)
    operations = []
    for name, values in getattr(a, "operations", None) or []:
        op = make_operation(name, values, n, a.labels, a.source_password)
        ranges = arrange.ranges_after(op, ranges, n)
        n = len(op.items(n)) if op.moves_pages() else n
        operations.append(op)
    return operations, ranges


def describe_arranged(made, n: int) -> None:
    operations, ranges, count = made
    for op in operations:
        print("  " + op.describe())
    print("  " + ntr("{count} page at the end", "{count} pages at the end", count))
    for r, last in labels.spans(ranges, count):
        print(f"    {pages_text(r, last)}: {labels.describe(r, last)}")


def pages_command(a) -> int:
    if not getattr(a, "operations", None) and not (a.split_every or a.split_at):
        raise LabelError(tr("nothing to do: give an operation, as --move, --delete or --rotate"))

    def make(pdf, n):
        operations, ranges = arranged(pdf, a)
        count = arrange.items_of(operations, n)[1]
        return operations, ranges, count

    def write(pdf, made):
        operations, ranges, _ = made
        for op in operations:
            op.apply(pdf)
        labels.write_labels(pdf, ranges)

    if not (a.split_every or a.split_at):
        return change(a, a.inputs, make, write=write, describe=describe_arranged)
    return split_command(a, make, write)


def split_command(a, make, write) -> int:
    """pages --split-every / --split-at: the result of the operations, saved as several files."""
    if a.output is not None or a.in_place:
        raise LabelError(tr("--split-every and --split-at save several files: use --output-dir, not -o or -i"))
    failed = False
    for path in a.inputs:
        try:
            with open_pdf(path, password=a.password) as pdf:
                made = make(pdf, len(pdf.pages))
                write(pdf, made)
                n = len(pdf.pages)
                at = arrange.parse_page_list(a.split_at, n) if a.split_at else None
                parts = arrange.split_parts(n, a.split_every or 0, at)
                ranges = made[1]
                data = io.BytesIO()
                pdf.save(data)
            folder = a.output_dir or path.parent
            suffix = a.name_suffix or ""
            for k, (first, last) in enumerate(parts, 1):
                target = folder / f"{a.name_prefix}{path.stem}{suffix}-{k}.pdf"
                if a.dry_run:
                    print(tr("{path} would get pages {first}-{last}", path=target, first=first, last=last))
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                with pikepdf.open(io.BytesIO(data.getvalue()), password=a.password) as part:
                    op = arrange.Order(tuple(range(first, last + 1)))
                    part_ranges = arrange.ranges_after(op, ranges, n)
                    op.apply(part)
                    labels.write_labels(part, part_ranges)
                    save_pdf(part, target)
                print(ntr("Wrote {path} ({count} page)", "Wrote {path} ({count} pages)", last - first + 1,
                          path=target))
        except LabelError as e:
            report(e)
            failed = True
    return 1 if failed else 0


def view_command(a) -> int:
    given = {"layout": a.layout, "zoom": a.zoom, "page": a.open_at}
    if all(v is None for v in given.values()):
        if a.output is not None or a.in_place or a.dry_run:
            raise LabelError(tr("nothing to change: give --layout, --page-view or --open-at"))
        failed = False
        for k, path in enumerate(a.inputs):
            try:
                with open_pdf(path, password=a.password) as pdf:
                    shown = view.read_view(pdf)
            except LabelError as e:
                report(e)
                failed = True
                continue
            if k:
                print()
            print_view(shown, f"{path}:")
        return 1 if failed else 0
    return change(a, a.inputs, lambda pdf, n: view.changed(view.read_view(pdf), n, **given),
                  write=view.write_view, describe=lambda v, n: print_view(v, tr("When it is opened:")))


# what header-footer and watermark take from the options (besides those of each one)
STAMP_KEYS = ("pages", "parity", "bates_prefix", "bates_start", "bates_digits", "bates_suffix", "date_format",
              "show_on_menu", "font", "size", "color", "bold", "italic", "units")
HEADER_FOOTER_KEYS = STAMP_KEYS + ("top", "bottom", "left", "right", "shrink", "border", "border_color",
                                   "border_width")
WATERMARK_KEYS = STAMP_KEYS + ("source", "source_page", "scale", "rotation", "behind", "on_print", "on_screen",
                               "halign", "valign", "hoffset", "voffset")


def opacity(value: str) -> float:
    """0.3 or 30%: an opacity from 0 to 1."""
    text = value.strip()
    try:
        return float(text[:-1]) / 100 if text.endswith("%") else float(text)
    except ValueError:
        raise LabelError(tr("the opacity must be from 0 to 1, or 0% to 100% (not {value!r})", value=value)) from None


def stamp_changes(a, kind: str) -> dict:
    """The settings the options of header-footer or watermark give (those not given are left out)."""
    changes = {}
    if kind == stamps.HEADER_FOOTER:
        for slot in headfoot.SLOTS:
            if getattr(a, slot) is not None:
                changes[slot] = getattr(a, slot).replace("\\n", "\n")
        keys = HEADER_FOOTER_KEYS
    else:
        if a.text is not None:
            changes["text"] = a.text.replace("\\n", "\n")
            if a.source is None:
                changes["source"] = ""
        if a.source is not None and a.text is None:
            changes["text"] = ""
        if a.opacity is not None:
            changes["opacity"] = opacity(a.opacity)
        keys = WATERMARK_KEYS
    for key in keys:
        if getattr(a, key, None) is not None:
            changes[key] = getattr(a, key)
    if kind == stamps.HEADER_FOOTER and a.background is not None:
        changes["background"] = "" if a.background.strip().lower() in ("", "none") else a.background
    if a.save_profile:
        changes["name"] = a.save_profile
    return changes


def stamp_settings(a, kind: str, module, base=None):
    """The settings the options give, laid over BASE, or those of --profile, or the defaults."""
    cls = headfoot.HeaderFooter if kind == stamps.HEADER_FOOTER else watermark.Watermark
    if base is None:
        base = cls()
        if a.profile:
            found = module.read_profiles()
            if a.profile not in found:
                raise LabelError(tr("there is no profile {name!r} (see --list-profiles)", name=a.profile))
            base = found[a.profile]
    return module.check(dataclasses.replace(base, **stamp_changes(a, kind)))


def header_footer_settings(a) -> headfoot.HeaderFooter:
    return stamp_settings(a, stamps.HEADER_FOOTER, headfoot)


def describe_stamp(made, n: int) -> None:
    change, doc, offset = made
    if change.settings is None:
        what = (tr("headers and footers with Bates numbers taken away") if change.bates_only
                else tr("headers and footers taken away") if change.kind == stamps.HEADER_FOOTER
                else tr("watermarks taken away"))
        print("  " + what)
        return
    if isinstance(change.settings, headfoot.HeaderFooter):
        pages = [(number, [(tr(headfoot.SLOT_TITLES[slot]), text) for slot, text in texts.items() if text.strip()])
                 for number, texts in headfoot.page_texts(change.settings, doc, datetime.now(), offset)]
    else:
        pages = [(number, [(tr("Watermark"), text or tr("page {page} of {path}", page=change.settings.source_page,
                                                         path=change.settings.source))])
                 for number, text in watermark.page_texts(change.settings, doc, datetime.now(), offset)]
    if change.replaces is not None:
        print("  " + tr("(replacing the last one added)"))
    for number, texts in (pages[0], pages[-1]) if len(pages) > 1 else pages[:1]:
        print("  " + tr("page {page}", page=number) + ":")
        for what, text in texts:
            print(f"    {what}: {text}".replace("\n", " / "))
    print("  " + ntr("on {count} page", "on {count} pages", len(pages)))


def stamp_command(a, kind: str) -> int:
    """header-footer and watermark."""
    module = headfoot if kind == stamps.HEADER_FOOTER else watermark
    if a.list_profiles:
        found = module.read_profiles()
        if not found:
            print(tr("No profiles kept ({path})", path=module.profiles_path()))
        for name, settings in found.items():
            if kind == stamps.HEADER_FOOTER:
                summary = "; ".join(f"{tr(headfoot.SLOT_TITLES[s])}: {t}" for s, t in settings.texts().items()
                                    if t.strip())
            else:
                summary = settings.text or settings.source
            print(f"  {'*' if settings.show_on_menu else ' '} {name}  ({summary})")
        return 0
    if a.delete_profile:
        if not module.delete_profile(a.delete_profile):
            raise LabelError(tr("there is no profile {name!r} (see --list-profiles)", name=a.delete_profile))
        print(tr("Profile {name!r} forgotten", name=a.delete_profile))
        return 0
    removing = a.remove or getattr(a, "remove_bates", False)
    if sum([removing, a.update, a.add]) > 1:
        raise LabelError(tr("--add, --update and --remove go one at a time"))
    settings = None if (removing or a.update) else stamp_settings(a, kind, module)
    if a.save_profile:
        if settings is None:
            raise LabelError(tr("--save-profile keeps new settings: it doesn't go with --update or --remove"))
        try:
            path = module.save_profile(settings)
        except OSError as e:
            raise LabelError(tr("Could not keep the setting: {error}", error=e)) from None
        print(tr("Profile {name!r} kept in {path}", name=a.save_profile, path=path))
        if not a.inputs:
            return 0
    if not a.inputs:
        raise LabelError(tr("no PDF given (the files must end in .pdf)"))
    bates = {"offset": 0, "last": None}  # (Bates numbers go on from one file to the next)

    def make(pdf, n):
        doc = stamps.document_of(pdf, Path(pdf.filename))
        if removing:
            change = Change(None, kind=kind, pages=a.pages or "", bates_only=getattr(a, "remove_bates", False))
        elif a.update:
            last = module.last(pdf)
            if last is None:
                raise LabelError(tr("{path} has no {what} added by this version of py-pdftools to update",
                                    path=pdf.filename, what=tr("header and footer") if kind == stamps.HEADER_FOOTER
                                    else tr("watermark")))
            change = Change(stamp_settings(a, kind, module, last[1]), replaces=last[0])
        else:
            change = Change(settings, keep=a.add)
        offset = bates["offset"]
        if change.settings is not None:
            module.page_texts(change.settings, doc, datetime.now(), offset)  # (they can be written, first)
            used = change.bates_pages(n)
            if used:
                bates["offset"] += used
                bates["last"] = change.settings
        return change, doc, offset

    result = change(a, a.inputs, make, write=lambda pdf, made: made[0].apply(pdf, made[1], bates_offset=made[2]),
                    describe=describe_stamp)
    if bates["last"] is not None:
        print(tr("Next Bates number: {number}", number=stamps.bates_number(bates["last"], bates["offset"])))
    return result


def header_footer(a) -> int:
    return stamp_command(a, stamps.HEADER_FOOTER)


def watermark_command(a) -> int:
    return stamp_command(a, stamps.WATERMARK)


def completion(a) -> int:
    from ..cli import build_parser as whole
    from ..cli.completion import script

    print(script(a.shell, whole()), end="")
    return 0


def choose_interface(a) -> int:
    names = interface.names()
    if a.language is None:
        current = interface.code()
        print(tr("Languages of the interface:"))
        for code, name in names.items():
            print(f"  {'*' if code == current else ' '} {code}  {name}")
        print(tr("Configuration file: {path}", path=config.config_path()))
        return 0
    if not interface.use(a.language):
        raise LabelError(tr("the language {code} cannot be used: {error}", code=a.language,
                            error=interface.error()))
    try:
        path = config.set("interface", a.language)
    except OSError as e:
        raise LabelError(tr("Could not keep the setting: {error}", error=e)) from None
    print(tr("The interface is now in {name} (kept in {path}).", name=names[a.language], path=path))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    interface.use_configured(interface_option(argv))
    interface.translate_argparse()
    # "py-pdftools file.pdf ..." -> show
    words = [t for i, t in enumerate(argv) if not t.startswith("-") and (i == 0 or argv[i - 1] != "--interface")]
    first = words[0] if words else None
    if first and first not in COMMANDS and first.lower().endswith(".pdf"):
        argv.insert(argv.index(first), "show")
    parser = build_parser()
    a, extra = parser.parse_known_args(argv)
    # (argparse takes the positionals of a command in one go: those after an option are left over)
    if extra and a.command in ("set", "show", "clear", "copy", "view", "header-footer", "watermark", "pages") \
            and not any(t.startswith("-") and t != "-" for t in extra):
        if a.command == "set":
            a.items += extra
        else:
            a.inputs += [Path(t) for t in extra]
    elif extra:
        parser.error(tr("unrecognized arguments: %s") % " ".join(extra))
    if not a.command:
        parser.print_help()
        return 1
    commands = {"show": show, "set": set_labels, "clear": clear, "copy": copy, "view": view_command,
                "header-footer": header_footer, "watermark": watermark_command, "pages": pages_command,
                "completion": completion, "interface": choose_interface}
    try:
        return commands[a.command](a)
    except LabelError as e:
        report(e)
        return 1
