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
import math
import os
import re
import tempfile
from pathlib import Path

import pymupdf

from ..core import pdfdoc
from ..core.interface import N_, tr
from ..core.pdfdoc import nearest_word, normalized, rgb  # noqa: F401  (also annots.rgb ... for the others)
from ..core.replacing import replace

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
NAMES = {"highlight": N_("Highlight"), "underline": N_("Underline"), "strikeout": N_("Strikethrough"),
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
# A page this many times a Letter page, or more, in both directions is not paper as printed: a scan or a picture
# put in the PDF at 72 points to the pixel (a 300 dpi scan of an A4 page comes out over a metre wide). On such a
# page, new annotations are made larger in proportion (see page_scale), or a 12 point text could not be read.
LARGE_PAGE = 1.5


def page_scale(width: float, height: float) -> float:
    """How much larger than paper a page of WIDTH × HEIGHT points is (1 for paper as printed: Letter, A4, A3,
    tabloid...): the starting sizes of new annotations are multiplied by it."""
    short, long = sorted((abs(width), abs(height)))
    factor = min(short / 612, long / 792)  # (Letter)
    return round(factor, 2) if factor >= LARGE_PAGE else 1.0
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

# MuPDF's types and the kinds of py-pdftools. Several kinds share a type (arrow: line; area: square;
# cloud: polygon; marker: ink); kind_of tells them apart.
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
    # De una nota: el lugar y el tamaño de su ventana emergente (donde los lectores muestran su texto), si se le dio
    # uno (una nota hecha arrastrando un recuadro); None: el que MuPDF le da
    popup: Rect | None = None
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

def bounds(points: list[Point], pad: float = 0.0) -> Rect:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def union(rects) -> Rect:
    rects = list(rects)
    return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects),
            max(r[3] for r in rects))


def _r(value: float) -> float:
    # Dos decimales de punto quedan muy por debajo de lo que se distingue en pantalla o en papel.
    return round(value, 2)


def smooth_segments(points) -> list[tuple[Point, Point, Point]]:
    """The curve through POINTS (a stroke drawn by hand), as cubic Bézier segments, one from each point
    to the next: (first control point, second control point, end). Each point's tangent is the line
    between its neighbours (a Catmull–Rom spline), as PdfCraft draws ink (MIT/Apache-2.0)."""
    if not points:
        return []
    # En los extremos falta un vecino: el primer segmento usa su propio punto, y el último, el final.
    last = points[-1]

    def at(i: int) -> Point:
        return points[i] if 0 <= i < len(points) else last

    out = []
    for i in range(len(points) - 1):
        p0, p1, p2, p3 = at(max(i - 1, 0)), at(i), at(i + 1), at(i + 2)
        # Los puntos de control de Catmull-Rom (tensión 1/6) escritos como los de una Bézier cúbica.
        out.append(((p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6),
                    (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6), p2))
    return out


_AP_POINT = re.compile(r"^(-?[\d.]+) (-?[\d.]+) ([ml])$")


def _curved(doc: pymupdf.Document, xref: int) -> None:
    """Make the appearance of the drawing XREF (as MuPDF writes it: each stroke a point, 'm', and
    straight lines to the others, 'l') draw each stroke as a curve through its points."""
    # Only an appearance kept as an object of its own can be rewritten; any other is left as MuPDF drew it.
    kind, value = doc.xref_get_key(xref, "AP/N")
    if kind != "xref":
        return
    ap = int(value.split()[0])
    # latin-1 gives back the stream's bytes exactly as they were, whatever they hold.
    lines = doc.xref_stream(ap).decode("latin-1").split("\n")
    out: list[str] = []
    stroke: list[tuple[float, float]] = []

    def flush():
        # Con menos de tres puntos no hay curva que suavizar: se dejan las rectas.
        if len(stroke) >= 3:
            out.extend(f"{c1[0]:g} {c1[1]:g} {c2[0]:g} {c2[1]:g} {e[0]:g} {e[1]:g} c"
                       for c1, c2, e in smooth_segments(stroke))
        else:
            out.extend(f"{x:g} {y:g} l" for x, y in stroke[1:])
        stroke.clear()

    for line in lines:
        found = _AP_POINT.match(line.strip())
        # A point counts as part of a stroke only after its 'm': an 'l' with no stroke open is copied as it is.
        if found and (found[3] == "l" and stroke or found[3] == "m"):
            if found[3] == "m":
                flush()
                out.append(line.strip())
            stroke.append((float(found[1]), float(found[2])))
            continue
        flush()
        out.append(line)
    # El stream se reescribe solo si cambió algo, para no ensuciar el documento sin motivo.
    if any(line.endswith(" c") for line in out):
        doc.update_stream(ap, "\n".join(out).encode("latin-1"))


def frame(kind: str, paths, width: float) -> Rect:
    """The frame of a line, an arrow, a polygon or a drawing: around its points, with room for the line."""
    # Las flechas y las nubes dibujan fuera de sus puntos (la punta, las ondas): necesitan margen de más.
    pad = max(width, 2.0) + {"arrow": 4.0, "cloud": 6.0}.get(kind, 0.0)
    return tuple(_r(v) for v in bounds([p for path in paths for p in path], pad))


