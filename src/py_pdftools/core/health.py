"""Revisión de la configuración (Configuración > General > Revisar la configuración): qué tiene py-pdftools
para trabajar y si sus ajustes están bien. Revisa la versión de Python y de las bibliotecas, pyHanko (las
firmas), el archivo de configuración (si se lee, si la carpeta admite escribir, qué valores no valen o no se
conocen), tesseract y los idiomas del OCR, Ghostscript (PDF/A y PDF/X) y el espacio de la carpeta temporal.
Cada revisión da un Check: su estado, lo que se revisó, lo que se halló y, si algo falla, qué hacer. La
ventana añade las suyas (los atajos repetidos: véase gui/health_dialog.py)."""

from __future__ import annotations

import dataclasses
import os
import shutil
import sys
import tempfile
from importlib import metadata

from . import config
from .interface import N_, tr

OK, INFO, WARNING, ERROR = "ok", "info", "warning", "error"
STATUS = {OK: N_("Fine"), INFO: N_("Note"), WARNING: N_("Warning"), ERROR: N_("Problem")}
PYTHON = (3, 14)
# (the name shown, the module; the version is the module's own: PySide6 is installed as PySide6_Essentials)
LIBRARIES = (("PyMuPDF", "pymupdf"), ("pikepdf", "pikepdf"), ("reportlab", "reportlab"), ("PySide6", "PySide6"))
TEMP_FREE = 1 << 30  # (menos de 1 GB libre en la carpeta temporal: los documentos grandes no caben)


@dataclasses.dataclass(frozen=True)
class Check:
    status: str  # OK, INFO, WARNING or ERROR
    title: str  # what was checked
    detail: str  # what was found
    fix: str = ""  # what to do about it, if anything


def worst(checks: list[Check]) -> str:
    """The most serious status of CHECKS."""
    order = [OK, INFO, WARNING, ERROR]
    return max((c.status for c in checks), key=order.index, default=OK)


def python() -> Check:
    v = sys.version_info
    found = f"{v.major}.{v.minor}.{v.micro}"
    if v[:2] >= PYTHON:
        return Check(OK, tr("Python"), found)
    return Check(ERROR, tr("Python"), found, tr("py-pdftools needs Python {version} or later",
                                                version=".".join(map(str, PYTHON))))


def libraries() -> list[Check]:
    out = []
    import importlib

    for name, module in LIBRARIES:
        try:
            loaded = importlib.import_module(module)
        except ModuleNotFoundError:
            out.append(Check(ERROR, name, tr("Not installed"), tr("Install py-pdftools again")))
            continue
        except ImportError as e:  # (instalada, pero no se carga: una biblioteca del sistema que falta)
            out.append(Check(ERROR, name, tr("It can't be loaded: {error}", error=e), tr("Install py-pdftools again")))
            continue
        version = getattr(loaded, "__version__", "") or getattr(loaded, "VersionBind", "") or \
            getattr(loaded, "Version", "")
        out.append(Check(OK, name, str(version) or tr("Installed")))
    return out


def signatures() -> Check:
    title = tr("pyHanko (digital signatures)")
    try:
        return Check(OK, title, metadata.version("pyHanko"))
    except metadata.PackageNotFoundError:
        return Check(INFO, title, tr("Not installed: documents can't be signed, nor their signatures checked"),
                     "pip install 'py-pdftools[signatures]'")


def known(name: str) -> bool:
    """Whether NAME is a setting of the configuration file (of config.py or of annotate/settings.py)."""
    from ..annotate import settings

    if name in config.SETTINGS or name in ("author", "categories", "ocr_language", "pen_pressure", "pen_curve",
                                           "pen_button", "autosave"):
        return True
    if name.startswith("shortcut_"):
        return name[len("shortcut_"):] in settings.SHORTCUTS
    if name.startswith("palette_"):
        n, _, field = name[len("palette_"):].partition("_")
        return n.isdigit() and 1 <= int(n) <= settings.PALETTE_SIZE and field in ("color", "meaning")
    # Un campo de estilo puede llevar a su vez un guion bajo (font_size): se prueban todas las particiones
    return any(ch == "_" and name[:i] in settings.ANNOTATING and name[i + 1:] in settings.STYLE_FIELDS
               for i, ch in enumerate(name))


def valid(name: str, value) -> bool:
    """Whether VALUE is a value the program takes for the setting NAME (else it uses the usual one)."""
    from ..annotate import settings

    if name in config.SETTINGS:
        usual = config.SETTINGS[name]
        # bool antes que int: True también es un int
        if isinstance(usual, bool):
            return isinstance(value, bool)
        if isinstance(usual, int):
            return isinstance(value, int) and not isinstance(value, bool)
        if name == "interface":
            from . import interface

            return value in interface.names()
        if name == "memory":
            from ..gui.performance import LIMITS

            return value in LIMITS
        return isinstance(value, str)
    if name.startswith("shortcut_"):
        return settings.valid("shortcut", value)
    if name.startswith("palette_"):
        return settings.valid("color" if name.endswith("_color") else "meaning", value)
    if name in ("author", "categories", "ocr_language", "pen_pressure", "pen_curve", "pen_button", "autosave"):
        return settings.valid(name, value)
    for i, ch in enumerate(name):
        if ch == "_" and name[:i] in settings.ANNOTATING and name[i + 1:] in settings.STYLE_FIELDS:
            return settings.valid(name[i + 1:], value) and settings.relevant(name[:i], name[i + 1:])
    return False


