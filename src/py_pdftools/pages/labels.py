"""Page labels: the numbering a PDF viewer shows for each page.

A PDF keeps its page labels in the ``/PageLabels`` number tree of its
catalog. Each entry starts a *range* at a page (0-based in the file) and
gives its numbering style (``/S``), a prefix (``/P``) and the number of
its first page (``/St``, 1 if absent). A range lasts until the next one
starts. The styles of the file are:

    D   1, 2, 3 ...             (decimal arabic numerals)
    r   i, ii, iii ...          (lowercase roman numerals)
    R   I, II, III ...          (uppercase roman numerals)
    a   a, b ... z, aa, bb ...  (lowercase letters)
    A   A, B ... Z, AA, BB ...  (uppercase letters)
    -   no number: the prefix only (no /S in the file)

py-pdftools adds what the file cannot say by itself: folios (``f``: 1r,
1v, 2r, 2v ..., the recto and verso of each leaf) and a suffix after the
number (``[i]``, ``12bis``). Such a range is *virtual*: it is written as
one prefix-only entry per page, with the whole label, and recognised
again when the file is read (see read_labels and from_labels).

Here pages are 1-based, as users write them. A range is written on the
command line in one of two ways:

    compact:  PAGES:STYLE[:START[:PREFIX]]     9:D   215:D:1:App-   5:f:12v
    named:    PAGES [style=S] [start=N] [prefix=P] [suffix=X]

PAGES is a first page (``9``) or a span (``9-200``, ``9..200``, ``201-``);
``LAST`` and ``LAST-N`` name pages from the end. The START of folios is a
leaf and its side (``12v``; ``12`` is ``12r``).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, Pdf

from ..core.interface import N_, tr
from .numbers import (  # noqa: F401  (to_roman, to_letters and from_roman are part of this module's API)
    format_number, from_letters, from_roman, parse_folio, to_folio, to_letters, to_roman,
)

STYLES = ["D", "r", "R", "a", "A", "f", ""]  # ("" is no number; "f", folios, is py-pdftools' own)
NATIVE = {"D", "r", "R", "a", "A", ""}  # (the styles a PDF knows)

# the names a style may be given by, besides its code
STYLE_NAMES = {
    "D": "arabic", "r": "roman", "R": "ROMAN", "a": "letters", "A": "LETTERS", "f": "folio", "": "none",
}
NONE_CODE = "-"  # how "no number" is written in compact ranges

# what style_code takes: the codes, the names, "-" (as written) ...
STYLE_ALIASES = {**{c: c for c in STYLES}, **{name: c for c, name in STYLE_NAMES.items()}, NONE_CODE: ""}
# ... and these in any case
STYLE_ALIASES_ANY_CASE = {"none": "", "arabic": "D", "folio": "f", "folios": "f"}

# how the styles are shown (with tr)
STYLE_TITLES = {
    "D": N_("1, 2, 3"), "r": N_("i, ii, iii"), "R": N_("I, II, III"),
    "a": N_("a, b, c"), "A": N_("A, B, C"), "f": N_("1r, 1v, 2r (folios)"), "": N_("no number (prefix only)"),
}

KEYS = ("style", "start", "prefix", "suffix")  # of named ranges


class LabelError(Exception):
    """A user-facing error: a range that cannot be read, a page out of the document..."""


# =========================================================================== ranges


@dataclass(frozen=True)
class Range:
    """Pages from PAGE (1-based) on, numbered in STYLE from START, between PREFIX and SUFFIX.

    For folios, START counts sides: 1 is 1r, 2 is 1v, 3 is 2r ... Without a
    number (STYLE ""), the label is the prefix alone."""

    page: int
    style: str = "D"
    prefix: str = ""
    start: int = 1
    suffix: str = ""

    def __post_init__(self):
        if not self.style and self.suffix:  # (no number: the suffix is part of the text)
            object.__setattr__(self, "prefix", self.prefix + self.suffix)
            object.__setattr__(self, "suffix", "")

    @property
    def virtual(self) -> bool:
        """Can't the file say it in one entry (folios, or a suffix)?"""
        return self.style not in NATIVE or bool(self.suffix)

    def label(self, page: int) -> str:
        """The label of PAGE (1-based, in this range)."""
        if not self.style:
            return self.prefix
        return self.prefix + format_number(self.start + page - self.page, self.style) + self.suffix

    def start_text(self) -> str:
        return format_number(self.start, "f") if self.style == "f" else str(self.start)

    def spec(self) -> str:
        """This range as the command line writes it: compact (PAGE:STYLE[:START[:PREFIX]]),
        or named (PAGE style=S ...) if it has a suffix."""
        if self.suffix:
            return " ".join(self.tokens()[1:])
        out = f"{self.page}:{self.style or NONE_CODE}"
        if self.start != 1 or self.prefix:
            out += f":{self.start_text()}" if self.style else ":"
        if self.prefix:
            out += f":{self.prefix}"
        return out

    def tokens(self) -> list[str]:
        """This range as arguments of 'py-pdftools labels set'."""
        if not self.suffix:
            return [self.spec()]
        out = ["--range", str(self.page), f"style={STYLE_NAMES[self.style]}"]
        if self.start != 1:
            out.append(f"start={self.start_text()}")
        if self.prefix:
            out.append(f"prefix={self.prefix}")
        return out + [f"suffix={self.suffix}"]


