"""Headers and footers: text drawn on the pages, above and below their content.

Unlike the page labels and the view, these change the pages themselves. A
header and a footer have three places each, left, center and right, whose
text may hold variables ($page, $pagelabel, $totalpages, $date ...: see
stamps.VARIABLES), and are drawn in one of the PDF standard fonts (Helvetica,
Times or Courier), which every viewer has. Those fonts write the characters
of WinAnsiEncoding (cp1252): Latin script, with its accents and signs, but
not Greek or Cyrillic.

Each header and footer added is a layer of the pages it goes on (see
stamps.py): drawn after the original content, which is wrapped in q ... Q so
that nothing it leaves set changes them, and, with "shrink", scaling that
content down to leave room for them. A page may have several; a new one
replaces those of the pages it goes on unless it is added to them (KEEP), and
"update" replaces the last one added, on every page, by new settings.

Margins are the distances from the edges of the page (as it is shown, after
/Rotate) to the outer edge of the header and footer: the top margin to the
top of the header, the bottom margin to the bottom of the footer, and the
left and right margins to the text at the sides.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from pathlib import Path

import pikepdf
from pikepdf import Name, Pdf

from . import profiles, stamps
from .fontmetrics import FONTS
from ..core.interface import N_, tr
from .labels import LabelError
from .stamps import (  # noqa: F401  (part of this module's API)
    DATE_FORMATS, FAMILIES, FAMILY_TITLES, HEADER_FOOTER, PARITIES, POINTS, UNIT_TITLES, VARIABLES, Document,
    chosen_pages, compact_pages, document_of, text_width, unwritable,
)

SIDES = {"top": N_("top"), "bottom": N_("bottom"), "left": N_("left"), "right": N_("right")}  # (the margins)
SLOTS = ("header_left", "header_center", "header_right", "footer_left", "footer_center", "footer_right")
SLOT_TITLES = {
    "header_left": N_("Header left"), "header_center": N_("Header center"), "header_right": N_("Header right"),
    "footer_left": N_("Footer left"), "footer_center": N_("Footer center"), "footer_right": N_("Footer right"),
}
# the page numbers the window inserts: what it shows -> the text it inserts
PAGE_FORMATS = {
    N_("1"): "$page",
    N_("1 of n"): N_("$page of $totalpages"),
    N_("Page 1"): N_("Page $page"),
    N_("Page 1 of n"): N_("Page $page of $totalpages"),
    N_("Label (iv, 12v ...)"): "$pagelabel",
    N_("Page label of n"): N_("Page $pagelabel of $totalpages"),
}
LINE = 1.2  # the distance between lines, in font sizes
PAD = 0.3  # the room around the text inside a border or a background, in font sizes


@dataclass(frozen=True)
class HeaderFooter:
    """What to draw, where, how and on which pages (and, as a profile, under what name)."""

    header_left: str = ""
    header_center: str = ""
    header_right: str = ""
    footer_left: str = ""
    footer_center: str = ""
    footer_right: str = ""
    # margins, in UNITS (in, cm or pt)
    units: str = "cm"
    top: float = 1.0
    bottom: float = 1.0
    left: float = 2.0
    right: float = 2.0
    shrink: bool = False  # scale the content of the pages down, to leave room for the header and footer
    # appearance
    font: str = "helvetica"  # helvetica, times or courier
    size: float = 10.0
    color: str = "#000000"
    bold: bool = False
    italic: bool = False
    border: bool = False
    border_color: str = "#000000"
    border_width: float = 0.5  # points
    background: str = ""  # a color, or "" for none
    date_format: str = "medium"  # how $date writes the date (see stamps.DATE_FORMATS)
    # pages: a list of pages ("" for all; "5-200", "1,3,9-"), and of those, all, the even or the odd ones
    pages: str = ""
    parity: str = "all"
    # Bates numbering ($bates): PREFIX, the number from START in DIGITS digits (at least), SUFFIX
    bates_prefix: str = ""
    bates_start: int = 1
    bates_digits: int = 6
    bates_suffix: str = ""
    # as a profile
    name: str = ""
    show_on_menu: bool = False

    KIND = HEADER_FOOTER

    def texts(self) -> dict[str, str]:
        return {slot: getattr(self, slot) for slot in SLOTS}

    def has_text(self) -> bool:
        return any(t.strip() for t in self.texts().values())

    def base_font(self) -> str:
        return stamps.base_font(self.font, self.bold, self.italic)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> HeaderFooter:
        """A HeaderFooter from a dictionary (of a profile, or of a page), leaving out what it doesn't know."""
        return check(cls(**known_values(cls, data)))


