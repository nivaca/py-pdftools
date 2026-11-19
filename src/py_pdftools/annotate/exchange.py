"""Annotations out of the document and into it: exported as JSON (all they
hold, to import them again), as a report in Markdown, or as a table (CSV);
imported from such a JSON file or from another copy of the PDF; and copies
of the document flattened (the annotations made part of the pages) or
without annotations.

The JSON file:

    {"format": "py-pdftools", "version": 1,
     "document": {"file": "book.pdf", "pages": 120, "title": "...", "author": "..."},
     "annotations": [{"kind": "highlight", "page": 3, "rect": [...], "color": "#ffeb3b",
                      ..., "page_label": "iv", "marked_text": "..."}, ...]}

holds each annotation with the fields of annots.Annotation (pages from 0;
the image of a stamp in base64), and, to be read by people, the label of its
page and the text it marks.
"""

from __future__ import annotations

import base64
import csv
import html
import dataclasses
import io
import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pymupdf

from . import annots
from .annots import KINDS, MARKUP, AnnotateError, Annotation, Reply
from ..core.interface import ntr, tr

FORMAT = "py-pdftools"
FORMATS = (FORMAT, "py-annotate")  # (py-annotate, where this comes from, wrote the same files)
VERSION = 1


# --------------------------------------------------------------------- annotations as data

def to_data(a: Annotation) -> dict:
    data = dataclasses.asdict(a)
    data.pop("xref")
    data["image"] = base64.b64encode(a.image).decode("ascii") if a.image else ""
    data["data"] = base64.b64encode(a.data).decode("ascii") if a.data else ""
    data["replies"] = [{k: v for k, v in dataclasses.asdict(r).items() if k != "xref"} for r in a.replies]
    return data


def _reply(data: dict, keep_xref: bool) -> Reply:
    names = {f.name for f in dataclasses.fields(Reply)}
    values = {k: (int(v) if k == "xref" else str(v)) for k, v in data.items()
              if k in names and (k != "xref" or keep_xref)}
    return Reply(**values)


def from_data(data: dict, keep_xref: bool = False) -> Annotation | None:
    """The annotation of DATA (None if it isn't one). Its xref is kept only if KEEP_XREF."""
    if not isinstance(data, dict) or data.get("kind") not in KINDS:
        return None
    fields = {f.name: f for f in dataclasses.fields(Annotation)}
    values = {}
    try:
        for name, value in data.items():
            if name not in fields or (name == "xref" and not keep_xref):
                continue
            if name in ("image", "data"):
                value = base64.b64decode(value) if value else b""
            elif name == "rect":
                value = tuple(float(v) for v in value)
                if len(value) != 4:
                    return None
            elif name == "quads":
                value = tuple(tuple(float(v) for v in q) for q in value)
            elif name == "paths":
                value = tuple(tuple((float(p[0]), float(p[1])) for p in path) for path in value)
            elif name == "ends":
                value = (str(value[0]), str(value[1]))
            elif name in ("tags", "categories"):
                value = tuple(str(v) for v in value)
            elif name == "replies":
                value = tuple(_reply(r, keep_xref) for r in value if isinstance(r, dict))
            elif name == "critical":
                value = annots.critical_of(value) if value else None
            elif name in ("opacity", "width", "font_size"):
                value = float(value)
            elif name in ("page", "xref"):
                value = int(value)
            elif name in ("dashed", "locked"):
                value = bool(value)
            else:
                value = str(value)
            values[name] = value
        return Annotation(**values)
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def same_place(a: Annotation, b: Annotation) -> bool:
    """Whether A and B are the same annotation, made twice (or brought from two copies)."""
    return (a.kind, a.page, a.contents) == (b.kind, b.page, b.contents) and \
        all(abs(x - y) < 1.0 for x, y in zip(a.rect, b.rect))


def merged(have: list[Annotation], new: list[Annotation]) -> list[Annotation]:
    """Those of NEW that aren't in HAVE already."""
    out = []
    for a in new:
        if not any(same_place(a, b) for b in have + out):
            out.append(a)
    return out


