"""Las anotaciones de un documento guardadas aparte, en un archivo XML junto al
PDF (``libro.pdf.pdfnotes``), sin tocar el PDF: la otra manera de guardarlas,
que se elige para cada documento (Archivo > Anotaciones en un archivo aparte)
o para todos los que aún no tienen ese archivo (Ajustes > Documentos).

El archivo guarda el estado entero de las anotaciones editables, todos sus
campos (los de annots.Annotation, con sus respuestas), y además:

* las anotaciones que el PDF mismo tenía cuando se guardó (``<from-pdf>``: su
  xref y una huella de cómo eran). Al abrirlo, las anotaciones del PDF que
  siguen así quedan ocultas y en su lugar valen las del archivo (cambiadas,
  o borradas si el archivo ya no las tiene); las que el PDF tiene nuevas, o
  cambiadas por otro programa, se muestran también. Las anotaciones que
  vienen del PDF guardan su xref: al volver a guardarlas en el PDF, apply()
  las cambia donde están, en lugar de escribirlas otra vez;
* el giro de cada página con anotaciones, para ponerlas en su sitio si otro
  programa giró la página después;
* las capas mostradas u ocultas;
* de las anotaciones que se quitaron del PDF al pasarlas a este archivo, una
  copia exacta de sus objetos (``<raw>``: su diccionario y sus flujos tal
  como estaban, con su aspecto, sus respuestas, su ventana emergente y las
  claves de otros programas). Al volver al PDF, esa copia se devuelve tal
  cual, y luego se le aplican los cambios que se hicieron aquí, donde está:
  nada de lo que py-pdftools no conoce se pierde (véase capture y restore).

Si la carpeta del PDF no se puede escribir, el archivo va a la carpeta
``annotations`` de la configuración (véase config.py), con un nombre sacado
de la ruta del PDF.

El formato:

    <annotations format="py-pdftools" version="1">
      <document file="libro.pdf" pages="120"/>
      <page number="3" rotation="90"/>
      <layer name="Revisión" shown="false"/>
      <from-pdf xref="12" fingerprint="..."/>
      <annotation kind="highlight" page="3" rect="72 100 300 114" color="#ffeb3b" xref="12">
        <quad>72 100 300 114</quad>
        <contents>Un comentario</contents>
        <reply author="Ana" state="Accepted"><contents>De acuerdo</contents></reply>
      </annotation>
    </annotations>

Los campos de una anotación que no valen lo de siempre son atributos (los
números de un rectángulo, separados por espacios); los textos largos
(contents, rich, overlay), las listas (quad, path, tag, category), la entrada
de crítica textual, las respuestas y los datos (image y data, en base64) son
elementos. Un texto con caracteres que XML no admite va en base64
(``encoding="base64"``).
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import json
import os
import re
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import pymupdf

from ..core import config
from ..core.interface import tr
from . import annots
from .annots import OTHER, AnnotateError, Annotation, Reply
from .exchange import FORMAT, from_data, same_place, to_data

SUFFIX = ".pdfnotes"
VERSION = 1

# Fields written as elements of their own, not as attributes: long texts.
TEXTS = ("contents", "rich", "overlay")
BOOLS = ("dashed", "locked", "overlay_repeat")
BOXES = ("rect", "popup")
# Lo que XML 1.0 no admite: los caracteres de control (menos tabulador, salto de línea y retorno) y los sustitutos.
_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_DEFAULTS = {f.name: f.default for f in dataclasses.fields(Annotation)
             if f.default is not dataclasses.MISSING}
_REPLY_DEFAULTS = {f.name: f.default for f in dataclasses.fields(Reply)}


@dataclasses.dataclass
class Raw:
    """The objects of an annotation taken out of the PDF, exactly as they were (see capture)."""
    id: str
    page: int  # the page it was on
    root: int  # the xref the annotation had
    replies: tuple[int, ...]  # those of its replies, in their order
    in_page: tuple[int, ...]  # those of its objects that the page listed (/Annots): it, its replies, pop-ups
    objects: dict[int, tuple[str, bytes | None]]  # {xref: (its dictionary, its stream as stored, or None)}
    pages: dict[int, int]  # {xref: page number} of the pages its objects pointed to
    layers: dict[int, str]  # {xref: name} of the layers (optional content) they pointed to


@dataclasses.dataclass
class Kept:
    """What a file of annotations kept apart holds."""
    annotations: list[Annotation]
    base: dict[int, str]  # {xref: fingerprint} of the annotations the PDF had when it was written
    rotations: dict[int, int]  # the rotation of each page with annotations, then
    layers: dict[str, bool]
    pages: int = 0
    raws: dict[str, Raw] = dataclasses.field(default_factory=dict)  # {id: copy} (see Annotation.origin)


# --------------------------------------------------------------------- where

def beside(pdf: Path) -> Path:
    """The file of annotations beside the PDF: book.pdf -> book.pdf.pdfnotes."""
    return pdf.with_name(pdf.name + SUFFIX)


def in_config(pdf: Path) -> Path:
    """Where it goes if the folder of the PDF can't be written: a name of its own for each PDF (its path, summed
    up with SHA-1, as the recovery copies), in the configuration's folder."""
    key = hashlib.sha1(str(pdf.resolve()).encode("utf-8")).hexdigest()[:20]
    return config.config_dir() / "annotations" / f"{pdf.stem[:40]}-{key}{SUFFIX}"


