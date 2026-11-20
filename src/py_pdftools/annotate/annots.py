"""Annotations: what py-pdftools adds to the pages of a PDF, read from it and
written to it.

An annotation is kept as an Annotation, measured in points from the top left
corner of the page as it is shown (that is, with the page's rotation
applied), like everything the window shows. The kinds are:

* text markup, over lines of text: ``highlight``, ``underline``,
  ``strikeout``, ``squiggly`` (one rectangle in ``quads`` for each line),
  and ``caret``, a mark where text is to be inserted;
* ``note``: a sticky note, an icon whose text opens in the viewer;
* ``freetext``: a text written on the page, in a box; ``callout``: the same,
  with a line pointing at a place (``paths``: that place);
* shapes: ``area`` (a highlight over a region, not over text), ``rect``,
  ``ellipse``, ``polygon``, ``cloud`` (a polygon with a cloudy border),
  ``line``, ``arrow``, ``polyline``, and ``ink`` (drawn by hand; its strokes
  in ``paths``);
* ``stamp``: a rubber stamp, standard (``stamp``: its name) or of an image
  (``image``, which also keeps the look of every stamp, for showing it);
* ``marker``: a freehand highlight (an ink annotation, wide and see-through).

An annotation may have replies, and a review status (Accepted, Rejected...):
in the PDF, both are notes that answer it (/IRT), the status with /State.
Its tags and categories are its own (as in py-annotate) (/PyAnnotateTags and
/PyAnnotateCategories), which other programs leave alone.

The annotations of these kinds that a document already has are read into
the list too, and can be changed or deleted. Saving changes only those that
changed, and changes them where they are (so that what py-pdftools doesn't
know of them stays: their identifier, keys of other programs, the replies
that point at them); only if that can't be done is one taken out and
written again. An annotation left as it was is not touched, nor are those of
other kinds (links, file attachments, sounds, form fields...). Saving into
the document itself adds the changes at its end (an incremental save), so
that the signatures it has stay valid for what they signed.
"""

from __future__ import annotations

import dataclasses
import datetime
import html
import json
import os
import re
import tempfile
from pathlib import Path

import pymupdf

from ..core.interface import N_, tr

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1
Point = tuple[float, float]

# the annotations of other kinds (links, attachments, sounds...): listed, but neither changed nor written
# (Annotation.other gives their kind, as the PDF names it)
OTHER = "other"
OTHER_NAMES = {"Link": N_("Link"), "FileAttachment": N_("Attached file"), "Sound": N_("Sound"), "Movie": N_("Movie"),
               "Screen": N_("Screen"), "RichMedia": N_("Media"), "3D": N_("3D model"), "Redact": N_("Redaction mark"),
               "Watermark": N_("Watermark"), "PrinterMark": N_("Printer's mark"), "TrapNet": N_("Trap network"),
               "Projection": N_("Projection")}
KINDS = ("highlight", "underline", "strikeout", "squiggly", "caret", "note", "freetext", "callout", "area", "rect",
         "ellipse", "polygon", "cloud", "line", "arrow", "polyline", "ink", "marker", "stamp", "attachment", "redact")
# (those of the mode Annotate, with their styles and tools: a redaction box is of the mode Redact, and its look is
# that of the settings of redaction, see redact/settings.py)
ANNOTATING = KINDS[:-1]
NAMES = {"highlight": N_("Highlight"), "underline": N_("Underline"), "strikeout": N_("Strikeout"),
         "squiggly": N_("Squiggly underline"), "caret": N_("Insert text"), "note": N_("Note"),
         "freetext": N_("Text box"), "attachment": N_("Attached file"), "callout": N_("Callout"), "area": N_("Area highlight"),
         "rect": N_("Rectangle"), "ellipse": N_("Ellipse"), "polygon": N_("Polygon"), "cloud": N_("Cloud"),
         "line": N_("Line"), "arrow": N_("Arrow"), "polyline": N_("Polyline"), "ink": N_("Freehand"),
         "marker": N_("Freehand highlight"), "stamp": N_("Stamp"), "redact": N_("Redaction box")}
MARKUP = ("highlight", "underline", "strikeout", "squiggly")  # (over text: neither moved nor resized)
FIXED = ("note", "caret")  # (of a size of their own: moved, not resized)
TEXTUAL = ("freetext", "callout")  # (with a font)
FILLED = ("freetext", "callout", "area", "rect", "ellipse", "polygon", "cloud")  # (those with a fill)
STROKED = ("freetext", "callout", "rect", "ellipse", "polygon", "cloud", "line", "arrow", "polyline", "ink",
           "marker")
DRAWN = ("ink", "marker")  # (drawn by hand: strokes)
DASHABLE = ("freetext", "callout", "rect", "ellipse", "polygon", "line", "arrow", "polyline")
ENDED = ("line", "arrow", "polyline", "callout")  # (with ends: arrowheads...)
VERTICES = ("polygon", "cloud", "polyline", "line", "arrow")  # (whose points can be dragged one by one)
RESIZABLE = ("freetext", "callout", "area", "rect", "ellipse", "polygon", "cloud", "line", "arrow", "polyline",
             "ink", "marker", "stamp", "redact")
NOTE_SIZE = 16.0  # points: the side of a note's icon (MuPDF makes them all of this size)
CARET_SIZE = (20.0, 14.0)  # points: the size of a caret's mark (MuPDF's)

FONTS = {"helv": N_("Helvetica (sans serif)"), "tiro": N_("Times (serif)"), "cour": N_("Courier (monospaced)")}
_DA_FONTS = {"helv": "helv", "tiro": "tiro", "times": "tiro", "cour": "cour", "courier": "cour"}
FAMILIES = {"helv": "Helvetica", "tiro": "Times", "cour": "Courier"}  # (the fonts' names in rich text)
ATTACH_ICONS = {"Paperclip": N_("Paperclip"), "PushPin": N_("Push pin"), "Graph": N_("Graph"), "Tag": N_("Tag")}
ALIGNS = {"left": N_("Left"), "center": N_("Centre"), "right": N_("Right")}
ICONS = {"Note": N_("Note"), "Comment": N_("Comment"), "Key": N_("Key"), "Help": N_("Help"),
         "NewParagraph": N_("New paragraph"), "Paragraph": N_("Paragraph"), "Insert": N_("Insert")}
ENDS = {"None": N_("None"), "OpenArrow": N_("Open arrow"), "ClosedArrow": N_("Closed arrow"),
        "Circle": N_("Circle"), "Square": N_("Square"), "Diamond": N_("Diamond"), "Butt": N_("Bar"),
        "Slash": N_("Slash"), "ROpenArrow": N_("Reversed open arrow"), "RClosedArrow": N_("Reversed closed arrow")}
_END_CODES = {"None": pymupdf.PDF_ANNOT_LE_NONE, "OpenArrow": pymupdf.PDF_ANNOT_LE_OPEN_ARROW,
              "ClosedArrow": pymupdf.PDF_ANNOT_LE_CLOSED_ARROW, "Circle": pymupdf.PDF_ANNOT_LE_CIRCLE,
              "Square": pymupdf.PDF_ANNOT_LE_SQUARE, "Diamond": pymupdf.PDF_ANNOT_LE_DIAMOND,
              "Butt": pymupdf.PDF_ANNOT_LE_BUTT, "Slash": pymupdf.PDF_ANNOT_LE_SLASH,
              "ROpenArrow": pymupdf.PDF_ANNOT_LE_R_OPEN_ARROW, "RClosedArrow": pymupdf.PDF_ANNOT_LE_R_CLOSED_ARROW}
_END_NAMES = {code: name for name, code in _END_CODES.items()}
STAMPS = {"Approved": N_("Approved"), "AsIs": N_("As is"), "Confidential": N_("Confidential"),
          "Departmental": N_("Departmental"), "Experimental": N_("Experimental"), "Expired": N_("Expired"),
          "Final": N_("Final"), "ForComment": N_("For comment"), "ForPublicRelease": N_("For public release"),
          "NotApproved": N_("Not approved"), "NotForPublicRelease": N_("Not for public release"),
          "Sold": N_("Sold"), "TopSecret": N_("Top secret"), "Draft": N_("Draft")}  # (in MuPDF's order)
AREA_SUBJECT = "Area highlight"  # (the /Subj that tells an area highlight from a rectangle)
MARKER_SUBJECT = "Freehand highlight"  # (and a freehand highlight from a drawing)
SUBJECTS = {"area": AREA_SUBJECT, "marker": MARKER_SUBJECT}
# review states (the PDF's, of the model Review), with their names
STATES = {"Accepted": N_("Accepted"), "Rejected": N_("Rejected"), "Cancelled": N_("Cancelled"),
          "Completed": N_("Completed"), "None": N_("No status")}
TAGS_KEY, CATEGORIES_KEY = "PyAnnotateTags", "PyAnnotateCategories"
# the group of an annotation (see Annotation.group), besides the PDF's own (/IRT and /RT /Group, which
# _link_groups writes): with it, the group is known while those links are out (see apply)
GROUP_KEY = "PyAnnotateGroup"
CRITICAL_KEY = "PyAnnotateCritical"  # (an entry of textual criticism: its fields, as JSON)
REPEAT_KEY = "PyPdftoolsPages"  # (the pages a redaction box goes on, besides its own: see Annotation.repeat)
DASHES = (3, 3)