# --------------------------------------------------------------------- what the document says of them

def page_label(doc: pymupdf.Document, page: int) -> str:
    """The label of PAGE (its printed number: iv, 12...), or its number from 1 if it has none."""
    try:
        label = doc[page].get_label()
    except (RuntimeError, ValueError, IndexError):
        label = ""
    return label or str(page + 1)


_WORDS: dict[tuple[int, int], list] = {}  # (id of the document, page) -> its words, for marked_text


def marked_text(doc: pymupdf.Document, a: Annotation) -> str:
    """The text A marks (if it is a mark over text). The words of each page are read once,
    while the document is the same."""
    if a.kind not in MARKUP or not 0 <= a.page < doc.page_count:
        return ""
    key = (id(doc), a.page)
    if key not in _WORDS:
        if len(_WORDS) > 2000 or any(k[0] != id(doc) for k in _WORDS):
            _WORDS.clear()
        _WORDS[key] = annots.page_text(doc[a.page])
    return annots.text_in(_WORDS[key], a.quads)


def quotation(doc: pymupdf.Document, a: Annotation, name: str = "") -> str:
    """The text marked by A as a quotation, with where it is: “...” (book.pdf, p. 12)."""
    where = tr("p. {page}", page=page_label(doc, a.page))
    return f"“{marked_text(doc, a)}” ({name + ', ' if name else ''}{where})"


def _document_info(doc: pymupdf.Document, path: Path) -> dict:
    meta = doc.metadata or {}
    return {"file": path.name, "pages": doc.page_count, "title": meta.get("title", "") or "",
            "author": meta.get("author", "") or ""}


# --------------------------------------------------------------------- export