def known_values(cls, data: dict) -> dict:
    """The values of DATA that are fields of the dataclass CLS, of the type of their defaults."""
    values = {}
    defaults = cls()
    for f in fields(cls):
        if f.name in data:
            try:
                values[f.name] = type(getattr(defaults, f.name))(data[f.name])
            except (TypeError, ValueError):
                continue
    return values


def check(hf: HeaderFooter) -> HeaderFooter:
    """HF if its settings are right (raises LabelError if not), with its colors written as #rrggbb."""
    stamps.check_common(hf)
    for side, what in SIDES.items():
        if getattr(hf, side) < 0:
            raise LabelError(tr("the {what} margin cannot be negative", what=tr(what)))
    if not 0 <= hf.border_width <= 20:
        raise LabelError(tr("the width of the border must be from 0 to 20 points"))
    colors = {"color": stamps.hex_color(hf.color, N_("color")),
              "border_color": stamps.hex_color(hf.border_color, N_("border color"))}
    if hf.background:
        colors["background"] = stamps.hex_color(hf.background, N_("background color"))
    return replace(hf, **colors)


def expand(text: str, page: int, doc: Document, now: datetime, bates: str = "", date_format: str = "medium") -> str:
    """TEXT with its variables replaced, on PAGE (1-based) of DOC (see stamps.expand)."""
    return stamps.expand(text, page, doc, now, bates, date_format)


def bates_number(hf: HeaderFooter, index: int) -> str:
    return stamps.bates_number(hf, index)


def uses_bates(hf: HeaderFooter) -> bool:
    return stamps.uses_bates(*hf.texts().values())


# =========================================================================== drawing


@dataclass(frozen=True)
class Block:
    """The lines of one place (header left ...) and where they go, on a page as it is shown."""

    slot: str
    lines: tuple[str, ...]
    x: float  # the left of the box (with its padding)
    y: float  # the bottom of the box
    width: float
    height: float


def _pad(hf: HeaderFooter) -> float:
    return PAD * hf.size if (hf.border or hf.background) else 0.0


def _box_height(hf: HeaderFooter, lines: int) -> float:
    asc, desc, _ = FONTS[hf.base_font()]
    return (asc - desc) / 1000 * hf.size + (lines - 1) * LINE * hf.size + 2 * _pad(hf)


def layout(hf: HeaderFooter, texts: dict[str, str], width: float, height: float) -> list[Block]:
    """Where the text of each place goes on a page of WIDTH x HEIGHT points, as it is shown."""
    font = hf.base_font()
    pad = _pad(hf)
    unit = POINTS[hf.units]
    top, bottom, left, right = hf.top * unit, hf.bottom * unit, hf.left * unit, hf.right * unit
    blocks = []
    for slot in SLOTS:
        text = texts.get(slot, "")
        if not text.strip():
            continue
        lines = tuple(text.split("\n"))
        box_w = max(text_width(line, font, hf.size) for line in lines) + 2 * pad
        box_h = _box_height(hf, len(lines))
        side = slot.split("_")[1]
        x = left if side == "left" else width - right - box_w if side == "right" else (width - box_w) / 2
        y = height - top - box_h if slot.startswith("header") else bottom
        blocks.append(Block(slot, lines, x, y, box_w, box_h))
    return blocks