_TYPES = {pymupdf.PDF_ANNOT_HIGHLIGHT: "highlight", pymupdf.PDF_ANNOT_UNDERLINE: "underline",
          pymupdf.PDF_ANNOT_STRIKE_OUT: "strikeout", pymupdf.PDF_ANNOT_SQUIGGLY: "squiggly",
          pymupdf.PDF_ANNOT_CARET: "caret", pymupdf.PDF_ANNOT_TEXT: "note",
          pymupdf.PDF_ANNOT_FREE_TEXT: "freetext", pymupdf.PDF_ANNOT_SQUARE: "rect",
          pymupdf.PDF_ANNOT_CIRCLE: "ellipse", pymupdf.PDF_ANNOT_POLYGON: "polygon",
          pymupdf.PDF_ANNOT_POLY_LINE: "polyline", pymupdf.PDF_ANNOT_LINE: "line", pymupdf.PDF_ANNOT_INK: "ink",
          pymupdf.PDF_ANNOT_STAMP: "stamp", pymupdf.PDF_ANNOT_FILE_ATTACHMENT: "attachment",
          pymupdf.PDF_ANNOT_REDACT: "redact"}


# the kinds of entries of textual criticism (see Critical)
CRITICAL = {"variant": N_("Variant reading"), "manuscript": N_("Manuscript reading"), "emendation": N_("Emendation"),
            "conjecture": N_("Conjecture"), "lacuna": N_("Lacuna"), "illegible": N_("Illegible passage"),
            "scribal": N_("Scribal correction"), "marginal": N_("Marginal addition"),
            "interlinear": N_("Interlinear addition"), "deletion": N_("Deletion"), "abbreviation": N_("Abbreviation"),
            "expansion": N_("Expansion"), "uncertain": N_("Uncertain interpretation"),
            "editorial": N_("Editorial intervention"), "palaeographical": N_("Palaeographical observation"),
            "codicological": N_("Codicological observation")}
CONFIDENCE = {"": N_("Not given"), "certain": N_("Certain"), "probable": N_("Probable"), "possible": N_("Possible"),
              "doubtful": N_("Doubtful")}


@dataclasses.dataclass(frozen=True)
class Critical:
    """An entry of textual criticism, given to an annotation (usually a mark over the passage)."""
    type: str  # see CRITICAL
    lemma: str = ""  # the reading of the text
    reading: str = ""  # the reading proposed, or that of the witness
    witness: str = ""  # the manuscript or edition (its siglum)
    location: str = ""  # where, in it (folio, line...)
    source: str = ""  # where the reading comes from (an edition, a scholar...)
    rationale: str = ""
    confidence: str = ""  # see CONFIDENCE

    def name(self) -> str:
        return tr(CRITICAL[self.type]) if self.type in CRITICAL else self.type


@dataclasses.dataclass(frozen=True)
class Reply:
    """An answer to an annotation; with STATE, a review status given to it (see STATES)."""
    author: str = ""
    contents: str = ""
    state: str = ""
    created: str = ""
    modified: str = ""
    xref: int = 0


@dataclasses.dataclass(frozen=True)
class Annotation:
    kind: str
    page: int  # 0-based
    rect: Rect  # where it is: its frame (of a callout, its box), which moving and resizing change
    color: str = "#ffeb3b"  # of the mark, the line, the note, or the text of a text box
    fill: str = ""  # of the inside of a shape or a text box; '' for none
    opacity: float = 1.0  # from 0 to 1
    width: float = 1.5  # of the line of a shape, or the border of a text box (0: none), in points
    contents: str = ""  # the comment, or the text of a note or a text box
    author: str = ""
    font_size: float = 12.0  # of a text box
    # of a text box: its text with its formatting (bold, italic, colours, fonts), as XHTML paragraphs
    # (see rich_html); '' for plain text, all of it in COLOR and FONT
    rich: str = ""
    border: str = ""  # of a text box: the colour of its border (and callout line); '' for that of its text
    quads: tuple[Rect, ...] = ()  # text markup: a rectangle for each line
    # line, arrow, polyline, polygon and cloud: one path of their points; ink: its strokes;
    # callout: one path of one point, where it points
    paths: tuple[tuple[Point, ...], ...] = ()
    font: str = "helv"  # of a text box: see FONTS
    align: str = "left"  # of the text of a text box
    icon: str = "Note"  # of a note: see ICONS
    ends: tuple[str, str] = ("None", "None")  # of a line (or callout: its second, at the place pointed): see ENDS
    dashed: bool = False
    locked: bool = False  # (the PDF's flag: neither moved, resized nor deleted)
    stamp: str = ""  # a standard stamp (see STAMPS); '' for one of an image
    image: bytes = b""  # a stamp's look, as a PNG
    created: str = ""  # PDF dates (D:20261119...): '' if unknown, or not yet written
    modified: str = ""
    tags: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    # the annotations with the same group (on any page) are moved, selected and deleted together; '' for none.
    # Written as the PDF writes groups: the others answer the first (/IRT) as its group (/RT /Group)
    group: str = ""
    critical: Critical | None = None  # an entry of textual criticism, if it has one
    other: str = ""  # of an annotation of another kind (OTHER): its kind, as the PDF names it ('Link'...)
    # what a mark over text, or an insert-text mark, means (the PDF's /IT): 'Replace' (an insert-text mark
    # holding the text that replaces what its group strikes out), 'StrikeOutTextEdit' (that strikeout); '' none
    intent: str = ""
    data: bytes = b""  # of an attached file: its bytes
    filename: str = ""  # of an attached file: its name
    layer: str = ""  # the name of its layer (the PDF's optional content, which viewers show or hide); '' for none
    # a redaction box (kind 'redact': the PDF's redaction mark, /Redact, which marks what is to be removed, and
    # is applied when a redacted copy is made; see redact/redact.py): FILL is the colour it leaves (none: ''),
    # CONTENTS a note shown over it; OVERLAY is the text written where it was once applied (/OverlayText),
    # in COLOR, FONT_SIZE (0: as large as fits) and ALIGN, and OVERLAY_REPEAT says it is repeated all along
    # (/Repeat); REPEAT, the pages it goes on ('' only its own; else as 2-10, 15, LAST: see core/pagesel.py)
    overlay: str = ""
    overlay_repeat: bool = False
    repeat: str = ""
    replies: tuple[Reply, ...] = ()  # in the order they were made
    xref: int = 0  # of the annotation in the document it was read from; 0 if new

    def name(self) -> str:
        if self.kind == "caret" and self.intent == "Replace":
            return tr("Replacement")
        if self.kind == "freetext" and self.intent == TYPEWRITER:
            return tr("Typewriter")
        if self.kind == OTHER:
            return tr(OTHER_NAMES[self.other]) if self.other in OTHER_NAMES else self.other
        return tr(NAMES[self.kind])

    def status(self) -> str:
        """Its review status: that of its last reply that gives one ('' if none does, or it is 'None')."""
        states = [r.state for r in self.replies if r.state]
        return states[-1] if states and states[-1] != "None" else ""


class AnnotateError(Exception):
    """A document that cannot be read or written."""


class PasswordError(AnnotateError):
    """A document whose password is missing or wrong."""


# --------------------------------------------------------------------- geometry

def normalized(rect: Rect) -> Rect:
    x0, y0, x1, y1 = rect
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def bounds(points: list[Point], pad: float = 0.0) -> Rect:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def union(rects) -> Rect:
    rects = list(rects)
    return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects),
            max(r[3] for r in rects))


def _r(value: float) -> float:
    return round(value, 2)


def smooth_segments(points) -> list[tuple[Point, Point, Point]]:
    """The curve through POINTS (a stroke drawn by hand), as cubic Bézier segments, one from each point
    to the next: (first control point, second control point, end). Each point's tangent is the line
    between its neighbours (a Catmull–Rom spline), as PdfCraft draws ink (MIT/Apache-2.0)."""
    if not points:
        return []
    last = points[-1]

    def at(i: int) -> Point:
        return points[i] if 0 <= i < len(points) else last

    out = []
    for i in range(len(points) - 1):
        p0, p1, p2, p3 = at(max(i - 1, 0)), at(i), at(i + 1), at(i + 2)
        out.append(((p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6),
                    (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6), p2))
    return out


_AP_POINT = re.compile(r"^(-?[\d.]+) (-?[\d.]+) ([ml])$")


def _curved(doc: pymupdf.Document, xref: int) -> None:
    """Make the appearance of the drawing XREF (as MuPDF writes it: each stroke a point, 'm', and
    straight lines to the others, 'l') draw each stroke as a curve through its points."""
    kind, value = doc.xref_get_key(xref, "AP/N")
    if kind != "xref":
        return
    ap = int(value.split()[0])
    lines = doc.xref_stream(ap).decode("latin-1").split("\n")
    out: list[str] = []
    stroke: list[tuple[float, float]] = []

    def flush():
        if len(stroke) >= 3:
            out.extend(f"{c1[0]:g} {c1[1]:g} {c2[0]:g} {c2[1]:g} {e[0]:g} {e[1]:g} c"
                       for c1, c2, e in smooth_segments(stroke))
        else:
            out.extend(f"{x:g} {y:g} l" for x, y in stroke[1:])
        stroke.clear()

    for line in lines:
        found = _AP_POINT.match(line.strip())
        if found and (found[3] == "l" and stroke or found[3] == "m"):
            if found[3] == "m":
                flush()
                out.append(line.strip())
            stroke.append((float(found[1]), float(found[2])))
            continue
        flush()
        out.append(line)
    if any(line.endswith(" c") for line in out):
        doc.update_stream(ap, "\n".join(out).encode("latin-1"))


def frame(kind: str, paths, width: float) -> Rect:
    """The frame of a line, an arrow, a polygon or a drawing: around its points, with room for the line."""
    pad = max(width, 2.0) + {"arrow": 4.0, "cloud": 6.0}.get(kind, 0.0)
    return tuple(_r(v) for v in bounds([p for path in paths for p in path], pad))