def fitted(a: Annotation, rect: Rect) -> Annotation:
    """A, moved and stretched so that its frame becomes RECT."""
    x0, y0, x1, y1 = a.rect
    n0, m0, n1, m1 = normalized(rect)
    # Un marco sin anchura o sin altura (una línea horizontal, por ejemplo) no se estira en esa dirección.
    sx = (n1 - n0) / (x1 - x0) if x1 - x0 > 1e-6 else 1.0
    sy = (m1 - m0) / (y1 - y0) if y1 - y0 > 1e-6 else 1.0

    def point(p: Point) -> Point:
        return _r(n0 + (p[0] - x0) * sx), _r(m0 + (p[1] - y0) * sy)

    def box(r: Rect) -> Rect:
        return point((r[0], r[1])) + point((r[2], r[3]))

    # A callout's point stays where it is when its box is resized; it moves only when the whole is moved.
    paths = a.paths if a.kind == "callout" and (sx, sy) != (1.0, 1.0) else \
        tuple(tuple(point(p) for p in path) for path in a.paths)
    return dataclasses.replace(a, rect=(_r(n0), _r(m0), _r(n1), _r(m1)), quads=tuple(box(q) for q in a.quads),
                               paths=paths)


def moved(a: Annotation, dx: float, dy: float) -> Annotation:
    x0, y0, x1, y1 = a.rect
    out = fitted(a, (x0 + dx, y0 + dy, x1 + dx, y1 + dy))
    if a.popup:  # (a note's pop-up window goes with it)
        px0, py0, px1, py1 = a.popup
        out = dataclasses.replace(out, popup=(_r(px0 + dx), _r(py0 + dy), _r(px1 + dx), _r(py1 + dy)))
    return out


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

def hex_color(values) -> str:
    """A colour of a PDF (grey, RGB or CMYK, from 0 to 1) as '#rrggbb'; '' for none."""
    values = [min(max(float(v), 0.0), 1.0) for v in values or []]
    # Grey is repeated in the three channels; CMYK is turned into RGB by the plain formula, without profiles.
    if len(values) == 1:
        values = values * 3
    elif len(values) == 4:
        c, m, y, k = values
        values = [(1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)]
    elif len(values) != 3:
        return ""
    return "#" + "".join(f"{round(v * 255):02x}" for v in values)


