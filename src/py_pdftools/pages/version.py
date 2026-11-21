"""The version of a PDF: what a file says it is (its header, and the catalog's /Version, which may raise it),
and a copy saved as another. Raising it is always safe. Lowering it is safe only if the document uses
nothing newer than the version asked: features() says what it uses and since which version; the copy writes
no object streams below 1.5 (they came with it), and a document encrypted with AES-256 can't go below 1.7
(that encryption came with its extension level 3)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pikepdf

from ..core.interface import N_, tr

VERSIONS = ("1.3", "1.4", "1.5", "1.6", "1.7", "2.0")


class VersionError(Exception):
    pass


def _key(version: str) -> tuple[int, int]:
    major, _, minor = version.partition(".")
    return int(major), int(minor or 0)


def _open(path: Path, password: str) -> pikepdf.Pdf:
    try:
        return pikepdf.open(path, password=password)
    except pikepdf.PasswordError:
        raise VersionError(tr("{path} is protected by a password", path=path)) from None
    except (pikepdf.PdfError, OSError) as e:
        raise VersionError(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None


def version_of(path: Path, password: str = "") -> str:
    """The version of the PDF at PATH (the greater of its header and its catalog's /Version)."""
    with _open(path, password) as pdf:
        version = pdf.pdf_version
        declared = str(pdf.Root.get("/Version", "")).lstrip("/")
        if declared and declared[:1].isdigit() and _key(declared) > _key(version):
            version = declared
        return version


# (what, since which version, what to say of it)
FEATURES = [("transparency", "1.4", N_("Transparency (soft masks, transparency groups)")),
            ("object_streams", "1.5", N_("Objects in compressed streams (written plainly below 1.5)")),
            ("layers", "1.5", N_("Layers (optional content)")),
            ("jpx", "1.5", N_("JPEG 2000 pictures")),
            ("aes128", "1.6", N_("Encryption with AES-128")),
            ("aes256", "1.7", N_("Encryption with AES-256 (it can't go below 1.7)"))]


def features(path: Path, password: str = "") -> dict[str, str]:
    """{feature of FEATURES: since which version} of those the PDF at PATH uses."""
    found: dict[str, str] = {}
    since = {k: v for k, v, _ in FEATURES}
    with _open(path, password) as pdf:
        if pdf.Root.get("/OCProperties") is not None:
            found["layers"] = since["layers"]
        if pdf.is_encrypted:
            method = str(pdf.encryption.stream_method).rsplit(".", 1)[-1]
            if method == "aesv3":
                found["aes256"] = since["aes256"]
            elif method == "aes":
                found["aes128"] = since["aes128"]
        for obj in pdf.objects:
            if isinstance(obj, pikepdf.Stream):
                kind = obj.get("/Type")
                if kind == pikepdf.Name.ObjStm:
                    found["object_streams"] = since["object_streams"]
                filters = obj.get("/Filter")
                names = [str(f) for f in filters] if isinstance(filters, pikepdf.Array) else [str(filters)]
                if "/JPXDecode" in names:
                    found["jpx"] = since["jpx"]
                if obj.get("/SMask") is not None:
                    found["transparency"] = since["transparency"]
            elif isinstance(obj, pikepdf.Dictionary):
                group = obj.get("/Group")
                if isinstance(group, pikepdf.Dictionary) and group.get("/S") == pikepdf.Name.Transparency:
                    found["transparency"] = since["transparency"]
                if obj.get("/SMask") not in (None, pikepdf.Name.None_):
                    found["transparency"] = since["transparency"]
    return found


def newer_than(path: Path, version: str, password: str = "") -> list[str]:
    """What the PDF at PATH uses that is newer than VERSION, said (of FEATURES)."""
    used = features(path, password)
    # (los flujos de objetos no cuentan: la copia los escribe sin ellos cuando la versión no los admite)
    return [tr(text) for key, since, text in FEATURES
            if key in used and key != "object_streams" and _key(since) > _key(version)]


def set_version(source: Path, target: Path, version: str, password: str = "") -> str:
    """SOURCE saved as TARGET (which may be SOURCE) saying it is VERSION (of VERSIONS); without object streams
    below 1.5; its protection kept. Returns the version it had."""
    if version not in VERSIONS:
        raise VersionError(tr("Unknown PDF version: {version}", version=version))
    before = version_of(source, password)
    if _key(version) < (1, 7) and "aes256" in features(source, password):
        raise VersionError(tr("A document encrypted with AES-256 can't be below PDF 1.7"))
    with _open(source, password) as pdf:
        if "/Version" in pdf.Root:
            del pdf.Root["/Version"]
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
        os.close(fd)
        try:
            mode = pikepdf.ObjectStreamMode.disable if _key(version) < (1, 5) else pikepdf.ObjectStreamMode.preserve
            pdf.save(tmp, force_version=version, object_stream_mode=mode,
                     encryption=True if pdf.is_encrypted else None)
        except (pikepdf.PdfError, OSError) as e:
            Path(tmp).unlink(missing_ok=True)
            raise VersionError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    os.replace(tmp, target)
    return before