def find(pdf: Path) -> Path | None:
    """The file of annotations of the PDF at PDF, if it has one (beside it first)."""
    for place in (beside(pdf), in_config(pdf)):
        if place.is_file():
            return place
    return None


def place_for(pdf: Path) -> Path:
    """Where the annotations of PDF are to be written: where they are already, else beside it, if its folder can
    be written, else in the configuration's folder."""
    found = find(pdf)
    if found is not None:
        return found
    return beside(pdf) if os.access(pdf.parent, os.W_OK) else in_config(pdf)


def remove(pdf: Path) -> None:
    """Remove the files of annotations of PDF (raises OSError)."""
    for place in (beside(pdf), in_config(pdf)):
        place.unlink(missing_ok=True)


# --------------------------------------------------------------------- fingerprints

def fingerprint(a: Annotation) -> str:
    """What tells whether an annotation of the PDF is still as it was: a summary of all its fields but its xref."""
    # sort_keys: el mismo resumen para la misma anotación, sea cual sea el orden de los campos.
    data = to_data(a)
    data.pop("origin", None)  # (whether a copy of it is kept apart says nothing of how it is)
    text = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def base_of(in_pdf: list[Annotation]) -> dict[int, str]:
    """{xref: fingerprint} of the annotations of IN_PDF (as the PDF has them) that py-pdftools edits."""
    return {a.xref: fingerprint(a) for a in in_pdf if a.kind != OTHER and a.xref}


# --------------------------------------------------------------------- writing

def _number(value) -> str:
    # repr da el número más corto que se lee otra vez igual: nada se pierde al ir y volver.
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


def _numbers(values) -> str:
    return " ".join(_number(v) for v in values)


def _put_text(parent: ET.Element, tag: str, text: str, **attrs) -> ET.Element:
    el = ET.SubElement(parent, tag, attrs)
    if _INVALID.search(text):
        # (base64: XML can't hold those characters, not even escaped)
        el.set("encoding", "base64")
        el.text = base64.b64encode(text.encode("utf-8", "surrogatepass")).decode("ascii")
    else:
        el.text = text
    return el


def _put_value(el: ET.Element, name: str, value: str) -> None:
    """A string field: as an attribute, or, if XML can't hold it as one, as an element."""
    if _INVALID.search(value):
        _put_text(el, name, value)
    else:
        el.set(name, value)


def _reply_element(parent: ET.Element, r: Reply) -> None:
    el = ET.SubElement(parent, "reply")
    for name, value in dataclasses.asdict(r).items():
        if name == "contents" or value == _REPLY_DEFAULTS[name]:
            continue
        _put_value(el, name, str(value))
    if r.contents:
        _put_text(el, "contents", r.contents)