# Solo el año es obligatorio; los demás campos son opcionales, y la zona horaria se ignora.
PDF_DATE = re.compile(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?")


def now() -> str:
    """The time of now, as a PDF date."""
    return pymupdf.get_pdf_now()


def date_value(date: str) -> datetime.datetime | None:
    """A PDF date (D:20261119143000...) as a datetime (local, without its zone); None if it isn't one."""
    m = PDF_DATE.match(date.strip()) if date else None
    if not m:
        return None
    # The parts missing take their smallest values: month and day 1, hour, minute and second 0.
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
    return pdfdoc.open_pdf(path, password, AnnotateError, PasswordError)


def kind_of(doc: pymupdf.Document, annot: pymupdf.Annot) -> str | None:
    """The kind of ANNOT, if py-pdftools can edit it (None for the others, and for replies)."""
    kind = _TYPES.get(annot.type[0])
    # A note that answers another is a reply, not an annotation of its own, unless it is in its group
    # (/RT /Group).
    if kind is None or (doc.xref_get_key(annot.xref, "IRT")[0] != "null" and not _grouped(doc, annot.xref)):
        return None
    # Varios tipos del PDF se distinguen por otras claves: extremos en flecha, /IT, /Subj o un borde de nubes.
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
    # rotation_matrix lleva de la página sin girar a la página tal como se muestra.
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
    # transformation_matrix pasa del espacio del PDF (origen abajo a la izquierda) al de MuPDF (arriba a la
    # izquierda); su inversa hace lo contrario.
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


def _read_popup(doc: pymupdf.Document, page: pymupdf.Page, annot: pymupdf.Annot) -> Rect | None:
    """The place of the pop-up window of ANNOT (a note), as the page is shown; None if it has none."""
    # Su /Rect, leído tal cual y llevado como los demás rectángulos: popup_rect de PyMuPDF no tiene en cuenta el
    # giro de la página, y en una página girada la daba en otro lugar
    xref = annot.popup_xref if annot.has_popup else 0
    kind, value = doc.xref_get_key(xref, "Rect") if xref else ("null", "")
    try:
        numbers = [float(v) for v in value.strip("[]").split()] if kind == "array" else []
    except ValueError:
        numbers = []
    if len(numbers) != 4:
        return None
    where = (pymupdf.Rect(numbers) * page.transformation_matrix).normalize()
    return None if where.is_empty else _shown_rect(page, where)


def _write_popup(page: pymupdf.Page, annot: pymupdf.Annot, popup: Rect) -> None:
    """The pop-up window of ANNOT (a note) at POPUP (as the page is shown): see _read_popup."""
    if not annot.has_popup:
        annot.set_popup(_real_rect(page, popup))  # (made; its place is then written as the others are)
    page.parent.xref_set_key(annot.popup_xref, "Rect", _pdf_rect(page, _real_rect(page, popup)))


def _pdf_text(doc: pymupdf.Document, xref: int, key: str) -> str:
    kind, value = doc.xref_get_key(xref, key)
    return value if kind == "string" else ""


def _labels(text: str) -> tuple[str, ...]:
    """Tags or categories kept as 'a, b, c'."""
    return tuple(t for t in (" ".join(x.split()) for x in text.split(",")) if t)


def _off_edge(r: pymupdf.Rect, p: pymupdf.Point) -> float:
    """How far P is from the edge of R."""
    # Inside: the distance to the nearest side; outside: the straight distance to the rectangle.
    if r.contains(p):
        return min(p.x - r.x0, r.x1 - p.x, p.y - r.y0, r.y1 - p.y)
    dx = max(r.x0 - p.x, 0, p.x - r.x1)
    dy = max(r.y0 - p.y, 0, p.y - r.y1)
    return (dx * dx + dy * dy) ** 0.5


# Partes de un /DA ('0 0 1 rg /Helv 12 Tf'): el tamaño, la fuente y el color (gris, RGB o CMYK).
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
    # /RC lleva el XHTML dentro del encabezado que esperan los lectores de texto enriquecido (RC_HEAD).
    doc.xref_set_key(xref, "RC", pymupdf.get_pdf_str(RC_HEAD + (a.rich or plain_html(a.contents)) + "</body>"))
    doc.xref_set_key(xref, "DS", pymupdf.get_pdf_str(_rich_style(a)))
    doc.xref_set_key(xref, "DA", pymupdf.get_pdf_str(f"{r:g} {g:g} {b:g} rg /{a.font.capitalize()} "
                                                       f"{a.font_size:g} Tf"))
    doc.xref_set_key(xref, "Contents", pymupdf.get_pdf_str(a.contents))


# The usual head of a /RC: XHTML with the XFA attributes that the rich text of a PDF carries.
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
    # El color del texto: #rrggbb, o #rgb llevado a seis cifras; negro si /DS no da ninguno.
    text_color = DS_COLOR.search(ds or "")
    text_color = (text_color[1].lower() if len(text_color[1]) == 7 else
                  "#" + "".join(c * 2 for c in text_color[1][1:]).lower()) if text_color else "#000000"
    if (m := DS_SIZE.search(ds or "")):
        size = float(m[1]) or size
    if (m := DS_FAMILY.search(ds or "")):
        font = _DA_FONTS.get(m[1].split()[0].lower(), font) if m[1].split() else font
    rich = found[1].strip()
    # Si el XHTML no dice más que el texto plano, no se guarda como texto enriquecido.
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
        # Se dibuja a 3x, para que la imagen siga nítida al ampliar la página.
        pix = annot.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=True)
        # En una página girada, si la imagen sale apaisada al revés que la caja mostrada, se dibuja otra vez, girada.
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
    # Each standard stamp is drawn once, on a blank document in memory, and kept for the rest of the run.
    if name not in _STANDARD:
        doc = pymupdf.open()
        page = doc.new_page()
        # MuPDF knows the standard stamps by their index, in the order of STAMPS.
        annot = page.add_stamp_annot(pymupdf.Rect(0, 0, 160, 50), stamp=list(STAMPS).index(name))
        _STANDARD[name] = _stamp_image(annot), (_r(annot.rect.width), _r(annot.rect.height))
        doc.close()
    return _STANDARD[name]


def user_unit(page: pymupdf.Page) -> float:
    """The size in points of PAGE's unit (/UserUnit: 1 but on some pages of large format, which say "each unit is
    N points" instead of writing large numbers)."""
    kind, value = page.parent.xref_get_key(page.xref, "UserUnit")
    try:
        unit = float(value) if kind in ("int", "real") else 1.0
    except ValueError:
        return 1.0
    return unit if math.isfinite(unit) and unit > 0 else 1.0


def _in_units(page: pymupdf.Page, a: Annotation, back: bool = False) -> Annotation:
    """A with its font size and line width in PAGE's units, as the PDF keeps them (BACK: from them to points).
    MuPDF gives the places and sizes of a page with a /UserUnit in points, but writes and reads the size of a font
    and the width of a line as they are: in the page's units, 4 times larger on a page whose unit is 4 points."""
    unit = user_unit(page)
    if unit == 1:
        return a
    f = unit if back else 1 / unit
    return dataclasses.replace(a, font_size=round(a.font_size * f, 2), width=round(a.width * f, 3))


def read_annotation(doc: pymupdf.Document, page: pymupdf.Page, annot: pymupdf.Annot) -> Annotation | None:
    a = _read_annotation(doc, page, annot)
    # (el tamaño de la letra y el ancho de las líneas, en puntos, como los lugares: véase _in_units)
    return _in_units(page, a, back=True) if a is not None else None


