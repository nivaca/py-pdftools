"""What headers, footers and watermarks share: drawing text in the standard PDF
fonts, the variables of their text, the pages they go on, and the records that
let them be taken away again.

Each addition to a page is a *layer*: content streams added before and after
the original content (and, for what goes behind it, one stream before all),
with, if it shrank the page, the links and other annotations it moved. A page
keeps the record of its layers, in the order they were added, in its
dictionary (KEY); each record has the kind of the layer (HeaderFooter or
Watermark), the id of the addition it belongs to (the same on every page it
went on), its settings, as JSON (so that it can be updated), and whether it
writes Bates numbers. Any layer can be taken away, the last one or another:
the content streams of the others are balanced pairs, and the annotations are
put where the layers that are left would have them.

Version 0.7 kept one record, without kind, id or settings, under LEGACY; it is
read as a header and footer layer of addition 0.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, Pdf

from .fontmetrics import FONTS
from ..core.interface import N_, tr
# (the matrices; stamps.multiply, invert and transform for the others)
from ..core.matrix import IDENTITY, Matrix, invert, multiply  # noqa: F401
from ..core.matrix import apply as transform  # noqa: F401
from .labels import LabelError, page_labels, parse_pages, read_labels

KEY = "/PyFoliationStamps"  # the records of the layers of a page (an array, in the order they were added)
LEGACY = "/PyFoliationHeaderFooter"  # (0.7: the one record of a header and footer)
HEADER_FOOTER, WATERMARK = "HeaderFooter", "Watermark"  # the kinds of layers
POINTS = {"in": 72.0, "cm": 72 / 2.54, "pt": 1.0}  # points in each unit
UNIT_TITLES = {"in": N_("inches"), "cm": N_("centimeters"), "pt": N_("points")}
FAMILIES = {"helvetica": "Helvetica", "times": "Times", "courier": "Courier"}
FAMILY_TITLES = {"helvetica": "Helvetica", "times": "Times", "courier": "Courier"}
PARITIES = {"all": N_("All pages"), "even": N_("Even pages only"), "odd": N_("Odd pages only")}

# $name -> what it writes (for the help of the window and the command line)
VARIABLES = {
    "page": N_("the page number (of the file, from 1)"),
    "pagelabel": N_("the label of the page"),
    "bookmark": N_("the bookmark the page is under"),
    "totalpages": N_("the number of pages of the document"),
    "author": N_("the author of the document (as its properties give it)"),
    "filename": N_("the name of the file"),
    "filepath": N_("the full path of the file"),
    "date": N_("today's date, in the date format chosen"),
    "shortdate": N_("today's date, as 11/28/07"),
    "time": N_("the time, as 3:05 PM"),
    "day": N_("the day of the month"),
    "month": N_("the month, in two digits"),
    "year": N_("the year, in four digits"),
    "shortyear": N_("the year, in two digits"),
    "hour": N_("the hour, from 1 to 12"),
    "longhour": N_("the hour, from 0 to 23"),
    "minute": N_("the minute"),
    "second": N_("the second"),
    "ampm": N_("AM or PM"),
    "bates": N_("the Bates number: the prefix, the number and the suffix (see Bates numbering)"),
}
MONTHS = (N_("Jan"), N_("Feb"), N_("Mar"), N_("Apr"), N_("May"), N_("Jun"), N_("Jul"), N_("Aug"), N_("Sep"),
          N_("Oct"), N_("Nov"), N_("Dec"))
LONG_MONTHS = (N_("January"), N_("February"), N_("March"), N_("April"), N_("May (month)"), N_("June"),
               N_("July"), N_("August"), N_("September"), N_("October"), N_("November"), N_("December"))
# the formats of $date: code -> how it is shown in the window (with an example: November 28, 2007)
DATE_FORMATS = {
    "medium": N_("Nov 28, 2007"),
    "long": N_("November 28, 2007"),
    "m/d/yy": "11/28/07",
    "m/d/yyyy": "11/28/2007",
    "mm/dd/yyyy": "11/28/2007 (mm/dd)",
    "d/m/yy": "28/11/07",
    "d/m/yyyy": "28/11/2007",
    "dd/mm/yyyy": "28/11/2007 (dd/mm)",
    "dd.mm.yyyy": "28.11.2007",
    "yyyy-mm-dd": "2007-11-28",
}
# Los nombres más largos primero, para que $pagelabel no se lea como $page seguido de 'label'.
_VARIABLE = re.compile(r"\$\$|\$(" + "|".join(sorted(VARIABLES, key=len, reverse=True)) + ")")


# =========================================================================== settings


def color(value: str, what: str) -> tuple[float, float, float]:
    """The red, green and blue (0 to 1) of a color written #RRGGBB."""
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not m:
        raise LabelError(tr("the {what} must be a color as #RRGGBB (not {value!r})", what=tr(what), value=value))
    h = m[1]
    # Canales de 0 a 1, como los esperan los operadores rg y RG.
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hex_color(value: str, what: str) -> str:
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in color(value, what))