def configuration() -> list[Check]:
    """The configuration file: whether it can be read and written, and its values."""
    path = config.config_path()
    title = tr("Configuration file")
    out = []
    try:
        data = config.read()
    except config.ConfigError as e:
        return [Check(ERROR, title, tr("It can't be read: {error}", error=e),
                      tr("The usual values are used meanwhile. Correct the file, or delete it to start afresh"))]
    folder = path.parent
    # La carpeta (o la primera que exista por encima) tiene que admitir escribir: si no, nada se guarda.
    there = folder
    while not there.exists() and there != there.parent:
        there = there.parent
    if not os.access(there, os.W_OK):
        out.append(Check(ERROR, title, tr("{folder} can't be written to: no setting will be kept", folder=folder),
                         tr("Give your user permission to write in that folder")))
    elif not path.exists():
        out.append(Check(OK, title, tr("{path} (not made yet: every setting has its usual value)", path=path)))
    else:
        out.append(Check(OK, title, str(path)))
    params = data.get("parameters", {}) if isinstance(data, dict) else {}
    if not isinstance(params, dict):
        out.append(Check(WARNING, tr("Settings"), tr("[parameters] is not a table: every setting has its usual "
                                                    "value"), tr("Correct the file, or delete it")))
        return out
    unknown = sorted(n for n in params if not known(n))
    wrong = sorted(n for n in params if known(n) and not valid(n, params[n]))
    if wrong:
        out.append(Check(WARNING, tr("Settings"),
                         tr("Values that aren't valid, replaced by the usual ones: {names}",
                            names=", ".join(f"{n} = {params[n]!r}" for n in wrong)),
                         tr("Set them again in Settings, or correct them in the file")))
    if unknown:
        out.append(Check(INFO, tr("Settings"), tr("Settings this version doesn't know, left alone: {names}",
                                                  names=", ".join(unknown)),
                         tr("They may come from another version; they do no harm")))
    if not wrong and not unknown:
        out.append(Check(OK, tr("Settings"), tr("{count} settings changed, all valid", count=len(params))))
    return out


def ocr() -> list[Check]:
    """tesseract, and the languages chosen for OCR."""
    from ..annotate import settings as user_settings
    from . import ocr as tesseract

    title = tr("tesseract (OCR)")
    if not tesseract.available():
        return [Check(WARNING, title, tr("Not found: the text of scanned pages can't be read"),
                      tr("Install tesseract (tesseract on Fedora, tesseract-ocr on Debian and Ubuntu)"))]
    out = [Check(OK, title, f"{tesseract.version()} ({tesseract.program()})")]
    have = set(tesseract.languages())
    wanted = tesseract.parse_languages(user_settings.load().ocr_language)
    missing = [n for n in wanted if n not in have]
    if missing:
        out.append(Check(WARNING, tr("Languages of OCR"),
                         tr("Chosen but not installed: {names}", names=", ".join(missing)),
                         tr("Add them in the mode OCR, with Languages…")))
    else:
        out.append(Check(OK, tr("Languages of OCR"), tr("{chosen} (installed: {count})",
                                                        chosen="+".join(wanted), count=len(have))))
    return out


def ghostscript() -> Check:
    """Whether PDF/A and PDF/X can be made."""
    from ..annotate import settings as user_settings
    from . import conform

    title = tr("Ghostscript (PDF/A and PDF/X)")
    given = user_settings.load().pdfconform
    if given:
        found = conform.command(given)
        if found is None:
            return Check(ERROR, tr("pdf2iso"), tr("{path} is not there", path=given),
                         tr("Choose it again in Settings, or leave the field empty to use the one of py-pdftools"))
        return Check(OK, tr("pdf2iso"), " ".join(found))
    why = conform.ghostscript()
    if why:
        return Check(WARNING, title, why, tr("Install Ghostscript (9.5 or later)"))
    from . import pdf2iso

    return Check(OK, title, pdf2iso.find_ghostscript())


def temporary() -> Check:
    folder = tempfile.gettempdir()
    title = tr("Temporary folder")
    try:
        free = shutil.disk_usage(folder).free
    except OSError as e:
        return Check(ERROR, title, tr("{folder} can't be used: {error}", folder=folder, error=e))
    gb = f"{free / (1 << 30):.1f}"
    if free < TEMP_FREE:
        return Check(WARNING, title, tr("{folder}: {gb} GB free", folder=folder, gb=gb),
                     tr("Large documents may not fit while they are edited; free some space"))
    return Check(OK, title, tr("{folder}: {gb} GB free", folder=folder, gb=gb))


def run() -> list[Check]:
    """Every check, in the order they are shown."""
    return [python(), *libraries(), signatures(), *configuration(), *ocr(), ghostscript(), temporary()]


def report(checks: list[Check]) -> str:
    """CHECKS as plain text, to copy (into a message asking for help, for example)."""
    from .. import __version__

    lines = [f"py-pdftools {__version__}, {sys.platform}", ""]
    for c in checks:
        lines.append(f"[{tr(STATUS[c.status])}] {c.title}: {c.detail}")
        if c.fix:
            lines.append(f"    → {c.fix}")
    return "\n".join(lines) + "\n"
