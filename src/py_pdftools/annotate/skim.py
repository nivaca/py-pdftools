"""Las notas de Skim (el lector de PDF del Mac): leídas de un archivo .skim
para importarlas como anotaciones, y escritas en uno para llevarlas a Skim.

Skim guarda sus notas fuera del PDF: en los atributos extendidos del archivo
o, si se le pide, en un ``libro.skim`` junto a él. Ese archivo es una lista
de diccionarios, uno por nota, de una de dos maneras: una lista de propiedades
(plist) con los colores como listas de números y el texto con formato en RTF,
o un archivo de NSKeyedArchiver, con los objetos de Cocoa (NSColor, NSFont,
NSAttributedString, NSDate) archivados. plistlib lee las dos; los objetos
archivados se reconstruyen aquí (véase _unarchive).

Las coordenadas de una nota son las del PDF (origen abajo a la izquierda);
las de sus puntos (de una línea, de los cuadriláteros de un resaltado, de los
trazos de tinta) se cuentan desde la esquina de su recuadro. Los tipos que
py-pdftools no tiene (los campos de formulario, Widget) se dejan fuera; el
texto con formato se toma como texto simple.

Al exportar se escribe la lista de propiedades binaria, la forma que Skim
escribe hoy por omisión, con los colores siempre de cuatro componentes (Skim
lee cuatro aunque la lista traiga tres). Skim no tiene todas las clases de
py-pdftools: un subrayado ondulado sale como subrayado, un resaltado de zona
como rectángulo relleno, los polígonos, nubes, polilíneas y resaltados a mano
alzada como trazos de tinta, y una llamada como cuadro de texto; las
inserciones de texto, los sellos y los archivos adjuntos se dejan fuera, como
las respuestas, las etiquetas y las categorías, que Skim no tiene.
"""

from __future__ import annotations

import datetime
import plistlib
import re
from pathlib import Path

import pymupdf

from . import annots
from .annots import AnnotateError, Annotation
from ..core.interface import tr

# Los tipos de Skim, y la clase de cada uno aquí ("MarkUp" es el nombre viejo de los tres de texto marcado).
TYPES = {"FreeText": "freetext", "Note": "note", "Text": "note", "Circle": "ellipse", "Square": "rect",
         "Highlight": "highlight", "Underline": "underline", "StrikeOut": "strikeout", "Squiggly": "squiggly",
         "Line": "line", "Ink": "ink", "Stamp": "stamp"}
MARKUP_TYPES = ("highlight", "strikeout", "underline", "squiggly")  # (PDFKit's kPDFMarkupType...)
LINE_STYLES = ("None", "Square", "Circle", "Diamond", "OpenArrow", "ClosedArrow")  # (kPDFLineStyle...)
ICONS = ("Comment", "Key", "Note", "Help", "NewParagraph", "Paragraph", "Insert")  # (kPDFTextAnnotationIcon...)
ALIGNS = ("left", "center", "right")
_EPOCH = datetime.datetime(2001, 1, 1, tzinfo=datetime.UTC)  # (Cocoa's dates count from here)


# --------------------------------------------------------------------- the file

class _Color(tuple):
    """A colour read from the file: (r, g, b, a), from 0 to 1."""


def _color_bytes(text: bytes) -> list[float]:
    # NSColor archiva sus componentes como texto: b"0.5 0.2 0.1 1\x00".
    return [float(v) for v in text.rstrip(b"\x00").split()]


def _color(values) -> _Color | None:
    """A colour of Skim as (r, g, b, a): from a list of numbers (white and alpha, or red, green, blue and alpha)."""
    try:
        values = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    if len(values) in (1, 2):
        return _Color((values[0], values[0], values[0], values[1] if len(values) == 2 else 1.0))
    if len(values) in (3, 4):
        return _Color((*values[:3], values[3] if len(values) == 4 else 1.0))
    return None