def base_font(family: str, bold: bool, italic: bool) -> str:
    """The standard PDF font of FAMILY (helvetica, times or courier) in that style."""
    name = FAMILIES[family]
    style = {(False, False): "", (True, False): "Bold", (False, True): "Oblique", (True, True): "BoldOblique"}
    suffix = style[bold, italic]
    # Times names its styles Roman and Italic where Helvetica and Courier say Oblique.
    if name == "Times":
        suffix = {"": "Roman", "Oblique": "Italic", "BoldOblique": "BoldItalic"}.get(suffix, suffix)
    return f"{name}-{suffix}" if suffix else name


def check_common(settings) -> None:
    """Check what headers, footers and watermarks share (raises LabelError)."""
    if settings.units not in POINTS:
        raise LabelError(tr("the units must be in, cm or pt (not {value!r})", value=settings.units))
    if settings.font not in FAMILIES:
        raise LabelError(tr("the font must be helvetica, times or courier (not {value!r})", value=settings.font))
    if settings.parity not in PARITIES:
        raise LabelError(tr("the pages must be all, even or odd (not {value!r})", value=settings.parity))
    if not 1 <= settings.size <= 500:
        raise LabelError(tr("the font size must be from 1 to 500 points (not {value})", value=settings.size))
    if settings.date_format not in DATE_FORMATS:
        raise LabelError(tr("unknown date format {value!r} (one of: {names})", value=settings.date_format,
                            names=", ".join(DATE_FORMATS)))
    # El número Bates puede empezar en 0; más de 20 dígitos no tiene uso práctico.
    if settings.bates_start < 0 or not 1 <= settings.bates_digits <= 20:
        raise LabelError(tr("the Bates number starts at 0 or more, with 1 to 20 digits"))


# =========================================================================== the pages


def chosen_pages(settings, n: int) -> list[int]:
    """The pages (1-based) of a document of N pages that SETTINGS (with .pages and .parity) go on."""
    # Las páginas que pasan del documento hacen fallar parse_pages; no se recortan en silencio.
    if settings.pages.strip():
        pages: set[int] = set()
        for part in settings.pages.split(","):
            if part.strip():
                first, last = parse_pages(part, n)
                pages.update(range(first, (last or first) + 1))
    else:
        pages = set(range(1, n + 1))
    if settings.parity == "even":
        pages = {p for p in pages if p % 2 == 0}
    elif settings.parity == "odd":
        pages = {p for p in pages if p % 2 == 1}
    return sorted(pages)


@dataclass(frozen=True)
class Pages:
    """Some pages: a list of them ('' for all) and, of those, all, the even or the odd ones."""

    pages: str = ""
    parity: str = "all"


def compact_pages(pages) -> str:
    """'3-5,9': PAGES (1-based) as a list of pages."""
    out, run = [], []
    for p in sorted(set(pages)):
        if run and p == run[-1] + 1:
            run.append(p)
            continue
        if run:
            out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
        run = [p]
    if run:
        out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
    return ",".join(out)


# =========================================================================== the variables


@dataclass(frozen=True)
class Document:
    """What the variables of a document need to know of it."""

    count: int
    labels: tuple[str, ...]
    bookmarks: tuple[str, ...]  # the bookmark each page is under ("" if none)
    author: str = ""
    path: Path | None = None