def fitted(a: Annotation, rect: Rect) -> Annotation:
    """A, moved and stretched so that its frame becomes RECT."""
    x0, y0, x1, y1 = a.rect
    n0, m0, n1, m1 = normalized(rect)
    sx = (n1 - n0) / (x1 - x0) if x1 - x0 > 1e-6 else 1.0
    sy = (m1 - m0) / (y1 - y0) if y1 - y0 > 1e-6 else 1.0

    def point(p: Point) -> Point:
        return _r(n0 + (p[0] - x0) * sx), _r(m0 + (p[1] - y0) * sy)

    def box(r: Rect) -> Rect:
        return point((r[0], r[1])) + point((r[2], r[3]))

    paths = a.paths if a.kind == "callout" and (sx, sy) != (1.0, 1.0) else \
        tuple(tuple(point(p) for p in path) for path in a.paths)
    return dataclasses.replace(a, rect=(_r(n0), _r(m0), _r(n1), _r(m1)), quads=tuple(box(q) for q in a.quads),
                               paths=paths)


def moved(a: Annotation, dx: float, dy: float) -> Annotation:
    x0, y0, x1, y1 = a.rect
    return fitted(a, (x0 + dx, y0 + dy, x1 + dx, y1 + dy))


def with_vertex(a: Annotation, index: int, point: Point) -> Annotation:
    """A with its point INDEX (of its first path) at POINT; for a callout, the place it points at."""
    path = list(a.paths[0])
    path[index] = (_r(point[0]), _r(point[1]))
    paths = (tuple(path),) + a.paths[1:]
    if a.kind == "callout":
        return dataclasses.replace(a, paths=paths)
    return dataclasses.replace(a, paths=paths, rect=frame(a.kind, paths, a.width))


def shown_size(rotation: int, size: tuple[float, float]) -> tuple[float, float]:
    """SIZE (of a caret, made by MuPDF along the page), as a page turned ROTATION degrees shows it."""
    return (size[1], size[0]) if rotation % 180 else size


