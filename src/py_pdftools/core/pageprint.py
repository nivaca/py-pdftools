"""La huella de una página: un resumen de todo aquello de lo que depende su dibujo (su contenido, sus
recursos, es decir, fuentes, imágenes y formularios, sus anotaciones, su tamaño y su giro, y las capas del
documento). Dos páginas con la misma huella se dibujan igual, de modo que la ventana puede quedarse con el
dibujo de una página que un cambio del documento no tocó, aunque el cambio la haya movido o haya renumerado
sus objetos (pikepdf los numera de nuevo al guardar).

La huella no depende de los números de los objetos: cada referencia se sustituye por la huella del objeto al
que apunta. Lo que no se dibuja (el destino de un enlace, la página madre, la anotación de la que otra es
respuesta) no entra: así un cambio en otra página no cambia la huella de esta, y se evitan los ciclos.

Ante la duda la huella cambia, nunca al revés: dos páginas que se dibujan distinto no pueden tener la misma
huella, aunque dos que se dibujan igual puedan tener huellas distintas (entonces solo se dibuja de nuevo)."""

from __future__ import annotations

import hashlib
import re

import pymupdf

# Keys that don't change what is drawn, and lead to other pages or back up the tree (and so into cycles).
SKIPPED = frozenset({"Parent", "P", "Dest", "D", "A", "AA", "IRT", "Popup", "Next", "Prev", "First", "Last",
                     "PA", "Pg", "StructParent", "StructParents", "Metadata", "PieceInfo", "Thumb", "B", "ID"})
CYCLE = b"(cycle)"
UNPACK_BELOW = 1 << 20  # bytes: streams up to this size are fingerprinted decompressed
# the filters that qpdf decodes and compresses again with Flate when it saves (not those of pictures)
GENERAL = {"FlateDecode", "LZWDecode", "ASCII85Decode", "ASCIIHexDecode", "RunLengthDecode", "Fl", "LZW", "A85",
           "AHx", "RL"}
PACKING = ("Filter", "DecodeParms", "DL")  # (how a stream is compressed: left out once it is decompressed)


