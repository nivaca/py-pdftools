"""Low-level PDF helpers shared by all commands.

Conventions
-----------
* A *rect* is a tuple ``(x0, y0, x1, y1)`` with x0 <= x1, y0 <= y1, in points.
* A *matrix* is a PDF transformation tuple ``(a, b, c, d, e, f)``;
  ``mul(m1, m2)`` means "apply m1, then m2".
* Page *visual* geometry means what a viewer shows, i.e. after ``/Rotate``.
"""

from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass, field

import pikepdf
from pikepdf import Array, Dictionary, Name, Pdf

from ..core.matrix import IDENTITY, Matrix, apply, invert  # noqa: F401  (pdfutil.apply ... for the others)
from ..core.matrix import multiply as mul

Rect = tuple[float, float, float, float]

# Marked-content tags so that stuck-on items can be peeled off again.
TAG_TEXT = "PyImpText"
TAG_TAPE = "PyImpTape"
TAG_MARKS = "PyImpMarks"
TAG_PDF = "PyImpStick"
TAG_BLEED = "PyImpBleed"

HISTORY_KEY = "/PyImpositionHistory"

# Source PDFs whose objects were copied into an output must stay open until the
# output is saved (pikepdf copies stream data lazily).
_KEEP_ALIVE: list = []


def open_source(path) -> "Pdf":
    """Open an auxiliary PDF (background, overlay...) and keep it alive."""
    pdf = Pdf.open(path)
    _KEEP_ALIVE.append(pdf)
    return pdf


def keep_alive(pdf: "Pdf") -> "Pdf":
    _KEEP_ALIVE.append(pdf)
    return pdf


# --------------------------------------------------------------------------- matrices


def chain(*ms: Matrix) -> Matrix:
    # chain(a, b, c) applies a first and c last, so it reads in the order of the transformations.
    out = IDENTITY
    for m in ms:
        out = mul(out, m)
    return out


def translate(tx: float, ty: float) -> Matrix:
    return (1, 0, 0, 1, tx, ty)


def scale(sx: float, sy: float | None = None) -> Matrix:
    return (sx, 0, 0, sx if sy is None else sy, 0, 0)


def rotate(deg_ccw: float) -> Matrix:
    # Giro antihorario, como en matemáticas. /Rotate gira en sentido horario, y por eso quien llama pasa ángulos
    # negativos.
    r = math.radians(deg_ccw)
    c, s = math.cos(r), math.sin(r)
    # snap tiny values so right angles stay exact
    c, s = (0.0 if abs(c) < 1e-12 else c), (0.0 if abs(s) < 1e-12 else s)
    return (c, s, -s, c, 0, 0)