def _read_annotation(doc: pymupdf.Document, page: pymupdf.Page, annot: pymupdf.Annot) -> Annotation | None:
    kind = kind_of(doc, annot)
    if kind is None:
        return None
    colors = annot.colors or {}
    stroke, fill = hex_color(colors.get("stroke")), hex_color(colors.get("fill"))
    border = annot.border or {}
    # A width of -1 or None means 'not given': 1 point is the PDF's default.
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
        # The vertices of text markup: four points for each line (a quad).
        quads = [_shown_rect(page, bounds(vertices[i:i + 4])) for i in range(0, len(vertices) - 3, 4)]
        if not quads:
            quads = [_shown_rect(page, annot.rect)]
        return Annotation(rect=union(quads), color=stroke or "#ffeb3b", quads=tuple(quads), **fields)
    if kind in TEXTUAL:
        color, size, font = _text_style(doc, annot.xref)
        rich, border, color, size, font = _rich_text(doc, annot.xref, fields["contents"], color, size, font)
        # /RD gives the room between /Rect and the box itself (the /Rect of a callout also holds its line).
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
            # Un callout sin puntos no tiene a dónde apuntar: se lee como un cuadro de texto.
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
        # Ink keeps one path for each stroke; a line, its two ends; a polygon or a polyline, one path of all its points.
        if kind in DRAWN:
            paths = tuple(tuple(_shown_point(page, p) for p in stroke_) for stroke_ in vertices if stroke_)
        elif kind in ("line", "arrow"):
            paths = (tuple(_shown_point(page, p) for p in vertices[:2]),)
        else:
            paths = (tuple(_shown_point(page, p) for p in vertices),)
        # Una línea con menos de dos puntos, o un dibujo sin trazos, no se puede editar: se deja fuera.
        if not paths or len(paths[0]) < (1 if kind in DRAWN else 2):
            return None
        return Annotation(rect=frame(kind, paths, width), color=stroke or "#000000", fill=fill, paths=paths,
                          ends=ends if kind in ENDED else ("None", "None"), **fields)
    if kind == "redact":
        # A redaction mark keeps the style of its overlay text in /DA, as a text box does.
        color, size, _ = _text_style(doc, annot.xref)
        kind_, da = doc.xref_get_key(annot.xref, "DA")
        if kind_ != "string" or not DA_SIZE.search(da) or not float(DA_SIZE.search(da)[1]):
            size = 0.0  # (as large as fits)
        # /IC es el color que deja la redacción; sin /IC, no deja ninguno.
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
        # /Name tells a standard stamp; the others (images, names of other programs) keep their look in IMAGE.
        name = doc.xref_get_key(annot.xref, "Name")[1].lstrip("/")
        return Annotation(rect=_shown_rect(page, annot.rect), color=stroke or "#000000",
                          stamp=name if name in STAMPS else "", image=_stamp_image(annot, page), **fields)
    if kind == "attachment":
        # Un archivo adjunto dañado no impide leer la anotación: queda sin datos.
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
    popup = _read_popup(doc, page, annot) if kind == "note" else None
    return Annotation(rect=_shown_rect(page, annot.rect), color=stroke or ("#ffd54f" if kind == "note" else "#1e88e5"),
                      icon=icon if icon in ICONS else "Note", popup=popup, **fields)


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
    # Una respuesta a otra respuesta va con la primera del hilo; SEEN evita un ciclo en un PDF dañado.
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
    targets = _Targets(doc)  # (where the links go: see _others)
    for page in doc:
        # A page without annotations is skipped before any object is loaded: most pages of a book have none.
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
                # Las respuestas de una anotación conocida ya están en ella: no se vuelven a leer.
                if roots[xref] not in known:
                    replies.setdefault(roots[xref], []).append(read_reply(doc, page.load_annot(xref)))
                continue
            if xref in known:
                found.append(known[xref])
                continue
            a = read_annotation(doc, page, page.load_annot(xref))
            if a is not None:
                found.append(a)
        # Las de otros tipos (enlaces, sonidos, adjuntos ajenos...) van al final de su página.
        found += _others(doc, page, items, targets)
        for a in found:
            if a.xref in replies and a.xref not in known:
                # Replies in the order they were made; the xref decides between equal or missing dates.
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
    # Vale tanto el JSON guardado en el PDF como el diccionario de un archivo exportado.
    try:
        values = json.loads(data) if isinstance(data, str) else data
    except ValueError:
        return None
    if not isinstance(values, dict) or not values.get("type"):
        return None
    names = {f.name for f in dataclasses.fields(Critical)}
    # Unknown keys are dropped, and every value is made a string.
    return Critical(**{k: str(v) for k, v in values.items() if k in names})


