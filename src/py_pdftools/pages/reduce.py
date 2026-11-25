"""Making a PDF smaller: its pictures drawn again at a lower resolution (only those above a limit, measured
as they are shown on the page, not as they are stored) and compressed more; its fonts reduced to the
characters used; what nothing uses taken out; and the rest compressed, objects in streams too. The file is
not changed: a copy is written. where() says where the bytes of a file go (pictures, fonts, the pages'
content, the rest), to know what is worth reducing."""

from __future__ import annotations

import dataclasses
import math
import os
import tempfile
import zlib
from pathlib import Path

import pymupdf

from ..core import pdfdoc
from ..core.interface import N_, tr


class ReduceError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Options:
    dpi: int = 150  # pictures above DPI * 1.5 are drawn again at DPI (0: pictures left as they are)
    quality: int = 75  # of the JPEG of the pictures drawn again (1-100)
    gray: bool = False  # las imágenes en color, en gris
    fonts: bool = True  # las fuentes reducidas a los caracteres usados


# (clave, nombre, qué hace, sus opciones)
LEVELS = [
    ("high", N_("Good quality"), N_("Pictures down to 220 dpi: as good on paper, a little smaller"),
     Options(220, 85)),
    ("medium", N_("Medium"), N_("Pictures down to 150 dpi: good on screen and on most printers"), Options(150, 75)),
    ("small", N_("Smallest"), N_("Pictures down to 96 dpi, more compressed: for the screen, and to send by mail"),
     Options(96, 60)),
    ("lossless", N_("Without touching the pictures"), N_("Only fonts, unused objects and compression: nothing "
                                                         "changes in how it looks"), Options(0, 0)),
]
KINDS = [("images", N_("Pictures")), ("fonts", N_("Fonts")), ("content", N_("Content of the pages")),
         ("other", N_("The rest"))]


def options_of(level: str) -> Options:
    return next(o for k, _, _, o in LEVELS if k == level)


def _open(path: Path, password: str) -> pymupdf.Document:
    return pdfdoc.open_pdf(path, password, ReduceError, ReduceError)


def where(path: Path, password: str = "") -> dict[str, int]:
    """{kind of KINDS: bytes} of the PDF at PATH (its streams as stored; the rest of the file is 'other')."""
    with _open(path, password) as doc:
        contents = {x for page in doc for x in page.get_contents()}
        found = {k: 0 for k, _ in KINDS}
        for xref in range(1, doc.xref_length()):
            try:
                if not doc.xref_is_stream(xref):
                    continue
                size = len(doc.xref_stream_raw(xref))
            except (RuntimeError, ValueError):
                continue
            subtype = doc.xref_get_key(xref, "Subtype")[1]
            if subtype == "/Image":
                kind = "images"
            elif xref in contents:
                kind = "content"
            elif subtype in ("/Type1C", "/CIDFontType0C", "/OpenType") or \
                    doc.xref_get_key(xref, "Length1")[0] != "null":
                kind = "fonts"
            else:
                kind = "other"
            found[kind] += size
    total = path.stat().st_size
    found["other"] += max(0, total - sum(found.values()))
    return found


def _shown_dpi(doc: pymupdf.Document) -> dict[int, float]:
    """{xref: the highest resolution it is shown at, in dots per inch} of the pictures drawn on the pages
    (also inside forms). A picture shown twice counts at its sharpest; one never found (in a pattern, in an
    annotation) is not there, and is left as it is."""
    found: dict[int, float] = {}
    for page in doc:
        try:
            infos = page.get_image_info(xrefs=True)
        except (RuntimeError, ValueError):
            continue
        for info in infos:
            xref = info.get("xref") or 0
            if xref <= 0:  # (las imágenes en línea, dentro del contenido de la página, no se tocan)
                continue
            a, b, c, d = info["transform"][:4]
            wide, high = math.hypot(a, b) / 72, math.hypot(c, d) / 72  # (shown, in inches)
            if wide <= 0 or high <= 0:
                continue
            dpi = max(info["width"] / wide, info["height"] / high)
            found[xref] = max(found.get(xref, 0), dpi)
    return found


