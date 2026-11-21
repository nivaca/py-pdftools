"""Hidden information: what a PDF holds besides what its pages show.
inspect() says what a document has of each kind; remove() takes out the
kinds chosen.
"""

from __future__ import annotations

import re

import pikepdf
import pymupdf

from ..core.interface import N_

# (key, name shown, what it is)
KINDS = [
    ("metadata", N_("Metadata"), N_("Title, author, subject, keywords, the program that made it (and the XMP)")),
    ("attachments", N_("Attached files"), N_("Files attached to the document or to its pages")),
    ("bookmarks", N_("Bookmarks"), N_("The outline, which may show headings of removed pages")),
    ("page_labels", N_("Page labels"), N_("The numbers a viewer shows for the pages (82, 83…), which may tell where "
                                          "the pages came from; without them they are 1, 2, 3…")),
    ("comments", N_("Comments and markups"), N_("Notes, highlights and other annotations (links are below)")),
    ("forms", N_("Form fields"), N_("Fields and their values; they are flattened: what they show stays, as "
                                    "part of the page")),
    ("hidden_text", N_("Hidden text"), N_("Text that is not drawn (invisible), such as an OCR layer")),
    ("layers", N_("Hidden layers"), N_("Layers switched off, which a viewer doesn't show until they are switched on: "
                                       "what they hold is removed, and so are their names")),
    ("links", N_("Links, actions and JavaScript"), N_("Links to pages and web addresses, actions and scripts")),
    ("thumbnails", N_("Page thumbnails"), N_("Small pictures of the pages, made before any redaction")),
    ("unused", N_("Deleted or unused content"), N_("Objects that nothing uses any more, as earlier versions of "
                                                   "the document leave them")),
]
DEFAULT = ("metadata", "attachments", "comments", "hidden_text", "layers", "links", "thumbnails", "unused")


def _hidden_text_spans(page: pymupdf.Page) -> int:
    """How many pieces of text of PAGE are not drawn (text render mode 3)."""
    n = 0
    for trace in page.get_texttrace():
        # El tipo 3 es el modo de render 3 (texto que no se pinta), el de las capas de OCR; la opacidad 0
        # atrapa el texto pintado pero transparente.
        if trace.get("type") == 3 or trace.get("opacity", 1) == 0:
            n += 1
    return n


def inspect(doc: pymupdf.Document) -> dict[str, int]:
    """{kind: how many} of what DOC holds (0: none; -1: some, not counted)."""
    found = {k: 0 for k, _, _ in KINDS}
    # 'format' and 'encryption' are not written by anyone: PyMuPDF derives them from the file.
    meta = {k: v for k, v in (doc.metadata or {}).items() if v and k not in ("format", "encryption")}
    found["metadata"] = len(meta) + (1 if doc.get_xml_metadata().strip() else 0)
    found["attachments"] = doc.embfile_count()
    found["bookmarks"] = len(doc.get_toc(simple=True))
    found["page_labels"] = len(doc.get_page_labels())
    found["layers"] = len(hidden_layers(doc))
    for page in doc:
        for annot in page.annots() or []:
            # Un adjunto de página es una anotación, pero se cuenta con los adjuntos; los enlaces, las marcas
            # /Redact y los campos de formulario no son comentarios.
            if annot.type[0] == pymupdf.PDF_ANNOT_FILE_ATTACHMENT:
                found["attachments"] += 1
            elif annot.type[0] not in (pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_REDACT, pymupdf.PDF_ANNOT_WIDGET):
                found["comments"] += 1
        found["forms"] += len(list(page.widgets() or []))
        found["links"] += len(page.get_links())
        found["hidden_text"] += _hidden_text_spans(page)
        # Búsqueda aproximada: /Thumb en el texto del diccionario de la página. Las páginas sin
        # contenido se saltan.
        if page.get_contents() and "/Thumb" in doc.xref_object(page.xref):
            found["thumbnails"] += 1
    try:
        # Document-level JavaScript or an OpenAction counts as one more item under 'links'.
        if doc.xref_get_key(doc.pdf_catalog(), "Names/JavaScript")[0] != "null" \
                or doc.xref_get_key(doc.pdf_catalog(), "OpenAction")[0] != "null":
            found["links"] += 1
    except (RuntimeError, ValueError):
        pass
    found["unused"] = -1  # (known only once the file is written again)
    return found


