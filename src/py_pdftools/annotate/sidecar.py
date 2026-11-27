"""Las anotaciones de un documento guardadas aparte, en un archivo XML junto al
PDF (``libro.pdf.annot.xml``), sin tocar el PDF: la otra manera de guardarlas,
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
* las capas mostradas u ocultas.

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
import dataclasses
import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pymupdf

from ..core import config
from ..core.interface import tr
from .annots import OTHER, AnnotateError, Annotation, Reply
from .exchange import FORMAT, from_data, same_place, to_data

SUFFIX = ".annot.xml"
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
class Kept:
    """What a file of annotations kept apart holds."""
    annotations: list[Annotation]
    base: dict[int, str]  # {xref: fingerprint} of the annotations the PDF had when it was written
    rotations: dict[int, int]  # the rotation of each page with annotations, then
    layers: dict[str, bool]
    pages: int = 0


# --------------------------------------------------------------------- where

def beside(pdf: Path) -> Path:
    """The file of annotations beside the PDF: book.pdf -> book.pdf.annot.xml."""
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
    text = json.dumps(to_data(a), sort_keys=True, ensure_ascii=False)
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
          base: dict[int, str], layers: dict[str, bool] | None = None) -> None:
    """Write ANNOTATIONS (those of the document DOC, the file named PDF_NAME) as TARGET. BASE: {xref: fingerprint}
    of those the PDF has (see base_of); LAYERS: the layers shown or hidden. Raises OSError."""
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
        return kept
    except (OSError, ET.ParseError, ValueError, TypeError) as e:
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
