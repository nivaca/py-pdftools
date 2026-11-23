"""Los sellos propios: imágenes (un sello oficial, un logotipo, la firma escaneada) que la herramienta Sello pone
como los sellos de siempre. Se hacen de una imagen (PNG, JPEG...) o de una página de un PDF, de la que se toma
solo lo dibujado, sobre fondo transparente y a su tamaño verdadero; se guardan como PNG en la carpeta
«stamps» de la configuración, con su tamaño en puntos en stamps.json. Una anotación de sello con imagen y sin
nombre estándar ya era un sello de imagen: estos sellos no cambian el modelo, solo lo alimentan."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

from ..core.interface import tr

FOLDER = "stamps"
SIZES = "stamps.json"
PICTURE_DPI = 150  # (the resolution a picture is taken to have, for its size on the page)
PDF_DPI = 200  # (the resolution a page of a PDF is drawn at)
LARGEST = 1600  # (pixels: a larger picture is reduced, keeping its proportions)
WIDEST = 220  # (points: a picture wider than this is put narrower; a PDF keeps its own size)


class StampError(Exception):
    """A file that can't be made a stamp, or a stamp that isn't there."""


def folder() -> Path:
    from ..core import config

    return config.config_dir() / FOLDER


def _sizes() -> dict:
    try:
        data = json.loads((folder() / SIZES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _keep_sizes(sizes: dict):
    path = folder() / SIZES
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(sizes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def names() -> list[str]:
    """The stamps of one's own, by name, in alphabetical order."""
    if not folder().is_dir():
        return []
    return sorted((p.stem for p in folder().glob("*.png")), key=str.casefold)


def safe_name(name: str) -> str:
    """NAME as it can be the name of a file: no slashes nor other signs that a folder can't hold."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", name)
    return " ".join(name.split()).strip(". ")[:60]


def _from_picture(path: Path) -> tuple[pymupdf.Pixmap, tuple[float, float]]:
    try:
        pix = pymupdf.Pixmap(str(path))
    except (RuntimeError, ValueError, pymupdf.mupdf.FzErrorBase) as e:
        raise StampError(tr("{path} can't be read as a picture: {error}", path=path.name, error=e)) from None
    if pix.n - pix.alpha not in (1, 3):  # (CMYK u otro: a RGB, que PNG sabe guardar)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    while max(pix.width, pix.height) > LARGEST:
        pix.shrink(1)  # (a la mitad)
    w, h = pix.width * 72 / PICTURE_DPI, pix.height * 72 / PICTURE_DPI
    if w > WIDEST:
        w, h = WIDEST, h * WIDEST / w
    return pix, (w, h)


def _from_pdf(path: Path, page_number: int) -> tuple[pymupdf.Pixmap, tuple[float, float]]:
    try:
        doc = pymupdf.open(str(path))
    except (RuntimeError, ValueError, pymupdf.FileDataError, pymupdf.mupdf.FzErrorBase) as e:
        raise StampError(tr("{path} can't be read as a PDF: {error}", path=path.name, error=e)) from None
    if not 1 <= page_number <= doc.page_count:
        raise StampError(tr("{path} has no page {page}", path=path.name, page=page_number))
    page = doc[page_number - 1]
    drawn = painted(page)
    if drawn is None:
        raise StampError(tr("Page {page} of {path} is blank", page=page_number, path=path.name))
    pix = page.get_pixmap(dpi=PDF_DPI, alpha=True, clip=drawn)
    return pix, (drawn.width, drawn.height)


def painted(page: pymupdf.Page) -> pymupdf.Rect | None:
    """The part of PAGE that has something painted, in points (None: nothing). It is measured on the page drawn
    on a transparent background: the boxes the page reports for its curves include their control points, and a
    circle would come out much larger than it is."""
    pix = page.get_pixmap(dpi=72, alpha=True)
    w, n = pix.width, pix.n
    alphas = bytes(pix.samples)[n - 1::n]  # (solo el canal alfa)
    rows = [y for y in range(pix.height) if alphas[y * w:(y + 1) * w].strip(b"\0")]
    if not rows:
        return None
    left, right = w, 0
    for y in rows:
        row = alphas[y * w:(y + 1) * w]
        left = min(left, len(row) - len(row.lstrip(b"\0")))
        right = max(right, len(row.rstrip(b"\0")))
    # (los píxeles, a 72 ppp, son puntos; uno de margen, para no cortar el borde de un trazo)
    box = pymupdf.Rect(left - 1, rows[0] - 1, right + 1, rows[-1] + 2) + (page.rect.x0, page.rect.y0) * 2
    return box & page.rect


def add(path: Path, name: str = "", page: int = 1) -> str:
    """A stamp of one's own made of the picture or the PDF (its PAGE) at PATH, named NAME (its file's name, if
    none; another stamp of that name is replaced). Its name."""
    path = Path(path)
    name = safe_name(name or path.stem)
    if not name:
        raise StampError(tr("A stamp needs a name"))
    if path.suffix.lower() == ".pdf":
        pix, size = _from_pdf(path, page)
    else:
        pix, size = _from_picture(path)
    folder().mkdir(parents=True, exist_ok=True)
    (folder() / f"{name}.png").write_bytes(pix.tobytes("png"))
    sizes = _sizes()
    sizes[name] = [round(size[0], 2), round(size[1], 2)]
    _keep_sizes(sizes)
    return name


def remove(name: str):
    (folder() / f"{name}.png").unlink(missing_ok=True)
    sizes = _sizes()
    if sizes.pop(name, None) is not None:
        _keep_sizes(sizes)


def image(name: str) -> tuple[bytes, tuple[float, float]]:
    """The PNG of the stamp NAME, and its size on the page, in points (StampError if it isn't there)."""
    path = folder() / f"{name}.png"
    try:
        data = path.read_bytes()
    except OSError:
        raise StampError(tr("The stamp {name} is no longer there", name=name)) from None
    size = _sizes().get(name)
    if not (isinstance(size, list) and len(size) == 2):
        # (sin su tamaño guardado: el de la imagen, como si fuera una foto)
        pix = pymupdf.Pixmap(data)
        w, h = pix.width * 72 / PICTURE_DPI, pix.height * 72 / PICTURE_DPI
        size = [WIDEST, h * WIDEST / w] if w > WIDEST else [w, h]
    return data, (float(size[0]), float(size[1]))