def _write_text(target: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(suffix=target.suffix, dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def export_json(doc: pymupdf.Document, path: Path, annotations: list[Annotation], target: Path) -> None:
    items = []
    for a in annotations:
        data = to_data(a)
        data["page_label"] = page_label(doc, a.page)
        data["marked_text"] = marked_text(doc, a)
        items.append(data)
    _write_text(target, json.dumps({"format": FORMAT, "version": VERSION, "document": _document_info(doc, path),
                                    "annotations": items}, ensure_ascii=False, indent=1) + "\n")


def import_json(source: Path) -> list[Annotation]:
    """The annotations of a JSON file of py-pdftools (or of py-annotate) (raises AnnotateError)."""
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AnnotateError(tr("{path} cannot be read: {error}", path=source, error=e)) from None
    if not isinstance(data, dict) or data.get("format") not in FORMATS or not isinstance(data.get("annotations"), list):
        raise AnnotateError(tr("{path} is not a file of annotations of py-pdftools", path=source))
    return [a for a in (from_data(d) for d in data["annotations"]) if a is not None]


def import_pdf(source: Path, password: str = "") -> list[Annotation]:
    """The annotations of another PDF (another copy of the document, annotated by someone else)."""
    doc = annots.open_pdf(source, password)
    try:
        return [dataclasses.replace(a, xref=0) for a in annots.read(doc) if a.kind != annots.OTHER]
    finally:
        doc.close()


CSV_COLUMNS = ("page", "page_label", "kind", "color", "meaning", "author", "created", "modified", "marked_text",
               "contents", "critical_type", "lemma", "reading", "witness", "location", "source", "rationale",
               "confidence")


def export_csv(doc: pymupdf.Document, annotations: list[Annotation], target: Path,
               meaning: Callable[[str], str] = lambda color: "") -> None:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_COLUMNS)
    for a in sorted(annotations, key=lambda a: (a.page, a.rect[1], a.rect[0])):
        w.writerow([a.page + 1, page_label(doc, a.page), a.name(), a.color, meaning(a.color), a.author,
                    annots.date_text(a.created), annots.date_text(a.modified), marked_text(doc, a), a.contents]
                   + ([c.name(), c.lemma, c.reading, c.witness, c.location, c.source, c.rationale,
                       tr(annots.CONFIDENCE.get(c.confidence, "")) if c.confidence else ""]
                      if (c := a.critical) else [""] * 8))
    _write_text(target, out.getvalue())


def report(doc: pymupdf.Document, path: Path, annotations: list[Annotation],
           color_name: Callable[[str], str] = lambda color: color) -> str:
    """A report of ANNOTATIONS, in Markdown: how many there are of each kind,
    colour and author, then each of them, page by page, with the text it
    marks and its comment."""
    info = _document_info(doc, path)
    lines = ["# " + tr("Annotations of {name}", name=info["title"] or path.name), ""]
    pages = len({a.page for a in annotations})
    lines += [ntr("{count} annotation", "{count} annotations", len(annotations)) + ", "
              + ntr("on {count} page", "on {count} pages", pages) + ".", ""]
    for title, counter in ((tr("By kind"), Counter(a.name() for a in annotations)),
                           (tr("By colour"), Counter(color_name(a.color) for a in annotations)),
                           (tr("By author"), Counter(a.author or tr("(no author)") for a in annotations))):
        if not counter:
            continue
        lines += [f"## {title}", ""]
        lines += [f"* {name}: {count}" for name, count in counter.most_common()]
        lines.append("")
    page = None
    for a in sorted(annotations, key=lambda a: (a.page, a.rect[1], a.rect[0])):
        if a.page != page:
            page = a.page
            label = page_label(doc, page)
            heading = tr("Page {page}", page=page + 1) + (f" ({label})" if label != str(page + 1) else "")
            lines += [f"## {heading}", ""]
        head = f"* **{a.name()}** ({color_name(a.color)})"
        if a.author:
            head += ", " + tr("by {author}", author=a.author)
        when = annots.date_text(a.modified or a.created)
        if when:
            head += f", {when}"
        lines.append(head)
        text = marked_text(doc, a)
        if text:
            lines += ["", f"  > {text}"]
        if a.contents.strip():
            lines += [""] + ["  " + line for line in a.contents.strip().splitlines()]
        if a.critical:
            lines += ["", "  " + apparatus_entry(doc, a)]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def apparatus_entry(doc: pymupdf.Document, a: Annotation, with_page: bool = False) -> str:
    """The entry of textual criticism of A, as a line of an apparatus: 'lemma ] reading W
    (Variant reading; probable). Source. Rationale.'"""
    c = a.critical
    lemma = c.lemma or marked_text(doc, a)
    head = (f"*{lemma}* ]" if lemma else "]") + (f" {c.reading}" if c.reading else "") \
        + (f" {c.witness}" if c.witness else "") + (f" ({c.location})" if c.location else "")
    kind = c.name() + (f"; {tr(annots.CONFIDENCE[c.confidence]).lower()}" if c.confidence in annots.CONFIDENCE
                       and c.confidence else "")
    text = f"{head} — {kind}." + "".join(f" {part.rstrip('.')}." for part in (c.source, c.rationale) if part)
    if with_page:
        label = page_label(doc, a.page)
        text = f"**{tr('p. {page}', page=label)}** " + text
    return text


def apparatus(doc: pymupdf.Document, path: Path, annotations: list[Annotation]) -> str:
    """The critical apparatus of ANNOTATIONS (those with an entry of textual criticism), in
    Markdown: its entries in the order of the text."""
    info = _document_info(doc, path)
    entries = sorted((a for a in annotations if a.critical), key=lambda a: (a.page, a.rect[1], a.rect[0]))
    lines = ["# " + tr("Critical apparatus of {name}", name=info["title"] or path.name), ""]
    lines += [ntr("{count} entry", "{count} entries", len(entries)) + ".", ""]
    lines += [f"* {apparatus_entry(doc, a, with_page=True)}" for a in entries]
    return "\n".join(lines).rstrip() + "\n"


def export_apparatus(doc: pymupdf.Document, path: Path, annotations: list[Annotation], target: Path) -> int:
    """Write the critical apparatus of ANNOTATIONS (see apparatus) as TARGET; returns how many entries."""
    _write_text(target, apparatus(doc, path, annotations))
    return sum(1 for a in annotations if a.critical)


def export_markdown(doc: pymupdf.Document, path: Path, annotations: list[Annotation], target: Path,
                    color_name: Callable[[str], str] = lambda color: color) -> None:
    _write_text(target, report(doc, path, annotations, color_name))


# --------------------------------------------------------------------- copies of the document

def save_flattened(source: Path, annotations: list[Annotation], target: Path, password: str = "") -> None:
    """A copy of SOURCE with ANNOTATIONS made part of its pages: they are seen,
    and printed, but are no longer annotations (raises AnnotateError)."""
    doc = annots.open_pdf(source, password)
    try:
        annots.apply(doc, annotations)
        doc.bake(annots=True, widgets=False)
        annots.save_doc(doc, target)
    except (OSError, RuntimeError, ValueError) as e:
        raise AnnotateError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    finally:
        doc.close()


def save_partly_flattened(source: Path, annotations: list[Annotation], target: Path, password: str = "",
                          kinds: set[str] = frozenset()) -> None:
    """A copy of SOURCE with ANNOTATIONS, those of KINDS made part of the pages
    and the others left as annotations (raises AnnotateError). For PDF/A and
    PDF/X: Ghostscript removes some kinds of annotations, which are kept this way."""
    doc = annots.open_pdf(source, password)
    try:
        annots.apply(doc, annotations)
        # (only those of KINDS stay as annotations, to be flattened; the others are written again after)
        for page in doc:
            for xref in [a.xref for a in page.annots() or []
                         if (kind := annots.kind_of(doc, a)) is not None and kind not in kinds]:
                page.delete_annot(page.load_annot(xref))
        doc.bake(annots=True, widgets=False)
        annots.apply(doc, [dataclasses.replace(a, xref=0) for a in annotations if a.kind not in kinds])
        annots.save_doc(doc, target)
    except (OSError, RuntimeError, ValueError) as e:
        raise AnnotateError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    finally:
        doc.close()


def kinds_lost(annotations: list[Annotation], target: Path, password: str = "") -> Counter:
    """How many annotations of each kind of ANNOTATIONS are not in TARGET (a
    copy of them made by another program)."""
    doc = annots.open_pdf(target, password)
    try:
        have = Counter("polygon" if a.kind == "cloud" else a.kind for a in annots.read(doc))
    finally:
        doc.close()
    want = Counter("polygon" if a.kind == "cloud" else a.kind for a in annotations)
    return want - have


def save_without(source: Path, target: Path, password: str = "") -> int:
    """A copy of SOURCE without any annotation (links and form fields stay).
    Returns how many were taken out (raises AnnotateError)."""
    doc = annots.open_pdf(source, password)
    try:
        count = 0
        for page in doc:
            for xref in [a.xref for a in page.annots() or [] if a.type[0] != pymupdf.PDF_ANNOT_POPUP]:
                page.delete_annot(page.load_annot(xref))
                count += 1
        annots.save_doc(doc, target)
    except (OSError, RuntimeError, ValueError) as e:
        raise AnnotateError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    finally:
        doc.close()
    return count


# --------------------------------------------------------------------- XFDF

XFDF_NS = "http://ns.adobe.com/xfdf/"  # (the namespace the format requires, ISO 19444-1)
_XFDF_ELEMENTS = {"highlight": "highlight", "underline": "underline", "strikeout": "strikeout",
                  "squiggly": "squiggly", "caret": "caret", "note": "text", "freetext": "freetext",
                  "callout": "freetext", "area": "square", "rect": "square", "ellipse": "circle",
                  "polygon": "polygon", "cloud": "polygon", "line": "line", "arrow": "line", "polyline": "polyline",
                  "ink": "ink", "marker": "ink", "stamp": "stamp"}


def _xy(values) -> str:
    return ",".join(f"{v:g}" for v in values)


def _pdf_box(page: pymupdf.Page, rect) -> list[float]:
    a, b = annots.to_pdf(page, (rect[0], rect[1])), annots.to_pdf(page, (rect[2], rect[3]))
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]