def bookmarks_of(pdf: Pdf) -> tuple[str, ...]:
    """The title of the bookmark (outline item) each page is under: the last one, in the
    order of the outline, that goes to it or to a page before it ('' if none)."""
    from .view import _destination  # (an explicit destination: its page)

    n = len(pdf.pages)
    starts: list[tuple[int, int, str]] = []  # (page, order, title)
    # Destinos con nombre, del catálogo (estilo PDF 1.1) y del árbol de nombres: los marcadores pueden usarlos.
    names = {}
    try:
        if "/Dests" in pdf.Root:
            names.update({str(k): v for k, v in pdf.Root.Dests.items()})
        if "/Names" in pdf.Root and "/Dests" in pdf.Root.Names:
            names.update({str(k): v for k, v in pikepdf.NameTree(pdf.Root.Names.Dests).items()})
    # A damaged name tree should not stop the header from being drawn; bookmarks then just go unresolved.
    except (pikepdf.PdfError, TypeError, ValueError, KeyError):
        pass
    try:
        with pdf.open_outline() as outline:
            order = 0

            def walk(items):
                nonlocal order
                for item in items:
                    target = item.destination
                    if target is None and item.action is not None and item.action.get("/S") == Name.GoTo:
                        target = item.action.get("/D")
                    # A named destination may be stored as a dictionary whose /D holds the explicit destination.
                    if isinstance(target, (pikepdf.String, Name)) or isinstance(target, str):
                        # Algunos archivos guardan el nombre con barra (como Name) y otros sin ella; se prueban ambos.
                        target = names.get(str(target).lstrip("/"), names.get(str(target)))
                    if isinstance(target, Dictionary):
                        target = target.get("/D")
                    found = _destination(pdf, target) if target is not None else None
                    if found:
                        starts.append((found[0], order, str(item.title or "")))
                    order += 1
                    walk(item.children)

            walk(outline.root)
    # Con un esquema dañado, ninguna página tiene marcador; $bookmark queda vacío en todas.
    except (pikepdf.PdfError, pikepdf.OutlineStructureError, TypeError, ValueError, KeyError):
        return ("",) * n
    # Ordenar por (página, orden) hace que, si dos marcadores van a la misma página, gane el último del esquema.
    starts.sort()
    out, k, current = [], 0, ""
    for page in range(1, n + 1):
        while k < len(starts) and starts[k][0] <= page:
            current = starts[k][2]
            k += 1
        out.append(current)
    return tuple(out)


def document_of(pdf: Pdf, path: Path | None = None, labels: list[str] | None = None) -> Document:
    """What the variables need of PDF (with these LABELS of its pages, or those it has)."""
    n = len(pdf.pages)
    if labels is None:
        labels = page_labels(read_labels(pdf), n)
    author = ""
    try:
        # pdf.docinfo crea un diccionario /Info si no existe; se mira antes el tráiler para no añadirlo sin querer.
        author = str(pdf.docinfo.get("/Author", "")) if pdf.trailer.get("/Info") is not None else ""
    except (pikepdf.PdfError, ValueError):
        pass
    return Document(n, tuple(labels), bookmarks_of(pdf), author, path)


def format_date(now: datetime, date_format: str = "medium") -> str:
    """NOW as DATE_FORMAT says (see DATE_FORMATS)."""
    if date_format == "medium":
        return tr("{month} {day}, {year}", month=tr(MONTHS[now.month - 1]), day=now.day, year=now.year)
    if date_format == "long":
        # ("May (month)": a key apart from the short "May"; untranslated, it is written "May")
        month = tr(LONG_MONTHS[now.month - 1]).removesuffix(" (month)")
        return tr("{long_month} {day}, {year}", long_month=month, day=now.day, year=now.year)
    out = date_format
    # Longest codes first, so 'yyyy' is not taken as two 'yy'; the lookarounds keep 'd' out of words.
    for code, value in (("yyyy", f"{now.year:04d}"), ("mm", f"{now.month:02d}"), ("dd", f"{now.day:02d}"),
                        ("yy", f"{now.year % 100:02d}"), ("m", str(now.month)), ("d", str(now.day))):
        out = re.sub(rf"(?<![a-z]){code}(?![a-z])", value, out)
    return out


