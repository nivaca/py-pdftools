"""Comprueba, con el Python de un instalador, que el programa corre por sí solo: escribe y lee una anotación con
PyMuPDF, etiquetas de página con pikepdf, hace un PDF con reportlab, importa pyHanko (las firmas digitales) y
abre la ventana con un documento, sin tocar la configuración del usuario. La corren tools/bundle-installer.py,
antes de hacer el instalador, y .github/workflows/installers.yml, una vez instalado.

    PYTHON check.py
"""

import io
import os
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

# (ni la configuración ni la caché del usuario: todo en una carpeta que se borra)
work = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["PY_PDFTOOLS_CONFIG"] = os.path.join(work.name, "config")
os.environ["XDG_CONFIG_HOME"] = os.path.join(work.name, "xdg")
os.environ["APPDATA"] = os.path.join(work.name, "appdata")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pikepdf
import pyhanko.sign  # noqa: F401  (las firmas digitales)
import pymupdf
import PySide6
import reportlab
from reportlab.pdfgen import canvas

from py_pdftools import __version__
from py_pdftools.annotate import annots
from py_pdftools.pages import labels

doc = pymupdf.open()
doc.new_page()
annots.apply(doc, [annots.Annotation("rect", 0, (60, 50, 200, 80), "#ff0000", contents="check")])
assert [a.kind for a in annots.read(doc)] == ["rect"]
pdf = pikepdf.open(io.BytesIO(doc.tobytes()))
labels.write_labels(pdf, [labels.Range(1, "r")])
assert [r.style for r in labels.read_labels(pdf)] == ["r"]
made = io.BytesIO()
page = canvas.Canvas(made)
page.drawString(72, 720, "py-pdftools")
page.save()
assert pymupdf.open("pdf", made.getvalue()).page_count == 1

from PySide6.QtWidgets import QApplication

from py_pdftools.gui import renderer
from py_pdftools.gui.window import MainWindow

app = QApplication([])
renderer.ENABLED = False  # (sin procesos de dibujo: la ventana basta aquí)
path = Path(work.name) / "check.pdf"
doc.save(path)
window = MainWindow()
window.ask_recover = lambda when: False
assert window.open_path(path)
window.drop_work()
window.close()
print(f"py-pdftools {__version__}: PyMuPDF {pymupdf.VersionBind}, pikepdf {pikepdf.__version__}, "
      f"reportlab {reportlab.Version}, pyHanko {version('pyhanko')}, PySide6 {PySide6.__version__}; Python {sys.version.split()[0]}: "
      "an annotation and page labels written and read, a PDF made, the window opened a document")
