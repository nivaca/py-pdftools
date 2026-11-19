"""Watermarks: a text ("Draft", "Copy", with variables, as in headers and footers) or a page of
another PDF, drawn on the pages in front of their content or behind it, turned, scaled, with
some transparency, where it is asked to go.

Each watermark added is a layer of the pages it goes on (see stamps.py), so it can be taken
away again, replaced or updated. Shown only when printing, or only on the screen, it is put in
an optional content group whose automatic states say so (viewers that do not follow them show
it always).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

import pikepdf
from pikepdf import Dictionary, Name, Pdf

from . import profiles, stamps
from .fontmetrics import FONTS
from .headfoot import LINE, known_values
from ..core.interface import N_, tr
from .labels import LabelError
from .stamps import POINTS, WATERMARK, Document, chosen_pages

HALIGNS = {"left": N_("Left"), "center": N_("Center"), "right": N_("Right")}
VALIGNS = {"top": N_("Top"), "center": N_("Center"), "bottom": N_("Bottom")}


@dataclass(frozen=True)
class Watermark:
    """What to draw (a text, or page SOURCE_PAGE of the PDF SOURCE), how, where and on which pages."""

    text: str = ""
    source: str = ""  # a PDF file, whose page SOURCE_PAGE is the watermark (instead of a text)
    source_page: int = 1
    # the text
    font: str = "helvetica"
    size: float = 60.0
    color: str = "#808080"
    bold: bool = False
    italic: bool = False
    date_format: str = "medium"
    # appearance
    scale: float = 0.0  # the percent of the page it fills (0: its own size)
    rotation: float = 45.0  # degrees, counterclockwise
    opacity: float = 0.5  # from 0 (invisible) to 1
    behind: bool = False  # behind the content of the page (else in front of it)
    on_print: bool = True  # shown when printing
    on_screen: bool = True  # shown on the screen
    # position: from the left, center or right, and the top, center or bottom, moved by the offsets
    halign: str = "center"
    valign: str = "center"
    units: str = "cm"
    hoffset: float = 0.0
    voffset: float = 0.0
    # pages
    pages: str = ""
    parity: str = "all"
    # Bates numbering ($bates)
    bates_prefix: str = ""
    bates_start: int = 1
    bates_digits: int = 6
    bates_suffix: str = ""
    # as a profile
    name: str = ""
    show_on_menu: bool = False

    KIND = WATERMARK

    def base_font(self) -> str:
        return stamps.base_font(self.font, self.bold, self.italic)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Watermark:
        return check(cls(**known_values(cls, data)))


def check(wm: Watermark) -> Watermark:
    """WM if its settings are right (raises LabelError if not), with its color written as #rrggbb."""
    stamps.check_common(wm)
    if bool(wm.text.strip()) == bool(wm.source.strip()):
        raise LabelError(tr("a watermark is a text or a page of a PDF (one of the two)"))
    if wm.source and not Path(wm.source).is_file():
        raise LabelError(tr("{path} not found", path=wm.source))
    if wm.source_page < 1:
        raise LabelError(tr("the page of the watermark's PDF must be 1 or more"))
    if not 0 <= wm.opacity <= 1:
        raise LabelError(tr("the opacity must be from 0 to 1 (not {value})", value=wm.opacity))
    if not 0 <= wm.scale <= 1000:
        raise LabelError(tr("the scale must be from 0 to 1000 percent (not {value})", value=wm.scale))
    if wm.halign not in HALIGNS or wm.valign not in VALIGNS:
        raise LabelError(tr("the watermark goes left, center or right, and top, center or bottom"))
    if not (wm.on_print or wm.on_screen):
        raise LabelError(tr("a watermark shown neither when printing nor on the screen is never shown"))
    return replace(wm, color=stamps.hex_color(wm.color, N_("color")))


def uses_bates(wm: Watermark) -> bool:
    return stamps.uses_bates(wm.text)


# =========================================================================== the source page


_SOURCES: dict[Path, Pdf] = {}  # (kept open: what is copied from them is read when the copy is saved)