class Prints:
    """The fingerprints of the pages of one document, worked out when asked for and kept (the document must
    not change meanwhile: a changed document is another, with Prints of its own)."""

    def __init__(self, doc: pymupdf.Document, extra: bytes = b""):
        self.doc = doc
        self.extra = extra  # (whatever else the drawing depends on, given by the caller)
        self._objects: dict[int, bytes] = {}  # xref -> its digest (only those that met no cycle)
        self._pages: dict[int, bytes] = {}
        self._whole: bytes | None = None

    def page(self, number: int) -> bytes:
        """The fingerprint of page NUMBER."""
        got = self._pages.get(number)
        if got is None:
            got = self._pages[number] = self._page(number)
        return got

    def _page(self, number: int) -> bytes:
        page = self.doc[number]
        h = hashlib.blake2b(digest_size=20)
        h.update(self._document())
        # (inherited from the tree of pages if the page doesn't say them itself: PyMuPDF resolves them)
        h.update(repr((page.rotation, tuple(page.mediabox), tuple(page.cropbox))).encode())
        h.update(self._dict(page.xref, set())[0])
        if "Resources" not in self.doc.xref_get_keys(page.xref):
            h.update(self._inherited_resources(page.xref))
        return h.digest()

    def _document(self) -> bytes:
        """What every page depends on: the layers (which are shown), and the caller's extra."""
        if self._whole is None:
            h = hashlib.blake2b(digest_size=20)
            h.update(self.extra)
            catalog = self.doc.pdf_catalog()
            kind, value = self.doc.xref_get_key(catalog, "OCProperties") if catalog > 0 else ("null", "null")
            h.update(self._value(kind, value, set())[0])
            self._whole = h.digest()
        return self._whole

    def _inherited_resources(self, xref: int) -> bytes:
        seen = set()
        while xref not in seen:
            seen.add(xref)
            kind, value = self.doc.xref_get_key(xref, "Parent")
            if kind != "xref":
                return b""
            xref = int(value.split()[0])
            kind, value = self.doc.xref_get_key(xref, "Resources")
            if kind != "null":
                return self._value(kind, value, set())[0]
        return b""

    def _object(self, xref: int, busy: set[int]) -> tuple[bytes, bool]:
        """The digest of object XREF, and whether it is clean (met no cycle: only those are kept, since one
        that met a cycle stands for less than all it reaches)."""
        got = self._objects.get(xref)
        if got is not None:
            return got, True
        if xref in busy or xref <= 0 or xref >= self.doc.xref_length():
            return CYCLE, False  # (not its number: another file numbers it otherwise)
        busy.add(xref)
        try:
            h = hashlib.blake2b(digest_size=20)
            unpacked = False
            if self.doc.xref_is_stream(xref):
                raw = self.doc.xref_stream_raw(xref) or b""
                # Un flujo pequeño, descomprimido: pikepdf comprime al guardar los que no lo estaban, y lo que se
                # dibuja no cambia. Uno grande (una imagen, casi siempre ya comprimida), tal como está, con su
                # filtro: si alguien lo comprime de otra manera, la página solo se vuelve a dibujar.
                kind, packing = self.doc.xref_get_key(xref, "Filter")
                # (only what qpdf may compress again: nothing, or general filters; a JPEG decoded would cost too much)
                if len(raw) <= UNPACK_BELOW and (kind == "null" or set(re.findall(r"/(\w+)", packing)) <= GENERAL):
                    try:
                        raw, unpacked = self.doc.xref_stream(xref) or b"", True
                    except (RuntimeError, ValueError):
                        pass
                h.update(b"unpacked:" if unpacked else b"raw:")
                h.update(raw)
            keys = self.doc.xref_get_keys(xref)
            if keys:
                digest, clean = self._dict(xref, busy, PACKING if unpacked else ())
            else:  # (not a dictionary: an array, a number, a name...)
                digest, clean = self._text(self.doc.xref_object(xref, compressed=True), busy)
            h.update(digest)
            out = h.digest()
        finally:
            busy.discard(xref)
        if clean:
            self._objects[xref] = out
        return out, clean

    def _dict(self, xref: int, busy: set[int], without: tuple = ()) -> tuple[bytes, bool]:
        h = hashlib.blake2b(digest_size=20)
        clean = True
        busy = busy | {xref}
        for key in sorted(self.doc.xref_get_keys(xref)):
            if key in SKIPPED or key == "Length" or key in without:
                continue
            kind, value = self.doc.xref_get_key(xref, key)
            digest, ok = self._value(kind, value, busy)
            clean = clean and ok
            h.update(key.encode() + b"=" + digest + b";")
        return h.digest(), clean

    def _value(self, kind: str, value: str, busy: set[int]) -> tuple[bytes, bool]:
        if kind == "xref":
            return self._object(int(value.split()[0]), busy)
        return self._text(value, busy)

    def _text(self, text: str, busy: set[int]) -> tuple[bytes, bool]:
        """A value written out (a dictionary or an array inline, a number...), read with its references
        replaced by the digests of their objects, and the keys of its dictionaries in order (pikepdf may write
        them in another), without those of SKIPPED."""
        try:
            value, _ = _parse(_tokens(text), 0)
        except (IndexError, ValueError):  # (something the little reader doesn't know: as it is written)
            value = ("raw", text)
        state = [True]
        out = self._canonical(value, busy, state)
        return hashlib.blake2b(out, digest_size=20).digest(), state[0]

    def _canonical(self, value, busy: set[int], state: list) -> bytes:
        kind = value[0]
        if kind == "ref":
            digest, ok = self._object(value[1], busy)
            state[0] = state[0] and ok
            return b"<" + digest + b">"
        if kind == "dict":
            parts = [k.encode() + b"=" + self._canonical(v, busy, state) for k, v in sorted(value[1].items())
                     if k not in SKIPPED and k != "Length"]
            return b"{" + b";".join(parts) + b"}"
        if kind == "array":
            return b"[" + b",".join(self._canonical(v, busy, state) for v in value[1]) + b"]"
        return value[1].encode()


# Un lector mínimo de la sintaxis de PDF, para los valores que PyMuPDF da escritos: diccionarios, arreglos,
# referencias, nombres, números, cadenas.
_TOKEN = re.compile(r"<<|>>|\[|\]|\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|/[^\s/\[\]()<>{}%]*|[^\s/\[\]()<>{}%]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def _parse(tokens: list[str], at: int):
    """The value that starts at token AT, and the token after it."""
    token = tokens[at]
    if token == "<<":
        items, at = {}, at + 1
        while tokens[at] != ">>":
            key = tokens[at]
            if not key.startswith("/"):
                raise ValueError(key)
            items[key[1:]], at = _parse(tokens, at + 1)
        return ("dict", items), at + 1
    if token == "[":
        items, at = [], at + 1
        while tokens[at] != "]":
            item, at = _parse(tokens, at)
            items.append(item)
        return ("array", items), at + 1
    # "12 0 R": a reference
    if token.isdigit() and at + 2 < len(tokens) and tokens[at + 1].isdigit() and tokens[at + 2] == "R":
        return ("ref", int(token)), at + 3
    return ("atom", token), at + 1