def draw(hf: HeaderFooter, blocks: list[Block], font_name: str) -> bytes:
    """The content that draws BLOCKS, in the coordinates of the page as it is shown, with the
    font as the resource FONT_NAME; the header and the footer are marked as pagination artifacts."""
    font = hf.base_font()
    asc = FONTS[font][0]
    pad = _pad(hf)
    out: list[bytes] = []
    for kind, prefix in (("Header", "header_"), ("Footer", "footer_")):
        group = [b for b in blocks if b.slot.startswith(prefix)]
        if not group:
            continue
        out.append(f"/Artifact <</Type /Pagination /Subtype /{kind}>> BDC".encode())
        for b in group:
            rect = f"{stamps.number(b.x)} {stamps.number(b.y)} {stamps.number(b.width)} {stamps.number(b.height)} re"
            if hf.background:
                out.append(f"q {stamps.rgb(hf.background, 'rg')} {rect} f Q".encode())
            if hf.border and hf.border_width > 0:
                out.append(f"q {stamps.rgb(hf.border_color, 'RG')} {stamps.number(hf.border_width)} w {rect} S Q"
                           .encode())
            side = b.slot.split("_")[1]
            inner = b.width - 2 * pad
            baseline = b.y + b.height - pad - asc / 1000 * hf.size
            for line in b.lines:
                if line:
                    free = inner - text_width(line, font, hf.size)
                    x = b.x + pad + (0 if side == "left" else free if side == "right" else free / 2)
                    out.append(f"BT /{font_name} {stamps.number(hf.size)} Tf {stamps.rgb(hf.color, 'rg')} "
                               f"{stamps.number(x)} {stamps.number(baseline)} Td ".encode()
                               + stamps.pdf_string(line) + b" Tj ET")
                baseline -= LINE * hf.size
        out.append(b"EMC")
    return b"\n".join(out)


def _lines_per_band(hf: HeaderFooter) -> tuple[int, int]:
    """(header, footer): the most lines a place of each has (0 if none has text)."""
    out = []
    for prefix in ("header_", "footer_"):
        out.append(max((len(t.split("\n")) for s, t in hf.texts().items() if s.startswith(prefix) and t.strip()),
                       default=0))
    return out[0], out[1]


def shrink_matrix(hf: HeaderFooter, width: float, height: float) -> stamps.Matrix:
    """The matrix that scales the content of a page of WIDTH x HEIGHT (as it is shown) down so
    that it fits between the header and the footer, centered across the page."""
    unit = POINTS[hf.units]
    header, footer = (_box_height(hf, n) if n else 0.0 for n in _lines_per_band(hf))
    gap = 0.5 * hf.size
    reserved_top = hf.top * unit + header + gap if header else 0.0
    reserved_bottom = hf.bottom * unit + footer + gap if footer else 0.0
    scale = (height - reserved_top - reserved_bottom) / height
    if scale < 0.2:
        raise LabelError(tr("the header and footer leave too little room to shrink the pages into"))
    return (scale, 0, 0, scale, (width - scale * width) / 2, reserved_bottom)


# =========================================================================== applying and removing


def page_texts(hf: HeaderFooter, doc: Document, now: datetime, bates_offset: int = 0
               ) -> list[tuple[int, dict[str, str]]]:
    """(page, {place: text}) for each page HF goes on, with the variables replaced (the Bates
    numbers counted from BATES_OFFSET pages on); raises LabelError if the standard fonts cannot
    write a text, or if there is no text at all."""
    if not hf.has_text():
        raise LabelError(tr("no text for the header or the footer"))
    out = []
    for index, number in enumerate(chosen_pages(hf, doc.count)):
        texts = {slot: expand(text, number, doc, now, bates_number(hf, bates_offset + index), hf.date_format)
                 for slot, text in hf.texts().items()}
        stamps.check_writable("".join(texts.values()), number)
        out.append((number, texts))
    return out


