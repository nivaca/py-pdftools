"""The view of a PDF when it is opened: how a viewer lays out its pages, at
what size, and at which page.

A PDF keeps these for the whole document (not for each page), in its catalog;
viewers call them its initial view:

    /PageLayout   the page layout: SinglePage (Single), OneColumn (Single
                  Continuous), TwoPageLeft (Facing), TwoColumnLeft (Facing
                  Continuous), TwoPageRight (Cover: like Facing, but the first
                  page alone), TwoColumnRight (Cover Continuous)
    /OpenAction   a destination: the page it opens at, and the page view
                  (/XYZ with a factor of 1: Actual Size; /FitH: Fit to Width;
                  /Fit: Fit to Page; other destinations are read too)

Whatever is not given is left to the viewer, and what py-pdftools doesn't
know (/PageMode, an opening script) is kept. A View holds the PDF's own
names; LAYOUTS and PAGE_VIEWS give the names the command line uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal

from pikepdf import Array, Dictionary, Name, Pdf

from ..core.interface import N_, tr
from .labels import LabelError, page_number

# PDF name -> name on the command line, in the order of the menus
LAYOUTS = {
    "SinglePage": "single", "OneColumn": "single-continuous", "TwoPageLeft": "facing",
    "TwoColumnLeft": "facing-continuous", "TwoPageRight": "cover", "TwoColumnRight": "cover-continuous",
}
LAYOUT_ALIASES = {  # (the names of py-foliation 0.5)
    "continuous": "OneColumn", "double": "TwoPageLeft", "double-continuous": "TwoColumnLeft",
    "double-cover": "TwoPageRight", "double-continuous-cover": "TwoColumnRight",
}
LAYOUT_TITLES = {
    "SinglePage": N_("Single"), "OneColumn": N_("Single Continuous"), "TwoPageLeft": N_("Facing"),
    "TwoColumnLeft": N_("Facing Continuous"), "TwoPageRight": N_("Cover"),
    "TwoColumnRight": N_("Cover Continuous"),
}
LAYOUT_TIPS = {
    "SinglePage": N_("One page at a time"),
    "OneColumn": N_("All the pages in one column, scrolled continuously"),
    "TwoPageLeft": N_("Two pages at a time, side by side: odd pages on the left, even pages on the right"),
    "TwoColumnLeft": N_("All the pages in two columns: odd pages on the left, even pages on the right"),
    "TwoPageRight": N_("As Facing, but with the first page alone, as the cover of a book"),
    "TwoColumnRight": N_("As Facing Continuous, but with the first page alone, as the cover of a book"),
}
ACTUAL_SIZE = "100"
PAGE_VIEWS = {ACTUAL_SIZE: "actual-size", "FitH": "fit-width", "Fit": "fit-page"}
PAGE_VIEW_TITLES = {ACTUAL_SIZE: N_("Actual Size"), "FitH": N_("Fit to Width"), "Fit": N_("Fit to Page")}
PAGE_VIEW_TIPS = {
    ACTUAL_SIZE: N_("The pages at the size they would be printed"),
    "FitH": N_("The width of the page fits the window"),
    "Fit": N_("The whole page fits the window"),
}
DESTINATIONS = ("Fit", "FitH", "FitV", "FitB", "FitBH", "FitBV")  # (the fits a file may have)
DEFAULT = "default"  # (on the command line: leave it to the viewer)


@dataclass(frozen=True)
class View:
    """LAYOUT: a PDF name ('' for the viewer's choice). ZOOM, the page view: a PDF
    name (Fit, FitH; FitV ... if the file has them), a percentage ('100': Actual Size)
    or ''. PAGE: the page it opens at (1-based; None for the viewer's choice; a page
    view needs a page: 1 if none)."""

    layout: str = ""
    zoom: str = ""
    page: int | None = None

    def __post_init__(self):
        if self.zoom and self.page is None:
            object.__setattr__(self, "page", 1)

    def __bool__(self) -> bool:
        return self != View()

    def options(self) -> list[str]:
        """This view as options of 'py-pdftools view'."""
        out = []
        if self.layout:
            out += ["--layout", LAYOUTS[self.layout]]
        if self.zoom:
            out += ["--page-view", PAGE_VIEWS.get(self.zoom) or f"{self.zoom}%"]
        if self.page is not None:
            out += ["--open-at", str(self.page)]
        return out


def page_view_title(zoom: str) -> str:
    """How the window and 'show' name a page view ('' for none)."""
    if not zoom:
        return ""
    if zoom in PAGE_VIEW_TITLES:
        return tr(PAGE_VIEW_TITLES[zoom])
    return tr("Other ({zoom})", zoom=f"{zoom} %" if zoom.isdigit() else zoom)


def describe(v: View) -> list[tuple[str, str]]:
    """(what, how) for each part of V, as 'show' and 'view' print them."""
    default = tr("(the viewer's choice)")
    return [
        (tr("Page layout"), tr(LAYOUT_TITLES[v.layout]) if v.layout else default),
        (tr("Page view"), page_view_title(v.zoom) or default),
        (tr("Opens at"), tr("page {page}", page=v.page) if v.page is not None else default),
    ]


# =========================================================================== the command line


def _unknown(what: str, value: str, names) -> LabelError:
    return LabelError(tr("unknown {what} {value!r} (one of: {names})", what=tr(what), value=value,
                         names=", ".join(list(names) + [DEFAULT])))


def parse_layout(value: str) -> str:
    """The PDF name of a page layout, given by its name (single ...) or 'default' ('')."""
    v = value.strip().lower()
    if v == DEFAULT:
        return ""
    for code, name in LAYOUTS.items():
        if v in (name, code.lower()):
            return code
    if v in LAYOUT_ALIASES:
        return LAYOUT_ALIASES[v]
    raise _unknown(N_("page layout"), value, LAYOUTS.values())


def parse_zoom(value: str) -> str:
    """A page view: a name (actual-size, fit-width, fit-page), a percentage (150 or 150%)
    or 'default' ('')."""
    v = value.strip().lower()
    if v == DEFAULT:
        return ""
    m = re.fullmatch(r"(\d+)\s*%?", v)
    if m:
        if not 1 <= int(m[1]) <= 6400:
            raise LabelError(tr("the zoom must be from 1% to 6400% (not {value})", value=value))
        return str(int(m[1]))
    for code, name in PAGE_VIEWS.items():
        if v in (name, code.lower()):
            return code
    raise _unknown(N_("page view"), value, PAGE_VIEWS.values())


def parse_page(value: str, n: int) -> int | None:
    """The page to open at (1-based; LAST and LAST-N allowed), or None for 'default' (but
    with a page view, a document opens at page 1)."""
    return None if value.strip().lower() == DEFAULT else page_number(value, n)


def changed(v: View, n: int, layout: str | None = None, zoom: str | None = None,
            page: str | None = None) -> View:
    """V with the parts given on the command line (None: kept) changed, in a document of N pages."""
    changes = {}
    if layout is not None:
        changes["layout"] = parse_layout(layout)
    if zoom is not None:
        changes["zoom"] = parse_zoom(zoom)
    if page is not None:
        changes["page"] = parse_page(page, n)
    return without_lone_first_page(v, replace(v, **changes), page_given=page is not None)


def without_lone_first_page(old: View, new: View, page_given: bool) -> View:
    """NEW, but without its page if it was only there for a page view that is gone."""
    if not page_given and old.zoom and not new.zoom and new.page == 1:
        return replace(new, page=None)
    return new


# =========================================================================== reading and writing


def _name(value) -> str:
    return str(value)[1:] if isinstance(value, Name) else ""


def _destination(pdf: Pdf, action) -> tuple[int | None, str] | None:
    """(page, zoom) of an /OpenAction that goes to a page of this document; None if it is something else."""
    if isinstance(action, Dictionary) and _name(action.get("/S")) == "GoTo":
        action = action.get("/D")
    if not isinstance(action, Array) or len(action) < 2:
        return None
    target = action[0]
    if isinstance(target, Dictionary):
        pages = {p.obj.objgen: i for i, p in enumerate(pdf.pages)}
        index = pages.get(target.objgen)
    else:
        try:
            index = int(target)
        except (TypeError, ValueError):
            return None
    if index is None or not 0 <= index < len(pdf.pages):
        return None
    kind = _name(action[1])
    if kind in DESTINATIONS:
        return index + 1, kind
    if kind == "XYZ":
        factor = action[4] if len(action) > 4 else None
        try:
            percent = round(float(factor) * 100) if factor is not None else 0
        except (TypeError, ValueError):
            percent = 0
        return index + 1, str(percent) if percent > 0 else ""
    return None


def read_view(pdf: Pdf) -> View:
    """The view of the document when it is opened (the parts it doesn't give, or that
    py-pdftools doesn't know, are left empty)."""
    layout = _name(pdf.Root.get("/PageLayout"))
    dest = _destination(pdf, pdf.Root.get("/OpenAction"))
    page, zoom = dest if dest else (None, "")
    return View(layout if layout in LAYOUTS else "", zoom, page)


def write_view(pdf: Pdf, v: View) -> None:
    """Give the document the view V, changing only the parts it doesn't have yet
    (so that what py-pdftools doesn't know is kept, unless it is replaced)."""
    old = read_view(pdf)
    root = pdf.Root
    if v.layout != old.layout:
        if v.layout:
            root.PageLayout = Name("/" + v.layout)
        elif "/PageLayout" in root:
            del root["/PageLayout"]
    if (v.page, v.zoom) != (old.page, old.zoom):
        if v.page is None:
            if "/OpenAction" in root:
                del root["/OpenAction"]
            return
        page = pdf.pages[min(v.page, len(pdf.pages)) - 1].obj
        if not v.zoom:
            dest = [page, Name.XYZ, None, None, None]  # (the viewer's zoom)
        elif v.zoom.isdigit():
            dest = [page, Name.XYZ, None, None, Decimal(v.zoom) / 100]
        elif v.zoom in ("Fit", "FitB"):
            dest = [page, Name("/" + v.zoom)]
        else:
            dest = [page, Name("/" + v.zoom), None]
        root.OpenAction = Array(dest)