def _key(doc: pymupdf.Document, xref: int, name: str) -> tuple[str, str]:
    try:
        return doc.xref_get_key(xref, name)
    except (RuntimeError, ValueError):
        return "null", "null"


def _picture(doc: pymupdf.Document, xref: int, gray: bool) -> pymupdf.Pixmap | None:
    """The picture XREF decoded, without alpha, in RGB (grey if GRAY, or if it was grey); None if MuPDF can't
    read it."""
    try:
        pix = pymupdf.Pixmap(doc, xref)
    except (RuntimeError, ValueError):
        return None
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if gray and pix.n != 1:
        pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
    elif pix.colorspace is None or pix.n not in (1, 3):  # (CMYK, Lab, sin espacio de color: a RGB)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix


def _scaled(pix: pymupdf.Pixmap, factor: float) -> pymupdf.Pixmap:
    return pymupdf.Pixmap(pix, max(1, round(pix.width * factor)), max(1, round(pix.height * factor)), None)


def _write(doc: pymupdf.Document, xref: int, pix: pymupdf.Pixmap, data: bytes, jpeg: bool, keep: str) -> None:
    """Replace the picture XREF by PIX, stored as DATA (a JPEG, or the samples to compress), keeping the keys
    in KEEP ('/SMask 12 0 R/Interpolate true...')."""
    space = "/DeviceGray" if pix.n == 1 else "/DeviceRGB"
    doc.update_object(xref, f"<</Type/XObject/Subtype/Image/Width {pix.width}/Height {pix.height}"
                            f"/ColorSpace{space}/BitsPerComponent 8{keep}>>")
    # update_stream quita /Filter al no comprimir: el del JPEG se pone después.
    doc.update_stream(xref, data, compress=not jpeg)
    if jpeg:
        doc.xref_set_key(xref, "Filter", "/DCTDecode")


def _kept_keys(doc: pymupdf.Document, xref: int) -> str:
    """The keys of the picture XREF that its new version keeps: its soft mask (a picture of its own, which may
    have other dimensions), a stencil mask, how it is smoothed and its rendering intent."""
    out = ""
    for name in ("SMask", "Mask", "Interpolate", "Intent"):
        kind, value = _key(doc, xref, name)
        if kind != "null" and not (name == "Mask" and kind == "array"):
            out += f"/{name} {value}"
    return out


def _rewrite_pictures(doc: pymupdf.Document, options: Options) -> None:
    """The pictures shown above 1.5 times OPTIONS.dpi drawn again at that resolution, as JPEG; the others
    stored as JPEG too, only when that is smaller (none of that with dpi 0); all in grey if OPTIONS.gray
    (without dpi, kept lossless).

    Only the objects of the pictures are written: the pages' content is never touched. (MuPDF's own
    rewrite_images, used before, passes every content stream through its filter, which lost fill colours
    that a 'Q' restored: a white box behind a logo came out black.) Left as they are: pictures in black and
    white (one bit per sample: fax or JBIG2 does better), stencil masks, pictures with colour-key masking,
    those used only as the soft mask of another, and those MuPDF can't read."""
    shown = _shown_dpi(doc)
    masks = {int(v.split()[0]) for x in shown for k, v in [_key(doc, x, "SMask")] if k == "xref"}
    threshold = options.dpi * 1.5
    for xref, dpi in shown.items():
        if xref in masks or _key(doc, xref, "ImageMask")[1] == "true" or _key(doc, xref, "Mask")[0] == "array":
            continue
        bits = _key(doc, xref, "BitsPerComponent")[1]
        if bits == "1" or _key(doc, xref, "Subtype")[1] != "/Image":
            continue
        try:
            before = len(doc.xref_stream_raw(xref))
        except (RuntimeError, ValueError):
            continue
        smaller = bool(options.dpi) and dpi > threshold
        if not options.dpi and not options.gray:
            continue
        pix = _picture(doc, xref, options.gray)
        if pix is None:
            continue
        was_gray = pix.n == 1 and not options.gray
        if smaller:
            pix = _scaled(pix, options.dpi / dpi)
        if options.dpi:
            data = pix.tobytes("jpeg", jpg_quality=options.quality)
            # (una imagen que crecería se deja como está; la que se redujo, también si no ganó nada)
            if len(data) >= before:
                continue
            keep = _kept_keys(doc, xref)
            mask = _key(doc, xref, "SMask")
            _write(doc, xref, pix, data, True, keep)
            if smaller and mask[0] == "xref":
                _shrink_mask(doc, int(mask[1].split()[0]), pix.width, pix.height)
        elif not was_gray and pix.n == 1:  # (solo gris, sin pérdida)
            _write(doc, xref, pix, pix.samples, False, _kept_keys(doc, xref))


