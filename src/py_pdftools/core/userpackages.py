"""Paquetes opcionales instalados por el usuario con pip (pyHanko, para las firmas) cuando el programa corre
con un Python que no los mira: el paquete RPM de Fedora arranca con «python3 -s», que deja fuera la carpeta
de paquetes del usuario (~/.local/lib/python3.X/site-packages), donde pip los instala. Si el módulo no está
en los del sistema pero sí en esa carpeta, se añade al final de sys.path: lo del sistema sigue primero, y
nada suyo queda sustituido."""

from __future__ import annotations

import importlib
import importlib.util
import site
import sys
from pathlib import Path


def reach(module: str) -> bool:
    """Whether MODULE can be imported, looking also in the user's packages if Python was started without
    them (-s), and it is there."""
    if importlib.util.find_spec(module) is not None:
        return True
    # (sin -s, la carpeta del usuario ya está en sys.path: si no se halló, no está)
    if not sys.flags.no_user_site:
        return False
    try:
        folder = site.getusersitepackages()
    except Exception:
        return False
    if not Path(folder, module).is_dir():
        return False
    if folder not in sys.path:
        sys.path.append(folder)  # (al final: los paquetes del sistema siguen primero)
        importlib.invalidate_caches()
    return importlib.util.find_spec(module) is not None


def install_hint(requirement: str) -> str:
    """How to install REQUIREMENT for the Python running now: as py-pdftools' extra if installed with pip,
    or by itself in the user's packages for a package of the system (the RPM), which then finds it."""
    if sys.flags.no_user_site:
        return f"python3 -m pip install --user {requirement}"
    return "pip install 'py-pdftools[signatures]'" if requirement.lower().startswith("pyhanko") \
        else f"pip install {requirement}"
