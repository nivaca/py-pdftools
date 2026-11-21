"""The data of forms, in and out: the values of a form written as JSON, CSV (a row of names and one of
values), XFDF or FDF (the formats PDF programs exchange forms in), and read back from any of them; the forms
of many filled copies put in one table (a row for each); and a copy with the fields flattened (what they show
becomes part of the page, and can no longer be changed)."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pymupdf

from ..core import pdfdoc
from ..core.interface import tr
from . import fields

FORMATS = ("json", "csv", "xfdf", "fdf")
XFDF_NS = "http://ns.adobe.com/xfdf/"  # (el espacio de nombres que la norma XFDF fija)


class DataError(Exception):
    pass


def open_form(path: Path, password: str = "") -> pymupdf.Document:
    return pdfdoc.open_pdf(path, password, DataError, DataError)


def button_names(doc: pymupdf.Document) -> set[str]:
    """The fields of DOC whose values are states of buttons (check boxes, radio buttons)."""
    return {f.name for f in fields.read(doc) if f.kind in ("check", "radio")}


def values_of(doc: pymupdf.Document) -> dict[str, str]:
    """{name: value} of the fields of DOC that take a value."""
    return {f.name: f.value for f in fields.read(doc) if f.kind in fields.FILLED}


# ----------------------------------------------------------------- writing

def _pdf_string(text: str) -> str:
    return pymupdf.get_pdf_str(text)


def _pdf_name(text: str) -> str:
    return "/" + "".join(c if c.isalnum() and c.isascii() else "".join(f"#{b:02X}" for b in c.encode())
                         for c in text)


def dumps(values: dict[str, str], fmt: str, source: str = "", names=()) -> str:
    """VALUES written in the format FMT (of FORMATS). SOURCE: the name of the PDF they belong to (XFDF, FDF).
    NAMES: the fields whose values are states of buttons, which FDF writes as names (/Yes), not texts."""
    if fmt == "json":
        return json.dumps(values, ensure_ascii=False, indent=2) + "\n"
    if fmt == "csv":
        out = io.StringIO()
        # (\n: the text is saved as text, which writes \r\n on Windows; csv's own \r\n would
        # become \r\r\n, an empty line after each row)
        w = csv.writer(out, lineterminator="\n")
        w.writerow(values.keys())
        w.writerow(values.values())
        return out.getvalue()
    if fmt == "xfdf":
        root = ET.Element("xfdf", xmlns=XFDF_NS)
        root.set("xml:space", "preserve")
        if source:
            ET.SubElement(root, "f", href=source)
        box = ET.SubElement(root, "fields")
        for name, value in values.items():
            field = ET.SubElement(box, "field", name=name)
            ET.SubElement(field, "value").text = value
        ET.indent(root)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    if fmt == "fdf":
        items = "\n".join(f"<< /T {_pdf_string(n)} /V {_pdf_name(v) if n in names else _pdf_string(v)} >>"
                          for n, v in values.items())
        head = f"/F {_pdf_string(source)} " if source else ""
        return ("%FDF-1.2\n1 0 obj\n<< /FDF << " + head + "/Fields [\n" + items + "\n] >> >>\nendobj\n"
                "trailer\n<< /Root 1 0 R >>\n%%EOF\n")
    raise DataError(tr("Unknown format: {format}", format=fmt))


def table(rows: list[tuple[str, dict[str, str]]]) -> str:
    """CSV of many forms: a column 'file' and one for each field (of any of them), a row for each form."""
    names: dict[str, None] = {}
    for _, values in rows:
        names.update(dict.fromkeys(values))
    out = io.StringIO()
    # (\n: the text is saved as text, which writes \r\n on Windows; csv's own \r\n would
    # become \r\r\n, an empty line after each row)
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["file", *names])
    for file, values in rows:
        w.writerow([file, *(values.get(n, "") for n in names)])
    return out.getvalue()


# ----------------------------------------------------------------- reading

_FDF_STRING = re.compile(rb"\((?:[^()\\]|\\.|\((?:[^()\\]|\\.)*\))*\)|<[0-9A-Fa-f\s]*>|/[^\s/<>\[\]()]+")


def _fdf_text(token: bytes) -> str:
    """A PDF string or name of an FDF, as text."""
    if token.startswith(b"/"):
        return re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), token[1:]).decode("latin-1")
    if token.startswith(b"<"):
        raw = bytes.fromhex(re.sub(rb"\s", b"", token[1:-1]).decode())
    else:
        body = token[1:-1]
        escapes = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}

        def one(m):
            c = m.group(1)
            if c[:1].isdigit():
                return bytes([int(c, 8) & 0xFF])
            return escapes.get(c, c)
        raw = re.sub(rb"\\([0-7]{1,3}|.)", one, body, flags=re.DOTALL)
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace")
    return raw.decode("latin-1")


def _read_fdf(data: bytes) -> dict[str, str]:
    values = {}
    for m in re.finditer(rb"/T\s*(" + _FDF_STRING.pattern + rb")\s*/V\s*(" + _FDF_STRING.pattern + rb")", data):
        values[_fdf_text(m.group(1))] = _fdf_text(m.group(2))
    for m in re.finditer(rb"/V\s*(" + _FDF_STRING.pattern + rb")\s*/T\s*(" + _FDF_STRING.pattern + rb")", data):
        values.setdefault(_fdf_text(m.group(2)), _fdf_text(m.group(1)))
    return values


def _read_xfdf(text: str) -> dict[str, str]:
    root = ET.fromstring(text)
    values = {}

    def walk(node, prefix):
        for field in node:
            if field.tag.rsplit("}", 1)[-1] != "field":
                continue
            name = prefix + field.get("name", "")
            value = next((v for v in field if v.tag.rsplit("}", 1)[-1] == "value"), None)
            if value is not None:
                values[name] = value.text or ""
            walk(field, name + ".")

    for box in root.iter():
        if box.tag.rsplit("}", 1)[-1] == "fields":
            walk(box, "")
    return values


def load(path: Path) -> dict[str, str]:
    """The values of a form written in the file PATH (JSON, CSV, XFDF or FDF, by its extension, or what it
    looks like)."""
    try:
        data = path.read_bytes()
    except OSError as e:
        raise DataError(tr("{path} cannot be read: {error}", path=path, error=e)) from None
    suffix = path.suffix.lower()
    try:
        if suffix == ".fdf" or data.startswith(b"%FDF"):
            return _read_fdf(data)
        text = data.decode("utf-8-sig")
        if suffix in (".xfdf", ".xml") or text.lstrip().startswith("<"):
            return _read_xfdf(text)
        if suffix == ".json" or text.lstrip().startswith("{"):
            found = json.loads(text)
            if not isinstance(found, dict):
                raise ValueError(tr("not an object of names and values"))
            return {str(k): "" if v is None else str(v) for k, v in found.items()}
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2:
            raise ValueError(tr("a row of names and one of values are needed"))
        return dict(zip(rows[0], rows[1], strict=False))
    except (ValueError, ET.ParseError, UnicodeDecodeError) as e:
        raise DataError(tr("{path} cannot be read as the data of a form: {error}", path=path, error=e)) from None


# ----------------------------------------------------------------- copies

def _save(doc: pymupdf.Document, target: Path):
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        doc.save(tmp, garbage=3, deflate=True, encryption=pdfdoc.kept_encryption(doc))
        doc.close()
        os.replace(tmp, target)
    except (OSError, RuntimeError, ValueError) as e:
        Path(tmp).unlink(missing_ok=True)
        raise DataError(tr("{path} cannot be written: {error}", path=target, error=e)) from None


def fill_file(source: Path, values: dict[str, str], target: Path, password: str = "", flatten: bool = False,
              formatted: bool = True) -> list[str]:
    """SOURCE with VALUES in its fields (checked, formatted and summed as the form says, if FORMATTED: see
    formats.py), flattened if FLATTEN, saved as TARGET. Returns the names of the fields filled; Refused (of
    formats.py) if a value doesn't fit its field."""
    from . import formats

    doc = open_form(source, password)
    try:
        found = fields.read(doc)
        by = {f.name: f for f in found}
        values = {n: v for n, v in values.items() if n in by}
        shown: dict[str, str] = {}
        if formatted:
            values = {n: formats.check(by[n], v) if by[n].kind == "text" else v for n, v in values.items()}
            current = {f.name: f.value for f in found} | values
            values |= formats.calculate(found, current, formats.calculation_order(doc))
            shown = {n: t for n, v in values.items() if by[n].kind == "text" and (t := formats.shown(by[n], v)) != v}
        done = fields.fill(doc, values, shown)
        if flatten:
            doc.bake(annots=False, widgets=True)
        _save(doc, target)
        return done
    finally:
        if not doc.is_closed:
            doc.close()


def flatten_file(source: Path, target: Path, password: str = "") -> int:
    """SOURCE with its fields flattened, saved as TARGET. Returns how many fields it had."""
    doc = open_form(source, password)
    try:
        count = len([f for f in fields.read(doc) if f.kind in fields.FILLED])
        doc.bake(annots=False, widgets=True)
        _save(doc, target)
        return count
    finally:
        if not doc.is_closed:
            doc.close()