def annotation_element(parent: ET.Element, a: Annotation) -> ET.Element:
    el = ET.SubElement(parent, "annotation", {"kind": a.kind, "page": str(a.page), "rect": _numbers(a.rect)})
    data = to_data(a)
    for name, value in data.items():
        if name in ("kind", "page", "rect") or name in TEXTS or value == _DEFAULTS.get(name, object()):
            continue
        if name == "popup":
            if value is not None:
                el.set("popup", _numbers(value))
        elif name == "ends":
            if tuple(value) != _DEFAULTS["ends"]:
                el.set("ends", f"{value[0]} {value[1]}")
        elif name in BOOLS:
            el.set(name, "true" if value else "false")
        elif name in ("opacity", "width", "font_size"):
            el.set(name, _number(value))
        elif name in ("quads", "paths", "tags", "categories", "replies", "critical", "image", "data"):
            continue  # (elements, below)
        else:
            _put_value(el, name, str(value))
    if a.xref:
        el.set("xref", str(a.xref))
    for name in TEXTS:
        if data[name]:
            _put_text(el, name, data[name])
    for q in a.quads:
        ET.SubElement(el, "quad").text = _numbers(q)
    for path in a.paths:
        ET.SubElement(el, "path").text = _numbers(v for point in path for v in point)
    for tag in a.tags:
        _put_text(el, "tag", tag)
    for category in a.categories:
        _put_text(el, "category", category)
    if a.critical is not None:
        crit = ET.SubElement(el, "critical")
        for name, value in dataclasses.asdict(a.critical).items():
            if value:
                _put_value(crit, name, str(value))
    for name in ("image", "data"):
        if data[name]:
            ET.SubElement(el, name).text = data[name]
    for r in a.replies:
        _reply_element(el, r)
    return el