def expand(text: str, page: int, doc: Document, now: datetime, bates: str = "",
           date_format: str = "medium") -> str:
    """TEXT with its variables replaced, on PAGE (1-based) of DOC ($$ writes $)."""
    hour12 = now.hour % 12 or 12
    values = {
        "page": str(page),
        # Las etiquetas pueden faltar (un documento cambiado después de leerlas); entonces vale el número de página.
        "pagelabel": doc.labels[page - 1] if page <= len(doc.labels) else str(page),
        "bookmark": doc.bookmarks[page - 1] if page <= len(doc.bookmarks) else "",
        "totalpages": str(doc.count),
        "author": doc.author,
        "filename": doc.path.name if doc.path else "",
        "filepath": str(doc.path.resolve()) if doc.path else "",
        "day": str(now.day),
        "month": f"{now.month:02d}",
        "year": f"{now.year:04d}",
        "shortyear": f"{now.year % 100:02d}",
        "hour": str(hour12),
        "longhour": f"{now.hour:02d}",
        "minute": f"{now.minute:02d}",
        "second": f"{now.second:02d}",
        "ampm": "AM" if now.hour < 12 else "PM",
        "bates": bates,
        "date": format_date(now, date_format),
    }
    values["shortdate"] = tr("{month}/{day}/{year}", month=values["month"], day=f"{now.day:02d}",
                             year=values["shortyear"])
    values["time"] = tr("{hour}:{minute} {ampm}", hour=hour12, minute=values["minute"], ampm=values["ampm"])
    # $$ escribe un $ literal; cualquier otro $ que no sea una variable se deja tal cual.
    return _VARIABLE.sub(lambda m: "$" if m[0] == "$$" else values[m[1]], text)


def bates_number(settings, index: int) -> str:
    """The Bates number of the INDEXth page (from 0) SETTINGS go on."""
    # Zero-padded to at least DIGITS digits; a larger number simply gets longer.
    return f"{settings.bates_prefix}{settings.bates_start + index:0{settings.bates_digits}d}{settings.bates_suffix}"


def uses_bates(*texts: str) -> bool:
    return any(m[1] == "bates" for t in texts for m in _VARIABLE.finditer(t))


def unwritable(text: str) -> str:
    """The characters of TEXT the standard fonts cannot write ('' if none)."""
    # Las cuatro familias estándar cubren los mismos caracteres de cp1252; basta mirar Helvetica.
    widths = FONTS["Helvetica"][2]
    return "".join(sorted({c for c in text if c not in widths and c not in "\n\t"}))


def check_writable(text: str, page: int) -> None:
    bad = unwritable(text)
    if bad:
        raise LabelError(tr("the standard PDF fonts cannot write {chars!r} (page {page})", chars=bad, page=page))


def text_width(text: str, font: str, size: float) -> float:
    widths = FONTS[font][2]
    # Un carácter sin ancho cuenta 0; check_writable ya debió rechazarlo antes de dibujar.
    return sum(widths.get(c, 0) for c in text) * size / 1000


# =========================================================================== drawing


def shown_frame(page: pikepdf.Page) -> tuple[float, float, Matrix]:
    """(width, height, matrix) of PAGE as it is shown: its crop box, turned by /Rotate. The
    matrix takes points of the page as shown (from its lower left corner) to its own space."""
    # cropbox is what a viewer shows; pikepdf falls back to the media box when there is no /CropBox.
    x0, y0, x1, y1 = (float(v) for v in page.cropbox)
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    w, h = x1 - x0, y1 - y0
    rotate = int(page.obj.get("/Rotate", 0) or 0) % 360
    # Each matrix turns the shown page back by /Rotate (clockwise) and moves its origin to a corner of the box.
    if rotate == 90:
        return h, w, (0, 1, -1, 0, x1, y0)
    if rotate == 180:
        return w, h, (-1, 0, 0, -1, x1, y1)
    if rotate == 270:
        return h, w, (0, -1, 1, 0, x0, y1)
    return w, h, (1, 0, 0, 1, x0, y0)


def number(x: float) -> str:
    # Cuatro decimales bastan (una diezmilésima de punto) y quitan ceros sobrantes al flujo.
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def matrix_text(m: Matrix) -> str:
    return " ".join(number(v) for v in m)


def pdf_string(text: str) -> bytes:
    # cp1252 is what WinAnsiEncoding writes; unwritable characters were rejected before getting here.
    data = text.encode("cp1252")
    # Paréntesis y barra invertida se escapan dentro de una cadena literal de PDF.
    return b"(" + data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def rgb(value: str, operator: str) -> str:
    r, g, b = color(value, N_("color"))
    return f"{number(r)} {number(g)} {number(b)} {operator}"