def stamp_page(pdf: Pdf, page: pikepdf.Page, hf: HeaderFooter, texts: dict[str, str],
               font: pikepdf.Object | None = None, addition: int | None = None, keep: bool = False) -> None:
    """Draw TEXTS ({place: text}, the variables already replaced) on PAGE of PDF as HF says, as
    part of ADDITION (a new one if None), replacing the headers and footers py-pdftools (or py-foliation) added
    to it before, unless KEEP."""
    if not keep:
        stamps.remove_layers(page, lambda r: stamps.kind_of(r) == HEADER_FOOTER)
    font = font if font is not None else stamps.font_object(pdf, hf.base_font())
    addition = stamps.next_id(pdf) if addition is None else addition
    width, height, frame = stamps.shown_frame(page)
    before, shrink = b"q", None
    if hf.shrink and hf.has_text():
        shrink = stamps.multiply(stamps.multiply(stamps.invert(frame), shrink_matrix(hf, width, height)), frame)
        before += f" {stamps.matrix_text(shrink)} cm".encode()
    font_name = page.add_resource(font, Name.Font, prefix="PyFol")
    after = (f"Q\nq {stamps.matrix_text(frame)} cm\n".encode()
             + draw(hf, layout(hf, texts, width, height), str(font_name)[1:]) + b"\nQ")
    stamps.add_layer(pdf, page, HEADER_FOOTER, addition, hf.as_dict(), before=before, after=after, shrink=shrink,
                     resources={"Font": [str(font_name)]}, bates=uses_bates(hf))


def apply(pdf: Pdf, hf: HeaderFooter, doc: Document, now: datetime | None = None, *, keep: bool = False,
          bates_offset: int = 0) -> int:
    """Draw HF on its pages of PDF, as a new addition (replacing the headers and footers
    py-pdftools (or py-foliation) added to those pages before, unless KEEP); DOC gives the variables what they
    need, and the Bates numbers go on from BATES_OFFSET. The number of pages it went on."""
    hf = check(hf)
    pages = page_texts(hf, doc, now or datetime.now(), bates_offset)
    font = stamps.font_object(pdf, hf.base_font())
    addition = stamps.next_id(pdf)
    for number, texts in pages:
        stamp_page(pdf, pdf.pages[number - 1], hf, texts, font, addition, keep)
    return len(pages)


def remove(pdf: Pdf, pages: str = "", *, bates_only: bool = False) -> int:
    """Take away the headers and footers py-pdftools (or py-foliation) added to PAGES ('' for all; only those with
    Bates numbers, if BATES_ONLY); the number of pages it took them from."""
    return stamps.remove(pdf, pages, HEADER_FOOTER, bates_only=bates_only)


def pages_with(pdf: Pdf, *, bates_only: bool = False) -> list[int]:
    """The pages (1-based) with a header or footer added by py-pdftools (or py-foliation)."""
    return stamps.pages_with(pdf, HEADER_FOOTER, bates_only=bates_only)


def last(pdf: Pdf) -> tuple[int, HeaderFooter] | None:
    """(addition, settings) of the header and footer added last (None if none, or if it was added
    by a version of py-foliation that did not keep its settings)."""
    found = stamps.last_addition(pdf, HEADER_FOOTER)
    if found is None or not found.settings:
        return None
    try:
        return found.id, HeaderFooter.from_dict(found.settings)
    except LabelError:
        return None


# =========================================================================== profiles


def profiles_path() -> Path:
    return profiles.path("header-footer.json")


def read_profiles() -> dict[str, HeaderFooter]:
    """The saved profiles, by name ({} if none or if the file cannot be read)."""
    return profiles.read("header-footer.json", HeaderFooter.from_dict)


def save_profile(hf: HeaderFooter) -> Path:
    return profiles.save("header-footer.json", check(hf), HeaderFooter.from_dict)


def delete_profile(name: str) -> bool:
    return profiles.delete("header-footer.json", name, HeaderFooter.from_dict)