def style_code(name: str) -> str:
    """The code of a style given by its code (D, r...), its name (arabic, roman...) or '-'."""
    code = STYLE_ALIASES.get(name, STYLE_ALIASES_ANY_CASE.get(name.lower()))
    if code is None:
        raise LabelError(tr("unknown style {style!r} (one of: {styles})", style=name, styles=styles_help()))
    return code


def styles_help() -> str:
    return ", ".join(f"{c or NONE_CODE} ({STYLE_NAMES[c]})" for c in STYLES)


# =========================================================================== pages


def page_number(token: str, n: int) -> int:
    """A page number (1-based, LAST and LAST-N allowed) checked against N pages."""
    t = token.strip().upper()
    if t.isdigit():
        page = int(t)
    elif t == "LAST":
        page = n
    elif re.fullmatch(r"LAST-\d+", t):
        page = n - int(t[5:])
    else:
        raise LabelError(tr("invalid page number {token!r}", token=token))
    if not 1 <= page <= n:
        raise LabelError(tr("page {page} is not in the document (1-{count})", page=token.strip(), count=n))
    return page


def parse_pages(spec: str, n: int) -> tuple[int, int | None]:
    """(first, last) of PAGES: 9 -> (9, None), 9-200 or 9..200 -> (9, 200), 201- -> (201, N)."""
    s = spec.strip()
    if ".." in s:
        a, b = s.split("..", 1)
    else:
        m = re.fullmatch(r"(\d+|LAST(?:-\d+)?)-(\d*|LAST(?:-\d+)?)", s, re.IGNORECASE)
        if m and not re.fullmatch(r"LAST-\d+", s, re.IGNORECASE):
            a, b = m.group(1), m.group(2)
        else:
            return page_number(s, n), None
    first = page_number(a, n)
    last = page_number(b, n) if b.strip() else n
    if last < first:
        raise LabelError(tr("the range {spec!r} ends before it starts", spec=spec))
    return first, last


@dataclass(frozen=True)
class Request:
    """A range asked for: a Range, and the last page it covers (None: up to the next range)."""

    range: Range
    last: int | None = None


def _start(value: str, spec: str, style: str) -> int:
    v = value.strip()
    if not v:
        return 1
    if style == "f":
        side = parse_folio(v)
        if side is None:
            raise LabelError(tr("the start of folios in {spec!r} must be a leaf and its side, as 12r or 12v",
                                spec=spec))
        return side
    if not v.isdigit() or int(v) < 1:
        raise LabelError(tr("the start number in {spec!r} must be a whole number from 1 on", spec=spec))
    return int(v)


def parse_compact(spec: str, n: int) -> Request:
    """PAGES:STYLE[:START[:PREFIX]] (the prefix may hold colons)."""
    parts = spec.split(":", 3)
    if len(parts) < 2:
        raise LabelError(tr("a range is PAGES:STYLE[:START[:PREFIX]], as 9:D or 215:D:1:App- (not {spec!r})",
                            spec=spec))
    first, last = parse_pages(parts[0], n)
    style = style_code(parts[1])
    start = _start(parts[2] if len(parts) > 2 and style else "", spec, style)
    prefix = parts[3] if len(parts) > 3 else ""
    return Request(Range(first, style, prefix, start), last)


def parse_named(tokens: list[str], n: int) -> Request:
    """PAGES [style=S] [start=N] [prefix=P] [suffix=X]."""
    if not tokens:
        raise LabelError(tr("--range needs the pages, as --range 9-200 style=arabic"))
    first, last = parse_pages(tokens[0], n)
    values = {"style": "D", "start": "", "prefix": "", "suffix": ""}
    for tok in tokens[1:]:
        key, eq, value = tok.partition("=")
        if not eq or key not in KEYS:
            raise LabelError(tr("{token!r} is not one of style=, start=, prefix= or suffix=", token=tok))
        values[key] = value
    spec = " ".join(tokens)
    style = style_code(values["style"])
    return Request(Range(first, style, values["prefix"], _start(values["start"], spec, style),
                         values["suffix"]), last)


