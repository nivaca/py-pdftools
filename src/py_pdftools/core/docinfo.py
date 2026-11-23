"""What File > PDF properties shows of a document: its metadata and what it is (the PDF version, its pages
and their size, the file, encryption, permissions, whether it is tagged or linearized, has a form, layers,
attachments, signatures), and the fonts it uses. Nothing here uses Qt.

Each item of properties() is (heading, label, value), the label and the heading in English, to be translated
where they are shown; the values are written as the window shows them (dates, sizes)."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from .interface import N_, ntr, tr

DOCUMENT, FILE, CONTENTS, SECURITY = N_("Document"), N_("File"), N_("Contents"), N_("Security")
# (the permissions of PDF, with their names: those a document without them doesn't allow are shown as such)
PERMISSIONS = [(pymupdf.PDF_PERM_PRINT, N_("Print")), (pymupdf.PDF_PERM_PRINT_HQ, N_("Print in high quality")),
               (pymupdf.PDF_PERM_COPY, N_("Copy text and pictures")),
               (pymupdf.PDF_PERM_ANNOTATE, N_("Add comments and fill in forms")),
               (pymupdf.PDF_PERM_FORM, N_("Fill in forms")), (pymupdf.PDF_PERM_ASSEMBLE, N_("Insert, delete and turn pages")),
               (pymupdf.PDF_PERM_MODIFY, N_("Change the document in other ways"))]
_SUBSET = re.compile(r"^[A-Z]{6}\+")  # (el prefijo de una fuente reducida a los caracteres usados: ABCDEF+)


def pdf_date(value: str) -> str:
    """A date of PDF (D:20261121111434-05'00') as 2026-11-21 11:14:34 −05:00; as it is if it can't be read."""
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+-])?(\d{2})?'?(\d{2})?", value or "")
    if not m:
        return value or ""
    y, mo, d, h, mi, s, sign, oh, om = m.groups()
    text = "-".join(p for p in (y, mo, d) if p)
    if h:
        text += f" {h}:{mi or '00'}:{s or '00'}"
        if sign in ("Z", "z"):
            text += " UTC"
        elif sign:
            text += f" {sign.replace('-', '−')}{oh or '00'}:{om or '00'}"
    return text


def file_size(size: int) -> str:
    """SIZE in bytes as 2.3 MB, 840 KB or 512 bytes."""
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return ntr("{count} byte", "{count} bytes", size)


def page_size(rect: pymupdf.Rect) -> str:
    """The size of a page as 210 × 297 mm (8.27 × 11.69 in)."""
    w, h = rect.width, rect.height
    return f"{w * 25.4 / 72:.0f} × {h * 25.4 / 72:.0f} mm ({w / 72:.2f} × {h / 72:.2f} in)"


def _catalog_has(doc: pymupdf.Document, key: str) -> str:
    """The value of KEY in the catalog of DOC ('' if it hasn't it)."""
    kind, value = doc.xref_get_key(doc.pdf_catalog(), key)
    return "" if kind == "null" else value