def _unarchive(top: dict):
    """The object at the root of a file of NSKeyedArchiver, rebuilt: lists, dictionaries, strings, numbers,
    data; colours as _Color, fonts as {"fontName", "fontSize"}, dates as datetime, attributed strings as their
    text. What can't be rebuilt (an NSImage) is None."""
    objects = top["$objects"]
    done: dict[int, object] = {}

    def value(item):
        return build(item.data) if isinstance(item, plistlib.UID) else item

    def build(index: int):
        if index in done:
            return done[index]
        raw = objects[index]
        if raw == "$null":
            return None
        if not (isinstance(raw, dict) and "$class" in raw):
            return raw
        name = objects[raw["$class"].data].get("$classname", "")
        out = None
        if name in ("NSArray", "NSMutableArray", "NSSet", "NSMutableSet"):
            out = []
            done[index] = out
            out.extend(value(v) for v in raw.get("NS.objects", []))
        elif name in ("NSDictionary", "NSMutableDictionary"):
            out = {}
            done[index] = out
            out.update({value(k): value(v) for k, v in zip(raw.get("NS.keys", []), raw.get("NS.objects", []))})
        elif name in ("NSString", "NSMutableString"):
            out = raw.get("NS.string", "")
        elif name in ("NSData", "NSMutableData"):
            out = raw.get("NS.data", b"")
        elif name == "NSDate":
            out = _EPOCH + datetime.timedelta(seconds=float(raw.get("NS.time", 0)))
        elif name in ("NSAttributedString", "NSMutableAttributedString"):
            out = value(raw.get("NSString", ""))
        elif name == "NSFont":
            out = {"fontName": value(raw.get("NSName", "")), "fontSize": float(raw.get("NSSize", 0))}
        elif name == "NSColor":
            if "NSRGB" in raw:
                out = _color(_color_bytes(raw["NSRGB"]))
            elif "NSWhite" in raw:
                out = _color(_color_bytes(raw["NSWhite"]))
            elif "NSComponents" in raw:
                out = _color(_color_bytes(raw["NSComponents"]))
        done[index] = out
        return out

    return value(top["$top"]["root"])


def read_notes(source: Path) -> list[dict]:
    """The notes of the .skim file SOURCE, as Skim's dictionaries (raises AnnotateError if it can't be read)."""
    try:
        data = plistlib.loads(source.read_bytes())
        notes = _unarchive(data) if isinstance(data, dict) and "$archiver" in data else data
    except (OSError, plistlib.InvalidFileException, ValueError, KeyError, IndexError, TypeError) as e:
        raise AnnotateError(tr("{path} cannot be read: {error}", path=source, error=e)) from None
    if not isinstance(notes, list):
        raise AnnotateError(tr("{path} cannot be read: {error}", path=source,
                               error=tr("not a file of notes of Skim")))
    return [n for n in notes if isinstance(n, dict)]


# --------------------------------------------------------------------- the values

def _numbers(text) -> list[float]:
    """The numbers of a point or rectangle of Cocoa: "{1, 2}", "{{1, 2}, {3, 4}}"."""
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?", str(text))]


def rtf_text(data: bytes) -> str:
    """The text of the RTF DATA, without its formatting (enough for the text of a note)."""
    text = data.decode("latin-1")
    # Los grupos que no son texto: tablas de fuentes y colores, información, imágenes, destinos con \*.
    text = re.sub(r"\{\\(?:fonttbl|colortbl|stylesheet|info|\*)[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", text)
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            m = re.match(r"\\(?:'([0-9a-fA-F]{2})|u(-?\d+) ?\??|([a-zA-Z]+)(-?\d+)? ?|(.))", text[i:], re.S)
            if m is None:
                i += 1
                continue
            hexa, uni, word, _, other = m.groups()
            if hexa:
                out.append(bytes([int(hexa, 16)]).decode("cp1252", "replace"))
            elif uni:
                out.append(chr(int(uni) % 65536))
            elif word in ("par", "line"):
                out.append("\n")
            elif word == "tab":
                out.append("\t")
            elif other in ("\\", "{", "}"):
                out.append(other)
            elif other == "\n":
                out.append("\n")
            i += m.end()
        elif ch in "{}\r\n":
            i += 1
        else:
            out.append(ch)
            i += 1
    joined = "".join(out).strip()
    # Un carácter fuera del plano básico llega como dos \\uN (un par sustituto): se unen aquí.
    return joined.encode("utf-16", "surrogatepass").decode("utf-16", "replace")