def write(target: Path, doc: pymupdf.Document, pdf_name: str, annotations: list[Annotation],
          base: dict[int, str], layers: dict[str, bool] | None = None, raws: dict[str, Raw] | None = None) -> None:
    """Write ANNOTATIONS (those of the document DOC, the file named PDF_NAME) as TARGET. BASE: {xref: fingerprint}
    of those the PDF has (see base_of); LAYERS: the layers shown or hidden; RAWS: the copies of the objects of
    those taken out of the PDF (only those an annotation still names are kept). Raises OSError."""
    root = ET.Element("annotations", {"format": FORMAT, "version": str(VERSION)})
    ET.SubElement(root, "document", {"file": pdf_name, "pages": str(doc.page_count)})
    editable = [a for a in annotations if a.kind != OTHER]
    for number in sorted({a.page for a in editable if 0 <= a.page < doc.page_count}):
        ET.SubElement(root, "page", {"number": str(number), "rotation": str(doc[number].rotation)})
    for name, shown in (layers or {}).items():
        _put_value(ET.SubElement(root, "layer", {"shown": "true" if shown else "false"}), "name", name)
    for xref, mark in sorted(base.items()):
        ET.SubElement(root, "from-pdf", {"xref": str(xref), "fingerprint": mark})
    # Solo se guardan los xref que siguen siendo del PDF: los demás no significarían nada al abrirlo otra vez.
    for a in editable:
        if a.xref and a.xref not in base:
            a = dataclasses.replace(a, xref=0, replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies))
        annotation_element(root, a)
    used = {a.origin for a in editable if a.origin}
    for raw in (raws or {}).values():
        if raw.id in used:
            raw_element(root, raw)
    ET.indent(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica, como la de las copias de recuperación: un temporal en la misma carpeta, y os.replace.
    fd, tmp = tempfile.mkstemp(suffix=SUFFIX, dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            ET.ElementTree(root).write(f, encoding="utf-8", xml_declaration=True)
            f.write(b"\n")
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------- reading

def _text(el: ET.Element) -> str:
    text = el.text or ""
    if el.get("encoding") == "base64":
        return base64.b64decode(text).decode("utf-8", "surrogatepass")
    return text


def _floats(text: str | None) -> list[float]:
    return [float(v) for v in (text or "").split()]


def _bool(text: str) -> bool:
    if text not in ("true", "false"):
        raise ValueError(text)
    return text == "true"


def _reply_data(el: ET.Element) -> dict:
    # (its attributes, and the elements that hold a value XML couldn't as an attribute)
    data = dict(el.attrib)
    for child in el:
        if child.tag in _REPLY_DEFAULTS:
            data[child.tag] = _text(child)
    return data


def annotation_data(el: ET.Element) -> dict:
    """The fields of the annotation EL, as exchange.from_data takes them."""
    data: dict = {}
    for name, value in el.attrib.items():
        if name in BOXES:
            data[name] = _floats(value)
        elif name == "ends":
            data[name] = value.split()
        elif name in BOOLS:
            data[name] = _bool(value)
        else:
            data[name] = value
    quads, paths, tags, categories, replies = [], [], [], [], []
    for child in el:
        if child.tag == "quad":
            quads.append(_floats(child.text))
        elif child.tag == "path":
            values = _floats(child.text)
            paths.append([values[i:i + 2] for i in range(0, len(values) - 1, 2)])
        elif child.tag == "tag":
            tags.append(_text(child))
        elif child.tag == "category":
            categories.append(_text(child))
        elif child.tag == "reply":
            replies.append(_reply_data(child))
        elif child.tag == "critical":
            crit = dict(child.attrib)
            for part in child:
                crit[part.tag] = _text(part)
            data["critical"] = crit
        elif child.tag in ("image", "data"):
            data[child.tag] = (child.text or "").strip()
        elif child.tag in _DEFAULTS:  # (contents, rich, overlay, or a field XML couldn't hold as an attribute)
            data[child.tag] = _text(child)
    data.update(quads=quads, paths=paths, tags=tags, categories=categories, replies=replies)
    return data


def read(source: Path) -> Kept:
    """The annotations kept in SOURCE (raises AnnotateError if it can't be read). Annotations of kinds this version
    doesn't know are left out."""
    try:
        root = ET.parse(source).getroot()
        if root.tag != "annotations" or root.get("format") != FORMAT:
            raise ValueError(tr("not a file of annotations of py-pdftools"))
        if int(root.get("version", "0")) > VERSION:
            raise ValueError(tr("made by a later version of py-pdftools"))
        kept = Kept([], {}, {}, {})
        for el in root:
            if el.tag == "document":
                kept.pages = int(el.get("pages", "0"))
            elif el.tag == "page":
                kept.rotations[int(el.get("number"))] = int(el.get("rotation", "0")) % 360
            elif el.tag == "layer":
                name = el.get("name")
                if name is None:
                    name = next((_text(c) for c in el if c.tag == "name"), "")
                kept.layers[name] = _bool(el.get("shown", "true"))
            elif el.tag == "from-pdf":
                kept.base[int(el.get("xref"))] = el.get("fingerprint", "")
            elif el.tag == "annotation":
                a = from_data(annotation_data(el), keep_xref=True)
                if a is not None:
                    kept.annotations.append(a)
            elif el.tag == "raw":
                raw = raw_of(el)
                kept.raws[raw.id] = raw
        return kept
    except (OSError, ET.ParseError, ValueError, TypeError, binascii.Error) as e:
        raise AnnotateError(tr("{path} cannot be read: {error}", path=source, error=e)) from None


# --------------------------------------------------------------------- with the PDF

_TURNS: dict[tuple, tuple[pymupdf.Matrix, pymupdf.Matrix]] = {}


def _turns(width: float, height: float, rotation: int) -> tuple[pymupdf.Matrix, pymupdf.Matrix]:
    """The rotation and derotation matrices of a page WIDTH x HEIGHT (not turned) turned ROTATION degrees."""
    key = (round(width, 3), round(height, 3), rotation)
    if key not in _TURNS:
        # Las matrices de MuPDF mismas, de una página en blanco del mismo tamaño: las mismas cuentas que hace al
        # mostrar la página.
        with pymupdf.open() as blank:
            page = blank.new_page(width=width, height=height)
            page.set_rotation(rotation)
            _TURNS[key] = (page.rotation_matrix, page.derotation_matrix)
    return _TURNS[key]


def turned(a: Annotation, page: pymupdf.Page, before: int) -> Annotation:
    """A, placed on PAGE when it was turned BEFORE degrees, as PAGE is shown now."""
    if before == page.rotation:
        return a
    box = page.cropbox  # (the page not turned)
    derotate = _turns(box.width, box.height, before)[1]
    matrix = derotate * page.rotation_matrix

    def point(p):
        q = pymupdf.Point(p) * matrix
        return round(q.x, 2), round(q.y, 2)

    def rect(r):
        q = (pymupdf.Rect(r) * matrix).normalize()
        return round(q.x0, 2), round(q.y0, 2), round(q.x1, 2), round(q.y1, 2)

    return dataclasses.replace(a, rect=rect(a.rect), popup=rect(a.popup) if a.popup else None,
                               quads=tuple(rect(q) for q in a.quads),
                               paths=tuple(tuple(point(p) for p in path) for path in a.paths))


@dataclasses.dataclass
class Combined:
    annotations: list[Annotation]
    new_in_pdf: int = 0  # annotations of the PDF that the file didn't know (added or changed by another program)
    turned: int = 0  # annotations put in place again on a page turned since
    dropped: int = 0  # annotations of pages the document no longer has


def combine(doc: pymupdf.Document, in_pdf: list[Annotation], kept: Kept) -> Combined:
    """The annotations of the document DOC: those KEPT apart, in place of those the PDF has (IN_PDF, as read()
    gives them) that are as they were when they were kept; with those the PDF has that the file doesn't know."""
    # Cada anotación del PDF se reconoce por su huella, no por su xref: si otro programa guardó el PDF entero y
    # cambió los números de los objetos, siguen siendo las mismas.
    by_mark: dict[str, list[int]] = {}
    for xref, mark in kept.base.items():
        by_mark.setdefault(mark, []).append(xref)
    now: dict[int, int] = {}  # {xref then: xref now} of those of the PDF that are as they were
    pdf_replies: dict[int, tuple[Reply, ...]] = {}
    extra: list[Annotation] = []
    others = []
    for a in in_pdf:
        if a.kind == OTHER:
            others.append(a)  # (links and the like: always the PDF's, never kept apart)
            continue
        mark = fingerprint(a)
        if by_mark.get(mark):
            then = a.xref if a.xref in by_mark[mark] else by_mark[mark][0]
            by_mark[mark].remove(then)
            now[then] = a.xref
            pdf_replies[a.xref] = a.replies
        else:
            extra.append(a)
    out = Combined([])
    for a in kept.annotations:
        if not 0 <= a.page < doc.page_count:
            out.dropped += 1
            continue
        xref = now.get(a.xref, 0) if a.xref else 0
        if xref:
            theirs = pdf_replies[xref]
            # Las respuestas conservan sus xref solo si el PDF las tiene en el mismo orden (si no, son nuevas).
            mine = a.replies
            same = len(theirs) >= len(mine) and all(
                dataclasses.replace(r, xref=0) == dataclasses.replace(t, xref=0) for r, t in zip(mine, theirs))
            replies = tuple(dataclasses.replace(r, xref=t.xref if same else 0) for r, t in zip(mine, theirs)) \
                if same else tuple(dataclasses.replace(r, xref=0) for r in mine)
            a = dataclasses.replace(a, xref=xref, replies=replies)
        else:
            a = dataclasses.replace(a, xref=0, replies=tuple(dataclasses.replace(r, xref=0) for r in a.replies))
        before = kept.rotations.get(a.page, doc[a.page].rotation)
        if before != doc[a.page].rotation:
            a = turned(a, doc[a.page], before)
            out.turned += 1
        out.annotations.append(a)
    # Lo nuevo del PDF se muestra también, salvo lo que el archivo ya tiene en el mismo sitio.
    for a in extra:
        if not any(same_place(a, b) for b in out.annotations):
            out.annotations.append(a)
            out.new_in_pdf += 1
    out.annotations.sort(key=lambda a: a.page)  # (stable: in each page, in the order they were)
    out.annotations += others
    out.annotations.sort(key=lambda a: a.page)
    return out


# --------------------------------------------------------------------- exact copies of what is taken out of the PDF

def _ints(text: str | None) -> tuple[int, ...]:
    return tuple(int(v) for v in (text or "").split())


def raw_element(parent: ET.Element, raw: Raw) -> None:
    el = ET.SubElement(parent, "raw", {"id": raw.id, "page": str(raw.page), "root": str(raw.root),
                                       "replies": " ".join(map(str, raw.replies)),
                                       "in-page": " ".join(map(str, raw.in_page))})
    for xref, (text, stream) in sorted(raw.objects.items()):
        obj = _put_text(el, "object", text, number=str(xref))
        if stream is not None:
            obj.set("stream", base64.b64encode(stream).decode("ascii"))
    for xref, number in sorted(raw.pages.items()):
        ET.SubElement(el, "page-ref", {"number": str(xref), "page": str(number)})
    for xref, name in sorted(raw.layers.items()):
        _put_value(ET.SubElement(el, "layer-ref", {"number": str(xref)}), "name", name)


def raw_of(el: ET.Element) -> Raw:
    raw = Raw(el.get("id", ""), int(el.get("page", "0")), int(el.get("root", "0")), _ints(el.get("replies")),
              _ints(el.get("in-page")), {}, {}, {})
    for child in el:
        if child.tag == "object":
            stream = child.get("stream")
            raw.objects[int(child.get("number"))] = (_text(child), base64.b64decode(stream) if stream is not None
                                                     else None)
        elif child.tag == "page-ref":
            raw.pages[int(child.get("number"))] = int(child.get("page"))
        elif child.tag == "layer-ref":
            name = child.get("name")
            raw.layers[int(child.get("number"))] = name if name is not None else \
                next((_text(c) for c in child if c.tag == "name"), "")
    return raw


# Los subtipos de anotación del PDF (las anotaciones suelen no llevar /Type /Annot).
ANNOT_SUBTYPES = {"Text", "Link", "FreeText", "Line", "Square", "Circle", "Polygon", "PolyLine", "Highlight",
                  "Underline", "Squiggly", "StrikeOut", "Stamp", "Caret", "Ink", "Popup", "FileAttachment", "Sound",
                  "Movie", "Widget", "Screen", "PrinterMark", "TrapNet", "Watermark", "3D", "Redact", "RichMedia",
                  "Projection"}
_REF = re.compile(r"(\d+)\s+(\d+)\s+R(?![A-Za-z0-9])")


def _refs(text: str) -> list[tuple[int, int, int]]:
    """The references (N 0 R) of the PDF object TEXT, as (start, end, number): not those inside its strings."""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "(":  # (a literal string: up to its closing parenthesis, nested ones and escapes counted)
            depth, i = 1, i + 1
            while i < n and depth:
                if text[i] == "\\":
                    i += 1
                elif text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                i += 1
            continue
        if ch == "<" and text[i + 1:i + 2] != "<" and (i == 0 or text[i - 1] != "<"):
            end = text.find(">", i)  # (a hexadecimal string)
            i = n if end < 0 else end + 1
            continue
        if ch.isdigit() and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in ".-+")):
            m = _REF.match(text, i)
            if m:
                out.append((m.start(), m.end(), int(m.group(1))))
                i = m.end()
                continue
            while i < n and (text[i].isdigit() or text[i] == "."):
                i += 1
            continue
        i += 1
    return out


