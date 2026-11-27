"""Los motores que pueden dibujar las páginas en la pantalla: MuPDF (el de
siempre), PDFium y Poppler. La idea viene de Okular, que ofrece varios motores
para un mismo tipo de documento y, si se le pide, pregunta cuál usar al abrir
uno.

Solo el dibujo cambia. Las anotaciones, el texto, las búsquedas, guardar,
imprimir y exportar siguen siendo de MuPDF y pikepdf. MuPDF prepara además
cada página antes de que otro motor la dibuje: le quita las anotaciones que
la ventana dibuja por su cuenta (véase rendering.py) y hace con ella un PDF
de una sola página, en memoria, que el otro motor dibuja entero, con lo que le
quede (los campos de formulario, por ejemplo). Así ninguna anotación sale dos
veces, y un documento con contraseña llega ya abierto.

PDFium llega de dos maneras: el Qt PDF de PySide6, donde lo hay (el de Fedora;
el de pip no lo trae), o pypdfium2 (``pip install 'py-pdftools[pdfium]'``, y en
la AppImage y los instaladores). Poppler es el programa pdftoppm, que lee la
página por su entrada y escribe la imagen por su salida, sin archivos.

Si otro motor falla con una página, la dibuja MuPDF: una página nunca se queda
en blanco por el motor elegido.
"""

from __future__ import annotations

import functools
import shutil
import subprocess

import pymupdf

from .interface import N_, tr

MUPDF, PDFIUM, POPPLER = "mupdf", "pdfium", "poppler"
BACKENDS = (MUPDF, PDFIUM, POPPLER)
NAMES = {MUPDF: N_("MuPDF"), PDFIUM: N_("PDFium"), POPPLER: N_("Poppler")}
DESCRIPTIONS = {MUPDF: N_("The engine of py-pdftools, which also edits the documents"),
                PDFIUM: N_("The engine of Chrome"),
                POPPLER: N_("The engine of Okular and Evince (its program pdftoppm): slower, one program for "
                            "each page")}
TIMEOUT = 60  # seconds for pdftoppm (the window's watchdog stops a page sooner: see gui/renderer.py)


class BackendError(Exception):
    """A page another engine couldn't draw (MuPDF draws it then)."""


@functools.cache
def _qtpdf() -> bool:
    try:
        from PySide6 import QtPdf  # noqa: F401
    except ImportError:
        return False
    return True


@functools.cache
def _pypdfium2() -> bool:
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False
    return True


@functools.cache
def _pdftoppm() -> str | None:
    return shutil.which("pdftoppm")


def why_not(backend: str) -> str:
    """'' if BACKEND can draw here, else what it needs."""
    if backend == PDFIUM and not (_qtpdf() or _pypdfium2()):
        return tr("Needs Qt PDF or pypdfium2: pip install 'py-pdftools[pdfium]'")
    if backend == POPPLER and _pdftoppm() is None:
        return tr("Needs Poppler's pdftoppm (poppler-utils on Fedora, Debian and Ubuntu)")
    if backend not in BACKENDS:
        return tr("Not an engine of py-pdftools")
    return ""


def available() -> list[str]:
    """The engines that can draw here, MuPDF first."""
    return [b for b in BACKENDS if not why_not(b)]


def detail(backend: str) -> str:
    """How BACKEND draws here (for the check of the system): the library or the program."""
    if backend == PDFIUM:
        return "Qt PDF" if _qtpdf() else "pypdfium2" if _pypdfium2() else ""
    if backend == POPPLER:
        return _pdftoppm() or ""
    return f"PyMuPDF {pymupdf.VersionBind}"


# ----------------------------------------------------------------- drawing

def draw(page: pymupdf.Page, scale: float, clip: tuple | None = None, backend: str = MUPDF) -> pymupdf.Pixmap:
    """PAGE drawn at SCALE by BACKEND (only CLIP of it: x0, y0, x1, y1 in points of the page as shown), as an RGB
    pixmap of MuPDF. Another engine that fails leaves it to MuPDF."""
    if backend != MUPDF and not why_not(backend):
        try:
            return _other(page, scale, clip, backend)
        except Exception:  # noqa: BLE001 (any failure of the other engine: MuPDF draws the page)
            pass
    return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False,
                           clip=pymupdf.Rect(clip) if clip is not None else None)


def _one_page(page: pymupdf.Page) -> bytes:
    """PAGE as a PDF of its own, in memory (with what is left on it: see the module)."""
    one = pymupdf.open()
    one.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
    try:
        return one.tobytes()
    finally:
        one.close()