def remove(doc: pymupdf.Document, kinds: set[str]) -> None:
    """Take out of DOC (in memory) the KINDS of hidden information. The
    'unused' objects go when DOC is saved with garbage collection, as
    write_redacted always does."""
    if "forms" in kinds:  # (flattened first: its looks stay on the page)
        # annots=False: only the fields are baked into the page; comments are handled just below.
        doc.bake(annots=False, widgets=True)
    if "comments" in kinds:
        for page in doc:
            for annot in list(page.annots() or []):
                if annot.type[0] not in (pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_REDACT,
                                         pymupdf.PDF_ANNOT_FILE_ATTACHMENT):
                    page.delete_annot(annot)
    # redactions=False: las marcas /Redact quedan para redact(), que las quita antes de aplicar los
    # recuadros; clean_pages=False deja intacto el contenido de las páginas.
    doc.scrub(attached_files="attachments" in kinds, clean_pages=False, embedded_files="attachments" in kinds,
              hidden_text="hidden_text" in kinds, javascript="links" in kinds, metadata="metadata" in kinds,
              redactions=False, remove_links="links" in kinds, reset_fields=False, reset_responses=False,
              thumbnails="thumbnails" in kinds, xml_metadata="metadata" in kinds)
    if "metadata" in kinds:
        doc.set_metadata({})
    if "layers" in kinds:
        remove_hidden_layers(doc)
    if "bookmarks" in kinds:
        doc.set_toc([])
    if "page_labels" in kinds:
        doc.set_page_labels([])


# ----------------------------------------------------------------- hidden layers (optional content)

_REF = re.compile(r"(\d+)\s+0\s+R")
_NAMED_REF = re.compile(r"/([^\s/<>\[\]()]+)\s*(\d+)\s+0\s+R")


def _refs(text: str) -> list[int]:
    return [int(x) for x in _REF.findall(text or "")]


def _key(doc: pymupdf.Document, xref: int, key: str) -> tuple[str, str]:
    try:
        return doc.xref_get_key(xref, key)
    except (RuntimeError, ValueError):
        return "null", "null"


def hidden_layers(doc: pymupdf.Document) -> set[int]:
    """The layers (optional content groups, by xref) that DOC shows switched off when it opens."""
    if not doc.is_pdf:
        return set()
    cat = doc.pdf_catalog()
    every = set(_refs(_key(doc, cat, "OCProperties/OCGs")[1]))
    if not every:
        return set()
    if _key(doc, cat, "OCProperties/D/BaseState")[1] == "/OFF":
        return every - set(_refs(_key(doc, cat, "OCProperties/D/ON")[1]))
    return every & set(_refs(_key(doc, cat, "OCProperties/D/OFF")[1]))


def _is_hidden(doc: pymupdf.Document, xref: int, hidden: set[int]) -> bool:
    """Whether what is marked with the optional content XREF (a layer, or a combination of them) is hidden."""
    if xref in hidden:
        return True
    if _key(doc, xref, "Type")[1] != "/OCMD":
        return False
    groups = _refs(_key(doc, xref, "OCGs")[1])
    if not groups:
        return False
    off = [g in hidden for g in groups]
    policy = _key(doc, xref, "P")[1]
    # Se ve si alguna está encendida (AnyOn, por omisión), si todas (AllOn), si alguna apagada (AnyOff), si todas (AllOff).
    return {"/AllOn": any(off), "/AnyOff": not any(off), "/AllOff": not all(off)}.get(policy, all(off))


def _named(doc: pymupdf.Document, xref: int, key: str) -> dict[str, int]:
    """The names of the dictionary KEY of the object XREF (a path, such as 'Resources/XObject') and their xrefs."""
    kind, value = _key(doc, xref, key)
    if kind == "xref":
        value = doc.xref_object(_refs(value)[0], compressed=True)
    return {name: int(n) for name, n in _NAMED_REF.findall(value)} if kind in ("dict", "xref") else {}


def _resources_of(doc: pymupdf.Document, xref: int) -> int:
    """The object (XREF, or a page above it, from which it takes them) that has the resources of XREF."""
    seen = set()
    while xref and xref not in seen and _key(doc, xref, "Resources")[0] == "null":
        seen.add(xref)
        parent = _refs(_key(doc, xref, "Parent")[1])
        if not parent:
            break
        xref = parent[0]
    return xref


