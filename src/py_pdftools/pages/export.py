"""Exporting a PDF: its pages as pictures (PNG, JPEG or TIFF, at a resolution, in colour or grey), the
pictures it holds (as they are stored, or as PNG when they have a mask that makes parts of them transparent),
and its text (plain, HTML, or Markdown, whose headings are guessed from the size of the letters)."""

from __future__ import annotations

import collections
import html
import re
import struct
import zlib
from pathlib import Path

import pymupdf

from ..core import pdfdoc
from ..core.interface import tr

PICTURE_FORMATS = ("png", "jpg", "tiff")
TEXT_FORMATS = ("txt", "html", "md")


class ExportError(Exception):
    pass


def _open(path: Path, password: str) -> pymupdf.Document:
    return pdfdoc.open_pdf(path, password, ExportError, ExportError)


def _names(doc: pymupdf.Document, pages: list[int]) -> dict[int, str]:
    """A part of a file name for each of PAGES: its number, with zeros to sort well (and its label, if it has
    another one)."""
    width = len(str(doc.page_count))
    out = {}
    for n in pages:
        label = doc[n].get_label() or ""
        safe = re.sub(r"[^\w.-]+", "_", label).strip("_")
        out[n] = f"{n + 1:0{width}}" + (f"-{safe}" if safe and safe != str(n + 1) else "")
    return out


# ----------------------------------------------------------------- TIFF (PyMuPDF writes none without Pillow)

def write_tiff(pix: pymupdf.Pixmap, path: Path, dpi: int):
    """PIX (grey or RGB, without alpha) as a TIFF file, compressed with Deflate (as libtiff and every program
    that reads TIFF read it), with its resolution."""
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    width, height, n = pix.width, pix.height, pix.n
    rows = bytes(pix.samples)
    if pix.stride != width * n:
        rows = b"".join(rows[y * pix.stride:y * pix.stride + width * n] for y in range(height))
    data = zlib.compress(rows, 6)
    entries = []  # (etiqueta, tipo, cuántos, valor o posición)

    def entry(tag, kind, count, value):
        entries.append((tag, kind, count, value))

    header = 8
    bits_at = header + len(data) + (len(data) % 2)
    res_at = bits_at + (6 if n == 3 else 0)
    entry(256, 4, 1, width)  # ImageWidth
    entry(257, 4, 1, height)  # ImageLength
    entry(258, 3, n, bits_at if n == 3 else 8)  # BitsPerSample
    entry(259, 3, 1, 8)  # Compression: Deflate (zlib)
    entry(262, 3, 1, 2 if n == 3 else 1)  # Photometric: RGB, o gris con el negro en 0
    entry(273, 4, 1, header)  # StripOffsets (una sola tira: la imagen entera)
    entry(277, 3, 1, n)  # SamplesPerPixel
    entry(278, 4, 1, height)  # RowsPerStrip
    entry(279, 4, 1, len(data))  # StripByteCounts
    entry(282, 5, 1, res_at)  # XResolution
    entry(283, 5, 1, res_at + 8)  # YResolution
    entry(296, 3, 1, 2)  # ResolutionUnit: pulgadas
    extra = (b"\x00" if len(data) % 2 else b"") + (struct.pack("<3H", 8, 8, 8) if n == 3 else b"") + \
        struct.pack("<4I", dpi, 1, dpi, 1)
    ifd_at = res_at + 16
    out = bytearray(b"II*\x00" + struct.pack("<I", ifd_at))
    out += data + extra
    out += struct.pack("<H", len(entries))
    for tag, kind, count, value in entries:
        if kind == 3 and count == 1:
            out += struct.pack("<HHIHH", tag, kind, count, value, 0)
        else:
            out += struct.pack("<HHII", tag, kind, count, value)
    out += struct.pack("<I", 0)
    path.write_bytes(bytes(out))


# ----------------------------------------------------------------- pages as pictures

def export_pages(source: Path, folder: Path, pages: list[int] | None = None, fmt: str = "png", dpi: int = 150,
                 gray: bool = False, quality: int = 90, password: str = "", stem: str = "",
                 progress=None) -> list[Path]:
    """PAGES (0-based; all if None) of SOURCE drawn as pictures in FOLDER, in the format FMT (of
    PICTURE_FORMATS), at DPI, in grey if GRAY; a JPEG with QUALITY. Named STEM-number(-label).ext.
    PROGRESS(done, total), if given, after each. Returns their paths."""
    if fmt not in PICTURE_FORMATS:
        raise ExportError(tr("Unknown format: {format}", format=fmt))
    folder.mkdir(parents=True, exist_ok=True)
    with _open(source, password) as doc:
        pages = list(range(doc.page_count)) if pages is None else pages
        names = _names(doc, pages)
        stem = stem or source.stem
        out = []
        for i, n in enumerate(pages):
            pix = doc[n].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY if gray else pymupdf.csRGB, alpha=False)
            path = folder / f"{stem}-{names[n]}.{fmt}"
            try:
                if fmt == "tiff":
                    write_tiff(pix, path, dpi)
                elif fmt == "jpg":
                    pix.set_dpi(dpi, dpi)
                    pix.save(path, jpg_quality=quality)
                else:
                    pix.set_dpi(dpi, dpi)
                    pix.save(path)
            except (OSError, RuntimeError, ValueError) as e:
                raise ExportError(tr("{path} cannot be written: {error}", path=path, error=e)) from None
            out.append(path)
            if progress is not None:
                progress(i + 1, len(pages))
        return out


