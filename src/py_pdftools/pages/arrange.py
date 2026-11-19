"""Arranging the pages of a PDF: moving, deleting, duplicating, reversing, putting them in a new
order, inserting pages of another PDF, replacing pages by them, and rotating pages; and saving
some of the pages as new files (extracting, splitting).

Each operation that changes the sequence of pages says what the new sequence is: for each page
of the result, which page it was (its position, from 1) or which page of another PDF it is
(Inserted). The pages keep their objects, so their bookmarks, links and everything added to them
go with them; a page duplicated is a copy, with copies of its annotations; and the bookmarks,
links and destinations that went to a page deleted go to the page after it (or, if none is left
after it, the one before).

What becomes of the page labels is up to the caller (labels_after): they FOLLOW the pages (each
page keeps its label, and inserted pages bring the labels they had), or they stay by POSITION
(the ranges stay where they are, and the pages take the labels of their new places).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, Page, Pdf

from ..core.interface import N_, ntr, tr
from .labels import LabelError, page_labels, parse_pages, read_labels

FOLLOW, POSITION = "follow", "position"  # what the labels do when the pages change places
LABEL_CHOICES = {FOLLOW: N_("The labels follow the pages"), POSITION: N_("The pages are renumbered by position")}
ANGLES = (90, 180, 270)  # (clockwise)


@dataclass(frozen=True)
class Inserted:
    """Page PAGE (from 1) of the PDF at SOURCE."""

    source: str
    page: int
    password: str = ""


@dataclass(frozen=True)
class Blank:
    """A blank page, of the size of the page at position LIKE (from 1)."""

    like: int


Item = int | Inserted | Blank  # a page of the result: its position before, a page of another PDF, or a blank page


# =========================================================================== lists of pages


def parse_page_list(spec: str, n: int) -> list[int]:
    """The pages (1-based, in order, once each) of a list as '9-20,31', 'all', 'even', 'odd' or
    '1-50,odd' (even and odd keep those of the others, or of all)."""
    pages: set[int] = set()
    parity = ""
    some = False
    for part in (p.strip() for p in spec.split(",")):
        word = part.lower()
        if not part:
            continue
        if word in ("even", "odd"):
            parity = word
        elif word == "all":
            pages.update(range(1, n + 1))
            some = True
        else:
            first, last = parse_pages(part, n)
            pages.update(range(first, (last or first) + 1))
            some = True
    if not some:
        pages = set(range(1, n + 1))
    if parity:
        pages = {p for p in pages if p % 2 == (0 if parity == "even" else 1)}
    if not pages:
        raise LabelError(tr("no page is chosen by {spec!r}", spec=spec))
    return sorted(pages)


def parse_order(spec: str, n: int) -> list[int]:
    """A sequence of pages, as '1-8,20-30,9-19,31-' (in that order; pages may be repeated or left
    out; a span may go down, as 10-1)."""
    out: list[int] = []
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        a, sep, b = part.partition("-")
        if sep and a.strip().isdigit() and b.strip().isdigit() and int(a) > int(b):
            first, last = parse_pages(f"{b}-{a}", n)
            out.extend(range(last, first - 1, -1))
        else:
            first, last = parse_pages(part, n)
            out.extend(range(first, (last or first) + 1))
    if not out:
        raise LabelError(tr("no page is chosen by {spec!r}", spec=spec))
    return out


def parse_where(spec: str, n: int) -> int:
    """Where pages go: before page N (1-based), at the start, or at the end (n + 1)."""
    word = spec.strip().lower()
    if word in ("start", "begin", "first"):
        return 1
    if word in ("end", "last+1"):
        return n + 1
    first, _ = parse_pages(spec, n)
    return first


# =========================================================================== the operations


@dataclass(frozen=True)
class Operation:
    """An operation on the pages; LABELS: what the page labels do (FOLLOW or POSITION)."""

    labels: str = field(default=FOLLOW, kw_only=True)

    def items(self, n: int) -> list[Item]:
        """The pages of the result, for a document of N pages."""
        return list(range(1, n + 1))

    def apply(self, pdf: Pdf) -> None:
        rebuild(pdf, self.items(len(pdf.pages)))

    def moves_pages(self) -> bool:
        """Whether it changes which page is where (and so may change the labels)."""
        return True

    def describe(self) -> str:
        return ""


def _check_pages(pages, n: int) -> tuple[int, ...]:
    pages = tuple(sorted(set(pages)))
    if not pages or pages[0] < 1 or pages[-1] > n:
        raise LabelError(tr("the pages must be from 1 to {count}", count=n))
    return pages


@dataclass(frozen=True)
class Order(Operation):
    """The pages in this ORDER (positions, from 1; repeated: duplicated; left out: deleted)."""

    order: tuple[int, ...] = ()

    def items(self, n: int) -> list[Item]:
        if not self.order or min(self.order) < 1 or max(self.order) > n:
            raise LabelError(tr("the pages must be from 1 to {count}", count=n))
        return list(self.order)

    def describe(self) -> str:
        return tr("New order of the pages")


@dataclass(frozen=True)
class Move(Operation):
    """PAGES moved before page BEFORE (n + 1: to the end), keeping their order."""

    pages: tuple[int, ...] = ()
    before: int = 1

    def items(self, n: int) -> list[Item]:
        chosen = _check_pages(self.pages, n)
        rest = [p for p in range(1, n + 1) if p not in chosen]
        at = sum(1 for p in rest if p < self.before)
        return rest[:at] + list(chosen) + rest[at:]

    def describe(self) -> str:
        return tr("Pages moved")


@dataclass(frozen=True)
class Delete(Operation):
    pages: tuple[int, ...] = ()

    def items(self, n: int) -> list[Item]:
        chosen = set(_check_pages(self.pages, n))
        kept = [p for p in range(1, n + 1) if p not in chosen]
        if not kept:
            raise LabelError(tr("a document needs one page at least: not every page can be deleted"))
        return kept

    def describe(self) -> str:
        return tr("Pages deleted")


@dataclass(frozen=True)
class Duplicate(Operation):
    """Copies of PAGES, put before page BEFORE (0: right after the last of them)."""

    pages: tuple[int, ...] = ()
    before: int = 0

    def items(self, n: int) -> list[Item]:
        chosen = list(_check_pages(self.pages, n))
        before = self.before or chosen[-1] + 1
        out = list(range(1, n + 1))
        at = before - 1
        return out[:at] + chosen + out[at:]

    def describe(self) -> str:
        return tr("Pages duplicated")


@dataclass(frozen=True)
class Reverse(Operation):
    """PAGES (all if none) in the reverse order, in the places they had."""

    pages: tuple[int, ...] = ()

    def items(self, n: int) -> list[Item]:
        chosen = list(_check_pages(self.pages, n)) if self.pages else list(range(1, n + 1))
        out = list(range(1, n + 1))
        for place, page in zip(chosen, reversed(chosen)):
            out[place - 1] = page
        return out

    def describe(self) -> str:
        return tr("Pages reversed")


@dataclass(frozen=True)
class Insert(Operation):
    """Pages SOURCE_PAGES (all if none) of the PDF SOURCE, put before page BEFORE (n + 1: at the end)."""

    source: str = ""
    source_pages: tuple[int, ...] = ()
    before: int = 1
    password: str = ""

    def items(self, n: int) -> list[Item]:
        count = source_count(self.source, self.password)
        pages = self.source_pages or tuple(range(1, count + 1))
        if min(pages) < 1 or max(pages) > count:
            raise LabelError(tr("{path} has no page {page}", path=self.source, page=max(pages)))
        if not 1 <= self.before <= n + 1:
            raise LabelError(tr("the pages must be from 1 to {count}", count=n + 1))
        out: list[Item] = list(range(1, n + 1))
        at = self.before - 1
        return out[:at] + [Inserted(self.source, p, self.password) for p in pages] + out[at:]

    def describe(self) -> str:
        return tr("Pages inserted from {path}", path=Path(self.source).name)


@dataclass(frozen=True)
class InsertBlank(Operation):
    """COUNT blank pages, put before page BEFORE (n + 1: at the end), of the size of the page before
    them (or, at the start, of the first page)."""

    before: int = 1
    count: int = 1

    def items(self, n: int) -> list[Item]:
        if not 1 <= self.before <= n + 1:
            raise LabelError(tr("the pages must be from 1 to {count}", count=n + 1))
        if not 1 <= self.count <= 10000:
            raise LabelError(tr("from 1 to 10000 blank pages (not {count})", count=self.count))
        like = self.before - 1 if self.before > 1 else 1
        out: list[Item] = list(range(1, n + 1))
        at = self.before - 1
        return out[:at] + [Blank(like)] * self.count + out[at:]

    def describe(self) -> str:
        return ntr("Blank page inserted", "Blank pages inserted", self.count)


@dataclass(frozen=True)
class Rotate(Operation):
    """PAGES turned clockwise by ANGLE (90, 180 or 270; -90 is 270)."""

    pages: tuple[int, ...] = ()
    angle: int = 90

    def apply(self, pdf: Pdf) -> None:
        angle = self.angle % 360
        if angle not in ANGLES:
            raise LabelError(tr("pages turn by 90, 180 or 270 degrees (not {angle})", angle=self.angle))
        for p in _check_pages(self.pages, len(pdf.pages)):
            page = pdf.pages[p - 1]
            page.obj.Rotate = (int(page.obj.get("/Rotate", 0) or 0) + angle) % 360

    def moves_pages(self) -> bool:
        return False

    def describe(self) -> str:
        return tr("Pages rotated")


@dataclass(frozen=True)
class Replace(Operation):
    """The content of PAGES replaced by that of pages of the PDF SOURCE, from SOURCE_FIRST on (the
    pages keep their links, and the bookmarks that go to them)."""

    pages: tuple[int, ...] = ()
    source: str = ""
    source_first: int = 1
    password: str = ""

    def apply(self, pdf: Pdf) -> None:
        pages = _check_pages(self.pages, len(pdf.pages))
        source = _open_source(self.source, self.password)
        last = self.source_first + len(pages) - 1
        if self.source_first < 1 or last > len(source.pages):
            raise LabelError(tr("{path} has no page {page}", path=self.source, page=last))
        from .stamps import KEY, LEGACY  # (what was added to a page goes with its content)
        for k, p in enumerate(pages):
            pdf.pages.append(source.pages[self.source_first - 1 + k])  # (copied properly into PDF...)
            new = pdf.pages[-1].obj
            target = pdf.pages[p - 1].obj
            for key in ("/Contents", "/Resources", "/MediaBox", "/CropBox", "/BleedBox", "/TrimBox", "/ArtBox",
                        "/Rotate", "/UserUnit", "/Group"):
                if key in new:
                    target[key] = new[key]
                elif key in target and key != "/Resources":
                    del target[key]
            for key in (KEY, LEGACY):
                if key in target:
                    del target[key]
            del pdf.pages[-1]  # (... and its copy taken away again)

    def moves_pages(self) -> bool:
        return False

    def describe(self) -> str:
        return tr("Pages replaced from {path}", path=Path(self.source).name)


# =========================================================================== other PDFs


_SOURCES: dict[tuple[Path, str], Pdf] = {}  # (kept open: what is copied from them is read when saving)


def _open_source(path: str, password: str = "") -> Pdf:
    key = (Path(path).resolve(), password)
    if key not in _SOURCES:
        try:
            _SOURCES[key] = pikepdf.open(key[0], password=password)
        except pikepdf.PasswordError:
            raise LabelError(tr("{path} is protected by a password (give it with --password)", path=path)) from None
        except (OSError, pikepdf.PdfError) as e:
            raise LabelError(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None
    return _SOURCES[key]


def source_count(path: str, password: str = "") -> int:
    return len(_open_source(path, password).pages)


def source_labels(path: str, password: str = "") -> list[str]:
    pdf = _open_source(path, password)
    return page_labels(read_labels(pdf), len(pdf.pages))


# =========================================================================== rebuilding


def _copy_page(pdf: Pdf, obj: pikepdf.Object) -> pikepdf.Object:
    """A copy of the page OBJ of PDF, with copies of its annotations."""
    from .stamps import KEY
    copy = pdf.make_indirect(Dictionary({k: v for k, v in obj.items() if k not in ("/Parent", "/Annots", KEY)}))
    annots = {}
    if "/Annots" in obj:
        new = Array()
        for annot in obj.Annots:
            if isinstance(annot, Dictionary):
                twin = pdf.make_indirect(Dictionary({k: v for k, v in annot.items() if k != "/P"}))
                twin.P = copy
                annots[annot.objgen] = twin
                new.append(twin)
            else:
                new.append(annot)
        copy.Annots = new
    if KEY in obj:  # (the records of what was added, with the copies of the annotations it moved)
        records = Array()
        for record in obj[KEY]:
            twin = Dictionary({k: v for k, v in record.items()})
            if "/Annots" in record:
                twin.Annots = Array([annots.get(a.objgen, a) for a in record.Annots])
            records.append(twin)
        copy[KEY] = records
    return copy


def _inherited(obj: pikepdf.Object, key: str):
    """The value of KEY in the page OBJ, or in the nearest of its parents that has it (None if none)."""
    seen = set()
    while isinstance(obj, Dictionary) and obj.objgen not in seen:
        if key in obj:
            return obj[key]
        seen.add(obj.objgen)
        obj = obj.get("/Parent")
    return None


def _blank_page(pdf: Pdf, like: pikepdf.Object) -> pikepdf.Object:
    """A blank page with the boxes and the rotation of the page LIKE (so it is shown just as big)."""
    page = Dictionary(Type=Name.Page, Resources=Dictionary(),
                      Contents=pdf.make_indirect(pikepdf.Stream(pdf, b"")))
    for key in ("/MediaBox", "/CropBox", "/Rotate"):  # (those a page may inherit)
        value = _inherited(like, key)
        if value is not None:
            page[key] = value
    if "/MediaBox" not in page:
        page.MediaBox = Array([0, 0, 612, 792])
    for key in ("/BleedBox", "/TrimBox", "/ArtBox", "/UserUnit"):
        if key in like:
            page[key] = like[key]
    return pdf.make_indirect(page)


def rebuild(pdf: Pdf, items: list[Item]) -> None:
    """Make ITEMS the pages of PDF (see Item)."""
    old = [p.obj for p in pdf.pages]
    kept_positions = {i for i in items if isinstance(i, int)}
    used: set[int] = set()
    new: list[pikepdf.Object | Inserted] = []
    for item in items:
        if isinstance(item, Inserted):
            new.append(item)
        elif isinstance(item, Blank):
            new.append(_blank_page(pdf, old[item.like - 1]))
        elif item in used:
            new.append(_copy_page(pdf, old[item - 1]))
        else:
            used.add(item)
            new.append(old[item - 1])
    # Only the pages that change are taken out and put in (one by one, each a slow step in a long
    # book): those at the start and at the end that stay as they were are left alone.
    def same(i: int, j: int) -> bool:
        return not isinstance(new[j], Inserted) and new[j].objgen == old[i].objgen

    start = 0
    while start < min(len(old), len(new)) and same(start, start):
        start += 1
    end = 0
    while end < min(len(old), len(new)) - start and same(len(old) - 1 - end, len(new) - 1 - end):
        end += 1
    for _ in range(len(old) - start - end):
        del pdf.pages[start]
    for k, item in enumerate(new[start:len(new) - end]):
        if isinstance(item, Inserted):
            pdf.pages.insert(start + k, _open_source(item.source, item.password).pages[item.page - 1])
        else:
            pdf.pages.insert(start + k, Page(item))
    # the destinations that went to pages deleted: to the next page left (or the last before it)
    gone = {}
    survivors = [p for p in range(1, len(old) + 1) if p in kept_positions]
    for p in range(1, len(old) + 1):
        if p not in kept_positions and survivors:
            after = [s for s in survivors if s > p]
            gone[old[p - 1].objgen] = old[(after[0] if after else survivors[-1]) - 1]
    if gone:
        retarget(pdf, gone)


def _retarget_dest(dest, gone: dict) -> None:
    if isinstance(dest, Array) and len(dest) and isinstance(dest[0], Dictionary) and dest[0].objgen in gone:
        dest[0] = gone[dest[0].objgen]


def _retarget_action(action, gone: dict) -> None:
    if isinstance(action, Dictionary) and action.get("/S") == Name.GoTo:
        _retarget_dest(action.get("/D"), gone)


def retarget(pdf: Pdf, gone: dict) -> None:
    """Make the destinations (bookmarks, links, named destinations, the opening action) that go to
    the pages GONE ({objgen: page object}) go to the pages given instead."""
    root = pdf.Root
    _retarget_dest(root.get("/OpenAction"), gone)
    _retarget_action(root.get("/OpenAction"), gone)
    for value in (root.get("/Dests") or Dictionary()).values():
        _retarget_dest(value.get("/D") if isinstance(value, Dictionary) else value, gone)
    if "/Names" in root and "/Dests" in root.Names:
        for _, value in pikepdf.NameTree(root.Names.Dests).items():
            _retarget_dest(value.get("/D") if isinstance(value, Dictionary) else value, gone)
    for page in pdf.pages:
        for annot in page.obj.get("/Annots", Array()):
            if isinstance(annot, Dictionary):
                _retarget_dest(annot.get("/Dest"), gone)
                _retarget_action(annot.get("/A"), gone)
    stack = []
    outlines = root.get("/Outlines")
    if isinstance(outlines, Dictionary) and "/First" in outlines:
        stack.append(outlines.First)
    seen = set()
    while stack:
        item = stack.pop()
        if not isinstance(item, Dictionary) or item.objgen in seen:
            continue
        seen.add(item.objgen)
        _retarget_dest(item.get("/Dest"), gone)
        _retarget_action(item.get("/A"), gone)
        for key in ("/First", "/Next"):
            if key in item:
                stack.append(item[key])


# =========================================================================== the labels


def items_of(operations, n: int) -> tuple[list[list[Item]], int]:
    """The items of each of OPERATIONS in turn, from a document of N pages, and the pages at the end."""
    out = []
    for op in operations:
        items = op.items(n) if op.moves_pages() else list(range(1, n + 1))
        out.append(items)
        n = len(items)
    return out, n


def labels_after(op: Operation, old: list[str], n: int) -> list[str] | None:
    """The labels of the pages after OP, on a document of N pages whose pages have the labels OLD,
    if they FOLLOW the pages (None if they stay by POSITION, or if OP moves no page)."""
    if not op.moves_pages() or op.labels != FOLLOW:
        return None
    out = []
    sources: dict[str, list[str]] = {}
    for item in op.items(n):
        if isinstance(item, Blank):
            out.append("")
        elif isinstance(item, Inserted):
            if item.source not in sources:
                sources[item.source] = source_labels(item.source, item.password)
            out.append(sources[item.source][item.page - 1])
        else:
            out.append(old[item - 1])
    return out


def position_after(op: Operation, page: int | None, n: int) -> int | None:
    """Where PAGE (a position before OP, on N pages) is after it (None if gone or None)."""
    if page is None or not op.moves_pages():
        return page
    items = op.items(n)
    return next((i + 1 for i, item in enumerate(items) if item == page), None)


# =========================================================================== new files


def split_parts(n: int, every: int = 0, at: list[int] | None = None) -> list[tuple[int, int]]:
    """(first, last) of the parts of a document of N pages: EVERY so many pages, or starting at the
    pages AT (and at page 1)."""
    if every:
        if every < 1:
            raise LabelError(tr("a part needs one page at least"))
        return [(f, min(f + every - 1, n)) for f in range(1, n + 1, every)]
    starts = sorted({1, *(p for p in (at or []) if 1 <= p <= n)})
    return [(s, (starts[i + 1] - 1) if i + 1 < len(starts) else n) for i, s in enumerate(starts)]


def ranges_after(op: Operation, ranges: list, n: int) -> list:
    """The label ranges after OP, on a document of N pages labelled by RANGES: the labels follow the
    pages (op.labels FOLLOW: the ranges are found again for them) or stay by position (POSITION:
    the ranges are kept). A document with no labels keeps none."""
    from .labels import from_labels
    if not ranges:
        return []
    new = labels_after(op, page_labels(ranges, n), n)
    return ranges if new is None else from_labels(new)