def _type_of(doc: pymupdf.Document, xref: int) -> tuple[str, str]:
    """The /Type and /Subtype of the object XREF ('' for none)."""
    kinds = []
    for key in ("Type", "Subtype"):
        kind, value = doc.xref_get_key(xref, key)
        kinds.append(value.lstrip("/") if kind == "name" else "")
    return kinds[0], kinds[1]


def capture(doc: pymupdf.Document, a: Annotation) -> Raw:
    """The objects of the annotation A of DOC (as read() gave it: its xref, and those of its replies), exactly as
    they are: what it points to (its look, its pop-up, fonts and pictures of its look...), but not the pages, the
    layers, nor other annotations (a group's links), which are noted to be pointed to again when it is put back."""
    page_of = {doc.page_xref(i): i for i in range(doc.page_count)}
    layer_of = {xref: info.get("name", "") for xref, info in doc.get_ocgs().items()}
    own = {a.xref, *(r.xref for r in a.replies)}
    raw = Raw(uuid.uuid4().hex[:16], a.page, a.xref, tuple(r.xref for r in a.replies), (), {}, {}, {})
    listed = {x for x, _, _ in doc[a.page].annot_xrefs()}
    todo = sorted(own)
    while todo:
        xref = todo.pop()
        if xref in raw.objects:
            continue
        text = doc.xref_object(xref, compressed=False)
        stream = doc.xref_stream_raw(xref) if doc.xref_is_stream(xref) else None
        raw.objects[xref] = (text, stream)
        for _, _, ref in _refs(text):
            if ref in raw.objects or ref in raw.pages or ref in raw.layers:
                continue
            if ref in page_of:
                raw.pages[ref] = page_of[ref]
            elif ref in layer_of:
                raw.layers[ref] = layer_of[ref]
            elif 0 < ref < doc.xref_length():
                kind, subtype = _type_of(doc, ref)
                annotation = kind == "Annot" or not kind and subtype in ANNOT_SUBTYPES
                # De otras anotaciones solo se copia la ventana emergente; las demás (de un grupo) no son suyas.
                if kind in ("Page", "Pages", "Catalog", "OCG", "OCMD") or \
                        annotation and ref not in own and subtype != "Popup":
                    continue
                todo.append(ref)
    raw.in_page = tuple(x for x in sorted(raw.objects) if x in listed)
    return raw


