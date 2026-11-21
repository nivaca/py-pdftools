"""PDF/A and PDF/X output, made by the author's pdf2iso (Ghostscript and
pikepdf), which is part of py-pdftools (core/pdf2iso.py): the document is
written first as a plain PDF, then converted, in a process of its own
(``python -m py_pdftools.core.pdf2iso``). Only Ghostscript must be installed.
The setting "pdfconform" may name another pdf2iso (a script) to run instead.

PDF/A and PDF/X don't allow encryption, so a protected document comes out
unprotected (pdf2iso is given its password).
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .interface import N_, tr
from .replacing import replace

# What must be installed for PDF/A and PDF/X (named in the messages): pdf2iso is part of py-pdftools now,
# but Ghostscript does the conversion
COMMAND = "Ghostscript"
# (value of pdf2iso --target, name shown)
STANDARDS = [("a-1b", N_("PDF/A-1b (archiving, the oldest)")), ("a-2b", N_("PDF/A-2b (archiving)")),
             ("a-3b", N_("PDF/A-3b (archiving, with attachments)")), ("x-4", N_("PDF/X-4 (printing)"))]
TIMEOUT = 600  # seconds


class ConformError(Exception):
    """A conversion that failed."""


def own_folders() -> list[Path]:
    """The folders of this program's own Python (its virtual environment, or the
    AppImage), which pdf2iso must not see: it would run with this Python,
    which hasn't its libraries."""
    out = []
    if sys.prefix != sys.base_prefix:
        out.append(Path(sys.prefix).resolve())
    for name in ("APPDIR", "VIRTUAL_ENV"):  # (also a virtual environment this program was started from)
        if os.environ.get(name):
            out.append(Path(os.environ[name]).resolve())
    return out


def clean_env() -> dict[str, str]:
    """The environment for pdf2iso: the user's, without this program's Python."""
    own = own_folders()

    def ours(folder: str) -> bool:
        try:
            p = Path(folder).resolve()
        except OSError:
            return False
        return any(p == o or o in p.parents for o in own)

    # Estas variables llevarían a pdf2iso hacia nuestro Python o nuestras bibliotecas (en la AppImage,
    # LD_LIBRARY_PATH y QT_PLUGIN_PATH); se quitan todas.
    env = {k: v for k, v in os.environ.items()
           if k not in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
                        "SSL_CERT_FILE", "LD_LIBRARY_PATH", "QT_PLUGIN_PATH")}
    # The folders of our venv or AppImage also leave the PATH, so that 'python3' is the system's one.
    env["PATH"] = os.pathsep.join(f for f in os.environ.get("PATH", "").split(os.pathsep) if f and not ours(f))
    return env


def configured() -> str:
    """The path of pdf2iso given in the configuration file ('' for none)."""
    from . import config

    value = config.get("pdfconform")
    return value if isinstance(value, str) and "\n" not in value else ""


def builtin() -> list[str]:
    """How to run the pdf2iso of py-pdftools: with this program's own Python, which has pikepdf."""
    return [sys.executable, "-m", "py_pdftools.core.pdf2iso"]


def find(path: str = "") -> Path | None:
    """pdf2iso: PATH if given (another one, a script: None if there is no such file), or else the one of
    py-pdftools (core/pdf2iso.py). (Before it was part of py-pdftools, it was looked for on the PATH and
    in ~/bin and ~/.local/bin, also by its old name, py-pdfconform.)"""
    if path:
        # Una ruta dada no se busca en el PATH: o es un archivo, o no hay pdf2iso.
        p = Path(path).expanduser()
        return p if p.is_file() else None
    return Path(__file__).with_name("pdf2iso.py")


def command(path: str | None = None) -> list[str] | None:
    """How to run pdf2iso: the one of the configuration file (or PATH), if one is given ([the script], or
    [python3, the script] for a script that can't be run by itself; None if there is no such file), or
    else the one of py-pdftools."""
    given = configured() if path is None else path
    if not given:
        return builtin()
    script = find(given)
    if script is None:
        return None
    # (on Windows every file passes os.access(X_OK), and a script runs only through Python)
    if sys.platform != "win32" and os.access(script, os.X_OK):
        return [str(script)]
    # Sin permiso de ejecución (o en Windows) hay que llamar al intérprete, buscado en el PATH limpio.
    path = clean_env()["PATH"]
    names = ("py", "python", "python3") if sys.platform == "win32" else ("python3",)
    python = next((p for p in map(lambda n: shutil.which(n, path=path), names) if p), None) or "/usr/bin/python3"
    return [python, str(script)]


@functools.cache
def ghostscript() -> str:
    """Why Ghostscript can't make PDF/A and PDF/X here ('' if it can: it is installed, and recent enough).
    Looked for once: the window asks each time it shows its menus."""
    from . import pdf2iso

    try:
        pdf2iso.find_ghostscript()
    except pdf2iso.ConversionError as e:
        return str(e)
    return ""


def available(path: str | None = None) -> bool:
    """Whether PDF/A and PDF/X can be made: with another pdf2iso (if one is given), whether it is there;
    with the one of py-pdftools, whether Ghostscript is installed."""
    exe = command(path)
    if exe is None:
        return False
    return exe != builtin() or not ghostscript()


def label(standard: str) -> str:
    return "PDF/" + standard[0].upper() + standard[1:] if standard else "PDF"


def convert(source: Path, target: Path, standard: str, password: str = "") -> str:
    """SOURCE converted to STANDARD ('a-2b', 'x-4'...) as TARGET (safely: TARGET
    may be SOURCE). Returns what pdf2iso says about it (its check)."""
    exe = command()
    if exe is None:
        raise ConformError(tr("{command} is not installed (or not on the PATH)", command=configured()))
    own = exe == builtin()
    if own and ghostscript():
        raise ConformError(ghostscript())
    if standard not in [s for s, _ in STANDARDS]:
        raise ConformError(standard)
    # The temporary file is made in the target's folder, so that os.replace is a rename on one file system.
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    args = [*exe, "-t", standard, "-o", tmp] + (["-p", password] if password else []) + [str(source)]
    try:
        # (another pdf2iso runs without this program's Python, which hasn't its libraries; the own one, with it)
        r = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT,
                           env=dict(os.environ) if own else clean_env())
        # pdf2iso may end with 0 and still leave an empty file: both are failures.
        if r.returncode != 0 or not Path(tmp).stat().st_size:
            raise ConformError(tr("{command} could not make {standard}: {error}", command=COMMAND,
                                  standard=label(standard),
                                  error=(r.stderr or r.stdout).strip() or r.returncode))
        replace(tmp, target)
    except subprocess.TimeoutExpired:
        raise ConformError(tr("{command} took too long", command=COMMAND)) from None
    except OSError as e:
        raise ConformError(str(e)) from None
    finally:
        # Si os.replace ya movió el archivo, no queda nada que borrar (missing_ok).
        Path(tmp).unlink(missing_ok=True)
    # its last line: "OK  (veraPDF: PASS) in.pdf -> out.pdf [PDF/A-2b]"
    said = r.stdout.strip().splitlines()
    check = said[-1] if said else ""
    return check[check.index("(") + 1:check.index(")")] if "(" in check and ")" in check else ""
