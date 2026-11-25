"""Signing a PDF with a digital ID (pyHanko): visibly, in an area of a page (a new signature field) or in an
empty signature field the form has, or invisibly; with a reason, a place and a way to reach the signer;
certifying it, if wished (the first signature only: what may still change without breaking it); locking the
form's fields; and with a timestamp from a server, if one is given. The signature is added after what the
file has (an incremental update), so earlier signatures stay valid."""

from __future__ import annotations

import dataclasses
import os
import tempfile
from pathlib import Path

import pymupdf

from ..core.interface import N_, tr
from .ids import IdError, read_id

# (clave, nombre): lo que una firma que certifica aún permite
CERTIFY = [("", N_("No: an ordinary signature")), ("none", N_("Certify: no changes allowed")),
           ("forms", N_("Certify: filling in the form allowed")),
           ("annotations", N_("Certify: the form and comments allowed"))]


class SignError(Exception):
    pass


PICTURE_SIZE = 75  # (percent of the height of a visible signature taken by the picture, by default)


@dataclasses.dataclass(frozen=True)
class Options:
    id_path: Path
    password: str
    reason: str = ""
    location: str = ""
    contact: str = ""
    page: int | None = None  # the page of a visible signature (None: invisible, or in FIELD)
    rect: tuple[float, float, float, float] | None = None  # its area, as the page is shown
    field: str = ""  # an empty signature field of the form to sign in ('': a new one)
    certify: str = ""  # of CERTIFY
    lock: bool = False  # the fields of the form locked once signed
    timestamp_url: str = ""  # un servidor de sellos de tiempo (RFC 3161); '' si ninguno
    picture: bytes = b""  # a PNG of the handwritten signature, shown in a visible signature (b'': only text)
    picture_size: int = PICTURE_SIZE  # el porcentaje del alto de la firma que ocupa la imagen (el texto, debajo)


def empty_fields(doc: pymupdf.Document) -> list[str]:
    """The names of the signature fields of DOC not signed yet."""
    found = []
    for page in doc:
        for w in page.widgets() or []:
            if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE and \
                    doc.xref_get_key(w.xref, "V")[0] == "null" and w.field_name not in found:
                found.append(w.field_name)
    return found


def _box(path: Path, password: str, page: int, shown) -> tuple[float, float, float, float]:
    """SHOWN (an area of PAGE, as it is shown) in the PDF's own coordinates, as pyHanko places a field."""
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            doc.authenticate(password)
        p = doc[page]
        r = (pymupdf.Rect(shown) * p.derotation_matrix).normalize() * p.transformation_matrix
        r.normalize()
        return (r.x0, r.y0, r.x1, r.y1)


def _new_name(path: Path, password: str) -> str:
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            doc.authenticate(password)
        names = {w.field_name for page in doc for w in page.widgets() or []}
    n = 1
    while f"Signature{n}" in names:
        n += 1
    return f"Signature{n}"


def _style(text: str, picture: bytes, lines: int, height: float = 0.0, share: int = PICTURE_SIZE):
    """How a visible signature looks: its TEXT (who, when, why) alone, framed, as pyHanko draws it; or, with a
    PICTURE of the handwritten signature, the picture at the top, as large as fits in SHARE percent of the box's
    HEIGHT (points; 0 if unknown: above the text), on no background and with no frame, and the text small at the
    bottom, over the picture's lower part if they don't both fit."""
    from pyhanko import stamp

    if not picture:
        return stamp.TextStampStyle(stamp_text=text)
    import io

    from PIL import Image
    from pyhanko.pdf_utils import images, layout
    from pyhanko.pdf_utils import text as texts

    size = 6
    under = lines * (size + 1.5) + 2  # (el alto de las líneas de texto, más un respiro: la imagen va encima)
    if height > 0:
        # El resto del alto, bajo la imagen; si el texto necesita más, la imagen lo pisa (se dibuja debajo).
        under = height * (100 - max(10, min(share, 100))) / 100
    return stamp.TextStampStyle(
        stamp_text=text, border_width=0, background=images.PdfImage(Image.open(io.BytesIO(picture))),
        background_opacity=1,
        background_layout=layout.SimpleBoxLayoutRule(x_align=layout.AxisAlignment.ALIGN_MID,
                                                     y_align=layout.AxisAlignment.ALIGN_MAX,
                                                     margins=layout.Margins(bottom=under),
                                                     inner_content_scaling=layout.InnerScaling.STRETCH_TO_FIT),
        # (pyHanko deja 10 puntos alrededor del texto; 2 bastan, y le dejan más sitio a la imagen)
        text_box_style=texts.TextBoxStyle(font_size=size, box_layout_rule=layout.SimpleBoxLayoutRule(
            x_align=layout.AxisAlignment.ALIGN_MIN, y_align=layout.AxisAlignment.ALIGN_MIN,
            margins=layout.Margins.uniform(2))),
        inner_content_layout=layout.SimpleBoxLayoutRule(x_align=layout.AxisAlignment.ALIGN_MIN,
                                                        y_align=layout.AxisAlignment.ALIGN_MIN))