def export_xfdf(doc: pymupdf.Document, path: Path, annotations: list[Annotation], target: Path) -> None:
    """ANNOTATIONS as XFDF, the exchange format of annotations of PDF programs (their replies and
    review states too; tags and categories are py-pdftools' own, and are left out)."""
    import xml.etree.ElementTree as ET

    root = ET.Element("xfdf", {"xmlns": XFDF_NS, "xml:space": "preserve"})
    ET.SubElement(root, "f", {"href": path.name})
    items = ET.SubElement(root, "annots")
    for n, a in enumerate((a for a in annotations if a.kind not in (annots.OTHER, "attachment")), 1):
        if not 0 <= a.page < doc.page_count:
            continue
        page = doc[a.page]
        name = f"py-pdftools-{n}"
        attrs = {"page": str(a.page), "name": name, "title": a.author, "color": a.color.upper(),
                 "opacity": f"{a.opacity:g}", "date": a.modified or annots.now(),
                 "creationdate": a.created or annots.now(), "flags": "print" + (",locked" if a.locked else "")}
        box = _pdf_box(page, a.rect)
        if a.kind in MARKUP:
            box = _pdf_box(page, annots.union(a.quads))
            attrs["coords"] = _xy(v for q in a.quads for corner in ((q[0], q[1]), (q[2], q[1]), (q[0], q[3]),
                                                                    (q[2], q[3]))
                                  for v in annots.to_pdf(page, corner))
        elif a.kind in ("rect", "ellipse", "area", "freetext", "callout", "polygon", "cloud", "polyline"):
            attrs["width"] = f"{0 if a.kind == 'area' else a.width:g}"
            if a.fill and a.kind not in ("freetext", "callout"):
                attrs["interior-color"] = a.fill.upper()
            if a.dashed:
                attrs["style"], attrs["dashes"] = "dash", "3,3"
            if a.kind == "cloud":
                attrs["style"], attrs["intensity"] = "cloudy", "1"
            if a.kind == "area":
                attrs["subject"] = annots.AREA_SUBJECT
        if a.kind in ("line", "arrow"):
            attrs["start"] = _xy(annots.to_pdf(page, a.paths[0][0]))
            attrs["end"] = _xy(annots.to_pdf(page, a.paths[0][-1]))
            ends = a.ends if a.kind == "line" or a.ends != ("None", "None") else ("None", "OpenArrow")
            attrs["head"], attrs["tail"] = ends
            attrs["width"] = f"{a.width:g}"
        if a.kind == "polyline":
            attrs["head"], attrs["tail"] = a.ends
        if a.kind in ("ink", "marker"):
            attrs["width"] = f"{a.width:g}"
            if a.kind == "marker":
                attrs["subject"] = annots.MARKER_SUBJECT
        if a.kind == "note":
            attrs["icon"] = a.icon
        if a.kind == "stamp":
            attrs["icon"] = a.stamp or "Draft"
        if a.kind == "callout" and a.paths:
            tip = a.paths[0][0]
            attrs["callout"] = _xy(v for p in (tip, annots.anchor(a.rect, tip)) for v in annots.to_pdf(page, p))
            attrs["head"] = a.ends[1]
            attrs["intent"] = "FreeTextCallout"
        if a.kind in ("freetext", "callout"):
            attrs["justification"] = {"center": "centered", "right": "right"}.get(a.align, "left")
        if a.kind in ("ink", "marker", "polygon", "cloud", "polyline", "line", "arrow"):
            box = _pdf_box(page, annots.frame(a.kind, a.paths, a.width))
        attrs["rect"] = _xy(box)
        element = ET.SubElement(items, _XFDF_ELEMENTS[a.kind], attrs)
        if a.contents:
            ET.SubElement(element, "contents").text = a.contents
        if a.kind in ("freetext", "callout"):
            family = {"tiro": "TiRo", "cour": "Cour"}.get(a.font, "Helv")
            r, g, b = annots.rgb(a.color)
            ET.SubElement(element, "defaultappearance").text = f"{r:g} {g:g} {b:g} rg /{family} {a.font_size:g} Tf"
            if a.fill:
                element.set("color", a.fill.upper())  # (in XFDF, the colour of a text box is its fill)
            else:
                del element.attrib["color"]
        if a.kind in ("polygon", "cloud", "polyline"):
            ET.SubElement(element, "vertices").text = ";".join(_xy(annots.to_pdf(page, p)) for p in a.paths[0])
        if a.kind in ("ink", "marker"):
            ink = ET.SubElement(element, "inklist")
            for stroke in a.paths:
                ET.SubElement(ink, "gesture").text = ";".join(_xy(annots.to_pdf(page, p)) for p in stroke)
        for m, r in enumerate(a.replies, 1):
            reply = {"page": str(a.page), "name": f"{name}-r{m}", "inreplyto": name, "title": r.author,
                     "rect": _xy(box), "date": r.modified or r.created or annots.now(),
                     "creationdate": r.created or annots.now(), "icon": "Comment"}
            if r.state:
                reply["state"], reply["statemodel"] = r.state, "Review"
            ET.SubElement(ET.SubElement(items, "text", reply), "contents").text = r.contents
    ET.indent(root)
    _write_text(target, '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n")


def _floats(text: str | None) -> list[float]:
    return [float(v) for v in (text or "").replace(";", ",").split(",") if v.strip()]


def _pairs(values: list[float]) -> list[tuple[float, float]]:
    return [(values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)]


def _color(value: str | None) -> str:
    value = (value or "").strip().lower()
    return value if len(value) == 7 and value.startswith("#") else ""


def import_xfdf(doc: pymupdf.Document, source: Path) -> list[Annotation]:
    """The annotations of an XFDF file (raises AnnotateError), on the pages of DOC."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(source).getroot()
    except (OSError, ET.ParseError) as e:
        raise AnnotateError(tr("{path} cannot be read: {error}", path=source, error=e)) from None
    if root.tag.split("}")[-1] != "xfdf":
        raise AnnotateError(tr("{path} is not a file of annotations of py-pdftools", path=source))
    items = next((e for e in root if e.tag.split("}")[-1] == "annots"), None)
    if items is None:
        return []
    found: dict[str, Annotation] = {}
    replies: list[tuple[str, Reply]] = []
    for e in items:
        tag = e.tag.split("}")[-1]
        try:
            number = int(e.get("page", "0"))
        except ValueError:
            continue
        if not 0 <= number < doc.page_count:
            continue
        page = doc[number]
        contents = "".join(c.text or "" for c in e if c.tag.split("}")[-1] == "contents")
        author, created, modified = e.get("title", ""), e.get("creationdate", ""), e.get("date", "")
        if tag == "text" and e.get("inreplyto"):
            replies.append((e.get("inreplyto"), Reply(author, contents, e.get("state", "") if e.get("state") in
                                                      annots.STATES else "", created, modified)))
            continue
        box = _floats(e.get("rect"))
        if len(box) != 4:
            continue
        a_, b_ = annots.from_pdf(page, (box[0], box[1])), annots.from_pdf(page, (box[2], box[3]))
        rect = annots.normalized(a_ + b_)
        common = {"page": number, "rect": rect, "color": _color(e.get("color")) or "#000000",
                  "opacity": float(e.get("opacity", "1") or 1), "contents": contents, "author": author,
                  "created": created, "modified": modified, "locked": "locked" in e.get("flags", ""),
                  "dashed": e.get("style") == "dash"}
        width = float(e.get("width", "1.5") or 1.5)
        a: Annotation | None = None
        if tag in ("highlight", "underline", "strikeout", "squiggly"):
            points = [annots.from_pdf(page, p) for p in _pairs(_floats(e.get("coords")))]
            quads = tuple(annots.bounds(points[i:i + 4]) for i in range(0, len(points) - 3, 4)) or (rect,)
            a = Annotation(tag, rect=annots.union(quads), quads=tuple(tuple(round(v, 2) for v in q) for q in quads),
                           **{k: v for k, v in common.items() if k != "rect"})
        elif tag in ("square", "circle"):
            kind = "area" if e.get("subject") == annots.AREA_SUBJECT else ("rect" if tag == "square" else "ellipse")
            half = width / 2 if kind != "area" else 0
            inner = (rect[0] + half, rect[1] + half, rect[2] - half, rect[3] - half)
            a = Annotation(kind, width=width, fill=_color(e.get("interior-color")),
                           **dict(common, rect=inner if inner[2] > inner[0] and inner[3] > inner[1] else rect))
        elif tag in ("line", "polygon", "polyline", "ink"):
            if tag == "line":
                paths = ((annots.from_pdf(page, tuple(_floats(e.get("start")))),
                          annots.from_pdf(page, tuple(_floats(e.get("end"))))),)
                ends = (e.get("head", "None"), e.get("tail", "None"))
                kind = "arrow" if any(x.endswith("Arrow") for x in ends) else "line"
            elif tag == "ink":
                gestures = [g.text for c in e if c.tag.split("}")[-1] == "inklist" for g in c]
                paths = tuple(tuple(annots.from_pdf(page, p) for p in _pairs(_floats(g))) for g in gestures)
                kind, ends = ("marker" if e.get("subject") == annots.MARKER_SUBJECT else "ink"), ("None", "None")
            else:
                text = next((c.text for c in e if c.tag.split("}")[-1] == "vertices"), "")
                paths = (tuple(annots.from_pdf(page, p) for p in _pairs(_floats(text))),)
                kind = "cloud" if e.get("style") == "cloudy" else tag
                ends = (e.get("head", "None"), e.get("tail", "None")) if tag == "polyline" else ("None", "None")
            if not paths or not paths[0]:
                continue
            ends = tuple(x if x in annots.ENDS else "None" for x in ends)
            a = Annotation(kind, width=width, fill=_color(e.get("interior-color")), paths=paths, ends=ends,
                           **dict(common, rect=annots.frame(kind, paths, width)))
        elif tag == "freetext":
            da = next((c.text for c in e if c.tag.split("}")[-1] == "defaultappearance"), "") or ""
            size = annots.DA_SIZE.search(da)
            color = annots.DA_COLOR.search(da)
            font = annots.DA_FONT.search(da)
            callout = _pairs(_floats(e.get("callout")))
            kind = "callout" if callout or e.get("intent") == "FreeTextCallout" else "freetext"
            a = Annotation(kind, font_size=float(size[1]) if size else 12.0,
                           font=annots._DA_FONTS.get(font[1].lower(), "helv") if font else "helv",
                           align={"centered": "center", "right": "right"}.get(e.get("justification", ""), "left"),
                           width=float(e.get("width", "0") or 0), fill=_color(e.get("color")),
                           paths=((annots.from_pdf(page, callout[0]),),) if kind == "callout" and callout else (),
                           ends=("None", e.get("head", "OpenArrow") if e.get("head") in annots.ENDS else "OpenArrow"),
                           **dict(common, color=(annots.hex_color(color[1].split()) if color else "") or "#000000"))
            if kind != "callout" or not a.paths:
                a = dataclasses.replace(a, kind="freetext", ends=("None", "None"))
        elif tag in ("text", "caret"):
            a = Annotation("note" if tag == "text" else "caret",
                           icon=e.get("icon", "Note") if e.get("icon") in annots.ICONS else "Note", **common)
        elif tag == "stamp":
            name = e.get("icon", "")
            if name in annots.STAMPS:
                image, _ = annots.standard_stamp(name)
                a = Annotation("stamp", stamp=name, image=image, **common)
        if a is not None:
            found[e.get("name", str(len(found)))] = a
    for parent, reply in replies:
        if parent in found:
            found[parent] = dataclasses.replace(found[parent], replies=found[parent].replies + (reply,))
    return list(found.values())


# --------------------------------------------------------------------- a summary of the comments

CSS = "* {font-family: sans-serif; font-size: SIZEpt; line-height: 1.25} p {margin: 0}"


def save_summary(source: Path, annotations: list[Annotation], target: Path, password: str = "",
                 color_name: Callable[[str], str] = lambda color: color) -> int:
    """A PDF that shows each page with annotations, with them on it (numbered), beside a list
    of them: their kind, colour, author, date, the text they mark, their comment and replies.
    Returns how many pages it has (raises AnnotateError)."""
    doc = annots.open_pdf(source, password)
    out = pymupdf.open()
    try:
        annots.apply(doc, annotations)
        doc.bake(annots=True, widgets=False)
        column, margin, size = 260.0, 18.0, 8.5
        by_page: dict[int, list[Annotation]] = {}
        for a in sorted(annotations, key=lambda a: (a.page, a.rect[1], a.rect[0])):
            if 0 <= a.page < doc.page_count:
                by_page.setdefault(a.page, []).append(a)
        for number, items in by_page.items():
            src = doc[number]
            w, h = src.rect.width, src.rect.height
            page = out.new_page(width=w + column + 2 * margin, height=h)
            page.show_pdf_page(pymupdf.Rect(0, 0, w, h), doc, number)
            for n, a in enumerate(items, 1):  # (a number beside each annotation)
                x, y = a.rect[0], a.rect[1]
                spot = pymupdf.Rect(max(x - 13, 0), max(y - 13, 0), max(x - 13, 0) + 12, max(y - 13, 0) + 12)
                page.draw_circle((spot.tl + spot.br) / 2, 6, color=(0.75, 0.1, 0.1), fill=(1, 1, 1), width=1)
                page.insert_textbox(spot + (0, 2, 0, 2), str(n), fontsize=7, fontname="helv", color=(0.75, 0.1, 0.1),
                                    align=pymupdf.TEXT_ALIGN_CENTER)
            label = page_label(doc, number)
            heading = tr("Page {page}", page=number + 1) + (f" ({label})" if label != str(number + 1) else "")
            x0, y = w + margin, margin

            def title(page, text):  # (the heading of the column)
                page.insert_htmlbox(pymupdf.Rect(x0, margin, x0 + column, margin + 20),
                                    f"<b>{html.escape(text)}</b>", css=CSS.replace("SIZE", "11"), scale_low=1)

            title(page, heading)
            y += 24
            for n, a in enumerate(items, 1):
                head = f"<b>{n}. {html.escape(a.name())}</b> ({html.escape(color_name(a.color))})"
                if a.author:
                    head += ", " + html.escape(tr("by {author}", author=a.author))
                if a.modified or a.created:
                    head += f", {annots.date_text(a.modified or a.created)}"
                parts = [head]
                text = marked_text(doc, a) if a.kind in MARKUP else ""
                if text:
                    parts.append(f"<i>“{html.escape(text)}”</i>")
                if a.contents.strip():
                    parts.append(html.escape(a.contents.strip()).replace("\n", "<br>"))
                for r in a.replies:
                    state = f" [{html.escape(tr(annots.STATES[r.state]))}]" if r.state else ""
                    words = f": {html.escape(r.contents)}" if r.contents else ""
                    parts.append(f"&#8212; {html.escape(r.author or tr('(no author)'))}{state}{words}")
                entry = "<p>" + "<br>".join(parts) + "</p>"
                while True:
                    box = pymupdf.Rect(x0, y, x0 + column, h - margin)
                    spare, _ = page.insert_htmlbox(box, entry, css=CSS.replace("SIZE", f"{size:g}"), scale_low=1)
                    if spare >= 0:
                        y = box.y1 - spare + 6
                        break
                    # (no room left: on a page of its own, after this one)
                    page = out.new_page(width=w + column + 2 * margin, height=h)
                    title(page, heading + " " + tr("(continued)"))
                    y = margin + 24
                    if y + 40 > h:
                        break
        if not out.page_count:
            out.new_page().insert_text((72, 72), tr("This document has no annotations."), fontsize=12)
        out.set_metadata({"title": tr("Annotations of {name}", name=source.name), "producer": "py-pdftools"})
        annots.save_doc(out, target)
        return out.page_count
    except (OSError, RuntimeError, ValueError) as e:
        raise AnnotateError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    finally:
        out.close()
        doc.close()