def _strip(doc: pymupdf.Document, data: bytes, holder: int, hidden: set[int], done: set[int]) -> bytes | None:
    """The content stream DATA (of a page or a form, whose resources are those of HOLDER) without what is
    marked with hidden layers; None if nothing in it is."""
    res = _resources_of(doc, holder)
    marks = {name for name, x in _named(doc, res, "Resources/Properties").items() if _is_hidden(doc, x, hidden)}
    objects = _named(doc, res, "Resources/XObject")
    hidden_objects = set()
    for name, x in objects.items():
        oc = _refs(_key(doc, x, "OC")[1])
        if oc and _is_hidden(doc, oc[0], hidden):
            hidden_objects.add(name)
        elif x not in done and _key(doc, x, "Subtype")[1] == "/Form":
            done.add(x)  # (una forma puede dibujarse en muchas páginas, o dentro de sí: una vez)
            inner = _strip(doc, doc.xref_stream(x), x, hidden, done)
            if inner is not None:
                doc.update_stream(x, inner)
    if not marks and not hidden_objects:
        return None
    pdf = pikepdf.new()
    ops = pikepdf.parse_content_stream(pikepdf.Stream(pdf, data))
    out, stack, changed = [], [], False
    for operands, op in ops:
        name = str(op)
        if name in ("BDC", "BMC"):
            off = name == "BDC" and len(operands) == 2 and str(operands[0]) == "/OC" \
                and isinstance(operands[1], pikepdf.Name) and str(operands[1])[1:] in marks
            stack.append(off)
            if any(stack):
                changed = True
                continue
        elif name == "EMC":
            off = any(stack)
            if stack:
                stack.pop()
            if off:
                continue
        elif any(stack):
            changed = True
            continue
        elif name == "Do" and operands and str(operands[0])[1:] in hidden_objects:
            changed = True
            continue
        out.append((operands, op))
    return pikepdf.unparse_content_stream(out) if changed else None


def _drop_names(doc: pymupdf.Document, xref: int, sub: str, gone) -> None:
    """Take out of the resources of XREF (if it has them), in their dictionary SUB, the names of the objects
    that are GONE."""
    kind, value = _key(doc, xref, "Resources")
    if kind == "xref":
        holder, key = _refs(value)[0], sub
    elif kind == "dict":
        holder, key = xref, f"Resources/{sub}"
    else:
        return
    kind, value = _key(doc, holder, key)
    if kind == "xref":
        holder, key, value = _refs(value)[0], None, doc.xref_object(_refs(value)[0], compressed=True)
    elif kind != "dict":
        return
    names = _NAMED_REF.findall(value)
    kept = [(n, x) for n, x in names if not gone(int(x))]
    if len(kept) == len(names):
        return
    text = "<<" + "".join(f"/{n} {x} 0 R" for n, x in kept) + ">>"
    if key is None:
        doc.update_object(holder, text)
    else:
        doc.xref_set_key(holder, key, text)


def remove_hidden_layers(doc: pymupdf.Document) -> int:
    """Take out of DOC what is in the layers switched off (their content on the pages and in the forms they
    draw, their annotations) and the layers themselves, with their names. Returns how many layers went."""
    hidden = hidden_layers(doc)
    if not hidden:
        return 0
    done: set[int] = set()
    for page in doc:
        data = page.read_contents()
        new = _strip(doc, data, page.xref, hidden, done) if data else None
        if new is not None:
            first = page.get_contents()[0]
            doc.update_stream(first, new)
            doc.xref_set_key(page.xref, "Contents", f"{first} 0 R")
        for annot in list(page.annots() or []):
            oc = _refs(_key(doc, annot.xref, "OC")[1])
            if oc and _is_hidden(doc, oc[0], hidden):
                page.delete_annot(annot)
    # Sus nombres salen de los recursos de páginas y formas (con las imágenes y formas que escondían) y de
    # la lista de capas.
    def gone(x: int) -> bool:
        oc = _refs(_key(doc, x, "OC")[1])
        return x in hidden or bool(oc) and _is_hidden(doc, oc[0], hidden)

    for xref in range(1, doc.xref_length()):
        for sub in ("Properties", "XObject"):
            _drop_names(doc, xref, sub, gone)
    cat = doc.pdf_catalog()
    kind, value = _key(doc, cat, "OCProperties")
    target = _refs(value)[0] if kind == "xref" else None
    text = doc.xref_object(target, compressed=True) if target else value
    left = set(_refs(_key(doc, cat, "OCProperties/OCGs")[1])) - hidden
    if not left:
        doc.xref_set_key(cat, "OCProperties", "null")
    else:
        text = re.sub(r"\b(\d+)\s+0\s+R", lambda m: "" if int(m.group(1)) in hidden else m.group(0), text)
        if target:
            doc.update_object(target, text)
        else:
            doc.xref_set_key(cat, "OCProperties", text)
    return len(hidden)
