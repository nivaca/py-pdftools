"""Making a PDF smaller: its pictures drawn again at a lower resolution (only those above a limit, measured
as they are shown on the page, not as they are stored) and compressed more; its fonts reduced to the
characters used; what nothing uses taken out; and the rest compressed, objects in streams too. The file is
not changed: a copy is written. where() says where the bytes of a file go (pictures, fonts, the pages'
content, the rest), to know what is worth reducing."""

from __future__ import annotations

import dataclasses
import os
import tempfile
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


def _rewriter(options: Options):
    """How MuPDF draws the pictures again: those shown above 1.5 times OPTIONS.dpi, at that resolution (cubic,
    to the resolution asked; MuPDF's own default only halves them), as JPEG; black-and-white ones as fax."""
    mu = pymupdf.mupdf
    opts = mu.PdfImageRewriterOptions()
    threshold, quality = round(options.dpi * 1.5), str(options.quality)
    for kind in ("color_lossless", "color_lossy", "gray_lossless", "gray_lossy"):
        setattr(opts, f"{kind}_image_recompress_method", mu.FZ_RECOMPRESS_JPEG)
        setattr(opts, f"{kind}_image_recompress_quality", quality)
        setattr(opts, f"{kind}_image_subsample_method", mu.FZ_SUBSAMPLE_BICUBIC)
        setattr(opts, f"{kind}_image_subsample_threshold", threshold)
        setattr(opts, f"{kind}_image_subsample_to", options.dpi)
    opts.recompress_when = mu.FZ_RECOMPRESS_WHEN_SMALLER  # (una imagen que crecería se deja como está)
    opts.bitonal_image_recompress_method = mu.FZ_RECOMPRESS_FAX
    opts.bitonal_image_subsample_method = mu.FZ_SUBSAMPLE_AVERAGE
    # (el texto escaneado en blanco y negro pierde mucho con menos de 300 ppp)
    opts.bitonal_image_subsample_threshold = max(threshold, 450)
    opts.bitonal_image_subsample_to = max(options.dpi, 300)
    return opts


def reduce(source: Path, target: Path, options: Options, password: str = "") -> tuple[int, int]:
    """SOURCE made smaller with OPTIONS, saved as TARGET (which may be SOURCE). Returns (bytes before,
    after). Its protection, if it has one, is kept."""
    doc = _open(source, password)
    before = source.stat().st_size
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        if options.dpi:
            # Se mide la resolución con que la imagen se ve en la página: solo se reducen las que pasan de
            # 1,5 veces la resolución pedida (por debajo, el ahorro no compensa la pérdida).
            doc.rewrite_images(options=_rewriter(options), set_to_gray=options.gray)
        elif options.gray:
            doc.rewrite_images(set_to_gray=True, lossy=False, lossless=True)
        if options.fonts:
            try:
                doc.subset_fonts()
            except (RuntimeError, ValueError):  # (a font it can't read is left whole)
                pass
        keep = pdfdoc.kept_encryption(doc)
        # Los flujos de objetos no se combinan bien con el cifrado de MuPDF (el archivo sale dañado): solo sin él.
        doc.save(tmp, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True,
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