class _Targets:
    """Where the links of a document go, read from their own objects. (PyMuPDF's get_links says it too, but
    finds each link's object by listing the page's annotations again, for every link: on a page with a
    hundred links, ten thousand steps, and a book full of references took seconds to open.)"""

    def __init__(self, doc: pymupdf.Document):
        self.doc = doc
        self._pages: dict[int, int] | None = None  # (the object of each page -> its number)
        self._names: dict | None = None  # (the named destinations)

    def page_of(self, xref: int) -> int | None:
        """The number (0-based) of the page of the object XREF, if it is one."""
        if self._pages is None:
            self._pages = {self.doc.page_xref(n): n for n in range(self.doc.page_count)}
        return self._pages.get(xref)

    def named(self, name: str) -> int | None:
        """The page (0-based) of the named destination NAME."""
        if self._names is None:
            # Solo si un enlace usa un destino con nombre: resolverlos todos lleva su tiempo en un libro grande.
            try:
                self._names = self.doc.resolve_names() or {}
            except (RuntimeError, ValueError):
                self._names = {}
        page = self._names.get(name, {}).get("page")
        return page if isinstance(page, int) and page >= 0 else None

    def dest(self, kind: str, value: str) -> int | None:
        """The page (0-based) of a destination, as xref_get_key gives it (KIND, VALUE)."""
        if kind == "xref":  # (the destination is in another object: an array, or a dictionary with /D)
            target = int(value.split()[0])
            inner = self.doc.xref_get_key(target, "D")
            if inner[0] != "null":
                return self.dest(*inner)
            return self.dest("array", self.doc.xref_object(target, compressed=True))
        if kind == "array":  # [12 0 R /XYZ 72 720 0]
            words = value.strip("[] ").replace("/", " /").split()
            if len(words) >= 3 and words[2] == "R" and words[0].isdigit():
                return self.page_of(int(words[0]))
            return None
        if kind in ("string", "name"):
            return self.named(value.lstrip("/") if kind == "name" else value)
        return None

    def of(self, xref: int) -> str:
        """What the link XREF goes to, to show: its address, or its page ('' if neither)."""
        doc = self.doc
        action = doc.xref_get_key(xref, "A/S")[1]
        if action == "/URI":
            return doc.xref_get_key(xref, "A/URI")[1]
        if action == "/GoTo":
            page = self.dest(*doc.xref_get_key(xref, "A/D"))
        elif action == "null":  # (no action: the link has its destination itself, /Dest)
            page = self.dest(*doc.xref_get_key(xref, "Dest"))
        else:
            page = None  # (another file, a program, a named action...)
        return tr("Page {page}", page=page + 1) if page is not None else ""


def _others(doc: pymupdf.Document, page: pymupdf.Page, items: list | None = None,
            targets: _Targets | None = None) -> list[Annotation]:
    """The annotations of PAGE of other kinds (see OTHER), to be listed: what each one is, where. ITEMS: its
    annot_xrefs(), if read already; TARGETS: where the links of DOC go (see _Targets)."""
    out = []
    targets = targets or _Targets(doc)
    shown = None  # (from the PDF's space to the page as shown: the same for all the links of the page)
    for xref, kind, name in page.annot_xrefs() if items is None else items:
        if kind in _TYPES or kind in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET):
            continue
        try:
            if kind == pymupdf.PDF_ANNOT_LINK:
                if shown is None:
                    shown = page.transformation_matrix * page.rotation_matrix
                x0, y0, x1, y1 = (float(v) for v in doc.xref_get_key(xref, "Rect")[1].strip("[]").split())
                r = (pymupdf.Rect(x0, y0, x1, y1) * shown).normalize()
                out.append(Annotation(OTHER, page.number, (_r(r.x0), _r(r.y0), _r(r.x1), _r(r.y1)), "#808080",
                                      contents=targets.of(xref), locked=True, other="Link", xref=xref))
                continue
            other = doc.xref_get_key(xref, "Subtype")[1].lstrip("/")
            annot = page.load_annot(xref)
            info = annot.info or {}
            text = info.get("content", "") or ""
            if kind == pymupdf.PDF_ANNOT_FILE_ATTACHMENT:
                with_file = (annot.file_info or {}).get("filename", "")
                text = " — ".join(t for t in (with_file, text) if t)
            out.append(Annotation(OTHER, page.number, _shown_rect(page, annot.rect), "#808080", contents=text,
                                  author=info.get("title", "") or "", locked=True, other=other, xref=xref,
                                  created=info.get("creationDate", "") or "", modified=info.get("modDate", "") or ""))
        # A damaged annotation of another kind is left out of the list: it is not ours to repair.
        except (RuntimeError, ValueError, KeyError, TypeError):
            continue
    return out


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
    # /OC también puede apuntar a un /OCMD (una combinación de capas): solo se nombra una capa simple, /OCG.
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
    # The layer is made visible; set_layers can hide it afterwards.
    return doc.add_ocg(name, on=True)


def set_layers(doc: pymupdf.Document, shown: dict[str, bool]) -> None:
    """Show or hide the layers of DOC as SHOWN says ({name: shown}; those it doesn't name stay as they
    are), making those it has not."""
    for name in shown:
        layer_xref(doc, name)
    groups = doc.get_ocgs() or {}
    # El estado que debe tener cada capa: el que pide SHOWN, o el que ya tenía.
    state = {x: shown.get(info["name"], bool(info["on"])) for x, info in groups.items()}
    # set_layer(-1) cambia la configuración por omisión de las capas: solo se llama si algo cambia.
    if any(bool(groups[x]["on"]) != on for x, on in state.items()):
        doc.set_layer(-1, on=[x for x, on in state.items() if on], off=[x for x, on in state.items() if not on])


