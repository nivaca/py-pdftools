"""The fields of a PDF form, as the window shows and fills them: read() gives each field (a name, a kind, its
value, where its widgets are, what it may take), and fill() writes values into a document. A field may have
several widgets (on several pages, or the buttons of a group of radio buttons); a value is always a text:
the text typed, the option chosen, or, for a check box or a radio button, the name of the state on (as the
PDF names it: 'Yes', 'large'...) or 'Off'."""

from __future__ import annotations

import dataclasses

import pymupdf

KINDS = {pymupdf.PDF_WIDGET_TYPE_TEXT: "text", pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "check",
         pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "radio", pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "combo",
         pymupdf.PDF_WIDGET_TYPE_LISTBOX: "list", pymupdf.PDF_WIDGET_TYPE_BUTTON: "button",
         pymupdf.PDF_WIDGET_TYPE_SIGNATURE: "signature"}
FILLED = ("text", "check", "radio", "combo", "list")  # (las clases en que se escribe un valor)
OFF = "Off"
# las banderas de los campos (PDF 32000, 12.7.3)
READ_ONLY, REQUIRED = 1, 2
MULTILINE, PASSWORD, COMB = 1 << 12, 1 << 13, 1 << 24
EDITABLE_COMBO = 1 << 18


@dataclasses.dataclass(frozen=True)
class Widget:
    page: int
    xref: int
    rect: tuple[float, float, float, float]  # como se muestra la página
    state: str = ""  # of a check box or radio button: the name of its state on


@dataclasses.dataclass(frozen=True)
class Field:
    name: str
    kind: str  # of KINDS
    value: str
    widgets: tuple[Widget, ...]
    options: tuple[str, ...] = ()  # de una lista o un desplegable
    label: str = ""  # what it is, as the form says (its tooltip, /TU); '' if it says nothing
    flags: int = 0
    max_len: int = 0  # (0: cualquier longitud)
    default: str = ""  # its value when the form is reset (/DV)
    scripts: tuple[tuple[str, str], ...] = ()  # (('F', 'AFNumber_Format(...)'), ...): format, keystroke...

    @property
    def page(self) -> int:
        return self.widgets[0].page

    @property
    def read_only(self) -> bool:
        return bool(self.flags & READ_ONLY)

    @property
    def required(self) -> bool:
        return bool(self.flags & REQUIRED)

    @property
    def multiline(self) -> bool:
        return self.kind == "text" and bool(self.flags & MULTILINE)

    @property
    def states(self) -> tuple[str, ...]:
        """The states on of its buttons (a check box, a group of radio buttons), without repeats."""
        return tuple(dict.fromkeys(w.state for w in self.widgets if w.state))

    def script(self, key: str) -> str:
        return dict(self.scripts).get(key, "")

    @property
    def title(self) -> str:
        return self.label or self.name


def _string(doc: pymupdf.Document, xref: int, key: str) -> str:
    """The text KEY of the field of widget XREF, from the widget or the fields above it ('' if none)."""
    seen = set()
    while xref and xref not in seen:
        seen.add(xref)
        kind, value = doc.xref_get_key(xref, key)
        if kind == "string":
            return value
        if kind not in ("null",):
            return value.lstrip("/") if kind == "name" else value
        kind, parent = doc.xref_get_key(xref, "Parent")
        xref = int(parent.split()[0]) if kind == "xref" else 0
    return ""


def _scripts(doc: pymupdf.Document, xref: int) -> tuple[tuple[str, str], ...]:
    """The scripts of the field of widget XREF: format (F), keystroke (K), validation (V), calculation (C)."""
    found = []
    seen = set()
    while xref and xref not in seen:
        seen.add(xref)
        for key in ("F", "K", "V", "C"):
            if key in dict(found):
                continue
            kind, js = doc.xref_get_key(xref, f"AA/{key}/JS")
            if kind == "string" and js.strip():
                found.append((key, js))
            elif kind == "xref":  # (el script en un flujo propio)
                try:
                    found.append((key, doc.xref_stream(int(js.split()[0])).decode("latin-1")))
                except (RuntimeError, ValueError):
                    pass
        kind, parent = doc.xref_get_key(xref, "Parent")
        xref = int(parent.split()[0]) if kind == "xref" else 0
    return tuple(sorted(found))