def _shrink_mask(doc: pymupdf.Document, xref: int, width: int, height: int) -> None:
    """The soft mask XREF drawn again at WIDTH × HEIGHT (its picture's new size), if it was larger."""
    try:
        mask = pymupdf.Pixmap(doc, xref)
    except (RuntimeError, ValueError):
        return
    if mask.n != 1 or mask.alpha or mask.width <= width:
        return
    small = pymupdf.Pixmap(mask, width, height, None)
    keep = "".join(f"/{n} {v}" for n in ("Matte", "Interpolate") for k, v in [_key(doc, xref, n)] if k != "null")
    doc.update_object(xref, f"<</Type/XObject/Subtype/Image/Width {width}/Height {height}"
                            f"/ColorSpace/DeviceGray/BitsPerComponent 8{keep}>>")
    doc.update_stream(xref, small.samples, compress=True)


def _recompress_contents(doc: pymupdf.Document) -> None:
    """The content streams of the pages compressed again (as they are, byte for byte: never parsed and
    rewritten, see _rewrite_pictures), each kept only if it gets smaller."""
    done = set()
    for page in doc:
        for xref in page.get_contents():
            if xref in done:
                continue
            done.add(xref)
            try:
                before = len(doc.xref_stream_raw(xref))
                data = doc.xref_stream(xref)
                fresh = zlib.compress(data, 9)
            except (RuntimeError, ValueError, zlib.error):
                continue
            if len(fresh) < before:
                doc.update_stream(xref, fresh, compress=False)
                doc.xref_set_key(xref, "Filter", "/FlateDecode")
                doc.xref_set_key(xref, "DecodeParms", "null")


def reduce(source: Path, target: Path, options: Options, password: str = "") -> tuple[int, int]:
    """SOURCE made smaller with OPTIONS, saved as TARGET (which may be SOURCE). Returns (bytes before,
    after). Its protection, if it has one, is kept."""
    doc = _open(source, password)
    before = source.stat().st_size
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        # Se mide la resolución con que la imagen se ve en la página: solo se reducen las que pasan de 1,5 veces
        # la resolución pedida (por debajo, el ahorro no compensa la pérdida).
        _rewrite_pictures(doc, options)
        if options.fonts:
            try:
                doc.subset_fonts()
            except (RuntimeError, ValueError):  # (a font it can't read is left whole)
                pass
        _recompress_contents(doc)
        keep = pdfdoc.kept_encryption(doc)
        # Los flujos de objetos no se combinan bien con el cifrado de MuPDF (el archivo sale dañado): solo sin él.
        doc.save(tmp, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
                 use_objstms=int(keep == pymupdf.PDF_ENCRYPT_NONE), encryption=keep)
        doc.close()
        after = Path(tmp).stat().st_size
        if after >= before:
            # (nada ganado: la copia es el archivo como estaba, no uno más grande)
            Path(tmp).unlink()
            if target.resolve() != source.resolve():
                target.write_bytes(source.read_bytes())
            return before, before
        os.replace(tmp, target)
        return before, after
    except BaseException as e:
        if not doc.is_closed:
            doc.close()
        Path(tmp).unlink(missing_ok=True)
        if isinstance(e, (OSError, RuntimeError, ValueError)):
            raise ReduceError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
        raise


def size_text(n: int) -> str:
    """N bytes as a size to read: '820 KB', '12.4 MB'."""
    if n < 1000:
        return tr("{count} bytes", count=n)
    if n < 1000 * 1000:
        return tr("{size} KB", size=f"{n / 1000:.0f}")
    return tr("{size} MB", size=f"{n / 1e6:.1f}")