def _hex(color) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(v * 255))) for v in color[:3]))


def _date(value) -> str:
    if isinstance(value, datetime.datetime):
        when = value if value.tzinfo else value.replace(tzinfo=datetime.UTC)
        return when.astimezone(datetime.UTC).strftime("D:%Y%m%d%H%M%SZ")
    return ""


def _text(value) -> str:
    if isinstance(value, bytes):
        return rtf_text(value)
    return value if isinstance(value, str) else ""


# --------------------------------------------------------------------- the annotations

def annotation_of(note: dict, doc: pymupdf.Document) -> Annotation | None:
    """The annotation of the Skim NOTE, on its page of DOC (None if it has no place here)."""
    kind = TYPES.get(str(note.get("type", "")))
    if note.get("type") == "MarkUp":
        markup = int(note.get("markupType", 0) or 0)
        kind = MARKUP_TYPES[markup] if 0 <= markup < len(MARKUP_TYPES) else "highlight"
    try:
        page_index = int(note.get("pageIndex", 0))
        x, y, w, h = _numbers(note.get("bounds", ""))[:4]
    except (TypeError, ValueError):
        return None
    if kind is None or not 0 <= page_index < doc.page_count:
        return None
    page = doc[page_index]

    def shown(px: float, py: float) -> annots.Point:
        # (a point of the PDF, from the bottom left, as the page is shown)
        return annots.from_pdf(page, (px, py))

    def box(points) -> annots.Rect:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return min(xs), min(ys), max(xs), max(ys)

    rect = box([shown(x, y), shown(x + w, y + h)])
    color = note.get("color")
    color = color if isinstance(color, _Color) else _color(color) if isinstance(color, list) else None
    inside = note.get("interiorColor")
    inside = inside if isinstance(inside, _Color) else _color(inside) if isinstance(inside, list) else None
    contents = _text(note.get("contents") or note.get("string") or "")
    longer = _text(note.get("text"))
    if longer and longer != contents:  # (an anchored note of Skim: a label, and its text)
        contents = f"{contents}\n\n{longer}" if contents else longer
    values = dict(kind=kind, page=page_index, rect=rect, contents=contents,
                  author=str(note.get("userName") or ""), modified=_date(note.get("modificationDate")))
    if color is not None:
        values["color"] = _hex(color)
        if kind in annots.MARKUP or kind in ("note", "ink"):
            values["opacity"] = round(color[3], 3) if 0 < color[3] < 1 else 1.0
    width = note.get("lineWidth")
    if isinstance(width, (int, float)):
        values["width"] = float(width)
    if note.get("dashPattern") or note.get("borderStyle") == 1:
        values["dashed"] = True

    if kind in annots.MARKUP:
        corners = [_numbers(p) for p in note.get("quadrilateralPoints") or []]
        quads = []
        # Cuatro puntos por línea marcada, contados desde la esquina del recuadro.
        for i in range(0, len(corners) - 3, 4):
            quads.append(box([shown(x + p[0], y + p[1]) for p in corners[i:i + 4]]))
        values["quads"] = tuple(quads) or (rect,)
    elif kind in ("ellipse", "rect"):
        if inside is not None and inside[3] > 0:
            values["fill"] = _hex(inside)
    elif kind == "line":
        start, end = _numbers(note.get("startPoint", "")), _numbers(note.get("endPoint", ""))
        if len(start) < 2 or len(end) < 2:
            return None
        ends = []
        for key in ("startLineStyle", "endLineStyle"):
            style = int(note.get(key, 0) or 0)
            ends.append(LINE_STYLES[style] if 0 <= style < len(LINE_STYLES) else "None")
        values["ends"] = tuple(ends)
        if "Arrow" in ends[1] and ends[0] == "None":
            values["kind"] = "arrow"
        values["paths"] = ((shown(x + start[0], y + start[1]), shown(x + end[0], y + end[1])),)
        values["rect"] = annots.frame(values["kind"], values["paths"], values.get("width", 1.5))
    elif kind == "ink":
        paths = []
        for stroke in note.get("pointLists") or []:
            points = [_numbers(p) for p in stroke]
            path = tuple(shown(x + p[0], y + p[1]) for p in points if len(p) >= 2)
            if path:
                paths.append(path)
        if not paths:
            return None
        values["paths"] = tuple(paths)
        values["rect"] = annots.frame("ink", values["paths"], values.get("width", 1.5))
    elif kind == "note":
        icon = note.get("iconType", 2)
        values["icon"] = ICONS[icon] if isinstance(icon, int) and 0 <= icon < len(ICONS) else "Note"
    elif kind == "freetext":
        # En Skim, el color de una nota de texto es su fondo; el del texto es fontColor.
        values.pop("color", None)
        if color is not None and color[3] > 0:
            values["fill"] = _hex(color)
        font_color = note.get("fontColor")
        font_color = font_color if isinstance(font_color, _Color) else \
            _color(font_color) if isinstance(font_color, list) else None
        values["color"] = _hex(font_color) if font_color is not None else "#000000"
        font = note.get("font") if isinstance(note.get("font"), dict) else note
        size = font.get("fontSize")
        if isinstance(size, (int, float)) and size > 0:
            values["font_size"] = float(size)
        name = str(font.get("fontName") or "").lower()
        values["font"] = "tiro" if "times" in name or "serif" in name and "sans" not in name else \
            "cour" if "courier" in name or "mono" in name else "helv"
        align = note.get("alignment", 0)
        values["align"] = ALIGNS[align] if isinstance(align, int) and 0 <= align < len(ALIGNS) else "left"
        values.setdefault("width", 0.0)
    elif kind == "stamp":
        image = note.get("image")
        png = b""
        if isinstance(image, bytes) and image:
            try:  # (Skim keeps the stamp's look as a TIFF: made PNG, as py-pdftools keeps them)
                png = pymupdf.Pixmap(image).tobytes("png")
            except (RuntimeError, ValueError):
                png = b""
        name = str(note.get("name") or "").lstrip("/")
        if png:
            values["image"] = png
        else:
            values["stamp"] = name if name in annots.STAMPS else "Draft"
    try:
        return Annotation(**values)
    except TypeError:
        return None


