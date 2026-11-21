"""Digital IDs: a private key and its certificate, in a PKCS #12 file (.p12, .pfx) protected by a password,
as signing needs them. make_id() makes one signed by itself (a self-signed ID): enough to sign one's own
documents, and for those who receive them to check that nothing changed after signing; others trust it
when they are given its certificate (the .cer file written beside it), not by themselves, as they would one
issued by a certification authority. The trusted certificates (trust()) are kept in the folder of the
settings, to check signatures with (see verify.py)."""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

from ..core import config
from ..core.interface import tr

DOCUMENT_SIGNING = "1.3.6.1.4.1.311.10.3.12"  # (the extended key usage of signing documents)


class IdError(Exception):
    pass


def available() -> bool:
    """Whether pyHanko (and cryptography) are installed: signing and checking signatures need them."""
    try:
        import cryptography  # noqa: F401
        import pyhanko  # noqa: F401
    except ImportError:
        return False
    return True


@dataclasses.dataclass(frozen=True)
class Identity:
    name: str
    email: str = ""
    organization: str = ""
    country: str = ""  # (two letters: CO, ES...)


def make_id(who: Identity, password: str, target: Path, years: int = 3) -> Path:
    """A self-signed digital ID for WHO, protected by PASSWORD, written as TARGET (.p12), valid for YEARS;
    its certificate is written beside it, as TARGET with .cer, to be given to those who check the
    signatures. Returns the path of the certificate."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier

    if not who.name.strip():
        raise IdError(tr("A digital ID needs a name"))
    if len(password) < 6:
        raise IdError(tr("The password must have six characters or more"))
    if who.country and (len(who.country) != 2 or not who.country.isalpha()):
        raise IdError(tr("The country is written with two letters (CO, ES, US…)"))
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    parts = [x509.NameAttribute(NameOID.COMMON_NAME, who.name.strip())]
    if who.organization.strip():
        parts.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, who.organization.strip()))
    if who.country:
        parts.append(x509.NameAttribute(NameOID.COUNTRY_NAME, who.country.upper()))
    if who.email.strip():
        parts.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, who.email.strip()))
    name = x509.Name(parts)
    now = dt.datetime.now(dt.UTC)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
               .not_valid_after(now + dt.timedelta(days=365 * years))
               .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
               .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True,
                                            key_encipherment=False, data_encipherment=False, key_agreement=False,
                                            key_cert_sign=False, crl_sign=False, encipher_only=False,
                                            decipher_only=False), critical=True)
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION,
                                                     ObjectIdentifier(DOCUMENT_SIGNING)]), critical=False)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False))
    if who.email.strip():
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.RFC822Name(who.email.strip())]),
                                        critical=False)
    cert = builder.sign(key, hashes.SHA256())
    data = pkcs12.serialize_key_and_certificates(who.name.strip().encode(), key, cert, None,
                                                 serialization.BestAvailableEncryption(password.encode()))
    cer = target.with_suffix(".cer")
    try:
        target.write_bytes(data)
        cer.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    except OSError as e:
        raise IdError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    return cer


def describe(certificate) -> str:
    """Who a certificate (cryptography's, or asn1crypto's as pyHanko gives it) names: its common name, and its
    e-mail address."""
    try:  # (asn1crypto)
        native = certificate.subject.native
        name, email = native.get("common_name", ""), native.get("email_address", "")
    except AttributeError:
        from cryptography.x509.oid import NameOID

        def one(oid):
            found = certificate.subject.get_attributes_for_oid(oid)
            return found[0].value if found else ""
        name, email = one(NameOID.COMMON_NAME), one(NameOID.EMAIL_ADDRESS)
    return f"{name} <{email}>" if name and email else name or email or tr("(no name)")


def read_id(path: Path, password: str):
    """(key, certificate) of the digital ID at PATH; IdError if the password is wrong or it is not one."""
    from cryptography.hazmat.primitives.serialization import pkcs12

    try:
        key, cert, _others = pkcs12.load_key_and_certificates(path.read_bytes(), password.encode())
    except OSError as e:
        raise IdError(tr("{path} cannot be read: {error}", path=path, error=e)) from None
    except ValueError:
        raise IdError(tr("The password of {file} is not right, or it is not a digital ID", file=path.name)) \
            from None
    if key is None or cert is None:
        raise IdError(tr("{file} has no key to sign with", file=path.name))
    return key, cert


# ----------------------------------------------------------------- trusted certificates

def trust_dir() -> Path:
    return config.config_dir() / "trusted"


def trusted() -> list[Path]:
    """The certificates trusted to check signatures with (each a .cer or .pem in trust_dir)."""
    folder = trust_dir()
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in (".cer", ".pem", ".crt", ".der")) \
        if folder.is_dir() else []


def trust(data: bytes, name: str) -> Path:
    """The certificate DATA (DER or PEM) kept as trusted, under NAME (a file name is made of it)."""
    folder = trust_dir()
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60] or "certificate"
    path = folder / f"{safe}.cer"
    n = 1
    while path.exists() and path.read_bytes() != data:
        n += 1
        path = folder / f"{safe}-{n}.cer"
    path.write_bytes(data)
    return path
