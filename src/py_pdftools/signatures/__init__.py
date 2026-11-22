"""Digital signatures (with pyHanko, installed apart: pip install py-pdftools[signatures]): digital IDs
made and read (ids.py), documents signed (sign.py), and their signatures checked (verify.py)."""

from ..core.userpackages import reach as _reach

# pyHanko instalado con «pip install --user» también vale para un Python que arranca sin mirar allí (el RPM)
_reach("pyhanko")
