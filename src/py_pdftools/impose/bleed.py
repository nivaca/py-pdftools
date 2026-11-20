"""Define bleeds (trim/bleed boxes), optionally generating content for the bleed area."""

from __future__ import annotations

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, add_page_args, command
from ..core.pagesel import select
from .pagetools import normalized
from ..core.interface import N_, tr


def _bleed_args(p):
    add_page_args(p)
    p.add_argument("--mode", choices=["all", "except-fold", "edges", "from-crop", "remove", "generate-only"],
                   default="all",
                   help=tr("all: same bleed on every edge; except-fold: no bleed on the binding edge; edges: "
                        "per-edge amounts; from-crop: trim = crop box, bleed = media box; remove: delete bleeds; "
                        "generate-only: keep existing boxes and just generate bleed content (default: all)"))
    p.add_argument("--amount", default="3mm", metavar="LEN", help=tr("bleed for all/except-fold (default: 3mm)"))
    for e in ("left", "right", "top", "bottom"):
        p.add_argument(f"--{e}", default="0", metavar="LEN", help=tr('bleed on the {edge} edge with --mode edges', edge=e))
    p.add_argument("--outside", action="store_true",
                   help=tr("take the bleed from outside the visible area (previously cropped content); "
                        "otherwise the bleed is inside the visible page"))
    p.add_argument("--show", action="store_true", help=tr("make the whole bleed area visible (crop box = bleed box)"))
    p.add_argument("--direction", choices=["left", "right"], default="left",
                   help=tr("binding edge for --mode except-fold (default: left)"))
    p.add_argument("--generate", choices=["none", "mirror", "scale"], default="none",
                   help=tr("fill the bleed area: mirror the page edges, or scale the trim area up (default: none)"))


@command("bleed", "define page bleeds (trim and bleed boxes)", _bleed_args,
         description=N_("Define bleeds: set TrimBox/BleedBox so imposition lines up the trim area and lets "
                     "artwork run beyond it. Can generate missing bleed content by mirroring or scaling."))
def bleed(pdf: Pdf, a, ctx: Context):
    sel = select(a.pages, len(pdf.pages), a.parity)
    imp = pu.Importer(pdf)
    for i in sel:
        # normalized() deja la página sin /Rotate y con la MediaBox en el origen, así las cajas se suman y restan sin
        # girarlas.
        page = normalized(pdf, i, imp)
        cb = pu.crop_box(page)
        mb = pu.media_box(page)
        if a.mode == "remove":
            for key in ("/TrimBox", "/BleedBox"):
                if key in page:
                    del page[key]
            # PDF/X requires a TrimBox, so with --pdfx one is kept, equal to the crop box.
            if ctx.pdfx:
                page.TrimBox = pu.rect_array(cb)
            continue
        if a.mode == "generate-only":
            trim, bl = pu.trim_box(page), pu.bleed_box(page)
        elif a.mode == "from-crop":
            trim, bl = cb, mb
        else:
            if a.mode == "edges":
                l, r, t, b = (ctx.L(getattr(a, e)) for e in ("left", "right", "top", "bottom"))
            else:
                l = r = t = b = ctx.L(a.amount)
                if a.mode == "except-fold":
                    # El índice 0 es la página 1 (impar). Con encuadernación a la izquierda, los rectos (impares) tienen
                    # el lomo a la izquierda.
                    odd = (i % 2 == 0)
                    fold_left = odd if a.direction == "left" else not odd
                    if fold_left:
                        l = 0
                    else:
                        r = 0
            # --outside: the trim stays at the visible edge and the bleed reaches beyond it, into content that was
            # cropped away.
            # Without --generate it cannot go past the media box, where there is no content.
            if a.outside:
                trim = cb
                want = pu.expand(cb, l, b, r, t)
                bl = want if a.generate != "none" else pu.intersect(want, mb)
                if bl != want:
                    ctx.warn(tr('page {index}: bleed limited to the media box (use --generate to create it)', index=i + 1))
            else:
                # Sangrado hacia dentro: la página visible pasa a ser la caja de sangrado y la de corte se encoge.
                trim = (cb[0] + l, cb[1] + b, cb[2] - r, cb[3] - t)
                bl = cb
                if trim[2] <= trim[0] or trim[3] <= trim[1]:
                    raise ImpositionError(tr('page {index}: bleed larger than the page', index=i + 1))
        if a.generate != "none":
            generate(pdf, imp, page, trim, bl, a.generate)
            # El contenido generado puede salir de la MediaBox; se agranda para que no quede cortado.
            if bl[0] < mb[0] or bl[1] < mb[1] or bl[2] > mb[2] or bl[3] > mb[3]:
                page.MediaBox = pu.rect_array((min(mb[0], bl[0]), min(mb[1], bl[1]),
                                               max(mb[2], bl[2]), max(mb[3], bl[3])))
        page.TrimBox = pu.rect_array(trim)
        page.BleedBox = pu.rect_array(bl)
        # Show the bleed when asked, and always when generated content lies outside the old visible page.
        if a.show or (a.generate != "none" and a.outside):
            page.CropBox = pu.rect_array(bl)
    return pdf


def generate(pdf: Pdf, imp: pu.Importer, page, trim: pu.Rect, bl: pu.Rect, how: str):
    """Draw content into the bleed area, behind the page."""
    # La página recortada a la TrimBox se convierte en forma y se dibuja otra vez, detrás del contenido, en la zona de
    # sangrado.
    form = imp.form(page, trim)
    canvas = pu.Canvas(pdf, page)
    x0, y0, x1, y1 = trim
    if how == "scale":
        # scale: the trim area is stretched (each axis on its own) to cover the whole bleed box, and clipped to it.
        sx = pu.rect_w(bl) / pu.rect_w(trim)
        sy = pu.rect_h(bl) / pu.rect_h(trim)
        m = pu.chain(pu.translate(-x0, -y0), pu.scale(sx, sy), pu.translate(bl[0], bl[1]))
        canvas.form(form, m, clip=bl, tag=pu.TAG_BLEED)
    else:
        # Espejo: cada una de las ocho zonas alrededor de la TrimBox recibe la página reflejada sobre el borde más
        # cercano
        # (x' = 2*x0 - x, y' = 2*y0 - y); las esquinas se reflejan en los dos ejes.
        mx = {"l": (-1, 0, 0, 1, 2 * x0, 0), "r": (-1, 0, 0, 1, 2 * x1, 0), "c": pu.IDENTITY}
        my = {"b": (1, 0, 0, -1, 0, 2 * y0), "t": (1, 0, 0, -1, 0, 2 * y1), "c": pu.IDENTITY}
        xr = {"l": (bl[0], x0), "c": (x0, x1), "r": (x1, bl[2])}
        yr = {"b": (bl[1], y0), "c": (y0, y1), "t": (y1, bl[3])}
        for hx in "lcr":
            for vy in "bct":
                if hx == "c" and vy == "c":
                    continue
                rx, ry = xr[hx], yr[vy]
                # Se omiten las franjas de ancho nulo (bordes sin sangrado).
                if rx[1] - rx[0] <= 0 or ry[1] - ry[0] <= 0:
                    continue
                m = pu.mul(mx[hx], my[vy])
                canvas.form(form, m, clip=(rx[0], ry[0], rx[1], ry[1]), tag=pu.TAG_BLEED)
    # prepend: lo generado se pinta antes que la página, de modo que queda debajo del contenido original.
    canvas.finish(prepend=True)