def _field_height(path: Path, password: str, name: str) -> float:
    """The height, in points, of the signature field NAME of the PDF at PATH (0 if it isn't there)."""
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            doc.authenticate(password)
        for page in doc:
            for w in page.widgets() or []:
                if w.field_name == name:
                    return abs(w.rect.height)
    return 0.0


def sign(source: Path, target: Path, options: Options, password: str = "") -> str:
    """SOURCE (opened with PASSWORD, if it has one) signed with OPTIONS, saved as TARGET (which may be SOURCE).
    Returns the name of the signature field."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers, timestamps
    from pyhanko.sign.fields import FieldMDPAction, FieldMDPSpec, MDPPerm, SigFieldSpec

    try:
        read_id(options.id_path, options.password)  # (un mensaje claro si la contraseña no es la correcta)
    except IdError as e:
        raise SignError(str(e)) from None
    signer = signers.SimpleSigner.load_pkcs12(pfx_file=str(options.id_path), passphrase=options.password.encode())
    if signer is None:
        raise SignError(tr("The password of {file} is not right, or it is not a digital ID",
                           file=options.id_path.name))
    name = options.field or _new_name(source, password)
    lock = FieldMDPSpec(action=FieldMDPAction.ALL) if options.lock else None
    perms = {"none": MDPPerm.NO_CHANGES, "forms": MDPPerm.FILL_FORMS,
             "annotations": MDPPerm.ANNOTATE}.get(options.certify)
    meta = signers.PdfSignatureMetadata(
        field_name=name, reason=options.reason or None, location=options.location or None,
        contact_info=options.contact or None, certify=bool(options.certify), docmdp_permissions=perms or
        MDPPerm.FILL_FORMS)
    timestamper = timestamps.HTTPTimeStamper(options.timestamp_url) if options.timestamp_url else None
    lines = ["%(signer)s", "%(ts)s"] + ([options.reason] if options.reason else [])
    height = 0.0
    if options.picture:
        if options.field:
            height = _field_height(source, password, options.field)
        elif options.page is not None and options.rect is not None:
            box = _box(source, password, options.page, options.rect)
            height = box[3] - box[1]
    style = _style("\n".join(line.replace("%", "%%") if i > 1 else line for i, line in enumerate(lines)),
                   options.picture, len(lines), height, options.picture_size)
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        with open(source, "rb") as inf:
            writer = IncrementalPdfFileWriter(inf, strict=False)
            if writer.security_handler is not None:
                writer.encrypt(password)
            if not options.field:
                if options.page is not None and options.rect is not None:
                    box = _box(source, password, options.page, options.rect)
                    spec = SigFieldSpec(sig_field_name=name, on_page=options.page, box=box, field_mdp_spec=lock)
                else:
                    spec = SigFieldSpec(sig_field_name=name, field_mdp_spec=lock)
                fields.append_signature_field(writer, spec)
            pdf_signer = signers.PdfSigner(meta, signer=signer, timestamper=timestamper, stamp_style=style)
            with open(tmp, "wb") as out:
                pdf_signer.sign_pdf(writer, output=out)
        os.replace(tmp, target)
    except (OSError, ValueError) as e:
        Path(tmp).unlink(missing_ok=True)
        raise SignError(tr("{path} cannot be signed: {error}", path=source, error=e)) from None
    except Exception as e:  # (pyHanko's own errors: a document already certified, a server that fails...)
        Path(tmp).unlink(missing_ok=True)
        raise SignError(tr("{path} cannot be signed: {error}", path=source, error=e)) from None
    return name