def font_object(pdf: Pdf, font: str) -> pikepdf.Object:
    # The 14 standard fonts need no embedding: a Type1 font with just its BaseFont name is enough.
    return pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name("/" + font),
                                        Encoding=Name.WinAnsiEncoding))


# =========================================================================== layers


def _contents(page: pikepdf.Page) -> list:
    """The content streams of PAGE (its /Contents, one stream or an array of them)."""
    contents = page.obj.get("/Contents")
    if contents is None:
        return []
    return list(contents) if isinstance(contents, Array) else [contents]


def records(page: pikepdf.Page) -> list[Dictionary]:
    """The records of the layers of PAGE, in the order they were added."""
    out = []
    legacy = page.obj.get(LEGACY)
    if isinstance(legacy, Dictionary):
        # El registro de 0.7 se lee como el de una capa de encabezado de la adición 0, sin tocar el archivo.
        legacy.Kind, legacy.Id = Name("/" + HEADER_FOOTER), 0
        out.append(legacy)
    stored = page.obj.get(KEY)
    if isinstance(stored, Array):
        out += [r for r in stored if isinstance(r, Dictionary)]
    return out


def _keep_records(page: pikepdf.Page, kept: list[Dictionary]) -> None:
    if LEGACY in page.obj:
        del page.obj[LEGACY]
    if kept:
        page.obj[KEY] = Array(kept)
    elif KEY in page.obj:
        del page.obj[KEY]


def kind_of(record: Dictionary) -> str:
    return str(record.get("/Kind", "/" + HEADER_FOOTER))[1:]


def id_of(record: Dictionary) -> int:
    return int(record.get("/Id", 0))