def anchor(box: Rect, point: Point) -> Point:
    """Where a callout's line leaves its BOX, going to POINT: the middle of the side nearest to it."""
    x0, y0, x1, y1 = box
    sides = [((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1), (x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)]
    return min(sides, key=lambda s: (s[0] - point[0]) ** 2 + (s[1] - point[1]) ** 2)


# --------------------------------------------------------------------- colours and dates

def rgb(color: str) -> tuple[float, float, float]:
    """'#rrggbb' as PyMuPDF's (r, g, b), each from 0 to 1."""
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(color)
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hex_color(values) -> str:
    """A colour of a PDF (grey, RGB or CMYK, from 0 to 1) as '#rrggbb'; '' for none."""
    values = [min(max(float(v), 0.0), 1.0) for v in values or []]
    if len(values) == 1:
        values = values * 3
    elif len(values) == 4:
        c, m, y, k = values
        values = [(1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)]
    elif len(values) != 3:
        return ""
    return "#" + "".join(f"{round(v * 255):02x}" for v in values)


PDF_DATE = re.compile(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?")


def now() -> str:
    """The time of now, as a PDF date."""
    return pymupdf.get_pdf_now()


def date_value(date: str) -> datetime.datetime | None:
    """A PDF date (D:20261119143000...) as a datetime (local, without its zone); None if it isn't one."""
    m = PDF_DATE.match(date.strip()) if date else None
    if not m:
        return None
    parts = [int(g) if g else d for g, d in zip(m.groups(), (0, 1, 1, 0, 0, 0))]
    try:
        return datetime.datetime(*parts)
    except ValueError:
        return None


def date_text(date: str) -> str:
    """A PDF date as 2026-11-19 14:30 ('' if there is none)."""
    value = date_value(date)
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


# --------------------------------------------------------------------- documents

def open_pdf(path: Path, password: str = "") -> pymupdf.Document:
    """The PDF at PATH, opened with PASSWORD if it needs one (raises AnnotateError)."""
    try:
        doc = pymupdf.open(path)
    except (pymupdf.FileNotFoundError, pymupdf.FileDataError, RuntimeError) as e:
        raise AnnotateError(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None
    if not doc.is_pdf:
        doc.close()
        raise AnnotateError(tr("{path} is not a PDF", path=path))
    if doc.needs_pass and not doc.authenticate(password):
        doc.close()
        raise PasswordError(tr("{path} is protected by a password", path=path))
    return doc


def kind_of(doc: pymupdf.Document, annot: pymupdf.Annot) -> str | None:
    """The kind of ANNOT, if py-pdftools can edit it (None for the others, and for replies)."""
    kind = _TYPES.get(annot.type[0])
    if kind is None or (doc.xref_get_key(annot.xref, "IRT")[0] != "null" and not _grouped(doc, annot.xref)):
        return None
    if kind == "line" and any(_END_NAMES.get(end, "").endswith("Arrow") for end in annot.line_ends or ()):
        return "arrow"
    if kind == "freetext" and doc.xref_get_key(annot.xref, "IT")[1] == "/FreeTextCallout":
        return "callout"
    if kind == "rect" and (annot.info or {}).get("subject") == AREA_SUBJECT:
        return "area"
    if kind == "polygon" and ((annot.border or {}).get("clouds") or 0) > 0:
        return "cloud"
    if kind == "ink" and (annot.info or {}).get("subject") == MARKER_SUBJECT:
        return "marker"
    return kind


def _shown_rect(page: pymupdf.Page, rect) -> Rect:
    r = (pymupdf.Rect(rect) * page.rotation_matrix).normalize()
    return _r(r.x0), _r(r.y0), _r(r.x1), _r(r.y1)


def _shown_point(page: pymupdf.Page, point) -> Point:
    p = pymupdf.Point(point) * page.rotation_matrix
    return _r(p.x), _r(p.y)


def _real_rect(page: pymupdf.Page, rect: Rect) -> pymupdf.Rect:
    return (pymupdf.Rect(normalized(rect)) * page.derotation_matrix).normalize()


def _real_point(page: pymupdf.Page, point: Point) -> pymupdf.Point:
    return pymupdf.Point(point) * page.derotation_matrix


def _pdf_points(page: pymupdf.Page, points) -> str:
    """POINTS (as the page is shown) in the PDF's own space, as the numbers of a PDF array."""
    inverse = ~page.transformation_matrix
    out = []
    for point in points:
        p = _real_point(page, point) * inverse
        out += [f"{p.x:.3f}", f"{p.y:.3f}"]
    return " ".join(out)


def to_pdf(page: pymupdf.Page, point: Point) -> tuple[float, float]:
    """POINT (as the page is shown) in the PDF's own space (from the bottom left corner of
    the page, not turned)."""
    p = _real_point(page, point) * ~page.transformation_matrix
    return round(p.x, 3), round(p.y, 3)


def from_pdf(page: pymupdf.Page, point: tuple[float, float]) -> Point:
    """POINT of the PDF's own space, as the page is shown."""
    p = pymupdf.Point(point) * page.transformation_matrix * page.rotation_matrix
    return _r(p.x), _r(p.y)


def _pdf_rect(page: pymupdf.Page, rect: pymupdf.Rect) -> str:
    """RECT (of the page as MuPDF sees it, not turned) as a PDF array."""
    r = (pymupdf.Rect(rect) * ~page.transformation_matrix).normalize()
    return f"[{r.x0:.3f} {r.y0:.3f} {r.x1:.3f} {r.y1:.3f}]"


def _pdf_text(doc: pymupdf.Document, xref: int, key: str) -> str:
    kind, value = doc.xref_get_key(xref, key)
    return value if kind == "string" else ""


def _labels(text: str) -> tuple[str, ...]:
    """Tags or categories kept as 'a, b, c'."""
    return tuple(t for t in (" ".join(x.split()) for x in text.split(",")) if t)


def _off_edge(r: pymupdf.Rect, p: pymupdf.Point) -> float:
    """How far P is from the edge of R."""
    if r.contains(p):
        return min(p.x - r.x0, r.x1 - p.x, p.y - r.y0, r.y1 - p.y)
    dx = max(r.x0 - p.x, 0, p.x - r.x1)
    dy = max(r.y0 - p.y, 0, p.y - r.y1)
    return (dx * dx + dy * dy) ** 0.5


DA_SIZE = re.compile(r"([\d.]+)\s+Tf")
DA_FONT = re.compile(r"/([A-Za-z]+)")
DA_COLOR = re.compile(r"((?:[\d.]+\s+){1,4})(g|rg|k)\b")


def plain_html(text: str) -> str:
    """TEXT as the XHTML of a text box: a paragraph for each line."""
    return "".join(f"<p>{html.escape(line, quote=False)}</p>" for line in text.split("\n"))


def _rich_style(a: Annotation) -> str:
    """The default style of the rich text of A (its /DS)."""
    return (f"font-size:{a.font_size:g}pt;font-family:{FAMILIES.get(a.font, 'Helvetica')};color:{a.color};"
            f"text-align:{a.align}")


def _rich_keys(doc: pymupdf.Document, xref: int, a: Annotation) -> None:
    """The keys of a text box written as rich text (after _info: setting its text takes them out): the
    rich text in /RC, its default look in /DS, its text, plain, in /Contents (for the programs that
    read only that), and the colour of its border in /DA."""
    r, g, b = rgb(a.border or a.color)
    doc.xref_set_key(xref, "RC", pymupdf.get_pdf_str(RC_HEAD + (a.rich or plain_html(a.contents)) + "</body>"))
    doc.xref_set_key(xref, "DS", pymupdf.get_pdf_str(_rich_style(a)))
    doc.xref_set_key(xref, "DA", pymupdf.get_pdf_str(f"{r:g} {g:g} {b:g} rg /{a.font.capitalize()} "
                                                       f"{a.font_size:g} Tf"))
    doc.xref_set_key(xref, "Contents", pymupdf.get_pdf_str(a.contents))


RC_HEAD = ('<?xml version="1.0"?><body xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:contentType="text/html" xfa:spec="2.4">')


RC_BODY = re.compile(r"<body\b[^>]*>(.*?)(?:</body>\s*)?$", re.S)
DS_COLOR = re.compile(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b")
DS_SIZE = re.compile(r"font-size\s*:\s*([\d.]+)\s*pt")
DS_FAMILY = re.compile(r"font-family\s*:\s*['\"]?([A-Za-z ]+)")


def _rich_text(doc: pymupdf.Document, xref: int, contents: str, color: str, size: float,
               font: str) -> tuple[str, str, str, float, str]:
    """The rich text of the text box XREF, its border's colour, and the colour, size and font of its
    text (COLOR, SIZE and FONT: those of its /DA, which are those of its border, if it has rich text)."""
    kind, rc = doc.xref_get_key(xref, "RC")
    found = RC_BODY.search(rc) if kind == "string" else None
    if found is None:
        return "", "", color, size, font
    _, ds = doc.xref_get_key(xref, "DS")
    text_color = DS_COLOR.search(ds or "")
    text_color = (text_color[1].lower() if len(text_color[1]) == 7 else
                  "#" + "".join(c * 2 for c in text_color[1][1:]).lower()) if text_color else "#000000"
    if (m := DS_SIZE.search(ds or "")):
        size = float(m[1]) or size
    if (m := DS_FAMILY.search(ds or "")):
        font = _DA_FONTS.get(m[1].split()[0].lower(), font) if m[1].split() else font
    rich = found[1].strip()
    return ("" if rich == plain_html(contents) else rich), ("" if color == text_color else color), text_color, \
        size, font


def _text_style(doc: pymupdf.Document, xref: int) -> tuple[str, float, str]:
    """The colour, the size and the font of the text of a text box, from its /DA."""
    kind, da = doc.xref_get_key(xref, "DA")
    if kind != "string":
        return "#000000", 12.0, "helv"
    size = DA_SIZE.search(da)
    color = DA_COLOR.search(da)
    font = DA_FONT.search(da)
    return ((hex_color(color[1].split()) if color else "#000000") or "#000000",
            (float(size[1]) or 12.0) if size else 12.0,
            _DA_FONTS.get(font[1].lower(), "helv") if font else "helv")


def _stamp_image(annot: pymupdf.Annot, page: pymupdf.Page | None = None) -> bytes:
    """How the stamp ANNOT looks, as a PNG (for showing it: the window draws it), the
    right way up on PAGE as it is shown (turned or not)."""
    try:
        pix = annot.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=True)
        if page is not None and page.rotation % 180:
            shown = annot.rect * page.rotation_matrix
            if (pix.width > pix.height) != (abs(shown.width) > abs(shown.height)):
                pix = annot.get_pixmap(matrix=pymupdf.Matrix(3, 3).prerotate(page.rotation), alpha=True)
        return pix.tobytes("png")
    except (RuntimeError, ValueError):
        return b""


_STANDARD: dict[str, tuple[bytes, tuple[float, float]]] = {}


def standard_stamp(name: str) -> tuple[bytes, tuple[float, float]]:
    """How the standard stamp NAME looks (a PNG), and its usual size in points."""
    if name not in _STANDARD:
        doc = pymupdf.open()
        page = doc.new_page()
        annot = page.add_stamp_annot(pymupdf.Rect(0, 0, 160, 50), stamp=list(STAMPS).index(name))
        _STANDARD[name] = _stamp_image(annot), (_r(annot.rect.width), _r(annot.rect.height))
        doc.close()
    return _STANDARD[name]


def read_annotation(doc: pymupdf.Document, page: pymupdf.Page, annot: pymupdf.Annot) -> Annotation | None:
    kind = kind_of(doc, annot)
    if kind is None:
        return None
    colors = annot.colors or {}
    stroke, fill = hex_color(colors.get("stroke")), hex_color(colors.get("fill"))
    border = annot.border or {}
    width = border.get("width", -1)
    width = width if width is not None and width >= 0 else 1.0
    opacity = annot.opacity if annot.opacity is not None and 0 <= annot.opacity <= 1 else 1.0
    info = annot.info or {}
    ends = tuple(_END_NAMES.get(e, "None") for e in (annot.line_ends or (0, 0)))
    fields = {"kind": kind, "page": page.number, "opacity": round(opacity, 3), "width": _r(width),
              "contents": info.get("content", "") or "", "author": info.get("title", "") or "",
              "created": info.get("creationDate", "") or "", "modified": info.get("modDate", "") or "",
              "locked": bool(annot.flags & pymupdf.PDF_ANNOT_IS_LOCKED),
              "dashed": bool(border.get("dashes")) or border.get("style") == "D",
              "tags": _labels(_pdf_text(doc, annot.xref, TAGS_KEY)),
              "categories": _labels(_pdf_text(doc, annot.xref, CATEGORIES_KEY)), "xref": annot.xref,
              "critical": critical_of(_pdf_text(doc, annot.xref, CRITICAL_KEY)),
              "layer": _layer_of(doc, annot.xref),
              "intent": _intent(doc, annot),
              "group": _pdf_text(doc, annot.xref, GROUP_KEY)
              or (f"#{_irt(doc, annot.xref)}" if _grouped(doc, annot.xref) else "")}
    vertices = annot.vertices or []
    if kind in MARKUP:
        quads = [_shown_rect(page, bounds(vertices[i:i + 4])) for i in range(0, len(vertices) - 3, 4)]
        if not quads:
            quads = [_shown_rect(page, annot.rect)]
        return Annotation(rect=union(quads), color=stroke or "#ffeb3b", quads=tuple(quads), **fields)
    if kind in TEXTUAL:
        color, size, font = _text_style(doc, annot.xref)
        rich, border, color, size, font = _rich_text(doc, annot.xref, fields["contents"], color, size, font)
        r = pymupdf.Rect(annot.rect)
        rd = doc.xref_get_key(annot.xref, "RD")
        delta = [float(v) for v in rd[1].strip("[]").split()] if rd[0] == "array" else []
        if len(delta) == 4 and any(delta):
            # (the box, inside the rectangle that holds the box and the line; /RD gives what is left out on
            # each side, as MuPDF writes it: left, below, right, above. Some programs give them in another
            # order: if the box this makes holds the place the line points at, or is empty, the other is tried)
            box = pymupdf.Rect(r.x0 + delta[0], r.y0 + delta[3], r.x1 - delta[2], r.y1 - delta[1])
            other = pymupdf.Rect(r.x0 + delta[0], r.y0 + delta[1], r.x1 - delta[2], r.y1 - delta[3])
            if kind == "callout" and len(vertices) > 1 and not other.is_empty:
                # (the line ends on the edge of the box: the reading that puts that end nearest to it)
                end = pymupdf.Point(vertices[-1])
                if _off_edge(other, end) < _off_edge(box, end) - 0.5:
                    box = other
            elif box.is_empty:
                box = other
            r = box if not box.is_empty else r
        elif width:  # (the rectangle holds the border, half of it outside the box)
            r = pymupdf.Rect(r.x0 + width / 2, r.y0 + width / 2, r.x1 - width / 2, r.y1 - width / 2)
        q = doc.xref_get_key(annot.xref, "Q")
        align = {"1": "center", "2": "right"}.get(q[1], "left") if q[0] == "int" else "left"
        paths = ()
        if kind == "callout":
            le = doc.xref_get_key(annot.xref, "LE")[1].lstrip("/")
            ends = ("None", le if le in _END_CODES else "None")
            if vertices:
                paths = ((_shown_point(page, vertices[0]),),)
            else:
                kind, fields["kind"] = "freetext", "freetext"
        # (a text box keeps its fill in /C, which PyMuPDF gives as its 'stroke')
        return Annotation(rect=_shown_rect(page, r), color=color, fill=stroke, font_size=_r(size), font=font,
                          rich=rich, border=border, align=align, paths=paths, ends=ends if kind == "callout" else ("None", "None"),
                          **fields)
    if kind in ("rect", "ellipse", "area"):  # (its rectangle holds the line, half of it outside the shape)
        r = pymupdf.Rect(annot.rect)
        half = width / 2
        if r.width > 2 * half and r.height > 2 * half:
            r = pymupdf.Rect(r.x0 + half, r.y0 + half, r.x1 - half, r.y1 - half)
        return Annotation(rect=_shown_rect(page, r), color=stroke or "#000000", fill=fill, **fields)
    if kind in ("line", "arrow", "polyline", "polygon", "cloud", "ink", "marker"):
        if kind in DRAWN:
            paths = tuple(tuple(_shown_point(page, p) for p in stroke_) for stroke_ in vertices if stroke_)
        elif kind in ("line", "arrow"):
            paths = (tuple(_shown_point(page, p) for p in vertices[:2]),)
        else:
            paths = (tuple(_shown_point(page, p) for p in vertices),)
        if not paths or len(paths[0]) < (1 if kind in DRAWN else 2):
            return None
        return Annotation(rect=frame(kind, paths, width), color=stroke or "#000000", fill=fill, paths=paths,
                          ends=ends if kind in ENDED else ("None", "None"), **fields)
    if kind == "redact":
        color, size, _ = _text_style(doc, annot.xref)
        kind_, da = doc.xref_get_key(annot.xref, "DA")
        if kind_ != "string" or not DA_SIZE.search(da) or not float(DA_SIZE.search(da)[1]):
            size = 0.0  # (as large as fits)
        ic = doc.xref_get_key(annot.xref, "IC")
        fill = hex_color(ic[1].strip("[]").split()) if ic[0] == "array" else ""
        q = doc.xref_get_key(annot.xref, "Q")
        return Annotation(rect=_shown_rect(page, annot.rect), color=color if kind_ == "string" else "#ffffff",
                          fill=fill or "", font_size=_r(size),
                          align={"0": "left", "2": "right"}.get(q[1], "center") if q[0] == "int" else "center",
                          overlay=_pdf_text(doc, annot.xref, "OverlayText"),
                          overlay_repeat=doc.xref_get_key(annot.xref, "Repeat")[1] == "true",
                          repeat=_pdf_text(doc, annot.xref, REPEAT_KEY), **fields)
    if kind == "stamp":
        name = doc.xref_get_key(annot.xref, "Name")[1].lstrip("/")
        return Annotation(rect=_shown_rect(page, annot.rect), color=stroke or "#000000",
                          stamp=name if name in STAMPS else "", image=_stamp_image(annot, page), **fields)
    if kind == "attachment":
        try:
            data, found = annot.get_file(), annot.file_info or {}
        except (RuntimeError, ValueError):
            data, found = b"", {}
        icon = doc.xref_get_key(annot.xref, "Name")[1].lstrip("/")
        return Annotation(rect=_shown_rect(page, annot.rect), color=stroke or "#1e88e5", data=data,
                          filename=found.get("filename", "") or "", icon=icon if icon in ATTACH_ICONS else "Paperclip",
                          **fields)
    # (a note, or a caret)
    icon = info.get("name", "") or "Note"
    return Annotation(rect=_shown_rect(page, annot.rect), color=stroke or ("#ffd54f" if kind == "note" else "#1e88e5"),
                      icon=icon if icon in ICONS else "Note", **fields)


def _reply_roots(doc: pymupdf.Document, page: pymupdf.Page) -> dict[int, int]:
    """{xref of a reply: xref of the annotation it answers, at the root of the thread} on PAGE."""
    return _roots(doc, page.annot_xrefs())


def _roots(doc: pymupdf.Document, items) -> dict[int, int]:
    """_reply_roots of the annotations ITEMS of a page ((xref, type, id), as annot_xrefs gives them): from
    the keys of their objects alone, without loading them (thousands of annotations)."""
    parent = {}
    for xref, kind, _ in items:
        if kind == pymupdf.PDF_ANNOT_TEXT and (irt := _irt(doc, xref)) \
                and not _grouped(doc, xref):  # (a note in the group of another isn't a reply to it)
            parent[xref] = irt
    roots = {}
    for xref in parent:
        root, seen = parent[xref], {xref}
        while root in parent and root not in seen:  # (a reply to a reply: to the first of the thread)
            seen.add(root)
            root = parent[root]
        roots[xref] = root
    return roots


def read_reply(doc: pymupdf.Document, annot: pymupdf.Annot) -> Reply:
    info = annot.info or {}
    state = _pdf_text(doc, annot.xref, "State")
    model = _pdf_text(doc, annot.xref, "StateModel")
    return Reply(author=info.get("title", "") or "", contents=info.get("content", "") or "",
                 state=state if state in STATES and model in ("Review", "") else "",
                 created=info.get("creationDate", "") or "", modified=info.get("modDate", "") or "",
                 xref=annot.xref)


def read(doc: pymupdf.Document, known: dict[int, Annotation] | None = None) -> list[Annotation]:
    """The annotations of DOC that py-pdftools can edit, page by page, with their replies. KNOWN:
    {xref: annotation} of those known to be as they were read before (they are not read again)."""
    known = known or {}
    out = []
    for page in doc:
        items = page.annot_xrefs()
        if not items:
            continue
        roots = _roots(doc, items)
        found, replies = [], {}
        # (by the numbers of their objects: an annotation known is not loaded at all)
        for xref, kind, _ in items:
            if kind in (pymupdf.PDF_ANNOT_WIDGET, pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_LINK):
                continue  # (_others lists links; form fields and pop-ups are never listed)
            if xref in roots:
                if roots[xref] not in known:
                    replies.setdefault(roots[xref], []).append(read_reply(doc, page.load_annot(xref)))
                continue
            if xref in known:
                found.append(known[xref])
                continue
            a = read_annotation(doc, page, page.load_annot(xref))
            if a is not None:
                found.append(a)
        found += _others(doc, page)
        for a in found:
            if a.xref in replies and a.xref not in known:
                thread = sorted(replies[a.xref], key=lambda r: (date_value(r.created) or datetime.datetime.min,
                                                                 r.xref))
                a = dataclasses.replace(a, replies=tuple(thread))
            out.append(a)
    # (the first of a group made by another program: it has no GROUP_KEY, but the others answer it)
    firsts = {a.group for a in out if a.group.startswith("#")}
    return [dataclasses.replace(a, group=f"#{a.xref}") if not a.group and f"#{a.xref}" in firsts else a
            for a in out]


def _editable(doc: pymupdf.Document, annot: pymupdf.Annot) -> bool:
    """Whether read() gives ANNOT (the same as kind_of(...) is not None, but quicker)."""
    return annot.type[0] in _TYPES and (doc.xref_get_key(annot.xref, "IRT")[0] == "null"
                                        or _grouped(doc, annot.xref))


def critical_of(data) -> Critical | None:
    """The entry of textual criticism of DATA (JSON, or a dict); None if it has none."""
    try:
        values = json.loads(data) if isinstance(data, str) else data
    except ValueError:
        return None
    if not isinstance(values, dict) or not values.get("type"):
        return None
    names = {f.name for f in dataclasses.fields(Critical)}
    return Critical(**{k: str(v) for k, v in values.items() if k in names})


def _others(doc: pymupdf.Document, page: pymupdf.Page) -> list[Annotation]:
    """The annotations of PAGE of other kinds (see OTHER), to be listed: what each one is, where."""
    out = []
    links = {link.get("xref"): link for link in page.get_links()}
    for xref, kind, name in page.annot_xrefs():
        if kind in _TYPES or kind in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET):
            continue
        other = doc.xref_get_key(xref, "Subtype")[1].lstrip("/")
        try:
            if kind == pymupdf.PDF_ANNOT_LINK:
                link = links.get(xref, {})
                rect = pymupdf.Rect(link["from"]) if link.get("from") else _pdf_rect_of(doc, page, xref)
                text = link.get("uri") or (tr("Page {page}", page=link["page"] + 1)
                                           if isinstance(link.get("page"), int) and link["page"] >= 0 else "")
                out.append(Annotation(OTHER, page.number, _shown_rect(page, rect), "#808080", contents=text,
                                      locked=True, other=other, xref=xref))
                continue
            annot = page.load_annot(xref)
            info = annot.info or {}
            text = info.get("content", "") or ""
            if kind == pymupdf.PDF_ANNOT_FILE_ATTACHMENT:
                with_file = (annot.file_info or {}).get("filename", "")
                text = " — ".join(t for t in (with_file, text) if t)
            out.append(Annotation(OTHER, page.number, _shown_rect(page, annot.rect), "#808080", contents=text,
                                  author=info.get("title", "") or "", locked=True, other=other, xref=xref,
                                  created=info.get("creationDate", "") or "", modified=info.get("modDate", "") or ""))
        except (RuntimeError, ValueError, KeyError, TypeError):
            continue
    return out


def _pdf_rect_of(doc: pymupdf.Document, page: pymupdf.Page, xref: int) -> pymupdf.Rect:
    """The /Rect of the annotation XREF, in PyMuPDF's coordinates of PAGE (unturned)."""
    x0, y0, x1, y1 = (float(v) for v in doc.xref_get_key(xref, "Rect")[1].strip("[]").split())
    return pymupdf.Rect(x0, y0, x1, y1) * page.transformation_matrix


TYPEWRITER = "FreeTextTypeWriter"  # (the intent of a text box written as with a typewriter: no border, no fill)


def _intent(doc: pymupdf.Document, annot: pymupdf.Annot) -> str:
    """The intent (/IT) of ANNOT that Annotation.intent keeps: of a strikeout or an insert-text mark,
    any; of a text box, only the typewriter's (a callout's makes it a callout)."""
    kind, value = doc.xref_get_key(annot.xref, "IT")
    if kind != "name":
        return ""
    value = value.lstrip("/")
    if annot.type[0] in (pymupdf.PDF_ANNOT_CARET, pymupdf.PDF_ANNOT_STRIKE_OUT):
        return value
    return value if annot.type[0] == pymupdf.PDF_ANNOT_FREE_TEXT and value == TYPEWRITER else ""


def _layer_of(doc: pymupdf.Document, xref: int) -> str:
    """The name of the layer (optional content group) of the annotation XREF; '' if it has none."""
    kind, value = doc.xref_get_key(xref, "OC")
    if kind != "xref":
        return ""
    oc = int(value.split()[0])
    return _pdf_text(doc, oc, "Name") if doc.xref_get_key(oc, "Type")[1] == "/OCG" else ""


def layers(doc: pymupdf.Document) -> dict[str, bool]:
    """The layers of DOC: {name: whether it is shown}."""
    return {info["name"]: bool(info["on"]) for info in (doc.get_ocgs() or {}).values()}


def layer_xref(doc: pymupdf.Document, name: str) -> int:
    """The layer NAME of DOC, made if it has none."""
    for xref, info in (doc.get_ocgs() or {}).items():
        if info["name"] == name:
            return xref
    return doc.add_ocg(name, on=True)


def set_layers(doc: pymupdf.Document, shown: dict[str, bool]) -> None:
    """Show or hide the layers of DOC as SHOWN says ({name: shown}; those it doesn't name stay as they
    are), making those it has not."""
    for name in shown:
        layer_xref(doc, name)
    groups = doc.get_ocgs() or {}
    state = {x: shown.get(info["name"], bool(info["on"])) for x, info in groups.items()}
    if any(bool(groups[x]["on"]) != on for x, on in state.items()):
        doc.set_layer(-1, on=[x for x, on in state.items() if on], off=[x for x, on in state.items() if not on])


def _grouped(doc: pymupdf.Document, xref: int) -> bool:
    """Whether the annotation XREF is in the group of another (not a reply to it)."""
    return doc.xref_get_key(xref, "RT")[1] == "/Group"


def _irt(doc: pymupdf.Document, xref: int) -> int:
    kind, value = doc.xref_get_key(xref, "IRT")
    return int(value.split()[0]) if kind == "xref" else 0


def _unlink_groups(doc: pymupdf.Document, pages: list[int] | None = None) -> None:
    """Take out the links of the groups (/IRT, /RT) of PAGES (all if None), keeping each group in
    GROUP_KEY (so that taking out the first of a group doesn't take the others with it, as MuPDF does
    with what answers it)."""
    for page in (doc if pages is None else (doc[n] for n in pages)):
        for xref, _, _ in page.annot_xrefs():
            if _grouped(doc, xref) and (first := _irt(doc, xref)):
                for x in (xref, first):
                    if doc.xref_get_key(x, GROUP_KEY)[0] == "null":
                        doc.xref_set_key(x, GROUP_KEY, pymupdf.get_pdf_str(f"#{first}"))
                doc.xref_set_key(xref, "IRT", "null")
                doc.xref_set_key(xref, "RT", "null")


def _link_groups(doc: pymupdf.Document) -> None:
    """Write the groups as the PDF does: each annotation of a group (GROUP_KEY) after the first
    answers it (/IRT) as its group (/RT /Group)."""
    first: dict[str, int] = {}
    for page in doc:
        for xref, _, _ in page.annot_xrefs():
            kind, group = doc.xref_get_key(xref, GROUP_KEY)
            if kind != "string" or not group:
                continue
            if group not in first:
                first[group] = xref
            elif _irt(doc, xref) != first[group]:
                doc.xref_set_key(xref, "IRT", f"{first[group]} 0 R")
                doc.xref_set_key(xref, "RT", "/Group")


def _delete(page: pymupdf.Page, xref: int) -> None:
    """Take out the annotation XREF of PAGE, if it is still there (PyMuPDF takes out the
    replies of an annotation with it)."""
    if xref in {x for x, _, _ in page.annot_xrefs()}:
        page.delete_annot(page.load_annot(xref))


def remove_editable(doc: pymupdf.Document, pages: list[int] | None = None) -> None:
    """Take out of DOC (of its PAGES: all if None) the annotations that read() gives, their replies and
    their pop-ups (for showing its pages without them: the window draws them itself). DOC is only shown,
    never saved: they are taken out of the list of each page (/Annots), and their objects left as they
    are, without loading a page or an annotation (thousands of them: deleting each one took long)."""
    for n in range(doc.page_count) if pages is None else pages:
        items = doc.page_annot_xrefs(n)
        if not items:
            continue
        roots = _roots(doc, items)
        editable = {x for x, kind, _ in items
                    if kind in _TYPES and (not _irt(doc, x) or _grouped(doc, x))}
        gone = editable | {x for x, root in roots.items() if root in editable}
        gone |= {x for x, kind, _ in items if kind == pymupdf.PDF_ANNOT_POPUP and _parent(doc, x) in gone}
        if gone:
            kept = [x for x, _, _ in items if x not in gone]
            doc.xref_set_key(doc.page_xref(n), "Annots",
                             "[" + " ".join(f"{x} 0 R" for x in kept) + "]" if kept else "null")


def _parent(doc: pymupdf.Document, xref: int) -> int:
    """The annotation a pop-up belongs to (0 if none)."""
    kind, value = doc.xref_get_key(xref, "Parent")
    return int(value.split()[0]) if kind == "xref" else 0


def _placed(page: pymupdf.Page, make, rect: Rect, size: tuple[float, float]) -> pymupdf.Annot:
    """An annotation of a size of its own (a note, a caret), made by MAKE(point),
    with its top left corner where RECT's is, as the page is shown."""
    x0, y0 = rect[0], rect[1]
    w, h = shown_size(page.rotation, size)
    where = _real_rect(page, (x0, y0, x0 + w, y0 + h))
    annot = make(where.tl)
    shift = where.tl - annot.rect.tl
    if abs(shift.x) > 0.01 or abs(shift.y) > 0.01:  # (on a turned page, MuPDF puts it beside the point)
        page.delete_annot(annot)
        annot = make(where.tl + shift)
    return annot


def _flags(annot: pymupdf.Annot, locked: bool) -> None:
    flags = annot.flags | pymupdf.PDF_ANNOT_IS_PRINT
    flags = flags | pymupdf.PDF_ANNOT_IS_LOCKED if locked else flags & ~pymupdf.PDF_ANNOT_IS_LOCKED
    if flags != annot.flags:
        annot.set_flags(flags)


def _info(annot: pymupdf.Annot, a: Annotation, when: str) -> None:
    info = {"content": a.contents, "title": a.author, "creationDate": a.created or when, "modDate": when}
    if a.kind in SUBJECTS:
        info["subject"] = SUBJECTS[a.kind]
    annot.set_info(**info)


def _labels_keys(doc: pymupdf.Document, xref: int, a: Annotation) -> None:
    for key, values in ((TAGS_KEY, a.tags), (CATEGORIES_KEY, a.categories)):
        doc.xref_set_key(xref, key, pymupdf.get_pdf_str(", ".join(values)) if values else "null")
    doc.xref_set_key(xref, GROUP_KEY, pymupdf.get_pdf_str(a.group) if a.group else "null")
    if a.kind in ("caret", "strikeout", "freetext"):
        doc.xref_set_key(xref, "IT", f"/{a.intent}" if re.fullmatch(r"[A-Za-z]+", a.intent) else "null")
    if a.layer != _layer_of(doc, xref):
        doc.xref_set_key(xref, "OC", f"{layer_xref(doc, a.layer)} 0 R" if a.layer else "null")
    entry = json.dumps({k: v for k, v in dataclasses.asdict(a.critical).items() if v}, ensure_ascii=False) \
        if a.critical else ""
    doc.xref_set_key(xref, CRITICAL_KEY, pymupdf.get_pdf_str(entry) if entry else "null")


def add(page: pymupdf.Page, a: Annotation, when: str | None = None) -> pymupdf.Annot:
    """Write A on PAGE, as a new annotation, made (if A has no date) and changed WHEN (a PDF
    date; now), with its replies."""
    when = when or now()
    stroke = rgb(a.color)
    fill = rgb(a.fill) if a.fill else None
    dashes = DASHES if a.dashed and a.kind in DASHABLE else None
    if a.kind in MARKUP:
        quads = [_real_rect(page, q).quad for q in (a.quads or (a.rect,))]
        method = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
                  "strikeout": page.add_strikeout_annot, "squiggly": page.add_squiggly_annot}[a.kind]
        annot = method(quads=quads)
        annot.set_colors(stroke=stroke)
    elif a.kind in TEXTUAL:
        box = _real_rect(page, a.rect)
        extra = {}
        if a.kind == "callout" and a.paths:
            tip = a.paths[0][0]
            extra = {"callout": [tuple(_real_point(page, tip)), tuple(_real_point(page, anchor(a.rect, tip)))],
                     "line_end": _END_CODES.get(a.ends[1], pymupdf.PDF_ANNOT_LE_OPEN_ARROW)}
        if a.rich or a.border:  # (rich text: its look is in /RC and /DS, and /DA has the colour of the border)
            annot = page.add_freetext_annot(box, a.rich or plain_html(a.contents), fontsize=a.font_size,
                                            fontname=a.font, fill_color=fill, border_width=a.width, dashes=dashes,
                                            align={"center": 1, "right": 2}.get(a.align, 0), rotate=page.rotation,
                                            richtext=True, style=_rich_style(a), **extra)
        else:
            annot = page.add_freetext_annot(box, a.contents, fontsize=a.font_size, fontname=a.font,
                                            text_color=stroke, fill_color=fill, border_width=a.width,
                                            dashes=dashes, align={"center": 1, "right": 2}.get(a.align, 0),
                                            rotate=page.rotation, **extra)
    elif a.kind in ("rect", "ellipse", "area"):
        method = page.add_circle_annot if a.kind == "ellipse" else page.add_rect_annot
        annot = method(_real_rect(page, a.rect))
        annot.set_border(width=0 if a.kind == "area" else a.width, dashes=dashes or [])
        annot.set_colors(stroke=stroke, fill=fill)
    elif a.kind in ("line", "arrow"):
        p1, p2 = a.paths[0][0], a.paths[0][-1]
        annot = page.add_line_annot(_real_point(page, p1), _real_point(page, p2))
        annot.set_border(width=a.width, dashes=dashes or [])
        annot.set_colors(stroke=stroke)
        annot.set_line_ends(*(_END_CODES.get(e, 0) for e in _line_ends(a)))
    elif a.kind in ("polygon", "cloud", "polyline"):
        points = [tuple(_real_point(page, p)) for p in a.paths[0]]
        annot = page.add_polyline_annot(points) if a.kind == "polyline" else page.add_polygon_annot(points)
        annot.set_border(width=a.width, dashes=dashes or [], clouds=1 if a.kind == "cloud" else -1)
        annot.set_colors(stroke=stroke, fill=fill if a.kind != "polyline" else None)
        if a.kind == "polyline":
            annot.set_line_ends(*(_END_CODES.get(e, 0) for e in a.ends))
    elif a.kind in DRAWN:
        annot = page.add_ink_annot([[tuple(_real_point(page, p)) for p in path] for path in a.paths])
        annot.set_border(width=a.width)
        annot.set_colors(stroke=stroke)
    elif a.kind == "note":
        annot = _placed(page, lambda p: page.add_text_annot(p, a.contents, icon=a.icon), a.rect,
                        (NOTE_SIZE, NOTE_SIZE))
        annot.set_colors(stroke=stroke)
    elif a.kind == "attachment":
        annot = _placed(page, lambda p: page.add_file_annot(p, a.data, a.filename or "file",
                                                            icon=a.icon if a.icon in ATTACH_ICONS else "Paperclip"),
                        a.rect, (NOTE_SIZE, NOTE_SIZE))
        annot.set_colors(stroke=stroke)
    elif a.kind == "caret":
        annot = _placed(page, page.add_caret_annot, a.rect, CARET_SIZE)
        annot.set_colors(stroke=stroke)
    elif a.kind == "stamp":
        stamps = list(STAMPS)
        annot = page.add_stamp_annot(_real_rect(page, a.rect),
                                     stamp=stamps.index(a.stamp) if a.stamp in stamps else a.image)
    elif a.kind == "redact":
        annot = page.add_redact_annot(_real_rect(page, a.rect), fill=fill if fill else False, cross_out=False)
        _redact_keys(page.parent, annot.xref, a)
    else:
        raise ValueError(a.kind)
    _info(annot, a, when)
    if a.opacity < 1:
        annot.set_opacity(a.opacity)
    _flags(annot, a.locked)
    _labels_keys(page.parent, annot.xref, a)
    if a.kind in TEXTUAL and (a.rich or a.border):
        _rich_keys(page.parent, annot.xref, a)
    if a.kind in TEXTUAL:  # (update() alone would forget the colour and size of its text)
        annot.update(fontsize=a.font_size, fontname=a.font, text_color=rgb(a.border or a.color), fill_color=fill,
                     rotate=page.rotation)
        if a.kind == "freetext":  # (PyMuPDF gives every text box a callout line, of no length)
            page.parent.xref_set_key(annot.xref, "CL", "null")
    elif a.kind == "redact":  # (update() would write its /DA and /OverlayText as MuPDF has them)
        pass
    elif a.kind != "stamp" or a.stamp:  # (an image stamp's look would be lost)
        annot.update()
    if a.kind in DRAWN:
        _curved(page.parent, annot.xref)
    for reply in a.replies:
        add_reply(page, annot, reply, when)
    return annot


def _redact_keys(doc: pymupdf.Document, xref: int, a: Annotation) -> None:
    """What a redaction box is (see Annotation.overlay), in the keys of the PDF's redaction marks."""
    r, g, b = rgb(a.color)
    doc.xref_set_key(xref, "DA", pymupdf.get_pdf_str(f"/Helv {_r(a.font_size):g} Tf {r:g} {g:g} {b:g} rg"))
    doc.xref_set_key(xref, "Q", str({"left": 0, "right": 2}.get(a.align, 1)))
    doc.xref_set_key(xref, "IC", "[" + " ".join(f"{v:g}" for v in rgb(a.fill)) + "]" if a.fill else "null")
    doc.xref_set_key(xref, "OverlayText", pymupdf.get_pdf_str(a.overlay) if a.overlay else "null")
    doc.xref_set_key(xref, "Repeat", "true" if a.overlay_repeat else "null")
    doc.xref_set_key(xref, REPEAT_KEY, pymupdf.get_pdf_str(a.repeat) if a.repeat.strip() else "null")


def _line_ends(a: Annotation) -> tuple[str, str]:
    return a.ends if a.kind == "line" or a.ends != ("None", "None") else ("None", "OpenArrow")


def add_reply(page: pymupdf.Page, parent: pymupdf.Annot, reply: Reply, when: str) -> pymupdf.Annot:
    """REPLY to PARENT, written as a note that answers it (and gives a status, if it has one)."""
    doc = page.parent
    annot = page.add_text_annot(parent.rect.tl, reply.contents, icon="Comment")
    doc.xref_set_key(annot.xref, "IRT", f"{parent.xref} 0 R")
    if reply.state:
        doc.xref_set_key(annot.xref, "State", pymupdf.get_pdf_str(reply.state))
        doc.xref_set_key(annot.xref, "StateModel", "(Review)")
    annot.set_info(content=reply.contents, title=reply.author, creationDate=reply.created or when,
                   modDate=reply.modified or reply.created or when)
    annot.update()
    return annot


def same(a: Annotation, b: Annotation, tolerance: float = 1.0) -> bool:
    """Whether A and B are the same annotation, but for small differences of place (and their
    xrefs, dates and stamp images, which writing changes)."""
    def close(x, y) -> bool:
        return len(x) == len(y) and all(abs(u - v) <= tolerance for u, v in zip(x, y, strict=True))

    def flat(items) -> list[float]:
        return [v for item in items for p in item for v in (p if isinstance(p, tuple) else (p,))]

    ignore = {"xref", "created", "modified", "image", "rect", "quads", "paths", "replies", "width"}
    fields = [f.name for f in dataclasses.fields(Annotation) if f.name not in ignore]
    if any(getattr(a, f) != getattr(b, f) for f in fields if not (f == "color" and a.kind == "stamp")):
        return False
    if a.kind in STROKED and abs(a.width - b.width) > 0.01:
        return False
    if a.kind in MARKUP:
        return close(flat(a.quads), flat(b.quads))
    if a.paths and not close(flat(a.paths), flat(b.paths)):
        return False
    if a.kind == "stamp" and a.stamp:  # (MuPDF gives a standard stamp its own proportions, around its centre)
        return close(((a.rect[0] + a.rect[2]) / 2, (a.rect[1] + a.rect[3]) / 2),
                     ((b.rect[0] + b.rect[2]) / 2, (b.rect[1] + b.rect[3]) / 2))
    return a.kind in ("line", "arrow", "polyline", "polygon", "cloud", "ink", "marker") or close(a.rect, b.rect)


def change(page: pymupdf.Page, annot: pymupdf.Annot, old: Annotation, a: Annotation, when: str) -> bool:
    """Change ANNOT (which was OLD) where it is into A, keeping all else it has. Returns
    whether that could be done (False: it has to be taken out and written again)."""
    doc = page.parent
    if old.kind != a.kind or old.page != a.page or a.kind in ("callout", "attachment", "redact"):
        return False  # (an attached file: written again, with its file; a redaction box, with its keys)
    look = ("contents", "rich", "border", "color", "font", "font_size", "align")
    if (a.rich or a.border or old.rich or old.border) and any(getattr(a, f) != getattr(old, f) for f in look):
        return False  # (rich text whose text or look changed: written again, with its /RC and /DS)
    stroke = rgb(a.color)
    fill = rgb(a.fill) if a.fill else None
    dashes = list(DASHES) if a.dashed and a.kind in DASHABLE else []
    try:
        if a.kind == "stamp":
            if a.rect != old.rect:
                annot.set_rect(_real_rect(page, a.rect))
        elif a.kind in MARKUP:
            quads = [_real_rect(page, q).quad for q in (a.quads or (a.rect,))]
            doc.xref_set_key(annot.xref, "QuadPoints", "[" + " ".join(
                _pdf_points(page, [tuple(pt * page.rotation_matrix) for pt in (q.ul, q.ur, q.ll, q.lr)])
                for q in quads) + "]")
            doc.xref_set_key(annot.xref, "Rect", _pdf_rect(page, _real_rect(page, union(a.quads or (a.rect,)))))
        elif a.kind in ("line", "arrow"):
            doc.xref_set_key(annot.xref, "L", "[" + _pdf_points(page, [a.paths[0][0], a.paths[0][-1]]) + "]")
        elif a.kind in ("polygon", "cloud", "polyline"):
            doc.xref_set_key(annot.xref, "Vertices", "[" + _pdf_points(page, a.paths[0]) + "]")
        elif a.kind in DRAWN:
            doc.xref_set_key(annot.xref, "InkList", "[" + " ".join(
                "[" + _pdf_points(page, path) + "]" for path in a.paths) + "]")
        elif a.kind in ("note", "caret"):
            w, h = shown_size(page.rotation, (NOTE_SIZE, NOTE_SIZE) if a.kind == "note" else CARET_SIZE)
            x0, y0 = a.rect[0], a.rect[1]
            doc.xref_set_key(annot.xref, "Rect", _pdf_rect(page, _real_rect(page, (x0, y0, x0 + w, y0 + h))))
        else:  # (a rectangle, an ellipse, an area, a text box: the line is half outside)
            half = 0 if a.kind == "area" else a.width / 2
            r = _real_rect(page, a.rect)
            doc.xref_set_key(annot.xref, "Rect", _pdf_rect(page, pymupdf.Rect(r.x0 - half, r.y0 - half,
                                                                              r.x1 + half, r.y1 + half)))
        if a.kind == "freetext":
            doc.xref_set_key(annot.xref, "Q", str({"center": 1, "right": 2}.get(a.align, 0)))
            doc.xref_set_key(annot.xref, "Contents", pymupdf.get_pdf_str(a.contents))
            annot.set_border(width=a.width, dashes=dashes)
        elif a.kind in ("rect", "ellipse", "area", "polygon", "cloud", "polyline", "line", "arrow"):
            annot.set_border(width=0 if a.kind == "area" else a.width, dashes=dashes,
                             clouds=1 if a.kind == "cloud" else (0 if a.kind == "polygon" else -1))
            annot.set_colors(stroke=stroke, fill=(fill or []) if a.kind in FILLED else None)
        elif a.kind in DRAWN:
            annot.set_border(width=a.width)
            annot.set_colors(stroke=stroke)
        elif a.kind != "stamp":
            annot.set_colors(stroke=stroke)
        if a.kind in ("line", "arrow", "polyline"):
            ends = _line_ends(a) if a.kind != "polyline" else a.ends
            annot.set_line_ends(*(_END_CODES.get(e, 0) for e in ends))
        if a.kind == "note" and a.icon != old.icon:
            annot.set_name(a.icon)
        _info(annot, a, when)
        annot.set_opacity(a.opacity)
        _flags(annot, a.locked)
        _labels_keys(doc, annot.xref, a)
        if a.kind == "freetext" and (a.rich or a.border):
            _rich_keys(doc, annot.xref, a)
        if a.kind == "freetext":
            annot.update(fontsize=a.font_size, fontname=a.font, text_color=rgb(a.border or a.color),
                         fill_color=fill, rotate=page.rotation)
        elif a.kind != "stamp" or a.stamp:
            annot.update()
        if a.kind in DRAWN:
            _curved(doc, annot.xref)
    except (RuntimeError, ValueError):
        return False
    after = read_annotation(doc, page, page.load_annot(annot.xref))
    return after is not None and same(dataclasses.replace(a, replies=()), after)


def _sync_replies(page: pymupdf.Page, parent: pymupdf.Annot, old: tuple[Reply, ...], new: tuple[Reply, ...],
                  when: str) -> None:
    """Make the replies of PARENT, which were OLD, be NEW: those gone taken out, those changed
    changed, those new written."""
    doc = page.parent
    keep = {r.xref for r in new if r.xref}
    for r in old:
        if r.xref not in keep:
            _delete(page, r.xref)
    before = {r.xref: r for r in old}
    for r in new:
        if r.xref and r.xref in before:
            if before[r.xref] != r:
                annot = page.load_annot(r.xref)
                annot.set_info(content=r.contents, title=r.author, modDate=when)
                doc.xref_set_key(r.xref, "State", pymupdf.get_pdf_str(r.state) if r.state else "null")
                doc.xref_set_key(r.xref, "StateModel", "(Review)" if r.state else "null")
                annot.update()
        else:
            add_reply(page, parent, r, when)


def apply(doc: pymupdf.Document, annotations: list[Annotation], when: str | None = None,
          kept: set[int] | None = None, untouched: dict[int, Annotation] | None = None,
          original: list[Annotation] | None = None) -> int:
    """Make the annotations of DOC that read() gives be ANNOTATIONS.

    Those of DOC are compared with ANNOTATIONS by their xref: those that are
    there and the same are left as they are; those changed are changed where
    they are (or, if that can't be done, taken out and written again, with
    their replies); those deleted are taken out, with their replies; the new
    ones are written. KEPT, if given, gets the xrefs of those that are still
    there (as they were, or changed where they are); UNTOUCHED, {xref:
    annotation} of those left as they were. ORIGINAL: the annotations DOC has, if they are known
    (as read() gave them, the file not changed since): they are not read again. Returns how many
    annotations were written."""
    when = when or now()
    _unlink_groups(doc)
    original = {a.xref: a for a in (read(doc) if original is None else original) if a.kind != OTHER}
    annotations = [a for a in annotations if a.kind != OTHER]  # (those of other kinds are left as they are)
    model = {a.xref: a for a in annotations if a.xref and a.xref in original}
    written = 0
    redo: list[Annotation] = []
    for page in doc:
        for xref in [x for x in original if original[x].page == page.number]:
            old = original[xref]
            a = model.get(xref)
            if a == old:
                if kept is not None:
                    kept.add(xref)
                if untouched is not None:
                    untouched[xref] = old
                continue
            annot = page.load_annot(xref)
            if a is not None and change(page, annot, old, a, when):
                _sync_replies(page, page.load_annot(xref), old.replies, a.replies, when)
                written += 1
                if kept is not None:
                    kept.add(xref)
                continue
            for r in old.replies:  # (taken out, with its replies; written again below if it is still there)
                _delete(page, r.xref)
            _delete(page, xref)
            if a is not None:
                redo.append(dataclasses.replace(a, replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies)))
    for a in redo + [a for a in annotations if not (a.xref and a.xref in original)]:
        if not 0 <= a.page < doc.page_count:
            continue
        if a.kind == "stamp" and not a.stamp and not a.image:
            continue  # (an image stamp whose image is lost: nothing to write)
        add(doc[a.page], dataclasses.replace(a, replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies)),
            when)
        written += 1
    _link_groups(doc)
    return written