def _transplant(doc: pymupdf.Document, raw: Raw, page: int) -> int:
    """RAW's objects put in DOC (new numbers), on its page PAGE; returns the new xref of the annotation."""
    new = {old: doc.get_new_xref() for old in raw.objects}
    target = doc.page_xref(page)
    layers = {info.get("name", ""): xref for xref, info in doc.get_ocgs().items()}

    def number(old: int) -> str:
        if old in new:
            return f"{new[old]} 0 R"
        if old in raw.pages:  # (its own page: the one it goes on now; another, if the document still has it)
            p = page if raw.pages[old] == raw.page else raw.pages[old]
            return f"{doc.page_xref(p)} 0 R" if 0 <= p < doc.page_count else "null"
        if old in raw.layers and raw.layers[old] in layers:
            return f"{layers[raw.layers[old]]} 0 R"
        return "null"  # (another annotation, a layer the document hasn't: apply() links them again)

    for old, (text, stream) in raw.objects.items():
        out, last = [], 0
        for start, end, ref in _refs(text):
            out += [text[last:start], number(ref)]
            last = end
        out.append(text[last:])
        if stream is not None:
            # Primero el flujo, tal como estaba guardado; después el diccionario, que devuelve su /Filter.
            doc.update_object(new[old], "<<>>")
            doc.update_stream(new[old], stream, compress=False)
        doc.update_object(new[old], "".join(out))
    kind, value = doc.xref_get_key(target, "Annots")
    added = " ".join(f"{new[x]} 0 R" for x in raw.in_page)
    if kind == "array":
        doc.xref_set_key(target, "Annots", value.rstrip().rstrip("]") + " " + added + "]")
    elif kind == "xref":
        holder = int(value.split()[0])
        doc.update_object(holder, doc.xref_object(holder).rstrip().rstrip("]") + " " + added + "]")
    else:
        doc.xref_set_key(target, "Annots", f"[{added}]")
    return new[raw.root]