def settings_of(record: Dictionary) -> dict:
    try:
        # Settings are stored as a UTF-8 JSON byte string; a missing or broken one reads as no settings.
        data = json.loads(bytes(record.get("/Settings", pikepdf.String(""))).decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def next_id(pdf: Pdf) -> int:
    """The id of a new addition: one more than any on the pages of PDF."""
    return 1 + max((id_of(r) for page in pdf.pages for r in records(page)), default=0)


def add_layer(pdf: Pdf, page: pikepdf.Page, kind: str, addition: int, settings: dict, *, before: bytes = b"",
              after: bytes = b"", behind: bytes = b"", shrink: Matrix | None = None,
              resources: dict[str, list[str]] | None = None, bates: bool = False,
              group: pikepdf.Object | None = None) -> None:
    """Add a layer to PAGE: BEHIND (drawn before everything), BEFORE and AFTER (around the content
    there is: BEFORE should start with q and AFTER with Q), and, with SHRINK, its annotations moved
    by that matrix (in the space of the page). RESOURCES: {category: [names]} it added to the page."""
    record = Dictionary(Kind=Name("/" + kind), Id=addition, Bates=bool(bates),
                        Settings=pikepdf.String(json.dumps(settings, ensure_ascii=False).encode("utf-8")))
    # Cada flujo es un objeto indirecto, para reconocerlo después por su número al quitar la capa.
    streams = {k: pdf.make_indirect(pikepdf.Stream(pdf, v)) for k, v in
               (("behind", behind), ("before", before), ("after", after)) if v}
    contents = _contents(page)
    # Orden final: detrás, antes, contenido original, después; las capas anteriores quedan dentro de este par.
    page.obj.Contents = Array([*(streams[k] for k in ("behind", "before") if k in streams), *contents,
                               *([streams["after"]] if "after" in streams else [])])
    record.Streams = Array(list(streams.values()))
    if shrink is not None:
        moved, rects = Array(), Array()
        # Annotations do not follow the content's cm; their /Rect is moved by hand and the old one kept for undoing.
        for annot in page.obj.get("/Annots", Array()):
            if isinstance(annot, Dictionary) and "/Rect" in annot:
                rects.append(Array(list(annot.Rect)))
                annot.Rect = moved_rect(annot.Rect, shrink)
                moved.append(annot)
        # El registro guarda las anotaciones movidas, sus rectángulos de antes y la matriz que se les aplicó.
        record.Annots, record.Rects, record.Matrix = moved, rects, Array([float(v) for v in shrink])
    if group is not None:
        record.Group = group
    if resources:
        record.Resources = Dictionary({"/" + k: Array([Name("/" + n.lstrip("/")) for n in v])
                                       for k, v in resources.items()})
    _keep_records(page, records(page) + [record])


# The box of the four transformed corners: after a rotation the result is still an upright rectangle.
def moved_rect(rect, m: Matrix) -> Array:
    x0, y0, x1, y1 = (float(v) for v in rect)
    corners = [transform(m, x, y) for x in (x0, x1) for y in (y0, y1)]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    return Array([min(xs), min(ys), max(xs), max(ys)])


def remove_layers(page: pikepdf.Page, which) -> int:
    """Take away the layers of PAGE whose record WHICH(record) chooses, putting back what they
    changed; the number taken away."""
    layers = records(page)
    gone = {i for i, r in enumerate(layers) if which(r)}
    if not gone:
        return 0
    added = {s.objgen for i in gone for s in layers[i].get("/Streams", Array())}
    # Los flujos de las capas se reconocen por su número de objeto; el resto del contenido queda igual.
    contents = [s for s in _contents(page) if s.objgen not in added]
    # Con un solo flujo se escribe el flujo directamente, no un arreglo de uno.
    page.obj.Contents = contents[0] if len(contents) == 1 else Array(contents)
    # the annotations each layer moved, back where the layers that are left would put them
    for i, layer in enumerate(layers):
        if i not in gone:
            continue
        # Rehacer la posición de cada anotación sin esta capa: partir del rectángulo que tenía antes de ella y aplicar
        # las matrices de las capas posteriores que siguen en la página.
        for annot, rect in zip(layer.get("/Annots", Array()), layer.get("/Rects", Array())):
            current = Array(list(rect))
            # A later layer that also moved this annotation must remember the new 'before' rectangle, so that
            # removing it afterwards still puts the annotation back in the right place.
            for j in range(i + 1, len(layers)):
                later = layers[j]
                ids = [a.objgen for a in later.get("/Annots", Array())]
                if annot.objgen not in ids or j in gone:
                    continue
                k = ids.index(annot.objgen)
                rects = list(later.Rects)
                rects[k] = Array(list(current))
                later.Rects = Array(rects)
                if "/Matrix" in later:
                    current = moved_rect(current, tuple(float(v) for v in later.Matrix))
            annot.Rect = current
    resources = page.obj.get("/Resources")
    for layer in (layers[i] for i in gone):
        names = layer.get("/Resources", Dictionary())
        # Registros de 0.7: la fuente iba en /Font y no en /Resources.
        legacy_font = layer.get("/Font")
        if legacy_font is not None:
            names = Dictionary(Font=Array([legacy_font]))
        for category, items in (names.items() if isinstance(names, Dictionary) else []):
            # Solo se borran de /Resources los nombres que añadió la capa, no los del contenido original.
            if resources is not None and category in resources:
                for name in items:
                    if name in resources[category]:
                        del resources[category][name]
    _keep_records(page, [r for i, r in enumerate(layers) if i not in gone])
    return len(gone)


# =========================================================================== what a document has


@dataclass(frozen=True)
class Addition:
    """One addition of a header and footer or of a watermark, with the pages it is on."""

    id: int
    kind: str
    settings: dict
    pages: tuple[int, ...]
    bates: bool


def additions(pdf: Pdf) -> list[Addition]:
    """What py-pdftools (or py-foliation) added to the pages of PDF, in the order it was added."""
    found: dict[int, dict] = {}
    for number_, page in enumerate(pdf.pages, 1):
        for r in records(page):
            # The id is shared by every page of one addition, so grouping by it gives the pages of each addition.
            a = found.setdefault(id_of(r), {"kind": kind_of(r), "settings": settings_of(r), "pages": [],
                                            "bates": bool(r.get("/Bates", False))})
            a["pages"].append(number_)
    return [Addition(i, a["kind"], a["settings"], tuple(a["pages"]), a["bates"]) for i, a in sorted(found.items())]


def last_addition(pdf_or_additions, kind: str) -> Addition | None:
    """The addition of KIND made last (None if none)."""
    items = additions(pdf_or_additions) if isinstance(pdf_or_additions, Pdf) else pdf_or_additions
    return next((a for a in reversed(items) if a.kind == kind), None)


def remove(pdf: Pdf, pages: str = "", kind: str | None = HEADER_FOOTER, *, bates_only: bool = False,
           addition: int | None = None) -> int:
    """Take away from PAGES ('' for all) the layers of KIND (None: any), only those with Bates
    numbers, or only those of ADDITION; the number of pages that had any."""
    chosen = chosen_pages(Pages(pages), len(pdf.pages))

    def which(r):
        return ((kind is None or kind_of(r) == kind) and (not bates_only or bool(r.get("/Bates", False)))
                and (addition is None or id_of(r) == addition))

    count = sum(bool(remove_layers(pdf.pages[p - 1], which)) for p in chosen)
    _drop_unused_groups(pdf)
    return count


def pages_with(pdf: Pdf, kind: str | None = HEADER_FOOTER, *, bates_only: bool = False) -> list[int]:
    """The pages (1-based) with a layer of KIND (None: any; only with Bates numbers, if BATES_ONLY)."""
    return [i + 1 for i, page in enumerate(pdf.pages)
            if any((kind is None or kind_of(r) == kind) and (not bates_only or bool(r.get("/Bates", False)))
                   for r in records(page))]


# =========================================================================== optional content


def optional_group(pdf: Pdf, name: str, print_: bool, view: bool) -> pikepdf.Object:
    """A new optional content group, shown or hidden when printing (PRINT_) and on the screen
    (VIEW), as the viewer's automatic states say."""
    # PyFoliation marca los grupos propios, para borrar después solo esos y nunca los del autor del PDF.
    group = pdf.make_indirect(Dictionary(
        Type=Name.OCG, Name=pikepdf.String(name),
        Usage=Dictionary(Print=Dictionary(PrintState=Name.ON if print_ else Name.OFF),
                         View=Dictionary(ViewState=Name.ON if view else Name.OFF)),
        PyFoliation=True))
    props = pdf.Root.get("/OCProperties")
    if props is None:
        props = pdf.Root.OCProperties = Dictionary(OCGs=Array(), D=Dictionary(Order=Array(), AS=Array()))
    props.OCGs = Array([*props.get("/OCGs", Array()), group])
    d = props.get("/D")
    if d is None:
        d = props.D = Dictionary()
    d.Order = Array([*d.get("/Order", Array()), group])
    if not view:
        # A group hidden on screen also starts OFF, for viewers that ignore /AS.
        d.OFF = Array([*d.get("/OFF", Array()), group])
    # /Usage says the state for print and view, but only viewers that apply /AS (automatic states) follow it.
    auto = [a for a in d.get("/AS", Array())]
    for event, category in (("/Print", "/Print"), ("/View", "/View")):
        auto.append(Dictionary(Event=Name(event), Category=Array([Name(category)]), OCGs=Array([group])))
    d.AS = Array(auto)
    return group


def _drop_unused_groups(pdf: Pdf) -> None:
    """Take out of the catalog the optional content groups py-pdftools (or py-foliation) made that no page uses."""
    props = pdf.Root.get("/OCProperties")
    if props is None:
        return
    used = set()
    for page in pdf.pages:
        for r in records(page):
            if "/Group" in r:
                used.add(r.Group.objgen)
    # Solo se consideran los grupos marcados como propios; los del documento original no se tocan.
    ours = [g for g in props.get("/OCGs", Array()) if isinstance(g, Dictionary) and g.get("/PyFoliation", False)]
    unused = {g.objgen for g in ours if g.objgen not in used}
    if not unused:
        return

    def keep(items):
        out = []
        for item in items:
            # Optional content membership dictionaries and /AS entries list groups in /OCGs; drop ours, keep the rest.
            if isinstance(item, Dictionary) and "/OCGs" in item:
                groups = [g for g in item.OCGs if g.objgen not in unused]
                if groups:
                    item.OCGs = Array(groups)
                    out.append(item)
            elif not (isinstance(item, Dictionary) and item.objgen in unused):
                out.append(item)
        return Array(out)

    props.OCGs = keep(props.get("/OCGs", Array()))
    d = props.get("/D", Dictionary())
    for key in ("/Order", "/OFF", "/ON", "/AS"):
        if key in d:
            d[key] = keep(d[key])
    # Sin grupos, /OCProperties ya no sirve de nada y se quita del catálogo.
    if not len(props.OCGs):
        del pdf.Root["/OCProperties"]