def _value(w: pymupdf.Widget, kind: str) -> str:
    v = w.field_value
    if kind in ("check", "radio"):
        return OFF if v in (None, False, "", "Off", "False") else str(v) if not isinstance(v, bool) else \
            (w.on_state() or "Yes")
    if isinstance(v, (list, tuple)):  # (una lista con varios elegidos: el primero)
        return str(v[0]) if v else ""
    return "" if v is None else str(v)


def read(doc: pymupdf.Document) -> list[Field]:
    """The fields of DOC, in the order of their pages and of their widgets on each."""
    if not doc.is_pdf or not doc.is_form_pdf:
        return []
    found: dict[str, dict] = {}
    for n in range(doc.page_count):
        page = doc[n]
        for w in page.widgets() or []:
            kind = KINDS.get(w.field_type, "button")
            name = w.field_name or f"#{w.xref}"
            rect = (pymupdf.Rect(w.rect) * page.rotation_matrix).normalize()
            state = ""
            if kind in ("check", "radio"):
                state = w.on_state() or "Yes"
                state = "Yes" if state is True else str(state)
            widget = Widget(n, w.xref, (rect.x0, rect.y0, rect.x1, rect.y1), state)
            if name not in found:
                found[name] = {"name": name, "kind": kind, "value": _value(w, kind), "widgets": [widget],
                               "options": tuple(str(o if not isinstance(o, (list, tuple)) else o[-1])
                                                for o in (w.choice_values or ())),
                               "label": _string(doc, w.xref, "TU"), "flags": w.field_flags or 0,
                               "max_len": w.text_maxlen or 0, "default": _string(doc, w.xref, "DV"),
                               "scripts": _scripts(doc, w.xref)}
            else:
                found[name]["widgets"].append(widget)
                if kind in ("check", "radio") and found[name]["value"] == OFF:
                    found[name]["value"] = _value(w, kind)
    return [Field(**{**f, "widgets": tuple(f["widgets"])}) for f in found.values()]


def _set_text(w: pymupdf.Widget, text: str):
    """TEXT written into the text field of W, its look made again. (Through MuPDF itself: PyMuPDF's
    Widget.update leaves a field as it was when its new value is empty.)"""
    mu = pymupdf.mupdf
    obj = mu.pdf_annot_obj(w._annot)
    mu.pdf_set_field_value(mu.pdf_get_bound_document(obj), obj, text, 1)
    mu.pdf_update_annot(w._annot)


def fill(doc: pymupdf.Document, values: dict[str, str], shown: dict[str, str] | None = None) -> list[str]:
    """Write VALUES ({field name: value}) into the fields of DOC. SHOWN: for a text field, the text its
    widgets show, if not the value itself (a number formatted: see formats.py); the value is still what the
    field holds. Returns the names of the fields written."""
    done = []
    for page in doc:
        for w in page.widgets() or []:
            name = w.field_name
            if name not in values:
                continue
            kind = KINDS.get(w.field_type, "button")
            value = values[name]
            if kind not in FILLED or (w.field_flags or 0) & READ_ONLY:
                continue
            if kind in ("check", "radio"):
                on = w.on_state() or "Yes"
                on = "Yes" if on is True else str(on)
                w.field_value = on if value == on else False
            elif kind == "text":
                _set_text(w, (shown or {}).get(name, value))
            else:
                w.field_value = value
            if kind != "text":
                w.update()
            if kind == "text" and shown and name in shown and shown[name] != value:
                # (el aspecto muestra el texto con formato; el campo guarda el valor tal cual)
                doc.xref_set_key(w.xref, "V", pymupdf.get_pdf_str(value))
                kind_parent, parent = doc.xref_get_key(w.xref, "Parent")
                if kind_parent == "xref" and doc.xref_get_key(int(parent.split()[0]), "V")[0] != "null":
                    doc.xref_set_key(int(parent.split()[0]), "V", pymupdf.get_pdf_str(value))
            if name not in done:
                done.append(name)
    return done


def reset_values(found: list[Field]) -> dict[str, str]:
    """The values that reset the form: each field's default, or empty (Off)."""
    return {f.name: f.default or (OFF if f.kind in ("check", "radio") else "") for f in found
            if f.kind in FILLED and not f.read_only}
