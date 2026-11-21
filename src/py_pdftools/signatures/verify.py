"""Checking the signatures of a PDF (pyHanko): for each, whether what it signed is unchanged (intact) and the
signature is right (valid), whether its signer is trusted (its certificate, or one that issued it, is among
the trusted ones: see ids.trusted), when it was signed, and what came after it in the file (nothing; form
filling or comments, which a signature may allow; or other changes). The version of the document a
signature signed can be cut out of the file (signed_version). It works offline: certificates are not
looked up, nor revoked ones."""

from __future__ import annotations

import dataclasses
import datetime as dt
import io
from pathlib import Path

from ..core.interface import N_, tr
from . import ids

# what came after a signature (pyHanko's ModificationLevel), said
CHANGES = {"NONE": N_("Nothing has changed since it was signed"),
           "LTA_UPDATES": N_("Only data to check it in the long term was added after it"),
           "FORM_FILLING": N_("The form was filled in or signed again after it"),
           "ANNOTATIONS": N_("Comments were added after it, or the form was filled in"),
           "OTHER": N_("The document was changed after it in ways the signature does not allow")}


class VerifyError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Report:
    field: str
    signer: str
    intact: bool  # what it signed is unchanged
    valid: bool  # the signature itself is right (and intact)
    trusted: bool  # its signer's certificate is trusted
    changes: str  # of CHANGES
    whole: bool  # it covers the whole file (nothing came after it)
    signed_at: dt.datetime | None = None  # as the signer's computer said
    timestamped: dt.datetime | None = None  # as a timestamp server vouches
    certified: bool = False
    reason: str = ""
    location: str = ""
    end: int = 0  # where what it signed ends in the file (its version is the file up to there)
    certificate: bytes = b""  # of the signer (DER), to trust it
    details: str = ""

    @property
    def verdict(self) -> str:
        """In a few words, what to think of it."""
        if not self.intact:
            return tr("Invalid: what it signed was changed")
        if not self.valid:
            return tr("Invalid")
        if self.changes == "OTHER":
            return tr("Valid, but the document was changed after it")
        if not self.trusted:
            return tr("Valid, but the signer is not among those trusted")
        return tr("Valid, and the signer is trusted")

    @property
    def good(self) -> bool:
        return self.intact and self.valid and self.trusted and self.changes != "OTHER"


def _context():
    from pyhanko.keys import load_cert_from_pemder
    from pyhanko_certvalidator import ValidationContext

    roots = []
    for path in ids.trusted():
        try:
            roots.append(load_cert_from_pemder(str(path)))
        except Exception:  # (un archivo que no es un certificado se pasa por alto)
            continue
    # Sin conexión: no se buscan certificados ni listas de revocados; lo que falte no invalida la firma.
    return ValidationContext(trust_roots=roots, allow_fetching=False, revocation_mode="soft-fail")


def check(path: Path, password: str = "") -> list[Report]:
    """The signatures of the PDF at PATH, checked, in the order they were made."""
    import logging

    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature

    # pyHanko escribe en el registro cada certificado que no es de confianza; aquí eso es un resultado, no un error.
    for name in ("pyhanko", "pyhanko_certvalidator"):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    try:
        data = path.read_bytes()
    except OSError as e:
        raise VerifyError(tr("{path} cannot be read: {error}", path=path, error=e)) from None
    try:
        reader = PdfFileReader(io.BytesIO(data), strict=False)
        if reader.security_handler is not None:
            reader.decrypt(password)
        found = list(reader.embedded_signatures)
    except Exception as e:
        raise VerifyError(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None
    out = []
    for sig in found:
        try:
            status = validate_pdf_signature(sig, _context())
        except Exception as e:  # (una firma dañada se cuenta como inválida, con la razón)
            out.append(Report(sig.field_name, tr("(unknown)"), False, False, False, "OTHER", False,
                              details=str(e)))
            continue
        cert = status.signing_cert
        level = getattr(status.modification_level, "name", "OTHER") if status.modification_level else "NONE"
        coverage = getattr(status.coverage, "name", "")
        sig_dict = sig.sig_object
        byte_range = [int(x) for x in sig_dict["/ByteRange"]]
        start, length = byte_range[2], byte_range[3]
        ts = getattr(status, "timestamp_validity", None)
        out.append(Report(
            field=sig.field_name, signer=ids.describe(cert), intact=bool(status.intact),
            valid=bool(status.valid), trusted=bool(status.trusted), changes=level if level in CHANGES else "OTHER",
            whole=coverage == "ENTIRE_FILE", signed_at=status.signer_reported_dt,
            timestamped=getattr(ts, "timestamp", None) if ts is not None else None,
            certified=sig.docmdp_level is not None, reason=str(sig_dict.get("/Reason", "") or ""),
            location=str(sig_dict.get("/Location", "") or ""), end=start + length,
            certificate=cert.dump() if cert is not None else b"", details=status.pretty_print_details()))
    return out


def signed_version(path: Path, report: Report, target: Path) -> Path:
    """The document as REPORT's signature signed it (the file up to where it ends), written as TARGET."""
    try:
        target.write_bytes(path.read_bytes()[:report.end])
    except OSError as e:
        raise VerifyError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    return target


def trust(report: Report) -> Path:
    """The certificate of REPORT's signer kept as trusted."""
    if not report.certificate:
        raise VerifyError(tr("This signature has no certificate to trust"))
    return ids.trust(report.certificate, report.signer)
