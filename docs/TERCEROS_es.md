Software libre que usa py-pdftools
==================================

*(English: [THIRD-PARTY.md](THIRD-PARTY.md))*

py-pdftools es software libre, con la Licencia Pública General de GNU,
versión 3 o posterior (GPL-3.0-or-later). Está construido sobre el software
libre de esta lista: las bibliotecas que importa, los programas que ejecuta,
los datos que usa y las herramientas que lo hacen, lo prueban y lo
empaquetan. Las versiones son las de py-pdftools 1.6.0 (tal como las
resuelve `uv.lock`); `uv tree` muestra las de una versión posterior. Las
licencias van con sus identificadores SPDX, tal como las declara cada
proyecto.

Todas estas licencias permiten usarlos en un programa bajo la GPL 3.
PyMuPDF y Ghostscript están bajo la GPL Affero de GNU 3, que la sección 13
de la GPL 3 permite combinar con ella; la Mozilla Public License 2.0
(pikepdf, certifi) es compatible con la GPL; PySide6 y Qt se usan bajo la
LGPL 3 de GNU, como bibliotecas que se cargan al ejecutarse.


Las bibliotecas que py-pdftools necesita
----------------------------------------

| Software | Versión | Licencia | Qué hace py-pdftools con él |
|---|---|---|---|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (con MuPDF) | 2.1 | AGPL-3.0 (o una licencia comercial de Artifex) | Dibuja las páginas, lee y escribe anotaciones, censura, capas de OCR, formularios, enlaces, exportaciones |
| [pikepdf](https://github.com/pikepdf/pikepdf) (con qpdf) | 10.18 | MPL-2.0 (qpdf: Apache-2.0) | Etiquetas de página, encabezados y pies, capas, orden de las páginas, imposición, contraseñas |
| [PySide6](https://pyside.org) y Shiboken6 (con Qt 6) | 6.12 | LGPL-3.0-only (o GPL-2.0-only o GPL-3.0-only) | La ventana |
| [reportlab](https://www.reportlab.com/) | 5.1 | BSD-3-Clause | El texto de la imposición (marcas, rótulos) |

Lo que estas traen consigo:

| Software | Versión | Licencia |
|---|---|---|
| [Pillow](https://python-pillow.org) | 13.0 | MIT-CMU |
| [lxml](https://lxml.de/) | 6.1 | BSD-3-Clause |
| [packaging](https://github.com/pypa/packaging) | 26.3 | Apache-2.0 OR BSD-2-Clause |
| [NumPy](https://numpy.org) | 2.5 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| [NetworkX](https://networkx.org/) | 3.7 | BSD-3-Clause |
| [ONNX Runtime](https://onnxruntime.ai) | 1.32 | MIT |
| [FlatBuffers](https://google.github.io/flatbuffers/) | 25.12 | Apache-2.0 |
| [Protocol Buffers](https://protobuf.dev) | 7.36 | BSD-3-Clause |
| [psutil](https://github.com/giampaolo/psutil) | 7.2 | BSD-3-Clause |
| [PyYAML](https://pyyaml.org/) | 6.0 | MIT |
| [tabulate](https://github.com/astanin/python-tabulate) | 0.10 | MIT |
| [charset-normalizer](https://github.com/jawah/charset_normalizer) | 3.5 | MIT |
| pymupdf-layout, pymupdf4llm | 2.1 | (paquetes vacíos, que PyMuPDF 2 conserva para actualizarse; su código está ahora en PyMuPDF, bajo su licencia) |


Firmas digitales (opcional)
---------------------------

Se instalan con `pip install 'py-pdftools[signatures]'`, y en la AppImage y
los instaladores; el paquete de Fedora va sin ellas.

| Software | Versión | Licencia |
|---|---|---|
| [pyHanko](https://github.com/MatthiasValvekens/pyHanko) | 0.38 | MIT |
| pyhanko-certvalidator | 0.33 | MIT |
| [cryptography](https://github.com/pyca/cryptography) | 50.0 | Apache-2.0 OR BSD-3-Clause |
| [cffi](https://github.com/python-cffi/cffi) | 2.1 | MIT-0 |
| [pycparser](https://github.com/eliben/pycparser) | 3.12 | BSD-3-Clause |
| [asn1crypto](https://github.com/wbond/asn1crypto) | 1.5 | MIT |
| [oscrypto](https://github.com/wbond/oscrypto) | 1.3 | MIT |
| [aiohttp](https://github.com/aio-libs/aiohttp) | 3.14 | Apache-2.0 AND MIT |
| aiohappyeyeballs | 2.7 | PSF-2.0 |
| aiosignal, frozenlist, multidict, propcache, yarl | 1.4, 1.8, 7.2, 0.5, 1.25 | Apache-2.0 |
| [attrs](https://www.attrs.org/) | 26.1 | MIT |
| [idna](https://github.com/kjd/idna) | 3.20 | BSD-3-Clause |
| [certifi](https://github.com/certifi/python-certifi) | 2026.11 | MPL-2.0 |
| [uritools](https://github.com/tkem/uritools) | 7.0 | MIT |
| [tzlocal](https://github.com/regebro/tzlocal) | 5.4 | MIT |


Programas que ejecuta, y sus datos
----------------------------------

Se instalan aparte (el paquete de Fedora los recomienda); py-pdftools los
ejecuta como programas propios, y funciona sin ellos, sin lo que hacen.

| Software | Licencia | Para |
|---|---|---|
| [Python](https://www.python.org) | PSF-2.0 | Todo (la AppImage lleva el suyo) |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | El OCR |
| [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) | Apache-2.0 | Los modelos más precisos de Tesseract, descargados desde la configuración si se quiere |
| [Ghostscript](https://www.ghostscript.com) | AGPL-3.0 | Las copias PDF/A y PDF/X (por medio de pdf2iso), con sus perfiles ICC |
| [veraPDF](https://verapdf.org) | GPL-3.0-or-later OR MPL-2.0 | La comprobación de las copias PDF/A, si está instalado |


Datos
-----

| Qué | Licencia | Nota |
|---|---|---|
| El ancho de los caracteres de las fuentes estándar de PDF (`pages/fontmetrics.py`) | — | Una tabla medida (en py-foliation, con su `tools/fontmetrics.py`) en las fuentes URW base 35 (AGPL-3.0, con la excepción de fuentes de URW); no incluye ninguna fuente |
| Los iconos de las acciones (`icons/actions`) y del programa | GPL-3.0-or-later | Dibujados para py-annotate y py-pdftools; antes se usa el tema de iconos del escritorio, si tiene uno con ese nombre |


Los programas del autor de los que viene
----------------------------------------

Todos con GPL-3.0-or-later, de Nicolas Vaughan; su código se copió en
py-pdftools:
[py-annotate](https://github.com/nivaca/py-annotate),
[py-redact](https://github.com/nivaca/py-redact),
[py-foliation](https://github.com/nivaca/py-foliation),
[py-imposition](https://github.com/nivaca/py-imposition),
[py-pdfocr](https://github.com/nivaca/py-pdfocr) y
[pdf2iso](https://github.com/nivaca/pdf2iso).


Para hacerlo, probarlo y empaquetarlo
-------------------------------------

Sirven para hacer py-pdftools, no los usa al ejecutarse.

| Software | Licencia | Para |
|---|---|---|
| [uv](https://github.com/astral-sh/uv) | MIT OR Apache-2.0 | El entorno, la rueda y el paquete fuente |
| [pytest](https://docs.pytest.org) (con iniconfig, pluggy, Pygments) | MIT (Pygments: BSD-2-Clause) | Las pruebas |
| [qpdf](https://github.com/qpdf/qpdf), las utilidades de [Poppler](https://poppler.freedesktop.org) | Apache-2.0; GPL-2.0-or-later | Comprobaciones en las pruebas |
| [python-appimage](https://github.com/niess/python-appimage) | GPL-3.0 | El Python de la AppImage |
| [appimagetool](https://github.com/AppImage/appimagetool), [type2-runtime](https://github.com/AppImage/type2-runtime) | MIT | Hacer la AppImage |
| RPM, rpmdevtools, Fedora Copr | GPL-2.0-or-later | El paquete de Fedora |
| [Xvfb](https://www.x.org) | MIT | Una pantalla para las pruebas de la ventana |