def save_doc(doc: pymupdf.Document, target: Path) -> None:
    """Save DOC as TARGET, safely (through a file of its own, put in its place at the end). If
    TARGET is the file DOC was opened from, DOC is closed first (Windows won't replace a file
    that is open)."""
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        doc.save(tmp, garbage=1, deflate=True,
                 encryption=pymupdf.PDF_ENCRYPT_KEEP if doc.needs_pass else pymupdf.PDF_ENCRYPT_NONE)
        if doc.name and Path(doc.name).resolve() == target.resolve():
            doc.close()
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write(source: Path, annotations: list[Annotation], target: Path, password: str = "",
          kept: set[int] | None = None, result: list[Annotation] | None = None,
          original: list[Annotation] | None = None, shown: dict[str, bool] | None = None,
          edit=None) -> int:
    """SOURCE with ANNOTATIONS (see apply), saved as TARGET; EDIT, if given, makes another change
    to the document (EDIT(doc), before it is saved: one that leaves its annotations as they are). Into SOURCE itself, the
    changes are added at its end (an incremental save: what was signed stays as it was
    signed), unless the file can't take that or has a password; else it is written whole
    (safely, through a file of its own). KEPT: see apply. RESULT, if given, gets the annotations as
    TARGET has them (as read() gives them: no need to read the file again). Returns how many
    annotations were written. ORIGINAL: see apply. SHOWN: the layers to show or hide (see set_layers)."""
    doc = open_pdf(source, password)
    try:
        same: dict[int, Annotation] = {}
        written = apply(doc, annotations, kept=kept, untouched=same, original=original)
        if shown:
            set_layers(doc, shown)
        if edit is not None:
            edit(doc)
        if result is not None:  # (saving keeps the numbers of the objects: garbage=1 doesn't renumber them)
            result[:] = read(doc, known=same)
        same_file = target.resolve() == source.resolve()
        # (not for a document with a password: PyMuPDF's incremental save of those has been seen to
        # leave this process unable to read them back now and then; they are written whole)
        if same_file and not doc.needs_pass and doc.can_save_incrementally():
            if written or doc.is_dirty:
                doc.save(str(source), incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        else:
            save_doc(doc, target)
    except (OSError, RuntimeError, ValueError) as e:
        raise AnnotateError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    finally:
        if not doc.is_closed:  # (save_doc closes it, to put the new file in its place)
            doc.close()
    return written


# --------------------------------------------------------------------- text

def words(page: pymupdf.Page) -> list[tuple[Rect, int, int]]:
    """The words of PAGE in reading order: (their rectangle as the page is
    shown, block number, line number)."""
    out = []
    for x0, y0, x1, y1, _text, block, line, _n in page.get_text("words", sort=False):
        r = (pymupdf.Rect(x0, y0, x1, y1) * page.rotation_matrix).normalize()
        out.append(((r.x0, r.y0, r.x1, r.y1), block, line))
    return out


def nearest_word(found: list[tuple[Rect, int, int]], x: float, y: float) -> int | None:
    """The index of the word at (X, Y), or else of the nearest one; None if there are none."""
    if not found:
        return None

    def distance(i):
        x0, y0, x1, y1 = found[i][0]
        dx = max(x0 - x, 0, x - x1)
        dy = max(y0 - y, 0, y - y1)
        return dx * dx + 4 * dy * dy  # (the line it is on matters more)

    return min(range(len(found)), key=distance)


def text_rects(found: list[tuple[Rect, int, int]], first: int, last: int) -> list[Rect]:
    """The rectangles that cover the words FIRST to LAST (in either order) of
    FOUND: one for each line."""
    if first > last:
        first, last = last, first
    lines: dict[tuple[int, int], list[float]] = {}
    for (x0, y0, x1, y1), block, line in found[first:last + 1]:
        r = lines.setdefault((block, line), [x0, y0, x1, y1])
        r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)
    return [(_r(x0), _r(y0), _r(x1), _r(y1)) for x0, y0, x1, y1 in lines.values()]


def page_text(page: pymupdf.Page) -> list[tuple[Rect, str]]:
    """The words of PAGE in reading order, each with its rectangle as the page is shown
    (read once, for text_in: much faster than reading the text under each mark)."""
    out = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words", sort=False):
        r = (pymupdf.Rect(x0, y0, x1, y1) * page.rotation_matrix).normalize()
        out.append(((r.x0, r.y0, r.x1, r.y1), text))
    return out


def text_in(found: list[tuple[Rect, str]], rects) -> str:
    """The words of FOUND (see page_text) whose middle is in one of RECTS, in reading order."""
    out = []
    for (x0, y0, x1, y1), text in found:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if any(r[0] - 1 <= cx <= r[2] + 1 and r[1] - 1 <= cy <= r[3] + 1 for r in rects):
            out.append(text)
    return " ".join(out)


def text_under(page: pymupdf.Page, rects: list[Rect]) -> str:
    """The text under RECTS (as the page is shown): the words whose middle is under one of them."""
    return text_in(page_text(page), rects)