def _source(path: str) -> Pdf:
    key = Path(path).resolve()
    if key not in _SOURCES:
        try:
            _SOURCES[key] = pikepdf.open(key)
        except (OSError, pikepdf.PdfError) as e:
            raise LabelError(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None
    return _SOURCES[key]


def _form(pdf: Pdf, wm: Watermark) -> tuple[pikepdf.Object, float, float, float, float]:
    """(form XObject, x0, y0, width, height) of the page of the watermark's PDF, copied into PDF."""
    source = _source(wm.source)
    if wm.source_page > len(source.pages):
        raise LabelError(tr("{path} has no page {page}", path=wm.source, page=wm.source_page))
    form = pdf.copy_foreign(source.pages[wm.source_page - 1].as_form_xobject())
    x0, y0, x1, y1 = (float(v) for v in form.BBox)
    return form, min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)


# =========================================================================== drawing


def text_box(wm: Watermark, text: str, size: float) -> tuple[float, float]:
    """(width, height) of TEXT at SIZE, its lines one under the other."""
    asc, desc, _ = FONTS[wm.base_font()]
    lines = text.split("\n")
    width = max(stamps.text_width(line, wm.base_font(), size) for line in lines)
    return width, (asc - desc) / 1000 * size + (len(lines) - 1) * LINE * size


def placement(wm: Watermark, width: float, height: float, page_w: float, page_h: float) -> stamps.Matrix:
    """The matrix that puts a watermark of WIDTH x HEIGHT (drawn from its lower left corner, at its
    own size) on a page of PAGE_W x PAGE_H, as it is shown: scaled, turned and placed."""
    turn = math.radians(wm.rotation)
    cos, sin = math.cos(turn), math.sin(turn)
    turned_w, turned_h = abs(width * cos) + abs(height * sin), abs(width * sin) + abs(height * cos)
    scale = wm.scale / 100 * min(page_w / turned_w, page_h / turned_h) if wm.scale and turned_w and turned_h else 1
    box_w, box_h = turned_w * scale, turned_h * scale
    unit = POINTS[wm.units]
    dx, dy = wm.hoffset * unit, wm.voffset * unit
    x = {"left": dx, "center": (page_w - box_w) / 2 + dx, "right": page_w - box_w - dx}[wm.halign]
    y = {"bottom": dy, "center": (page_h - box_h) / 2 + dy, "top": page_h - box_h - dy}[wm.valign]
    m = (1, 0, 0, 1, -width / 2, -height / 2)  # (the center of the watermark at the origin)
    m = stamps.multiply(m, (scale, 0, 0, scale, 0, 0))
    m = stamps.multiply(m, (cos, sin, -sin, cos, 0, 0))
    return stamps.multiply(m, (1, 0, 0, 1, x + box_w / 2, y + box_h / 2))


def _draw_text(wm: Watermark, text: str, font_name: str, width: float, height: float) -> bytes:
    asc = FONTS[wm.base_font()][0]
    baseline = height - asc / 1000 * wm.size
    out = []
    for line in text.split("\n"):
        if line:
            x = (width - stamps.text_width(line, wm.base_font(), wm.size)) / 2
            out.append(f"BT /{font_name} {stamps.number(wm.size)} Tf {stamps.rgb(wm.color, 'rg')} "
                       f"{stamps.number(x)} {stamps.number(baseline)} Td ".encode() + stamps.pdf_string(line)
                       + b" Tj ET")
        baseline -= LINE * wm.size
    return b"\n".join(out)


# =========================================================================== applying and removing


def page_texts(wm: Watermark, doc: Document, now: datetime, bates_offset: int = 0) -> list[tuple[int, str]]:
    """(page, text) for each page WM goes on, with the variables of its text replaced ('' for a
    page of a PDF); raises LabelError if the standard fonts cannot write it."""
    out = []
    for index, number in enumerate(chosen_pages(wm, doc.count)):
        text = ""
        if wm.text:
            text = stamps.expand(wm.text, number, doc, now, stamps.bates_number(wm, bates_offset + index),
                                 wm.date_format)
            stamps.check_writable(text, number)
        out.append((number, text))
    return out


@dataclass
class _Shared:
    """What every page of one addition shares (made once)."""

    addition: int
    font: pikepdf.Object | None = None
    form: tuple | None = None
    state: pikepdf.Object | None = None
    group: pikepdf.Object | None = None


def _shared(pdf: Pdf, wm: Watermark, addition: int | None = None) -> _Shared:
    shared = _Shared(stamps.next_id(pdf) if addition is None else addition)
    if wm.source:
        shared.form = _form(pdf, wm)
    else:
        shared.font = stamps.font_object(pdf, wm.base_font())
    shared.state = pdf.make_indirect(Dictionary(Type=Name.ExtGState, ca=wm.opacity, CA=wm.opacity))
    if not (wm.on_print and wm.on_screen):
        shared.group = stamps.optional_group(pdf, tr("Watermark {number}", number=shared.addition), wm.on_print,
                                             wm.on_screen)
    return shared


