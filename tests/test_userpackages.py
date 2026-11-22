"""core/userpackages.py: un paquete opcional instalado con pip --user se halla aunque Python haya arrancado
sin mirar los paquetes del usuario (python3 -s, como el RPM), al final de sys.path."""

from __future__ import annotations

import subprocess
import sys

from py_pdftools.core import userpackages


def test_a_module_in_the_users_packages_is_reached(tmp_path):
    """Started with -s, a module only in the user's folder is found once reach() adds it, at the end; one
    that isn't there anywhere is not; and the hint says to install it in the user's packages."""
    folder = tmp_path / "user-site"
    (folder / "onlyhere").mkdir(parents=True)
    (folder / "onlyhere" / "__init__.py").write_text("VALUE = 7\n")
    script = f"""
import site, sys
site.getusersitepackages = lambda: {str(folder)!r}
from py_pdftools.core import userpackages
assert sys.flags.no_user_site
assert not userpackages.reach("nowhere_at_all")
assert userpackages.reach("onlyhere")
import onlyhere
assert onlyhere.VALUE == 7 and sys.path[-1] == {str(folder)!r}
assert userpackages.install_hint("pyhanko") == "python3 -m pip install --user pyhanko"
print("ok")
"""
    out = subprocess.run([sys.executable, "-s", "-c", script], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "ok", out.stderr


def test_without_minus_s_nothing_is_added():
    """With the user's folder already looked at (no -s), nothing is added: what isn't found isn't there."""
    script = """
import sys
from py_pdftools.core import userpackages
before = list(sys.path)
assert not sys.flags.no_user_site
assert not userpackages.reach("nowhere_at_all") and sys.path == before
assert "py-pdftools[signatures]" in userpackages.install_hint("pyhanko")
print("ok")
"""
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "ok", out.stderr
