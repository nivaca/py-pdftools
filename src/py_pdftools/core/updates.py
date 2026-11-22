"""Ayuda > Buscar una versión nueva: la última versión publicada de py-pdftools, preguntada a GitHub solo cuando
el usuario lo pide (nunca por sí solo), y cómo se actualiza la copia que corre, según cómo se instaló.

La petición es simple: no lleva nada del usuario ni del equipo, solo «py-pdftools» como agente.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
from pathlib import Path

from .. import __version__
from .interface import tr

LATEST_URL = "https://api.github.com/repos/nivaca/py-pdftools/releases/latest"
RELEASES = "https://github.com/nivaca/py-pdftools/releases"


class UpdateError(Exception):
    """The latest version could not be found out (no connection, an answer not understood)."""


@dataclasses.dataclass(frozen=True)
class Release:
    version: str  # ('1.8.11', without the v of the tag)
    url: str  # (its page, with its files)


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.8.11' -> (1, 8, 11); what follows the numbers ('rc1', '+git') is ignored."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", text.strip())
    if not m:
        raise UpdateError(tr("{text} is not a version", text=text))
    return tuple(int(n) for n in m.group(1).split("."))


def newer(than: str, version: str) -> bool:
    """Whether VERSION is newer than THAN."""
    a, b = parse_version(than), parse_version(version)
    width = max(len(a), len(b))
    # (1.9 y 1.9.0 son la misma)
    return b + (0,) * (width - len(b)) > a + (0,) * (width - len(a))


def latest(timeout: float = 15) -> Release:
    """The latest release published (raises UpdateError)."""
    import urllib.request

    request = urllib.request.Request(LATEST_URL, headers={"User-Agent": "py-pdftools",
                                                          "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            data = json.loads(answer.read().decode("utf-8"))
    except OSError as e:  # (urllib's errors are OSErrors: no connection, a refusal, too long)
        raise UpdateError(str(getattr(e, "reason", None) or e)) from None
    except ValueError:
        raise UpdateError(tr("the answer could not be read")) from None
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str):
        raise UpdateError(tr("the answer could not be read"))
    parse_version(tag)  # (raises if it is not a version)
    url = data.get("html_url")
    return Release(tag.lstrip("v"), url if isinstance(url, str) and url.startswith("https://") else RELEASES)


def installation(package: Path | None = None) -> str:
    """How the copy running was installed: 'appimage', 'deb', 'rpm', 'installer' (install/install.sh or
    install.bat), 'source' (a clone run with uv) or 'pip'. PACKAGE: the folder of py_pdftools (this one)."""
    package = (package or Path(__file__).resolve().parent.parent).resolve()
    text = package.as_posix()
    # El .deb lleva los archivos de la AppImage en /opt/py-pdftools: se mira antes que la AppImage.
    if text.startswith("/opt/py-pdftools/"):
        return "deb"
    if os.environ.get("APPIMAGE"):
        return "appimage"
    if text.startswith(("/usr/lib/", "/usr/lib64/")) and sys.platform.startswith("linux"):
        return "rpm"  # (installed by the system's packages: on Fedora, the RPM; /usr/local is pip's)
    # (los instaladores hacen un entorno propio: …/py-pdftools/venv)
    if "/py-pdftools/venv/" in text:
        return "installer"
    root = package.parent.parent
    if (root / "pyproject.toml").is_file() and (root / ".git").exists():
        return "source"
    return "pip"


def how_to_update(kind: str, version: str) -> str:
    """What to do to install VERSION, for an installation of KIND (see installation)."""
    if kind == "rpm":
        return tr("Update it with the system's packages: sudo dnf upgrade py-pdftools")
    if kind == "deb":
        return tr("Download its package (py-pdftools_{version}-1_amd64.deb) from the page of the release, and "
                  "install it: sudo apt install ./py-pdftools_{version}-1_amd64.deb", version=version)
    if kind == "appimage":
        return tr("Download its AppImage (py-pdftools-{version}-x86_64.AppImage) from the page of the release, "
                  "make it executable, and use it in place of this one", version=version)
    if kind == "installer":
        return tr("Download its source (py-pdftools-{version}.zip) from the page of the release, and run its "
                  "installer again: install/install.sh, or install\\install.bat on Windows", version=version)
    if kind == "source":
        return tr("Bring the new version into the folder of the source: git pull")
    return tr("Install its wheel (py_pdftools-{version}-py3-none-any.whl), from the page of the release, with "
              "pip install --upgrade", version=version)