def stamp_page(pdf: Pdf, page: pikepdf.Page, wm: Watermark, text: str, shared: _Shared | None = None,
               keep: bool = False) -> None:
    """Draw WM (with TEXT, its variables replaced) on PAGE of PDF, replacing the watermarks
    py-pdftools (or py-foliation) added to it before, unless KEEP."""
    if not keep:
        stamps.remove_layers(page, lambda r: stamps.kind_of(r) == WATERMARK)
    shared = shared or _shared(pdf, wm)
    page_w, page_h, frame = stamps.shown_frame(page)
    resources: dict[str, list[str]] = {}
    state = str(page.add_resource(shared.state, Name.ExtGState, prefix="PyFolGS"))
    resources["ExtGState"] = [state]
    if shared.form is not None:
        form, x0, y0, width, height = shared.form
        name = str(page.add_resource(form, Name.XObject, prefix="PyFolWM"))
        resources["XObject"] = [name]
        body = f"q 1 0 0 1 {stamps.number(-x0)} {stamps.number(-y0)} cm {name} Do Q".encode()
    else:
        width, height = text_box(wm, text, wm.size)
        name = str(page.add_resource(shared.font, Name.Font, prefix="PyFol"))
        resources["Font"] = [name]
        body = _draw_text(wm, text, name[1:], width, height)
    m = placement(wm, width, height, page_w, page_h)
    content = (f"q {stamps.matrix_text(frame)} cm {state} gs {stamps.matrix_text(m)} cm\n".encode() + body
               + b"\nQ")
    content = b"/Artifact <</Type /Pagination /Subtype /Watermark>> BDC\n" + content + b"\nEMC"
    if shared.group is not None:
        group = str(page.add_resource(shared.group, Name.Properties, prefix="PyFolOC"))
        resources["Properties"] = [group]
        content = f"/OC {group} BDC\n".encode() + content + b"\nEMC"
    if wm.behind:
        stamps.add_layer(pdf, page, WATERMARK, shared.addition, wm.as_dict(), behind=b"q\n" + content + b"\nQ",
                         resources=resources, bates=uses_bates(wm), group=shared.group)
    else:
        stamps.add_layer(pdf, page, WATERMARK, shared.addition, wm.as_dict(), before=b"q",
                         after=b"Q\n" + content, resources=resources, bates=uses_bates(wm), group=shared.group)


def apply(pdf: Pdf, wm: Watermark, doc: Document, now: datetime | None = None, *, keep: bool = False,
          bates_offset: int = 0) -> int:
    """Draw WM on its pages of PDF, as a new addition (replacing the watermarks py-pdftools (or py-foliation) added
    to those pages before, unless KEEP). The number of pages it went on."""
    wm = check(wm)
    pages = page_texts(wm, doc, now or datetime.now(), bates_offset)
    shared = _shared(pdf, wm)
    for number, text in pages:
        stamp_page(pdf, pdf.pages[number - 1], wm, text, shared, keep)
    return len(pages)


def remove(pdf: Pdf, pages: str = "") -> int:
    """Take away the watermarks py-pdftools (or py-foliation) added to PAGES ('' for all)."""
    return stamps.remove(pdf, pages, WATERMARK)


def pages_with(pdf: Pdf) -> list[int]:
    return stamps.pages_with(pdf, WATERMARK)


def last(pdf: Pdf) -> tuple[int, Watermark] | None:
    """(addition, settings) of the watermark added last (None if none)."""
    found = stamps.last_addition(pdf, WATERMARK)
    if found is None or not found.settings:
        return None
    try:
        return found.id, Watermark.from_dict(found.settings)
    except LabelError:
        return None


# =========================================================================== profiles


def profiles_path() -> Path:
    return profiles.path("watermark.json")


def read_profiles() -> dict[str, Watermark]:
    return profiles.read("watermark.json", Watermark.from_dict)


def save_profile(wm: Watermark) -> Path:
    return profiles.save("watermark.json", check(wm), Watermark.from_dict)


def delete_profile(name: str) -> bool:
    return profiles.delete("watermark.json", name, Watermark.from_dict)