def restore(doc: pymupdf.Document, raws: dict[str, Raw], annotations: list[Annotation]) -> list[Annotation]:
    """(Writing ANNOTATIONS into the PDF DOC.) Those taken out of it (with an ORIGIN in RAWS) are put back first,
    exactly as they were; returned with the xrefs they have now, so that apply() changes them there, keeping
    everything else, if they were changed meanwhile. Each copy is put back once (a duplicate is written anew)."""
    done: dict[int, int] = {}  # {index in ANNOTATIONS: xref}
    used = set()
    for i, a in enumerate(annotations):
        raw = raws.get(a.origin)
        if raw is None or a.xref or a.origin in used or not 0 <= a.page < doc.page_count:
            continue
        used.add(a.origin)
        done[i] = _transplant(doc, raw, a.page)
    if not done:
        return annotations
    found = {b.xref: b for b in annots.read(doc) if b.xref in done.values()}
    out = list(annotations)
    for i, xref in done.items():
        a, back = annotations[i], found.get(done[i])
        if back is None:  # (not read back as an annotation py-pdftools edits: written anew)
            continue
        # Cada respuesta toma el xref de la que era igual (o, si cambió, de la que ocupaba su lugar).
        theirs = list(back.replies)
        replies = []
        for n, r in enumerate(a.replies):
            match = next((t for t in theirs if dataclasses.replace(t, xref=0) == dataclasses.replace(r, xref=0)),
                         None) or (theirs[0] if theirs and n < len(back.replies) else None)
            if match is not None:
                theirs.remove(match)
            replies.append(dataclasses.replace(r, xref=match.xref if match else 0))
        # (back in the PDF: no longer a copy kept apart)
        out[i] = dataclasses.replace(a, xref=xref, replies=tuple(replies), origin="")
    return out
