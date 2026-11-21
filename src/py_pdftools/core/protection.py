"""Protecting a PDF with passwords: one to open it, and one for its permissions (what may be done with it
once open: printing, copying its text, changing it...). The document is encrypted with AES-256, the strongest
method of PDF; a protection is removed only by whoever has the permissions password (or opened it with the
only password it has).

The permissions are a request that PDF programs keep, not a lock: what can be read can be copied by a program
that doesn't keep them. The password to open it is the lock (the file is encrypted with it)."""

from __future__ import annotations

import dataclasses
import os
import tempfile
from pathlib import Path

import pikepdf

from .interface import N_, tr

# (clave en pikepdf.Permissions, nombre mostrado); imprimir en alta calidad incluye imprimir. Leer el texto
# para la accesibilidad siempre se permite: AES-256 no deja negarlo.
PERMISSIONS = [
    ("print_lowres", N_("Print")),
    ("print_highres", N_("Print in high quality")),
    ("extract", N_("Copy text and pictures")),
    ("modify_annotation", N_("Add comments and fill in forms")),
    ("modify_form", N_("Fill in forms")),
    ("modify_assembly", N_("Insert, delete and turn pages")),
    ("modify_other", N_("Change the document in other ways")),
]


class ProtectionError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Protection:
    encrypted: bool = False
    method: str = ""  # ('AES-256', 'RC4-128'...)
    open_password: bool = False  # (si se pide una contraseña para abrirlo)
    owner: bool = True  # (si la contraseña con que se abrió da todos los permisos)
    allowed: frozenset[str] = frozenset(k for k, _ in PERMISSIONS)  # (keys of PERMISSIONS)


def _method(pdf: pikepdf.Pdf) -> str:
    enc = pdf.encryption
    name = str(enc.stream_method).rsplit(".", 1)[-1]
    return {"aesv3": "AES-256", "aes": "AES-128", "rc4": f"RC4-{enc.bits}"}.get(name, name)


def read(path: Path, password: str = "") -> Protection:
    """How the PDF at PATH is protected (opened with PASSWORD)."""
    try:
        with pikepdf.open(path, password=password) as pdf:
            if not pdf.is_encrypted:
                return Protection()
            allowed = frozenset(k for k, _ in PERMISSIONS if getattr(pdf.allow, k))
            try:  # (se prueba sin contraseña: si así abre, no pide ninguna)
                pikepdf.open(path).close()
                needs = False
            except pikepdf.PasswordError:
                needs = True
            return Protection(True, _method(pdf), needs, bool(pdf.owner_password_matched), allowed)
    except pikepdf.PasswordError:
        raise ProtectionError(tr("{path} is protected by a password", path=path)) from None
    except (pikepdf.PdfError, OSError) as e:
        raise ProtectionError(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None


def _write(source: Path, password: str, target: Path, encryption) -> None:
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        with pikepdf.open(source, password=password) as pdf:
            pdf.save(tmp, encryption=encryption)
        os.replace(tmp, target)
    except pikepdf.PasswordError:
        Path(tmp).unlink(missing_ok=True)
        raise ProtectionError(tr("{path} is protected by a password", path=source)) from None
    except (pikepdf.PdfError, OSError) as e:
        Path(tmp).unlink(missing_ok=True)
        raise ProtectionError(tr("{path} cannot be written: {error}", path=target, error=e)) from None


def protect(source: Path, target: Path, *, open_password: str = "", owner_password: str = "",
            allowed: set[str] | frozenset[str] | None = None, password: str = "") -> None:
    """SOURCE (opened with PASSWORD) saved as TARGET (which may be SOURCE), encrypted with AES-256: asking for
    OPEN_PASSWORD to open it (if given), with the permissions ALLOWED (keys of PERMISSIONS; all if None),
    which OWNER_PASSWORD gives back. Without one, the password to open it is also that of the permissions.
    Changing the protection of a protected document needs its permissions password."""
    current = read(source, password)
    if current.encrypted and not current.owner:
        raise ProtectionError(tr("Its protection can be changed only with its permissions password"))
    owner = owner_password or open_password
    if not owner:
        raise ProtectionError(tr("Give a password: to open it, or for its permissions"))
    allowed = {k for k, _ in PERMISSIONS} if allowed is None else set(allowed)
    if "print_highres" in allowed:  # (imprimir bien es imprimir)
        allowed.add("print_lowres")
    perms = pikepdf.Permissions(accessibility=True, **{k: k in allowed for k, _ in PERMISSIONS})
    _write(source, password, target, pikepdf.Encryption(user=open_password, owner=owner, R=6, allow=perms))


def unprotect(source: Path, target: Path, password: str = "") -> None:
    """SOURCE saved as TARGET (which may be SOURCE) with no protection: PASSWORD must be its permissions
    password (or the only one it has)."""
    current = read(source, password)
    if not current.encrypted:
        return
    if not current.owner:
        raise ProtectionError(tr("Its protection can be removed only with its permissions password"))
    _write(source, password, target, False)