def import_skim(doc: pymupdf.Document, source: Path) -> list[Annotation]:
    """The notes of the .skim file SOURCE, as annotations of the document DOC (raises AnnotateError)."""
    return [a for a in (annotation_of(n, doc) for n in read_notes(source)) if a is not None]


# --------------------------------------------------------------------- export

# Cada clase de py-pdftools con la de Skim que la representa (las que faltan no tienen ninguna).
EXPORT_TYPES = {"highlight": "Highlight", "underline": "Underline", "strikeout": "StrikeOut",
                "squiggly": "Underline", "area": "Square", "note": "Note", "freetext": "FreeText",
                "callout": "FreeText", "rect": "Square", "ellipse": "Circle", "line": "Line", "arrow": "Line",
                "ink": "Ink", "marker": "Ink", "polyline": "Ink", "polygon": "Ink", "cloud": "Ink"}
_FONT_NAMES = {"helv": "Helvetica", "tiro": "Times-Roman", "cour": "Courier"}


def _rgba(color: str, alpha: float = 1.0) -> list[float]:
    """The colour #RRGGBB as Skim's list of four numbers (red, green, blue, alpha) from 0 to 1."""
    value = color.lstrip("#")
    if len(value) != 6:
        return [0.0, 0.0, 0.0, 0.0]
    return [round(int(value[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)] + [round(max(0.0, min(1.0, alpha)), 4)]


def _cocoa(*values: float) -> str:
    """A point or rectangle written as Cocoa writes them: "{1, 2}", "{{1, 2}, {3, 4}}"."""
    def n(v: float) -> str:
        return f"{v:.3f}".rstrip("0").rstrip(".") or "0"

    if len(values) == 2:
        return f"{{{n(values[0])}, {n(values[1])}}}"
    return f"{{{{{n(values[0])}, {n(values[1])}}}, {{{n(values[2])}, {n(values[3])}}}}}"


def rtf_of(text: str) -> bytes:
    """TEXT as plain RTF, as Cocoa reads it (the long text of an anchored note of Skim)."""
    out = []
    for ch in text:
        code = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\\n")
        elif ch == "\t":
            out.append("\\tab ")
        elif 32 <= code < 128:
            out.append(ch)
        elif code < 32:
            continue
        else:
            # \uN (con signo, de 16 bits) y ? para quien no lo lea; fuera del plano básico, su par sustituto.
            units = ch.encode("utf-16-le")
            for i in range(0, len(units), 2):
                unit = int.from_bytes(units[i:i + 2], "little")
                out.append(f"\\u{unit - 65536 if unit > 32767 else unit}?")
    return ("{\\rtf1\\ansi\\ansicpg1252\\cocoartf2580\n{\\fonttbl\\f0\\fswiss\\fcharset0 Helvetica;}\n"
            "\\f0\\fs24 " + "".join(out) + "}").encode("ascii")


def _when(value: str) -> datetime.datetime | None:
    """The PDF date VALUE (D:20261126123000Z, with or without its zone) as a date, in UTC."""
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(?:([Zz+-])(\d{2})?'?(\d{2})?)?", value or "")
    if m is None:
        return None
    year, month, day, hour, minute, second, sign, zh, zm = m.groups()
    try:
        when = datetime.datetime(int(year), int(month or 1), int(day or 1), int(hour or 0), int(minute or 0),
                                 int(second or 0), tzinfo=datetime.UTC)
    except ValueError:
        return None
    if sign in ("+", "-"):
        offset = datetime.timedelta(hours=int(zh or 0), minutes=int(zm or 0))
        when = when - offset if sign == "+" else when + offset
    return when


def note_of(a: Annotation, doc: pymupdf.Document) -> dict | None:
    """The Skim note of the annotation A of DOC, as the dictionary of a .skim file (None if Skim has no kind
    for it)."""
    kind = EXPORT_TYPES.get(a.kind)
    if kind is None or not 0 <= a.page < doc.page_count:
        return None
    page = doc[a.page]

    def pdf(point) -> tuple[float, float]:
        return annots.to_pdf(page, point)

    def corners(rect) -> list[tuple[float, float]]:
        x0, y0, x1, y1 = rect
        return [pdf((x0, y0)), pdf((x1, y0)), pdf((x0, y1)), pdf((x1, y1))]

    def origin_of(points) -> tuple[float, float, float, float]:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)

    if a.kind in ("ink", "marker", "polyline", "polygon", "cloud"):
        strokes = [list(path) + ([path[0]] if a.kind in ("polygon", "cloud") and len(path) > 2 else [])
                   for path in a.paths if path]
        if not strokes:
            return None
        strokes = [[pdf(p) for p in path] for path in strokes]
        x, y, w, h = origin_of([p for path in strokes for p in path])
        pad = max(a.width, 2.0)  # (room for the line, as Skim leaves it)
        x, y, w, h = x - pad, y - pad, w + 2 * pad, h + 2 * pad
    elif a.kind in ("line", "arrow"):
        if not a.paths or len(a.paths[0]) < 2:
            return None
        ends = [pdf(a.paths[0][0]), pdf(a.paths[0][-1])]
        pad = max(a.width, 2.0) + 4.0
        x, y, w, h = origin_of(ends)
        x, y, w, h = x - pad, y - pad, w + 2 * pad, h + 2 * pad
    elif a.kind in annots.MARKUP:
        quads = [corners(q) for q in (a.quads or (a.rect,))]
        x, y, w, h = origin_of([p for q in quads for p in q])
    else:
        x, y, w, h = origin_of(corners(a.rect))
    note: dict = {"type": kind, "pageIndex": a.page, "bounds": _cocoa(x, y, w, h)}
    if a.author:
        note["userName"] = a.author
    when = _when(a.modified) or _when(a.created)
    if when is not None:
        note["modificationDate"] = when
    opacity = a.opacity if a.kind in annots.MARKUP or a.kind in ("note", "ink", "marker") else 1.0
    note["color"] = _rgba(a.color, opacity)
    contents = a.contents
    # Línea, borde y trazo: su grosor y si es discontinuo (Skim los guarda solo si hay grosor).
    stroked = a.kind in ("rect", "ellipse", "line", "arrow", "ink", "marker", "polyline", "polygon", "cloud") or \
        a.kind in annots.TEXTUAL and a.width > 0
    if stroked and a.width > 0:
        note["lineWidth"] = float(a.width)
        note["borderStyle"] = 1 if a.dashed else 0
        if a.dashed:
            note["dashPattern"] = [4.0, 2.0]

    if a.kind in annots.MARKUP:
        points = []
        for q in quads:
            (blx, bly), (brx, bry), (tlx, tly), (trx, try_) = sorted(q, key=lambda p: (p[1], p[0]))
            # Skim's own order: bottom left, top left, bottom right, top right (from the frame's corner)
            for px, py in ((blx, bly), (tlx, tly), (brx, bry), (trx, try_)):
                points.append(_cocoa(px - x, py - y))
        note["quadrilateralPoints"] = points
    elif a.kind == "area":
        note["color"] = _rgba(a.color, 0.0)
        note["interiorColor"] = _rgba(a.fill or a.color, a.opacity)
    elif a.kind in ("rect", "ellipse"):
        if a.fill:
            note["interiorColor"] = _rgba(a.fill, a.opacity)
    elif a.kind in ("line", "arrow"):
        start, end = ends
        note["startPoint"] = _cocoa(start[0] - x, start[1] - y)
        note["endPoint"] = _cocoa(end[0] - x, end[1] - y)
        line_ends = a.ends if a.kind == "line" or a.ends != ("None", "None") else ("None", "OpenArrow")
        note["startLineStyle"], note["endLineStyle"] = (LINE_STYLES.index(e) if e in LINE_STYLES else 0
                                                        for e in line_ends)
    elif note["type"] == "Ink":
        note["pointLists"] = [[_cocoa(px - x, py - y) for px, py in path] for path in strokes]
    elif a.kind == "note":
        note["iconType"] = ICONS.index(a.icon) if a.icon in ICONS else 2
        # Una nota anclada de Skim tiene un rótulo y un texto: el primer párrafo, y el resto (o todo, si es uno).
        label, sep, rest = contents.partition("\n\n")
        contents = label
        note["text"] = rtf_of(rest if sep else label)
    elif a.kind in annots.TEXTUAL:
        # En Skim, el color de un cuadro de texto es su fondo; el del texto es fontColor.
        note["color"] = _rgba(a.fill, 1.0) if a.fill else [0.0, 0.0, 0.0, 0.0]
        note["fontColor"] = _rgba(a.color, 1.0)
        note["fontName"] = _FONT_NAMES.get(a.font, "Helvetica")
        note["fontSize"] = float(a.font_size)
        note["alignment"] = ALIGNS.index(a.align) if a.align in ALIGNS else 0
    note["contents"] = contents
    return note


def export_skim(doc: pymupdf.Document, annotations: list[Annotation], target: Path) -> int:
    """ANNOTATIONS of DOC written as Skim's notes in the .skim file TARGET. Returns how many were written (those
    Skim has no kind for are left out)."""
    found = [n for n in (note_of(a, doc) for a in annotations) if n is not None]
    data = plistlib.dumps(found, fmt=plistlib.FMT_BINARY, sort_keys=True, aware_datetime=True)
    # Se escribe en un archivo propio, puesto en su lugar al final: uno a medias no reemplaza al bueno.
    tmp = target.with_name(target.name + ".part")
    try:
        tmp.write_bytes(data)
        tmp.replace(target)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise AnnotateError(str(e)) from None
    return len(found)