def _grouped(doc: pymupdf.Document, xref: int) -> bool:
    """Whether the annotation XREF is in the group of another (not a reply to it)."""
    return doc.xref_get_key(xref, "RT")[1] == "/Group"


def _irt(doc: pymupdf.Document, xref: int) -> int:
    # /IRT is an indirect reference ('12 0 R'): its object number is the first word.
    kind, value = doc.xref_get_key(xref, "IRT")
    return int(value.split()[0]) if kind == "xref" else 0


def _unlink_groups(doc: pymupdf.Document, pages: list[int] | None = None) -> None:
    """Take out the links of the groups (/IRT, /RT) of PAGES (all if None), keeping each group in
    GROUP_KEY (so that taking out the first of a group doesn't take the others with it, as MuPDF does
    with what answers it)."""
    for page in (doc if pages is None else (doc[n] for n in pages)):
        for xref, _, _ in page.annot_xrefs():
            if _grouped(doc, xref) and (first := _irt(doc, xref)):
                # Both the first and this one keep the name of the group, so that it survives while the links are out.
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
            # The first of a group found, in page order, is its head; the others are made to point at it.
            if group not in first:
                first[group] = xref
            elif _irt(doc, xref) != first[group]:
                doc.xref_set_key(xref, "IRT", f"{first[group]} 0 R")
                doc.xref_set_key(xref, "RT", "/Group")


def _delete(page: pymupdf.Page, xref: int) -> None:
    """Take out the annotation XREF of PAGE, if it is still there (PyMuPDF takes out the
    replies of an annotation with it)."""
    # Al borrar una anotación se van sus respuestas: la respuesta que se borra después puede no estar ya.
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
        # Lo mismo que _editable, pero sin cargar las anotaciones: solo con las claves de sus objetos.
        editable = {x for x, kind, _ in items
                    if kind in _TYPES and (not _irt(doc, x) or _grouped(doc, x))}
        gone = editable | {x for x, root in roots.items() if root in editable}
        # The pop-ups of those taken out go too: their parent would no longer be on the page.
        gone |= {x for x, kind, _ in items if kind == pymupdf.PDF_ANNOT_POPUP and _parent(doc, x) in gone}
        if gone:
            # Se reescribe la /Annots de la página con las que quedan; 'null' si no queda ninguna.
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
    # El rectángulo pedido, en la página sin girar; MuPDF hace la anotación a partir de su esquina.
    where = _real_rect(page, (x0, y0, x0 + w, y0 + h))
    annot = make(where.tl)
    shift = where.tl - annot.rect.tl
    if abs(shift.x) > 0.01 or abs(shift.y) > 0.01:  # (on a turned page, MuPDF puts it beside the point)
        page.delete_annot(annot)
        annot = make(where.tl + shift)
    return annot


def _flags(annot: pymupdf.Annot, locked: bool) -> None:
    # The print flag is always set: an annotation is printed as it is seen.
    flags = annot.flags | pymupdf.PDF_ANNOT_IS_PRINT
    flags = flags | pymupdf.PDF_ANNOT_IS_LOCKED if locked else flags & ~pymupdf.PDF_ANNOT_IS_LOCKED
    # El icono de una nota o de un adjunto: del mismo tamaño y derecho con cualquier zoom y giro, en los lectores
    # que siguen PDF (NoZoom, NoRotate), como en el lienzo de este programa
    if annot.type[0] in (pymupdf.PDF_ANNOT_TEXT, pymupdf.PDF_ANNOT_FILE_ATTACHMENT):
        flags |= pymupdf.PDF_ANNOT_IS_NO_ZOOM | pymupdf.PDF_ANNOT_IS_NO_ROTATE
    if flags != annot.flags:
        annot.set_flags(flags)


def _info(annot: pymupdf.Annot, a: Annotation, when: str) -> None:
    # A new annotation takes WHEN as its date of creation; a changed one keeps the date it had.
    info = {"content": a.contents, "title": a.author, "creationDate": a.created or when, "modDate": when}
    if a.kind in SUBJECTS:
        info["subject"] = SUBJECTS[a.kind]
    annot.set_info(**info)


