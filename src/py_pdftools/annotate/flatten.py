"""Anotaciones aplanadas: hechas parte del contenido de sus páginas, de modo
que se ven y se imprimen en cualquier programa, pero ya no se editan.

Se aplanan todas o solo algunas (las elegidas); las demás siguen siendo
anotaciones, exactamente como estaban (con las claves de otros programas: se
copian sus objetos antes y se devuelven después, como en sidecar.py). Con
``comments``, el comentario de cada anotación aplanada (el texto de una nota,
el de un resaltado o de una forma, y sus respuestas) se escribe también en la
página, en un recuadro pequeño a su lado: aplanado, ese texto se perdería,
pues solo queda dibujado su icono o su marca. Los cuadros de texto y las
llamadas no lo necesitan: su texto ya está en la página.

Se aplana en el documento mismo (un cambio del documento, véase
gui/working.py) o en una copia.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pymupdf

from . import annots, sidecar
from .annots import OTHER, TEXTUAL, AnnotateError, Annotation
from ..core.interface import tr

BOX_WIDTH = 170.0  # points: the width of the box of a comment written on the page
FONT_SIZE = 8.0
GAP = 6.0  # points between the annotation and the box of its comment
BOX_FILL = "#fff9c4"
BOX_BORDER = "#9e9e9e"


def comment_text(a: Annotation) -> str:
    """What the box of A's comment says: its comment (or the text of a note), then its replies, each with its
    author."""
    parts = [a.contents.strip()] if a.contents.strip() else []
    for r in a.replies:
        if r.contents.strip():
            parts.append(f"{r.author}: {r.contents.strip()}" if r.author else r.contents.strip())
    return "\n".join(parts)


def _lines(text: str, width: float) -> int:
    """How many lines TEXT takes in Helvetica of FONT_SIZE, in WIDTH points."""
    count = 0
    for paragraph in text.split("\n"):
        line, n = "", 1
        for word in paragraph.split():
            trial = f"{line} {word}".strip()
            if line and pymupdf.get_text_length(trial, fontname="helv", fontsize=FONT_SIZE) > width:
                n += 1
                line = word
            else:
                line = trial
        count += n
    return count


MIN_WIDTH = 80.0  # points: a margin narrower than this takes no box (it goes beside its annotation)


def text_area(page: pymupdf.Page) -> pymupdf.Rect | None:
    """The part of PAGE (as it is shown) that its text takes; None if it has none."""
    area = None
    for block in page.get_text("blocks"):
        if block[6] != 0:  # (only text: not pictures)
            continue
        r = pymupdf.Rect(block[:4]) * page.rotation_matrix  # (as the page is shown)
        r.normalize()
        area = r if area is None else area | r
    return area


def comment_box(page: pymupdf.Page, a: Annotation, placed: list | None = None,
                area: pymupdf.Rect | None = ...) -> Annotation | None:
    """A box with A's comment on PAGE (as the page is shown), level with A: in the margin beside the text, the
    right one first, so as not to cover the text; if both margins are too narrow, under A. PLACED: the boxes
    already on the page, which it doesn't overlap (it goes down). None if A has no comment, or shows its text
    itself (a text box, a callout)."""
    text = comment_text(a)
    if not text or a.kind in TEXTUAL:
        return None
    if area is ...:
        area = text_area(page)
    w, h = page.rect.width, page.rect.height  # (the page as it is shown: turned, if it is)
    x0, y0, x1, y1 = a.rect
    right_from = max(area.x1 if area else 0.0, x1) + GAP
    left_to = min(area.x0 if area else w, x0) - GAP
    if w - GAP - right_from >= MIN_WIDTH:  # (the right margin)
        width = min(BOX_WIDTH, w - GAP - right_from)
        left = right_from
    elif left_to - GAP >= MIN_WIDTH:  # (the left margin)
        width = min(BOX_WIDTH, left_to - GAP)
        left = left_to - width
    else:  # (no margin wide enough: under it, its right edges together, inside the page)
        width = min(BOX_WIDTH, w - 2 * GAP)
        left = max(GAP, min(x1 - width, w - GAP - width))
    pad = 3.0
    height = _lines(text, width - 2 * pad - 2) * FONT_SIZE * 1.25 + 2 * pad + 2
    under = not (w - GAP - right_from >= MIN_WIDTH or left_to - GAP >= MIN_WIDTH)
    top = max(0.0, min(y1 + GAP if under else y0, h - height))
    # Las cajas de una misma columna no se tapan entre sí: cada una baja hasta debajo de la anterior.
    for other in sorted(placed or [], key=lambda r: r[1]):
        if other[0] < left + width and left < other[2] and other[1] < top + height and top < other[3]:
            top = other[3] + 2
    top = max(0.0, min(top, h - height))
    box = (left, top, left + width, top + height)
    if placed is not None:
        placed.append(box)
    return Annotation("freetext", a.page, box, "#000000", fill=BOX_FILL, border=BOX_BORDER, width=0.5,
                      contents=text, font_size=FONT_SIZE, font="helv")


def flatten(source: Path, annotations: list[Annotation], chosen: list[int], target: Path, password: str = "",
            comments: bool = False) -> int:
    """SOURCE with ANNOTATIONS (as the window has them), the ones at the indices CHOSEN made part of the pages
    (with their comments beside them, if COMMENTS), written as TARGET; the others stay annotations, exactly as
    they were. Returns how many were flattened (raises AnnotateError)."""
    keep_idx = set(range(len(annotations))) - set(chosen)
    flat = [annotations[i] for i in sorted(chosen) if annotations[i].kind != OTHER]
    others = [annotations[i] for i in sorted(keep_idx) if annotations[i].kind != OTHER]
    doc = annots.open_pdf(source, password)
    try:
        # 1. Solo las que se quedan; se copian sus objetos, exactos, para devolverlos después del aplanado.
        annots.apply(doc, others)
        staying = [a for a in annots.read(doc) if a.kind != OTHER]
        raws = {}
        back = []
        for a in staying:
            raw = sidecar.capture(doc, a)
            raws[raw.id] = raw
            back.append(dataclasses.replace(a, xref=0, origin=raw.id,
                                            replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies)))
        # 2. Solo las que se aplanan (y los recuadros de sus comentarios), hechas contenido de la página.
        boxes = []
        if comments:
            placed: dict[int, list] = {}
            areas: dict[int, pymupdf.Rect | None] = {}
            for a in sorted(flat, key=lambda a: (a.page, a.rect[1])):
                if not 0 <= a.page < doc.page_count:
                    continue
                if a.page not in areas:
                    areas[a.page] = text_area(doc[a.page])
                box = comment_box(doc[a.page], a, placed.setdefault(a.page, []), areas[a.page])
                if box is not None:
                    boxes.append(box)
        # Sin sus respuestas: aplanadas serían iconos de nota; su texto está en el recuadro del comentario.
        fresh = [dataclasses.replace(a, xref=0, replies=()) for a in flat] + boxes
        annots.apply(doc, fresh)
        doc.bake(annots=True, widgets=False)
        # 3. Las demás, de vuelta tal como eran.
        restored = sidecar.restore(doc, raws, back)
        annots.apply(doc, restored)
        annots.save_doc(doc, target)
    except (OSError, RuntimeError, ValueError) as e:
        raise AnnotateError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    finally:
        if not doc.is_closed:
            doc.close()
    return len(flat)
