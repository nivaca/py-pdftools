"""Text that only seems redacted: text still in the file, under something drawn over it (a black or white
rectangle, a picture, an annotation), so that it can't be seen but can be selected, copied or found. Many
documents are "redacted" so, by drawing boxes over the text, and give away what they hide to anyone who
copies it. find() says where; a redaction box over each place, once applied, takes the text out.

What is drawn is followed in its order: a rectangle drawn after a text, and over it, covers it; one drawn
before it is a background. Only what hides the text counts: opaque rectangles, black or white (or nearly: one of
a colour is likely a highlight, through which the text shows), pictures, and annotations that hide what is
under them (filled rectangles and shapes, stamps, dark highlights).
Text that is not drawn at all (an OCR layer, say) is hidden text of another kind: see hidden.py."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pymupdf

from ..core.interface import N_

OPAQUE = 0.9  # (un relleno al menos así de opaco esconde lo que tiene debajo)
DARK = 0.25  # (así de oscuro, o más, esconde el texto negro aun multiplicado encima, como los resaltados)
LIGHT = 0.95  # (a fill this light, or lighter, hides text as white does)
TEXT_LIMIT = 300  # (caracteres del texto encontrado, como mucho, en cada lugar)

KIND_NAMES = {"shape": N_("A filled shape"), "image": N_("A picture"), "annotation": N_("An annotation")}


@dataclasses.dataclass(frozen=True)
class Covered:
    page: int  # (desde 0)
    rect: tuple[float, float, float, float]  # the text covered, as the page is shown (a box over it takes it out)
    kind: str  # lo que lo cubre: 'shape', 'image' o 'annotation' (KIND_NAMES)
    text: str  # the text under it


def _rect_like(drawing: dict) -> bool:
    """Whether DRAWING is a rectangle (or several), not the outline of a letter or of a drawing."""
    items = drawing.get("items") or []
    if items and all(it[0] in ("re", "qu") for it in items):
        return True
    if not items or any(it[0] != "l" for it in items):
        return False
    r = drawing["rect"]
    points = [p for it in items for p in it[1:3]]
    return all((abs(p.x - r.x0) < 0.5 or abs(p.x - r.x1) < 0.5) and (abs(p.y - r.y0) < 0.5 or abs(p.y - r.y1) < 0.5)
               for p in points)


def _luminance(color) -> float:
    if not color:
        return 1.0
    if len(color) == 1:
        return color[0]
    if len(color) == 4:  # (CMYK)
        c, m, y, k = color
        color = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    r, g, b = color[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _annotation_covers(annot: pymupdf.Annot) -> bool:
    kind = annot.type[0]
    opacity = annot.opacity
    if 0 <= opacity < OPAQUE:
        return False
    colors = annot.colors or {}
    if kind in (pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_POLYGON,
                pymupdf.PDF_ANNOT_FREE_TEXT):
        return bool(colors.get("fill"))
    if kind == pymupdf.PDF_ANNOT_STAMP:
        return True
    if kind == pymupdf.PDF_ANNOT_HIGHLIGHT:
        return _luminance(colors.get("stroke")) <= DARK
    return False


def _covers(page: pymupdf.Page) -> list[tuple[int, str, pymupdf.Rect]]:
    """What hides what is drawn before it on PAGE: (its place in the order of drawing, kind, rectangle), in
    that order. Annotations are drawn with the page, after its content: what is drawn in an annotation's
    rectangle is that annotation, and counts only if the annotation hides what is under it."""
    # (el rectángulo de una anotación está en el espacio propio de la página, como lo dibujado, aunque esté girada)
    annots = [(pymupdf.Rect(a.rect) + (-1, -1, 1, 1), _annotation_covers(a))
              for a in page.annots() or [] if a.type[0] not in (pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_WIDGET)]

    def owner(rect: pymupdf.Rect):
        return next((hides for r, hides in annots if r.contains(rect)), None)

    found = []
    for d in page.get_drawings():
        if d.get("fill") is None or d.get("type") not in ("f", "fs"):
            continue
        if (d.get("fill_opacity") if d.get("fill_opacity") is not None else 1) < OPAQUE:
            continue
        rect = pymupdf.Rect(d["rect"])
        hides = owner(rect)
        if hides is None:
            if not _rect_like(d):
                continue
            # Un relleno de color (ni oscuro ni blanco) es seguramente un resaltado, multiplicado sobre el
            # texto, que se ve a través: las censuras falsas son negras o blancas (o casi).
            if DARK < _luminance(d["fill"]) < LIGHT:
                continue
            found.append((d["seqno"], "shape", rect))
        elif hides:
            found.append((d["seqno"], "annotation", rect))
    for seqno, (kind, bbox) in enumerate(page.get_bboxlog()):
        if kind == "fill-image":
            rect = pymupdf.Rect(bbox)
            hides = owner(rect)
            if hides is None or hides:
                found.append((seqno, "image" if hides is None else "annotation", rect))
    found.sort(key=lambda c: c[0])
    return [c for c in found if not c[2].is_empty]


def find_on_page(page: pymupdf.Page, number: int) -> list[Covered]:
    """The places of PAGE (NUMBER) where text is drawn over and hidden."""
    covers = _covers(page)
    if not covers:
        return []
    spans = [t for t in page.get_texttrace() if t.get("type") != 3 and t.get("opacity", 1) > 0]
    taken: set[tuple[int, int]] = set()  # (tramo, carácter) ya encontrados bajo algo
    out = []
    for seqno, kind, rect in covers:
        chars, box = [], pymupdf.Rect()
        for s, span in enumerate(spans):
            if span["seqno"] >= seqno or not pymupdf.Rect(span["bbox"]).intersects(rect):
                continue
            words = []
            for c, char in enumerate(span["chars"]):
                b = pymupdf.Rect(char[3])
                centre = pymupdf.Point((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)
                if (s, c) in taken or not rect.contains(centre):
                    continue
                taken.add((s, c))
                words.append(chr(char[0]))
                if chr(char[0]).strip():
                    box |= b
            chars.append("".join(words).strip())
        text = " ".join(t for t in chars if t)
        if not text:
            continue
        shown = (box + (-1, -1, 1, 1)) * page.rotation_matrix
        shown.normalize()
        shown &= page.rect
        out.append(Covered(number, tuple(round(v, 2) for v in shown), kind,
                           text if len(text) <= TEXT_LIMIT else text[:TEXT_LIMIT - 1] + "…"))
    return out


def find(source: Path | pymupdf.Document, password: str = "", pages: list[int] | None = None) -> list[Covered]:
    """The places of the document (a file, with its PASSWORD; or one open) where text is hidden under
    something drawn over it (see the module's text), on PAGES (0-based; all if None)."""
    if isinstance(source, pymupdf.Document):
        doc, own = source, False
    else:
        from .redact import open_pdf

        doc, own = open_pdf(source, password), True
    try:
        out = []
        for n in range(doc.page_count) if pages is None else pages:
            out += find_on_page(doc[n], n)
        return out
    finally:
        if own:
            doc.close()