def properties(doc: pymupdf.Document, path: str | Path | None = None) -> list[tuple[str, str, str]]:
    """[(heading, label, value)] of DOC (opened from PATH, if given)."""
    meta = doc.metadata or {}
    yes, no = tr("Yes"), tr("No")
    items = [(DOCUMENT, N_("Title"), meta.get("title", "")), (DOCUMENT, N_("Subject"), meta.get("subject", "")),
             (DOCUMENT, N_("Author"), meta.get("author", "")), (DOCUMENT, N_("Keywords"), meta.get("keywords", "")),
             (DOCUMENT, N_("Made with"), meta.get("creator", "")),
             (DOCUMENT, N_("Turned into PDF by"), meta.get("producer", "")),
             (DOCUMENT, N_("Created"), pdf_date(meta.get("creationDate", ""))),
             (DOCUMENT, N_("Last changed"), pdf_date(meta.get("modDate", "")))]
    if path is not None:
        p = Path(path)
        items.append((FILE, N_("Name"), p.name))
        items.append((FILE, N_("Folder"), str(p.parent)))
        try:
            items.append((FILE, N_("Size"), file_size(p.stat().st_size)))
        except OSError:
            pass
    items.append((FILE, N_("PDF version"), (meta.get("format") or "").replace("PDF ", "")))
    pdf = doc.is_pdf
    items.append((FILE, N_("Linearized (fast web view)"), yes if pdf and doc.is_fast_webaccess else no))
    items.append((CONTENTS, N_("Pages"), str(doc.page_count)))
    if doc.page_count:
        sizes = {(round(p.rect.width), round(p.rect.height)) for p in doc}
        first = page_size(doc[0].rect)
        items.append((CONTENTS, N_("Page size"), first if len(sizes) == 1 else
                      tr("{size}, and others", size=first)))
    if pdf:
        items.append((CONTENTS, N_("Tagged (structure for accessibility)"),
                      yes if "/Marked true" in _catalog_has(doc, "MarkInfo") or _catalog_has(doc, "StructTreeRoot")
                      else no))
        items.append((CONTENTS, N_("Form fields"), yes if doc.is_form_pdf else no))
        layers = doc.layer_ui_configs() or []
        items.append((CONTENTS, N_("Layers"), str(len(layers)) if layers else no))
        items.append((CONTENTS, N_("Attached files"), str(doc.embfile_count()) if doc.embfile_count() else no))
        signed = any(w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE and w.field_value
                     for page in doc for w in page.widgets() or [])
        items.append((CONTENTS, N_("Digital signatures"), yes if signed else no))
        toc = doc.get_toc(simple=True)
        items.append((CONTENTS, N_("Bookmarks"), str(len(toc)) if toc else no))
    encryption = meta.get("encryption")
    items.append((SECURITY, N_("Encrypted"), encryption or no))
    if pdf and doc.permissions != -1:
        refused = [tr(name) for flag, name in PERMISSIONS if not doc.permissions & flag]
        items.append((SECURITY, N_("Not allowed"), ", ".join(refused) if refused else tr("Nothing")))
    return items


def fonts(doc: pymupdf.Document) -> list[dict]:
    """The fonts DOC uses: [{'name', 'type', 'encoding', 'embedded', 'subset', 'pages'}], by name; 'pages' is
    the list of the page numbers (from 1) that use it."""
    found: dict[int, dict] = {}
    for page in doc:
        for xref, ext, kind, base, _, encoding, *_ in page.get_fonts(full=True):
            font = found.get(xref)
            if font is None:
                name = base or ""
                font = found[xref] = {"name": _SUBSET.sub("", name) or tr("(no name)"), "type": kind,
                                      "encoding": encoding, "embedded": ext not in ("n/a", ""),
                                      "subset": bool(_SUBSET.match(name)), "pages": []}
            if page.number + 1 not in font["pages"]:
                font["pages"].append(page.number + 1)
    # Una misma fuente puede estar varias veces en el archivo (un subconjunto por página, o por capítulo):
    # se muestra una vez, con todas sus páginas.
    merged: dict[tuple, dict] = {}
    for font in found.values():
        key = (font["name"], font["type"], font["encoding"], font["embedded"], font["subset"])
        if key in merged:
            merged[key]["pages"] = sorted(set(merged[key]["pages"]) | set(font["pages"]))
        else:
            merged[key] = font
    return sorted(merged.values(), key=lambda f: (f["name"].lower(), f["type"]))


def page_ranges(pages: list[int]) -> str:
    """[1, 2, 3, 7, 9, 10] as 1-3, 7, 9-10."""
    parts, start = [], None
    for i, n in enumerate(pages):
        if start is None:
            start = n
        if i + 1 == len(pages) or pages[i + 1] != n + 1:
            parts.append(str(start) if start == n else f"{start}-{n}")
            start = None
    return ", ".join(parts)