# =========================================================================== labels from a list


Spec = tuple[str, str, int, str]  # (style, prefix, number, suffix) of a page


def _following(spec: Spec) -> Spec:
    """The spec of the page after one with SPEC, in the same range."""
    style, prefix, number, suffix = spec
    return style, prefix, number + 1, suffix


def _candidates(label: str) -> list[Spec]:
    """The ways LABEL may be written, the likeliest first; the last is always
    the label as a prefix with no number."""
    found: list[tuple[int, Spec]] = []

    def add(rank: int, style: str, m: re.Match, number: int):
        found.append((rank + (0 if m.end() == len(label) else 10) + (0 if m.start() == 0 else 1),
                      (style, label[:m.start()], number, label[m.end():])))

    for m in re.finditer(r"(?<!\d)(\d+)[rv](?![a-zA-Z])", label):
        if not m[1].startswith("0"):
            add(1, "f", m, parse_folio(m[0]))
    for m in re.finditer(r"\d+", label):
        if not m[0].startswith("0"):
            add(0, "D", m, int(m[0]))
    for style, rx in (("r", r"[ivxlcdm]+"), ("R", r"[IVXLCDM]+")):
        for m in re.finditer(rx, label):
            n = from_roman(m[0])
            if n:
                add(2, style, m, n)
    for style, rx in (("a", r"([a-z])\1*"), ("A", r"([A-Z])\1*")):
        for m in re.finditer(rx, label):
            add(3, style, m, from_letters(m[0]))
    out = [c for _, c in sorted(found, key=lambda x: x[0])]
    return out + [("", label, 1, "")]


def from_labels(labels: list[str], first_page: int = 1) -> list[Range]:
    """The ranges that give these LABELS to the pages from FIRST_PAGE on, as few as it can find.

    Each label is read as a prefix, a number and a suffix (or a text with no
    number) so that it goes on from the label before when it can."""
    out: list[Range] = []
    prev: Spec | None = None
    for i, label in enumerate(labels):
        cands = _candidates(label)
        if prev is not None:
            if prev[0] and _following(prev) in cands:
                prev = _following(prev)
                continue
            if not prev[0] and prev[1] == label:
                continue
        if i + 1 < len(labels) and labels[i + 1] == label:  # (the same text on several pages)
            out.append(Range(first_page + i, "", label))
            prev = ("", label, 1, "")
            continue
        nxt = _candidates(labels[i + 1]) if i + 1 < len(labels) else []
        pick = next((c for c in cands if c[0] and _following(c) in nxt), None)
        if pick is None:  # (a page on its own: plainly numbered if it can be, else its text)
            pick = next((c for c in cands if c[0] in NATIVE and c[0] and not c[1] and not c[3]), cands[-1])
        style, prefix, number, suffix = pick
        out.append(Range(first_page + i, style, prefix, number if style else 1, suffix))
        prev = pick
    return out


def from_list(listed: list[str], n: int) -> list[Range]:
    """The ranges that give a document of N pages the labels LISTED (one for each page)."""
    if len(listed) != n:
        raise LabelError(tr("the list has {labels} labels, but the document has {count} pages",
                            labels=len(listed), count=n))
    return from_labels(listed)


# =========================================================================== reading and writing


def _entries(node, seen: set) -> list[tuple[int, Dictionary]]:
    """The (index, label dictionary) pairs of a number tree node and its kids."""
    if not isinstance(node, Dictionary) or node.objgen in seen and node.objgen != (0, 0):
        return []
    seen.add(node.objgen)
    out = []
    nums = node.get("/Nums")
    if isinstance(nums, Array):
        for i in range(0, len(nums) - 1, 2):
            key, value = nums[i], nums[i + 1]
            if isinstance(value, Dictionary):
                try:
                    out.append((int(key), value))
                except (TypeError, ValueError):
                    pass
    for kid in node.get("/Kids", []):
        out += _entries(kid, seen)
    return out