def _labels_keys(doc: pymupdf.Document, xref: int, a: Annotation) -> None:
    # 'null' borra la clave: un valor vacío no deja rastro en el PDF.
    for key, values in ((TAGS_KEY, a.tags), (CATEGORIES_KEY, a.categories)):
        doc.xref_set_key(xref, key, pymupdf.get_pdf_str(", ".join(values)) if values else "null")
    doc.xref_set_key(xref, GROUP_KEY, pymupdf.get_pdf_str(a.group) if a.group else "null")
    if a.kind in ("caret", "strikeout", "freetext"):
        # Only a plain PDF name is written; anything else would make an /IT that isn't valid.
        doc.xref_set_key(xref, "IT", f"/{a.intent}" if re.fullmatch(r"[A-Za-z]+", a.intent) else "null")
    if a.layer != _layer_of(doc, xref):
        doc.xref_set_key(xref, "OC", f"{layer_xref(doc, a.layer)} 0 R" if a.layer else "null")
    # The entry of textual criticism is kept as JSON, with only the fields that have a value.
    entry = json.dumps({k: v for k, v in dataclasses.asdict(a.critical).items() if v}, ensure_ascii=False) \
        if a.critical else ""
    doc.xref_set_key(xref, CRITICAL_KEY, pymupdf.get_pdf_str(entry) if entry else "null")


def add(page: pymupdf.Page, a: Annotation, when: str | None = None) -> pymupdf.Annot:
    """Write A on PAGE, as a new annotation, made (if A has no date) and changed WHEN (a PDF
    date; now), with its replies."""
    when = when or now()
    a = _in_units(page, a)
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
        # Un callout: el punto al que apunta, y el punto del borde de la caja de donde sale la línea.
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
        # An area highlight is a rectangle without border, told apart by its /Subj (see _info).
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
        # clouds=-1 quita el borde de nubes; 1 lo pone, con la intensidad usual.
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
        if a.popup:  # (its pop-up window where the box was dragged, not MuPDF's above the icon)
            _write_popup(page, annot, a.popup)
    elif a.kind == "attachment":
        annot = _placed(page, lambda p: page.add_file_annot(p, a.data, a.filename or "file",
                                                            icon=a.icon if a.icon in ATTACH_ICONS else "Paperclip"),
                        a.rect, (NOTE_SIZE, NOTE_SIZE))
        annot.set_colors(stroke=stroke)
    elif a.kind == "caret":
        annot = _placed(page, page.add_caret_annot, a.rect, CARET_SIZE)
        annot.set_colors(stroke=stroke)
    elif a.kind == "stamp":
        # A standard stamp goes by its index; an image stamp is drawn from its PNG.
        stamps = list(STAMPS)
        annot = page.add_stamp_annot(_real_rect(page, a.rect),
                                     stamp=stamps.index(a.stamp) if a.stamp in stamps else a.image)
    elif a.kind == "redact":
        # cross_out=False: sin la cruz que MuPDF dibuja sobre la marca de redacción.
        annot = page.add_redact_annot(_real_rect(page, a.rect), fill=fill if fill else False, cross_out=False)
        _redact_keys(page.parent, annot.xref, a)
    else:
        raise ValueError(a.kind)
    # Lo común a todos los tipos: la información, la opacidad, las banderas y las claves propias.
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
    # MuPDF draws each stroke with straight segments; they are made curves afterwards, in the appearance stream.
    if a.kind in DRAWN:
        _curved(page.parent, annot.xref)
    # Las respuestas van después de la anotación, para que su /IRT pueda nombrar su xref.
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

    # Campos que cambian solos al escribir, o que se comparan aparte, con tolerancia.
    ignore = {"xref", "created", "modified", "image", "rect", "quads", "paths", "replies", "width", "popup"}
    fields = [f.name for f in dataclasses.fields(Annotation) if f.name not in ignore]
    # The colour of a stamp is not compared: MuPDF draws the standard stamps in colours of their own.
    if any(getattr(a, f) != getattr(b, f) for f in fields if not (f == "color" and a.kind == "stamp")):
        return False
    if a.kind in STROKED and abs(a.width - b.width) > 0.01:
        return False
    # (a note's pop-up, only if both have one: without one, MuPDF gives it its own when it is written)
    if a.popup and b.popup and not close(a.popup, b.popup):
        return False
    if a.kind in MARKUP:
        return close(flat(a.quads), flat(b.quads))
    # For the shapes made of points, the points decide: their frame follows from them.
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
    old, a = _in_units(page, old), _in_units(page, a)
    if old.kind != a.kind or old.page != a.page or a.kind in ("callout", "attachment", "redact"):
        return False  # (an attached file: written again, with its file; a redaction box, with its keys)
    look = ("contents", "rich", "border", "color", "font", "font_size", "align")
    if (a.rich or a.border or old.rich or old.border) and any(getattr(a, f) != getattr(old, f) for f in look):
        return False  # (rich text whose text or look changed: written again, with its /RC and /DS)
    # Desde aquí, la anotación se cambia clave por clave en su sitio, y quedan las claves de otros programas.
    stroke = rgb(a.color)
    fill = rgb(a.fill) if a.fill else None
    dashes = list(DASHES) if a.dashed and a.kind in DASHABLE else []
    try:
        # Un sello solo se mueve o cambia de tamaño; su aspecto no se toca.
        if a.kind == "stamp":
            if a.rect != old.rect:
                annot.set_rect(_real_rect(page, a.rect))
        elif a.kind in MARKUP:
            quads = [_real_rect(page, q).quad for q in (a.quads or (a.rect,))]
            # /QuadPoints wants the corners in the order ul, ur, ll, lr, in the PDF's space.
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
            # A note and a caret keep MuPDF's fixed size: only their top left corner moves.
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
            # En las formas con relleno, [] lo quita; las líneas no tienen relleno que tocar (None).
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
        if a.kind == "note" and a.popup and a.popup != old.popup:
            _write_popup(page, annot, a.popup)
        # Después de la geometría, lo común, como en add: la información, la opacidad, las banderas y las claves.
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
    # El cambio se comprueba leyendo otra vez la anotación: si no es A, apply la borra y la escribe de nuevo.
    after = _read_annotation(doc, page, page.load_annot(annot.xref))  # (in the page's units, as A is here)
    return after is not None and same(dataclasses.replace(a, replies=()), after)