# ----------------------------------------------------------------- the pictures it holds

def export_images(source: Path, folder: Path, pages: list[int] | None = None, smallest: int = 32,
                  password: str = "", stem: str = "") -> list[Path]:
    """The pictures that PAGES (all if None) of SOURCE show, each once, written in FOLDER as they are
    stored (JPEG as JPEG...), or as PNG if a mask makes parts of them transparent; those smaller than
    SMALLEST pixels on a side (marks, rules) left out. Returns their paths."""
    folder.mkdir(parents=True, exist_ok=True)
    stem = stem or source.stem
    out, seen = [], set()
    with _open(source, password) as doc:
        pages = list(range(doc.page_count)) if pages is None else pages
        width = len(str(doc.page_count))
        for n in pages:
            for k, info in enumerate(doc[n].get_images(full=True), 1):
                xref, smask, w, h = info[0], info[1], info[2], info[3]
                if xref in seen or min(w, h) < smallest:
                    continue
                seen.add(xref)
                base = folder / f"{stem}-p{n + 1:0{width}}-{k}"
                try:
                    if smask:
                        pix = pymupdf.Pixmap(pymupdf.Pixmap(doc, xref), pymupdf.Pixmap(doc, smask))
                        path = base.with_suffix(".png")
                        pix.save(path)
                    else:
                        found = doc.extract_image(xref)
                        if not found or not found.get("image"):
                            continue
                        path = base.with_suffix("." + found.get("ext", "png"))
                        path.write_bytes(found["image"])
                except (OSError, RuntimeError, ValueError) as e:
                    raise ExportError(tr("{path} cannot be written: {error}", path=base, error=e)) from None
                out.append(path)
    return out


# ----------------------------------------------------------------- the text

def _markdown(page: pymupdf.Page, body: float) -> str:
    """The text of PAGE as Markdown: headings for the lines in letters larger than the body's (BODY), bold
    and italic kept, lists of bullets as lists, words cut at the end of a line joined again."""
    out = []
    for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        if block.get("type") != 0:
            continue
        lines, sizes = [], []
        for line in block["lines"]:
            parts = []
            for span in line["spans"]:
                text = span["text"]
                if not text.strip():
                    parts.append(text)
                    continue
                sizes.append((span["size"], len(text)))
                bold, italic = span["flags"] & 16, span["flags"] & 2
                core = text.strip()
                mark = "**" if bold else ""
                mark += "*" if italic else ""
                lead, tail = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
                parts.append(f"{lead}{mark}{core}{mark[::-1]}{tail}" if mark else text)
            lines.append("".join(parts).strip())
        text = ""
        for line in lines:
            if not line:
                continue
            if text.endswith("-") and line[:1].islower():
                text = text[:-1] + line
            else:
                text = (text + " " + line) if text else line
        if not text:
            continue
        size = max(sizes, key=lambda s: s[1])[0] if sizes else body
        if size >= body * 1.6 and len(text) < 200:
            text = "# " + text.replace("**", "")
        elif size >= body * 1.3 and len(text) < 200:
            text = "## " + text.replace("**", "")
        elif size >= body * 1.12 and len(text) < 200:
            text = "### " + text.replace("**", "")
        elif re.match(r"^[•◦▪‣·–-]\s", text):
            text = "- " + text[2:].lstrip()
        out.append(text)
    return "\n\n".join(out)


def _body_size(doc: pymupdf.Document, pages: list[int]) -> float:
    """The size of the letters of most of the text of PAGES."""
    count: collections.Counter = collections.Counter()
    for n in pages:
        for block in doc[n].get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    count[round(span["size"], 1)] += len(span["text"].strip())
    return count.most_common(1)[0][0] if count else 11.0


def export_text(source: Path, target: Path, fmt: str = "", pages: list[int] | None = None,
                password: str = "") -> int:
    """The text of PAGES (all if None) of SOURCE written as TARGET: plain text (pages apart by a form
    feed), HTML or Markdown, FMT or by TARGET's extension. Returns how many characters of text it has."""
    fmt = fmt or {".htm": "html", ".html": "html", ".md": "md", ".markdown": "md"}.get(target.suffix.lower(), "txt")
    with _open(source, password) as doc:
        pages = list(range(doc.page_count)) if pages is None else pages
        if fmt == "html":
            title = html.escape((doc.metadata or {}).get("title") or source.stem)
            body = "\n".join(f'<section class="page" id="page-{n + 1}">\n{doc[n].get_text("xhtml")}\n</section>'
                             for n in pages)
            text = (f'<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n<title>{title}</title>\n</head>\n'
                    f"<body>\n{body}\n</body>\n</html>\n")
            count = sum(len(doc[n].get_text()) for n in pages)
        elif fmt == "md":
            size = _body_size(doc, pages)
            parts = [_markdown(doc[n], size) for n in pages]
            text = "\n\n".join(p for p in parts if p) + "\n"
            count = len(text)
        else:
            parts = [doc[n].get_text() for n in pages]
            text = "\f".join(parts)
            count = sum(map(len, parts))
    try:
        target.write_text(text, encoding="utf-8")
    except OSError as e:
        raise ExportError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    return count