def _box(page: pymupdf.Page, scale: float, clip: tuple | None) -> tuple[int, int, int, int, int, int]:
    """(the width and height of the whole page in pixels, as shown; x, y, width, height of the part drawn), as
    MuPDF counts them (its rounding outwards: 892.5 pixels are 893), so that every engine gives the same size."""
    m = pymupdf.Matrix(scale, scale)
    full = (page.rect * m).irect
    part = (pymupdf.Rect(clip) * m).irect & full if clip is not None else full
    return full.width, full.height, part.x0 - full.x0, part.y0 - full.y0, max(part.width, 1), max(part.height, 1)


def _other(page: pymupdf.Page, scale: float, clip: tuple | None, backend: str) -> pymupdf.Pixmap:
    data = _one_page(page)
    full_w, full_h, x, y, w, h = _box(page, scale, clip)
    if backend == POPPLER:
        rgb, stride, w, h = _poppler(data, scale, x, y, w, h, clip is not None)
    elif _qtpdf():
        rgb, stride, w, h = _qt(data, full_w, full_h, x, y, w, h)
    else:
        rgb, stride, w, h = _pdfium(data, page, scale, clip, w, h)
    if stride != w * 3:  # (MuPDF's pixmap wants the lines one after another)
        rgb = b"".join(rgb[r * stride: r * stride + w * 3] for r in range(h))
    return pymupdf.Pixmap(pymupdf.csRGB, w, h, rgb, False)


def _poppler(data: bytes, scale: float, x: int, y: int, w: int, h: int, clipped: bool) -> tuple:
    args = [_pdftoppm() or "pdftoppm", "-r", f"{72 * scale:.4f}", "-cropbox", "-f", "1", "-l", "1"]
    if clipped:
        args += ["-x", str(x), "-y", str(y), "-W", str(w), "-H", str(h)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # (en Windows, sin una consola por página)
    try:
        r = subprocess.run([*args, "-"], input=data, capture_output=True, timeout=TIMEOUT, creationflags=flags)
    except (OSError, subprocess.SubprocessError) as e:
        raise BackendError(str(e)) from None
    if r.returncode != 0 or not r.stdout.startswith(b"P6"):
        raise BackendError(r.stderr.decode("utf-8", "replace")[-300:])
    # PPM (P6): "P6", width, height, the largest value, separated by blanks; then the RGB pixels.
    parts, pos = [], 2
    while len(parts) < 3:
        while r.stdout[pos:pos + 1].isspace():
            pos += 1
        end = pos
        while not r.stdout[end:end + 1].isspace():
            end += 1
        parts.append(int(r.stdout[pos:end]))
        pos = end
    width, height = parts[0], parts[1]
    pixels = r.stdout[pos + 1: pos + 1 + width * height * 3]
    return pixels, width * 3, width, height


def _qt(data: bytes, full_w: int, full_h: int, x: int, y: int, w: int, h: int) -> tuple:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, QSize
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions

    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    doc = QPdfDocument(None)
    try:
        doc.load(buffer)
        if doc.status() != QPdfDocument.Status.Ready or doc.pageCount() < 1:
            raise BackendError(str(doc.error()))
        options = QPdfDocumentRenderOptions()
        # (con lo que quedó en la página: campos de formulario y demás; las anotaciones de la ventana ya no están)
        options.setRenderFlags(QPdfDocumentRenderOptions.RenderFlag.Annotations)
        options.setScaledSize(QSize(full_w, full_h))
        options.setScaledClipRect(QRect(x, y, w, h))
        drawn = doc.render(0, QSize(w, h), options)
        # Sobre blanco: lo que PDFium deja transparente es papel.
        out = QImage(drawn.size(), QImage.Format.Format_RGB888)
        out.fill(QColor("white"))
        painter = QPainter(out)
        painter.drawImage(0, 0, drawn)
        painter.end()
        return bytes(out.constBits()), out.bytesPerLine(), out.width(), out.height()
    finally:
        doc.close()
        buffer.close()


def _pdfium(data: bytes, page: pymupdf.Page, scale: float, clip: tuple | None, w: int, h: int) -> tuple:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    try:
        one = doc[0]
        crop = (0, 0, 0, 0)
        if clip is not None:
            # pypdfium2 recorta, después de girar la página, lo que se le dice de cada borde: izquierda, abajo,
            # derecha, arriba.
            width, height = page.rect.width, page.rect.height
            crop = (clip[0], height - clip[3], width - clip[2], clip[1])
        bitmap = one.render(scale=scale, crop=crop, may_draw_forms=True, draw_annots=True, rev_byteorder=True,
                            fill_color=(255, 255, 255, 255))
        mode = bitmap.mode
        raw = bytes(bitmap.buffer)
        width, height, stride = bitmap.width, bitmap.height, bitmap.stride
        if mode in ("RGBA", "RGBX"):  # (four bytes a pixel: the fourth dropped)
            rgb = b"".join(bytes(raw[r * stride + i: r * stride + i + 3])
                           for r in range(height) for i in range(0, width * 4, 4))
            return rgb, width * 3, width, height
        return raw, stride, width, height
    finally:
        doc.close()