def transform_rect(m: Matrix, r: Rect) -> Rect:
    # Se transforman las cuatro esquinas y se toma la caja que las contiene; con giros de 90° el resultado es exacto.
    pts = [apply(m, x, y) for x in (r[0], r[2]) for y in (r[1], r[3])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def cm_op(m: Matrix) -> bytes:
    return (" ".join(fmt(v) for v in m) + " cm\n").encode()


def fmt(v: float) -> str:
    # Números cortos en el flujo de contenido: enteros sin decimales, y nunca notación científica.
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.5f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- rects


def norm_rect(r) -> Rect:
    x0, y0, x1, y1 = (float(v) for v in r)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def rect_w(r: Rect) -> float:
    return r[2] - r[0]


def rect_h(r: Rect) -> float:
    return r[3] - r[1]


def intersect(a: Rect, b: Rect) -> Rect:
    r = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    # Sin solapamiento se devuelve un rectángulo vacío, no None, para que quien llama pueda seguir calculando con él.
    if r[2] < r[0] or r[3] < r[1]:
        return (r[0], r[1], r[0], r[1])
    return r


def expand(r: Rect, left: float, bottom: float, right: float, top: float) -> Rect:
    return (r[0] - left, r[1] - bottom, r[2] + right, r[3] + top)


def rect_array(r: Rect) -> Array:
    # Rounded to 4 decimals to keep the box arrays short in the output file.
    return Array([round(v, 4) for v in r])


def re_op(r: Rect) -> bytes:
    # El operador re pide x, y, ancho y alto, no dos esquinas.
    return f"{fmt(r[0])} {fmt(r[1])} {fmt(rect_w(r))} {fmt(rect_h(r))} re".encode()


# --------------------------------------------------------------------------- page boxes


def _inherited(page: Dictionary, key: str):
    # MediaBox, CropBox, Rotate and Resources can be inherited from the /Pages tree. The depth limit guards against
    # a cyclic /Parent chain in a broken file.
    node = page
    for _ in range(64):
        if key in node:
            return node[key]
        if "/Parent" not in node:
            return None
        node = node.Parent
    return None


def media_box(page: Dictionary) -> Rect:
    mb = _inherited(page, "/MediaBox")
    # Sin MediaBox (un PDF defectuoso) se supone US Letter.
    return norm_rect(mb) if mb is not None else (0, 0, 612, 792)


def crop_box(page: Dictionary) -> Rect:
    cb = _inherited(page, "/CropBox")
    mb = media_box(page)
    # As the PDF specification says, the crop box is clipped to the media box and defaults to it.
    return intersect(norm_rect(cb), mb) if cb is not None else mb


def trim_box(page: Dictionary) -> Rect:
    # TrimBox y BleedBox no son heredables: se leen solo de la propia página. Si falta, la TrimBox vale la CropBox.
    if "/TrimBox" in page:
        return intersect(norm_rect(page.TrimBox), media_box(page))
    return crop_box(page)


def bleed_box(page: Dictionary) -> Rect:
    # Aquí una BleedBox ausente vale la TrimBox (la especificación dice CropBox): sin caja de sangrado no hay sangrado.
    if "/BleedBox" in page:
        return intersect(norm_rect(page.BleedBox), media_box(page))
    return trim_box(page)


def has_bleed(page: Dictionary) -> bool:
    return "/TrimBox" in page and "/BleedBox" in page and trim_box(page) != bleed_box(page)


def page_rotation(page: Dictionary) -> int:
    r = _inherited(page, "/Rotate")
    return int(r) % 360 if r is not None else 0


def resources(page: Dictionary):
    r = _inherited(page, "/Resources")
    return r if r is not None else Dictionary()


def content_bytes(page: Dictionary) -> bytes:
    # /Contents puede ser un flujo o un arreglo de flujos. Los trozos se unen con un salto de línea, porque un flujo
    # puede terminar a mitad de un token y pegarse al siguiente.
    c = page.get("/Contents")
    if c is None:
        return b""
    if isinstance(c, pikepdf.Array):
        return b"\n".join(s.read_bytes() for s in c)
    return c.read_bytes()


@dataclass
class PageGeom:
    """Geometry of a source page as it will be imposed.

    ``box`` is the area aligned with the layout (trim box when bleeds are
    used, otherwise the crop box). ``clip`` is the area actually shown
    (bleed box or crop box). Both are in the page's own user space.
    ``rotation`` is the clockwise display rotation (``/Rotate``).
    """

    box: Rect
    clip: Rect
    rotation: int

    def visual_matrix(self, extra_cw: float = 0) -> Matrix:
        """Matrix taking page space to visual space where ``box`` sits at (0,0)."""
        return visual_matrix(self.box, self.rotation + extra_cw)

    def size(self, extra_cw: float = 0) -> tuple[float, float]:
        # rotate(-r) gira en sentido horario, como /Rotate; aquí solo interesa el tamaño, no la posición.
        r = transform_rect(rotate(-(self.rotation + extra_cw)), self.box)
        return rect_w(r), rect_h(r)

    def trimmed(self, left: float, bottom: float, right: float, top: float) -> "PageGeom":
        """The page with these amounts cut off its edges (as the page is seen, with its /Rotate).

        Both the layout box and the area shown shrink, so nothing beyond the
        new edges shows (any bleed is cut off too)."""
        if not (left or bottom or right or top):
            return self
        # The cut is made in visual space and mapped back, so 'left' is the left edge as the reader sees it.
        m = self.visual_matrix()
        v = transform_rect(m, self.box)
        new = (v[0] + left, v[1] + bottom, v[2] - right, v[3] - top)
        if new[2] - new[0] <= 0 or new[3] - new[1] <= 0:
            raise ValueError("trim larger than the page")
        box = transform_rect(invert(m), new)
        return PageGeom(box, box, self.rotation)

    def bleed_margins(self, extra_cw: float = 0) -> tuple[float, float, float, float]:
        """Visual (left, bottom, right, top) bleed beyond the box."""
        m = self.visual_matrix(extra_cw)
        b = transform_rect(m, self.box)
        c = transform_rect(m, self.clip)
        return (b[0] - c[0], b[1] - c[1], c[2] - b[2], c[3] - b[3])


def visual_matrix(box: Rect, rotation_cw: float) -> Matrix:
    # Gira según /Rotate y traslada para que la esquina inferior izquierda de la caja quede en el origen.
    r = rotate(-rotation_cw)
    t = transform_rect(r, box)
    return mul(r, translate(-t[0], -t[1]))


def geometry(page: Dictionary, use_bleed: bool = True) -> PageGeom:
    rot = page_rotation(page)
    # Tres casos: sangrado real (TrimBox y BleedBox distintas), solo TrimBox, o ninguna de las dos (se usa la CropBox).
    if use_bleed and has_bleed(page):
        return PageGeom(trim_box(page), bleed_box(page), rot)
    if use_bleed and "/TrimBox" in page:
        tb = trim_box(page)
        return PageGeom(tb, tb, rot)
    cb = crop_box(page)
    return PageGeom(cb, cb, rot)


# --------------------------------------------------------------------------- importing pages


class Importer:
    """Turns source pages into Form XObjects inside a destination PDF.

    Forms are cached so a page placed many times is stored once.
    """

    def __init__(self, dst: Pdf):
        self.dst = dst
        self._cache: dict = {}
        self._caches: list = []

    def form(self, page: Dictionary, clip: Rect) -> pikepdf.Object:
        # Indirect pages are cached per source document: object numbers are only unique within one PDF,
        # so each owner gets its own cache.
        if page.is_indirect:
            cache = None
            for sample, c in self._caches:
                if sample.same_owner_as(page):
                    cache = c
                    break
            if cache is None:
                cache = {}
                self._caches.append((page, cache))
            key = (page.objgen, tuple(round(v, 3) for v in clip))
        else:
            # Las páginas directas (creadas al vuelo) se identifican por id(), que vale mientras el objeto siga vivo.
            cache = self._cache
            key = (id(page), tuple(round(v, 3) for v in clip))
        if key in cache:
            return cache[key]
        # Resources of a page from another PDF must be copied into dst; from the same PDF they can be shared.
        same = (not page.is_indirect) or page.is_owned_by(self.dst)
        res = resources(page)
        data = content_bytes(page)
        if not same:
            res = import_obj(self.dst, res)
        # La Form XObject reutiliza el contenido de la página tal cual; la BBox lo recorta a la caja pedida.
        form = self.dst.make_stream(data)
        form.Type = Name.XObject
        form.Subtype = Name.Form
        form.BBox = rect_array(clip)
        form.Resources = res
        # The transparency group (/Group) keeps blending right once the page becomes a form.
        if "/Group" in page:
            form.Group = page.Group if same else import_obj(self.dst, page.Group)
        form = self.dst.make_indirect(form)
        cache[key] = form
        return form


def import_obj(dst: Pdf, obj):
    """Copy an object (direct or indirect) from another PDF into ``dst``."""
    if isinstance(obj, pikepdf.Object):
        if obj.is_indirect:
            return dst.copy_foreign(obj)
        if isinstance(obj, Dictionary):
            return Dictionary({k: import_obj(dst, v) for k, v in obj.items()})
        if isinstance(obj, Array):
            return Array([import_obj(dst, v) for v in obj])
    return obj


def registration_ops(mode: str, stroke: bool = True) -> tuple[bytes, dict]:
    """Colour operators for marks drawn in 'registration' colour.

    Returns (operators, extra colour-space resources).
    """
    # 'cmyk' pinta con los cuatro tintes al 100 %; 'all' usa la separación /All, que sale en todas las planchas,
    # también en las de tintas planas.
    if mode == "cmyk":
        return (b"1 1 1 1 K\n" if stroke else b"1 1 1 1 k\n"), {}
    if mode == "all":
        return (b"/CSReg CS 1 SCN\n" if stroke else b"/CSReg cs 1 scn\n"), {"/CSReg": "all"}
    return (b"0 G\n" if stroke else b"0 g\n"), {}


def all_separation(pdf: Pdf):
    # Separación /All con alternativa DeviceCMYK: la función de tipo 2 va de sin tinta (0) a CMYK al 100 % (1).
    fn = Dictionary(FunctionType=2, Domain=Array([0, 1]), C0=Array([0, 0, 0, 0]),
                    C1=Array([1, 1, 1, 1]), N=1)
    return pdf.make_indirect(Array([Name.Separation, Name("/All"), Name.DeviceCMYK, fn]))


class Canvas:
    """Accumulates drawing operations for a sheet (a new or existing page)."""

    def __init__(self, pdf: Pdf, page: Dictionary):
        self.pdf = pdf
        self.page = page
        self.ops: list[bytes] = []
        res = _inherited(page, "/Resources")
        if res is None:
            page.Resources = Dictionary()
        elif res.is_indirect or "/Resources" not in page:
            # don't modify resources shared with other pages: make a shallow page-local copy
            page.Resources = Dictionary({k: v for k, v in res.items()})
        # The XObject and ColorSpace subdictionaries are copied as well when indirect, since new names go into them.
        for cat in ("/XObject", "/ColorSpace"):
            if cat in page.Resources and page.Resources[cat].is_indirect:
                page.Resources[cat] = Dictionary({k: v for k, v in page.Resources[cat].items()})
        self.res = page.Resources
        self._n = 0

    def _name(self, category: str, prefix: str, obj) -> str:
        if category not in self.res:
            self.res[category] = Dictionary()
        cat = self.res[category]
        # Busca un nombre libre (Fx1, Fx2...) en la categoría de recursos; el contador sigue entre llamadas.
        while True:
            self._n += 1
            name = f"/{prefix}{self._n}"
            if name not in cat:
                break
        cat[name] = obj
        return name

    def form(self, form, matrix: Matrix, clip: Rect | None = None, tag: str | None = None):
        name = self._name("/XObject", "Fx", form)
        # Each placement is enclosed in q/Q, so its clip and its cm matrix do not affect what comes after.
        ops = b"q\n"
        if clip is not None:
            ops += re_op(clip) + b" W n\n"
        ops += cm_op(matrix) + name.encode() + b" Do\nQ\n"
        self.raw(ops, tag)

    def raw(self, ops: bytes, tag: str | None = None):
        # Contenido marcado (BMC/EMC) con la etiqueta, para poder encontrarlo y quitarlo después con 'peel'.
        if tag:
            ops = f"/{tag} BMC\n".encode() + ops + b"EMC\n"
        self.ops.append(ops)

    def colorspace(self, key: str, value):
        if "/ColorSpace" not in self.res:
            self.res.ColorSpace = Dictionary()
        self.res.ColorSpace[key] = value

    def reg_color(self, mode: str, stroke: bool = True) -> bytes:
        ops, cs = registration_ops(mode, stroke)
        for k in cs:
            if "/ColorSpace" not in self.res or k not in self.res.ColorSpace:
                self.colorspace(k, all_separation(self.pdf))
        return ops

    def finish(self, prepend: bool = False, wrap_existing: bool = True):
        """Write the operations to the page.

        New operations are appended (or prepended) to existing content. The
        existing content is wrapped in q/Q so its graphics state can't leak.
        """
        if not self.ops:
            return
        data = b"".join(self.ops)
        new = self.pdf.make_stream(data)
        existing = self.page.get("/Contents")
        items = []
        if existing is not None:
            items = list(existing) if isinstance(existing, pikepdf.Array) else [existing]
            # Se descartan los flujos vacíos de /Contents, para no envolver nada entre q y Q.
            items = [c for c in items if len(c.read_raw_bytes()) > 0]
        if not items:
            self.page.Contents = new
            self.ops = []
            return
        if wrap_existing:
            items = [self.pdf.make_stream(b"q\n")] + items + [self.pdf.make_stream(b"\nQ\n")]
        # Prepending puts the new operations under the existing content (they are painted first): bleed fill,
        # backgrounds.
        self.page.Contents = Array([new] + items if prepend else items + [new])
        self.ops = []


def new_sheet(pdf: Pdf, w: float, h: float) -> Canvas:
    page = pdf.add_blank_page(page_size=(w, h))
    # Como en reorder(), se quita el /Contents vacío que crea pikepdf; finish() pondrá el contenido real.
    if "/Contents" in page.obj:
        del page.obj["/Contents"]
    return Canvas(pdf, page.obj)


def place_page(canvas: Canvas, importer: Importer, page: Dictionary, geom: PageGeom,
               x: float, y: float, sx: float, sy: float | None = None, rotate_cw: float = 0,
               clip: Rect | None = None, tag: str | None = None) -> Rect:
    """Place ``page`` so the visual lower-left of its layout box is at (x, y).

    Returns the sheet rectangle occupied by the layout box (trim area).
    """
    sy = sx if sy is None else sy
    # Orden: girar y llevar la caja al origen, escalar y, por último, mover a (x, y) en el pliego.
    m = chain(geom.visual_matrix(rotate_cw), scale(sx, sy), translate(x, y))
    # The form is clipped to geom.clip (the bleed box when bleeds are used), so the bleed shows beyond the trim area.
    form = importer.form(page, geom.clip)
    canvas.form(form, m, clip, tag)
    w, h = geom.size(rotate_cw)
    return (x, y, x + w * sx, y + h * sy)


# --------------------------------------------------------------------------- marks


@dataclass
class MarkStyle:
    offset: float = 10.0  # gap between page edge and mark
    length: float = 20.0
    width: float = 0.5
    white_background: bool = False
    registration: str = "black"


def smart_crop_marks(canvas: Canvas, rects: list[Rect], style: MarkStyle, sheet: Rect | None = None):
    """Draw crop marks at every corner of ``rects`` that don't come near any page.

    A mark segment is dropped if any part of it would be closer than
    ``style.offset`` to any page rectangle; marks that survive on only one
    axis become fold marks.
    """
    segs: list[tuple[float, float, float, float]] = []
    o, ln = style.offset, style.length
    for r in rects:
        x0, y0, x1, y1 = r
        for cx, sxn in ((x0, -1), (x1, 1)):
            for cy, syn in ((y0, -1), (y1, 1)):
                # horizontal mark at y=cy extending outward in x
                segs.append((cx + sxn * o, cy, cx + sxn * (o + ln), cy))
                # vertical mark at x=cx extending outward in y
                segs.append((cx, cy + syn * o, cx, cy + syn * (o + ln)))
    keep = []
    seen = set()
    eps = 1e-6
    for s in segs:
        sx0, sy0, sx1, sy1 = min(s[0], s[2]), min(s[1], s[3]), max(s[0], s[2]), max(s[1], s[3])
        bad = False
        for r in rects:
            # Se descarta el segmento si entra en la franja de 'offset' alrededor de cualquier página; eps deja pasar
            # los que solo la tocan.
            g = o - eps
            if sx1 > r[0] - g and sx0 < r[2] + g and sy1 > r[1] - g and sy0 < r[3] + g:
                bad = True
                break
        if bad:
            continue
        if sheet is not None and (sx0 < sheet[0] - eps or sy0 < sheet[1] - eps
                                  or sx1 > sheet[2] + eps or sy1 > sheet[3] + eps):
            continue
        # Neighbouring pages produce the same mark twice; rounding to 0.01 pt removes the duplicates.
        key = tuple(round(v, 2) for v in (sx0, sy0, sx1, sy1))
        if key in seen:
            continue
        seen.add(key)
        keep.append((sx0, sy0, sx1, sy1))
    draw_lines(canvas, keep, style)


def draw_lines(canvas: Canvas, segs, style: MarkStyle, tag: str = TAG_MARKS):
    if not segs:
        return
    path = b"".join(
        f"{fmt(a)} {fmt(b)} m {fmt(c)} {fmt(d)} l\n".encode() for a, b, c, d in segs
    )
    # Extremos rectos (0 J), uniones en inglete (0 j) y trazo continuo.
    ops = b"q 0 J 0 j []0 d\n"
    # The halo is a wider line in almost white (0.99 gray), drawn first, under the mark.
    if style.white_background:
        ops += f"{fmt(style.width * 3)} w 0.99 G\n".encode() + path + b"S\n"
    ops += f"{fmt(style.width)} w\n".encode() + canvas.reg_color(style.registration) + path + b"S\nQ\n"
    canvas.raw(ops, tag)


def frame_rects(canvas: Canvas, rects: list[Rect], style: MarkStyle):
    if not rects:
        return
    ops = b"q 0 J 0 j []0 d " + f"{fmt(style.width)} w\n".encode() + canvas.reg_color(style.registration)
    ops += b"".join(re_op(r) + b"\n" for r in rects) + b"S\nQ\n"
    canvas.raw(ops, TAG_MARKS)


# --------------------------------------------------------------------------- documents


def roundtrip(pdf: Pdf) -> Pdf:
    """Save to memory and reopen, detaching from any foreign sources."""
    buf = io.BytesIO()
    pdf.save(buf)
    buf.seek(0)
    return Pdf.open(buf)


def get_history(pdf: Pdf) -> list[list[str]]:
    # La historia se guarda como JSON en el diccionario /Info; si no se puede leer, se empieza de cero.
    try:
        raw = pdf.trailer.get("/Info", {}).get(HISTORY_KEY)
        if raw is None:
            return []
        data = json.loads(str(raw))
        return [list(map(str, step)) for step in data]
    except Exception:
        return []


def set_history(pdf: Pdf, history: list[list[str]]):
    pdf.docinfo[HISTORY_KEY] = pikepdf.String(json.dumps(history))


def copy_docinfo(src: Pdf, dst: Pdf):
    # Values are copied as strings, so nothing in the new /Info points back into the source PDF.
    try:
        for k, v in src.docinfo.items():
            dst.docinfo[k] = pikepdf.String(str(v))
    except Exception:
        pass


def blank_like(pdf: Pdf, w: float, h: float) -> Dictionary:
    """Create (but don't insert) a blank page dictionary."""
    return pdf.make_indirect(Dictionary(
        Type=Name.Page,
        MediaBox=rect_array((0, 0, w, h)),
        Resources=Dictionary(),
    ))


def visual_size(page: Dictionary, use_bleed: bool = True) -> tuple[float, float]:
    return geometry(page, use_bleed).size()


def normalize_page(pdf: Pdf, page: Dictionary, importer: Importer | None = None) -> Dictionary:
    """Return a page (in ``pdf``) with no /Rotate whose MediaBox starts at (0,0).

    Boxes (crop/trim/bleed) are carried over in the new coordinates. If the
    page already qualifies, it is returned unchanged.
    """
    rot = page_rotation(page)
    mb = media_box(page)
    # Nothing to do when the page has no rotation and its origin is already at (0, 0).
    if rot == 0 and mb[0] == 0 and mb[1] == 0:
        return page
    # La página entera pasa a ser una forma, dibujada con la matriz visual en una página nueva sin /Rotate.
    m = visual_matrix(mb, rot)
    importer = importer or Importer(pdf)
    form = importer.form(page, mb)
    nmb = transform_rect(m, mb)
    # TODO: la página nueva no conserva /Annots ni otras entradas de la original (enlaces, /Group, metadatos);
    # habría que copiarlas, transformando los rectángulos de las anotaciones.
    new = Dictionary(Type=Name.Page, MediaBox=rect_array(nmb), Resources=Dictionary())
    c = Canvas(pdf, new)
    c.form(form, m)
    c.finish()
    # Cada caja se recorta a la MediaBox antes de transformarla; una CropBox heredada se escribe explícita.
    for key in ("/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
        if key in page:
            new[key] = rect_array(transform_rect(m, intersect(norm_rect(page[key]), mb)))
        elif key == "/CropBox" and _inherited(page, "/CropBox") is not None:
            new[key] = rect_array(transform_rect(m, crop_box(page)))
    return pdf.make_indirect(new)