def _sync_replies(page: pymupdf.Page, parent: pymupdf.Annot, old: tuple[Reply, ...], new: tuple[Reply, ...],
                  when: str) -> None:
    """Make the replies of PARENT, which were OLD, be NEW: those gone taken out, those changed
    changed, those new written."""
    doc = page.parent
    # Replies without an xref are new; those whose xref is not in NEW were deleted.
    keep = {r.xref for r in new if r.xref}
    for r in old:
        if r.xref not in keep:
            _delete(page, r.xref)
    before = {r.xref: r for r in old}
    for r in new:
        if r.xref and r.xref in before:
            # Una respuesta igual a la de antes no se toca, para no cambiar su fecha de modificación.
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
    # Groups are unlinked first: else, deleting the first of a group would take the others with it.
    _unlink_groups(doc)
    original = {a.xref: a for a in (read(doc) if original is None else original) if a.kind != OTHER}
    annotations = [a for a in annotations if a.kind != OTHER]  # (those of other kinds are left as they are)
    # MODEL: the annotations of the list that the document already has, by their xref.
    model = {a.xref: a for a in annotations if a.xref and a.xref in original}
    written = 0
    redo: list[Annotation] = []
    for page in doc:
        # TODO: every original annotation is looked at once for each page (pages x annotations); grouping
        # them by page beforehand would make long documents with many annotations faster.
        for xref in [x for x in original if original[x].page == page.number]:
            old = original[xref]
            a = model.get(xref)
            if a == old:
                if kept is not None:
                    kept.add(xref)
                if untouched is not None:
                    untouched[xref] = old
                continue
            # Changed or deleted (a is None): first it is tried in place, keeping what other programs put in it.
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
    # Lo que no se pudo cambiar en su sitio, y lo nuevo, se escribe al final como anotaciones nuevas.
    for a in redo + [a for a in annotations if not (a.xref and a.xref in original)]:
        # Una anotación de una página que ya no existe (tras borrar páginas) se descarta sin error.
        if not 0 <= a.page < doc.page_count:
            continue
        if a.kind == "stamp" and not a.stamp and not a.image:
            continue  # (an image stamp whose image is lost: nothing to write)
        add(doc[a.page], dataclasses.replace(a, replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies)),
            when)
        written += 1
    # Los grupos se enlazan otra vez al final, ya con los xref definitivos.
    _link_groups(doc)
    return written


def save_doc(doc: pymupdf.Document, target: Path) -> None:
    """Save DOC as TARGET, safely (through a file of its own, put in its place at the end). If
    TARGET is the file DOC was opened from, DOC is closed first (Windows won't replace a file
    that is open)."""
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        # garbage=1 takes out the objects no longer used without renumbering the others.
        doc.save(tmp, garbage=1, deflate=True,
                 encryption=pdfdoc.kept_encryption(doc))
        if doc.name and Path(doc.name).resolve() == target.resolve():
            doc.close()
        replace(tmp, target)
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
        # SAME: lo que apply dejó como estaba, para no leer otra vez esas anotaciones en RESULT.
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
            # Nothing changed: the file is not touched at all, not even its modification time.
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
    # Las cajas se pasan a la página tal como se muestra, como todo lo que dibuja la ventana.
    for x0, y0, x1, y1, _text, block, line, _n in page.get_text("words", sort=False):
        r = (pymupdf.Rect(x0, y0, x1, y1) * page.rotation_matrix).normalize()
        out.append(((r.x0, r.y0, r.x1, r.y1), block, line))
    return out


def text_rects(found: list[tuple[Rect, int, int]], first: int, last: int) -> list[Rect]:
    """The rectangles that cover the words FIRST to LAST (in either order) of
    FOUND: one for each line."""
    return pdfdoc.text_rects(found, first, last)


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
        # Una palabra cuenta si su centro cae dentro, con un punto de tolerancia: así no entran las vecinas.
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if any(r[0] - 1 <= cx <= r[2] + 1 and r[1] - 1 <= cy <= r[3] + 1 for r in rects):
            out.append(text)
    return " ".join(out)


def text_under(page: pymupdf.Page, rects: list[Rect]) -> str:
    """The text under RECTS (as the page is shown): the words whose middle is under one of them."""
    return text_in(page_text(page), rects)