def read_native(pdf: Pdf) -> list[Range]:
    """The ranges of the document's page labels as the file has them ([] if it has none)."""
    tree = pdf.Root.get("/PageLabels")
    n = len(pdf.pages)
    ranges: dict[int, Range] = {}
    for index, d in _entries(tree, set()):
        if not 0 <= index < n:
            continue
        s = d.get("/S")
        style = str(s)[1:] if isinstance(s, Name) and str(s)[1:] in NATIVE else ""
        prefix = str(d.get("/P", ""))
        try:
            start = max(int(d.get("/St", 1)), 1)
        except (TypeError, ValueError):
            start = 1
        ranges[index + 1] = Range(index + 1, style, prefix, start)
    return normalize(list(ranges.values()))


def read_labels(pdf: Pdf) -> list[Range]:
    """The ranges of the document's page labels ([] if it has none), with the
    virtual ones (folios, suffixes) found again in runs of one-page entries."""
    n = len(pdf.pages)
    ranges = read_native(pdf)
    out: list[Range] = []
    run: list[Range] = []

    def flush():
        if len(run) > 1:
            out.extend(from_labels([r.prefix for r in run], run[0].page))
        else:
            out.extend(run)
        run.clear()

    for r, last in spans(ranges, n):
        if not r.style and last == r.page:
            run.append(r)
        else:
            flush()
            out.append(r)
    flush()
    return normalize(out)


def entries(ranges: list[Range], n: int) -> list[tuple[int, str, str, int]]:
    """The entries of the tree of page labels that gives a document of N pages these RANGES:
    (page, from 1; style, '' for none; prefix; first number). Virtual ranges are one prefix-only
    entry for each page."""
    out = []
    for r, last in spans(normalize(ranges), n):
        if r.virtual:
            out += [(page, "", r.label(page), 1) for page in range(r.page, last + 1)]
        else:
            out.append((r.page, r.style, r.prefix, r.start))
    return out


def write_labels(pdf: Pdf, ranges: list[Range]) -> None:
    """Give the document these ranges ([]: no page labels at all). Virtual
    ranges are written as one prefix-only entry for each page."""
    ranges = normalize(ranges)
    if not ranges:
        if "/PageLabels" in pdf.Root:
            del pdf.Root["/PageLabels"]
        return
    nums = Array()
    for page, style, prefix, start in entries(ranges, len(pdf.pages)):
        d = Dictionary(Type=Name.PageLabel)
        if style:
            d.S = Name("/" + style)
        if prefix:
            d.P = pikepdf.String(prefix)
        if start != 1:
            d.St = start
        nums.append(page - 1)
        nums.append(pdf.make_indirect(d))
    pdf.Root.PageLabels = pdf.make_indirect(Dictionary(Nums=nums))


# =========================================================================== computing


def normalize(ranges: list[Range]) -> list[Range]:
    """RANGES sorted by page, one per page (the last given wins), starting at page 1."""
    by_page: dict[int, Range] = {}
    for r in ranges:
        by_page[r.page] = r
    out = [by_page[p] for p in sorted(by_page)]
    if out and out[0].page != 1:
        out.insert(0, Range(1))
    return out


def page_labels(ranges: list[Range], n: int) -> list[str]:
    """The label of each of N pages (their numbers if there are no ranges)."""
    ranges = normalize(ranges)
    if not ranges:
        return [str(i + 1) for i in range(n)]
    out = []
    k = 0
    for page in range(1, n + 1):
        while k + 1 < len(ranges) and ranges[k + 1].page <= page:
            k += 1
        out.append(ranges[k].label(page))
    return out


def find_label(ranges: list[Range], n: int, label: str) -> list[int]:
    """The pages (1-based) labelled LABEL; if none, those labelled so ignoring case."""
    labels = page_labels(ranges, n)
    exact = [i + 1 for i, x in enumerate(labels) if x == label]
    return exact or [i + 1 for i, x in enumerate(labels) if x.casefold() == label.casefold()]


def spans(ranges: list[Range], n: int) -> list[tuple[Range, int]]:
    """Each range of a document of N pages with its last page."""
    ranges = [r for r in normalize(ranges) if r.page <= n]
    return [(r, (ranges[i + 1].page - 1) if i + 1 < len(ranges) else n) for i, r in enumerate(ranges)]


def _page_specs(ranges: list[Range], n: int) -> list[Spec]:
    out = []
    ranges = normalize(ranges) or [Range(1)]
    for r, last in spans(ranges, n):
        for page in range(r.page, last + 1):
            out.append((r.style, r.prefix, r.start + page - r.page, r.suffix))
    return out


def _compress(specs: list[Spec]) -> list[Range]:
    """The fewest ranges giving these pages."""
    out: list[Range] = []
    prev = None
    for i, (style, prefix, number, suffix) in enumerate(specs):
        continues = (prev is not None and prev[0] == style and prev[1] == prefix and prev[3] == suffix
                     and (not style or number == prev[2] + 1))
        if not continues:
            out.append(Range(i + 1, style, prefix, number if style else 1, suffix))
        prev = (style, prefix, number, suffix)
    return out


def apply(base: list[Range], requests: list[Request], n: int, remove: list[int] = ()) -> list[Range]:
    """BASE (the ranges kept) with the REQUESTS laid over it, in a document of N pages.

    A request without a last page lasts until the next range starts (in BASE,
    or another request without a last page). Requests with a last page are
    laid over those: after one, the pages go on with the numbers they had.
    REMOVE: first pages whose range is dropped from BASE first (the range
    before it goes on over its pages).
    """
    base = normalize(base)
    for page in remove:
        if page == 1 or page not in {r.page for r in base}:
            raise LabelError(tr("no range starts at page {page} (ranges start at: {pages})", page=page,
                                pages=", ".join(str(r.page) for r in base[1:]) or "-"))
        base = [r for r in base if r.page != page]
    specs = _page_specs(base, n)
    open_ended = [q for q in requests if q.last is None]
    starts = {r.page for r in base} | {q.range.page for q in open_ended}
    for q in open_ended + [q for q in requests if q.last is not None]:
        r = q.range
        last = q.last
        if last is None:
            later = [p for p in starts if p > r.page]
            last = min(later) - 1 if later else n
        for page in range(r.page, last + 1):
            specs[page - 1] = (r.style, r.prefix, r.start + page - r.page, r.suffix)
    return _compress(specs)


# =========================================================================== chosen pages


def blocks(pages) -> list[tuple[int, int]]:
    """The runs of consecutive PAGES: [3, 4, 5, 9] -> [(3, 5), (9, 9)]."""
    out: list[tuple[int, int]] = []
    for p in sorted(set(pages)):
        if out and p == out[-1][1] + 1:
            out[-1] = (out[-1][0], p)
        else:
            out.append((p, p))
    return out


def number_pages(ranges: list[Range], n: int, pages, style: str, prefix: str = "", start: int = 1,
                 suffix: str = "") -> list[Range]:
    """RANGES with PAGES numbered in STYLE from START, one after the other (the
    pages between them, if they are not consecutive, keep their labels)."""
    requests = []
    count = 0
    for first, last in blocks(pages):
        requests.append(Request(Range(first, style, prefix, start + count if style else 1, suffix), last))
        count += last - first + 1
    return apply(ranges, requests, n)


def continue_numbering(ranges: list[Range], n: int, pages) -> list[Range]:
    """RANGES with each run of PAGES numbered to continue from the page before it."""
    specs = _page_specs(ranges, n)
    requests = []
    for first, last in blocks(pages):
        if first == 1:
            raise LabelError(tr("page 1 has no page before it to go on from"))
        style, prefix, number, suffix = specs[first - 2]
        requests.append(Request(Range(first, style, prefix, number + 1 if style else 1, suffix), last))
    return apply(ranges, requests, n)


def relabel(ranges: list[Range], n: int, new: dict[int, str]) -> list[Range]:
    """RANGES with the pages of NEW ({page: label}) given those labels, each run
    of them as the fewest ranges that give them (see from_labels)."""
    requests = []
    for first, last in blocks(new):
        found = from_labels([new[p] for p in range(first, last + 1)], first)
        for i, r in enumerate(found):
            requests.append(Request(r, found[i + 1].page - 1 if i + 1 < len(found) else last))
    return apply(ranges, requests, n)


def describe(r: Range, last: int) -> str:
    """'i … viii' (the labels of the first and last pages of a range)."""
    a, b = r.label(r.page), r.label(last)
    if last == r.page:
        return a
    if not r.style:
        return tr("{label} (every page)", label=a) if a else tr("(no label)")
    return f"{a} … {b}"


def pages_text(r: Range, last: int) -> str:
    """'pages 9-200' (or 'page 9': the pages of a range)."""
    if last > r.page:
        return tr("pages {first}-{last}", first=r.page, last=last)
    return tr("page {first}", first=r.page)


def set_command(input: Path, ranges: list[Range]) -> str:
    """The command line that gives a file these RANGES."""
    ranges = normalize(ranges)
    if not ranges:
        return shlex.join(["py-pdftools", "labels", "clear", str(input)])
    tokens = [t for r in ranges if not r.suffix for t in r.tokens()]
    tokens += [t for r in ranges if r.suffix for t in r.tokens()]  # (--range ... last: it takes the rest)
    return shlex.join(["py-pdftools", "labels", "set", str(input)] + tokens)
