Open-source software used by py-pdftools
=========================================

*(Español: [TERCEROS_es.md](TERCEROS_es.md))*

py-pdftools is free software, under the GNU General Public License, version 3
or later (GPL-3.0-or-later). It is built on the open-source software listed
here: the libraries it imports, the programs it runs, the data it uses, and
the tools that build, test and package it. The versions are those of
py-pdftools 1.6.1 (as `uv.lock` resolves them); `uv tree` shows those of any
later version. Licences are given as SPDX identifiers, as each project
declares them.

All of these licences allow their use in a program under the GPL 3. PyMuPDF
and Ghostscript are under the GNU Affero GPL 3, which section 13 of the GPL 3
allows to be combined with it; the Mozilla Public License 2.0 (pikepdf,
certifi) is compatible with the GPL; PySide6 and Qt are used under the GNU
LGPL 3, as libraries loaded at run time.


The libraries py-pdftools needs
-------------------------------

| Software | Version | Licence | What py-pdftools does with it |
|---|---|---|---|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (with MuPDF) | 2.1 | AGPL-3.0 (or a commercial licence from Artifex) | Draws the pages, reads and writes annotations, redacts, OCR layers, forms, links, exports |
| [pikepdf](https://github.com/pikepdf/pikepdf) (with qpdf) | 10.18 | MPL-2.0 (qpdf: Apache-2.0) | Page labels, headers and footers, layers, the order of pages, imposition, passwords |
| [PySide6](https://pyside.org) and Shiboken6 (with Qt 6) | 6.12 | LGPL-3.0-only (or GPL-2.0-only or GPL-3.0-only) | The window |
| [reportlab](https://www.reportlab.com/) | 5.1 | BSD-3-Clause | The text of imposition (marks, slugs) |

What these bring with them:

| Software | Version | Licence |
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
| pymupdf-layout, pymupdf4llm | 2.1 | (empty packages, kept by PyMuPDF 2 for upgrading; their code is now in PyMuPDF, under its licence) |


Digital signatures (optional)
-----------------------------

Installed with `pip install 'py-pdftools[signatures]'`, and in the AppImage
and the installers; the Fedora package goes without them.

| Software | Version | Licence |
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


Programs it runs, and their data
--------------------------------

These are installed apart (the Fedora package recommends them); py-pdftools
runs them as programs of their own, and works without them, without what
they do.

| Software | Licence | For |
|---|---|---|
| [Python](https://www.python.org) | PSF-2.0 | Everything (the AppImage brings its own) |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | OCR |
| [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) | Apache-2.0 | The more accurate models of Tesseract, downloaded from Settings when wished |
| [Ghostscript](https://www.ghostscript.com) | AGPL-3.0 | Copies as PDF/A and PDF/X (through pdf2iso), with its ICC profiles |
| [veraPDF](https://verapdf.org) | GPL-3.0-or-later OR MPL-2.0 | Checking PDF/A copies, if it is installed |
| [Pandoc](https://pandoc.org), by John MacFarlane and contributors | GPL-2.0-or-later | Documents: the text and the annotations exported as Word, ODT, EPUB, HTML or LaTeX, and PDFs made from documents |
| [LuaTeX](https://www.luatex.org) and [XeTeX](https://tug.org/xetex/) (of [TeX Live](https://tug.org/texlive/)), [Typst](https://typst.app) | GPL-2.0-or-later; MIT; Apache-2.0 | Making the PDFs of Pandoc (the first one installed) |
| [fontconfig](https://www.freedesktop.org/wiki/Software/fontconfig/) (`fc-list`) | MIT | Finding a font with Greek for those PDFs |
| [Libertinus](https://github.com/alerque/libertinus), [Noto](https://notofonts.github.io), [DejaVu](https://dejavu-fonts.github.io), [GNU FreeFont](https://www.gnu.org/software/freefont/) | OFL-1.1; OFL-1.1; Bitstream Vera licence; GPL-3.0-or-later with the font exception | The font of those PDFs, if one of them is installed (none is included) |


Data
----

| What | Licence | Note |
|---|---|---|
| The widths of the characters of the standard PDF fonts (`pages/fontmetrics.py`) | — | A table measured (in py-foliation, by its `tools/fontmetrics.py`) from the URW base 35 fonts (AGPL-3.0, with the URW font exception); no font is included |
| The icons of the actions (`icons/actions`) and of the program | GPL-3.0-or-later | Drawn for py-annotate and py-pdftools; the desktop's icon theme is used first, where it has an icon of that name |


The author's programs it comes from
-----------------------------------

All under GPL-3.0-or-later, by Nicolas Vaughan; their code was copied into
py-pdftools:
[py-annotate](https://github.com/nivaca/py-annotate),
[py-redact](https://github.com/nivaca/py-redact),
[py-foliation](https://github.com/nivaca/py-foliation),
[py-imposition](https://github.com/nivaca/py-imposition),
[py-pdfocr](https://github.com/nivaca/py-pdfocr),
[pdf-word-finder](https://github.com/nivaca/pdf-word-finder) and
[pdf2iso](https://github.com/nivaca/pdf2iso).


Projects it learnt from
-----------------------

Other free programs whose source was read, or whose ideas were taken, while
py-pdftools was made. Where nothing says that code was copied, it was only
read: what was learnt was written anew, in Python, for this program.

| Project | Authors | Licence | What was taken |
|---|---|---|---|
| [Okular](https://okular.kde.org) | KDE (Albert Astals Cid and contributors) | GPL-2.0-or-later | Source read: the arrangement of its toolbars, its default keys, the find bar, the magnifier, Trim margins, and the choice of the backend that draws a document |
| [Skim](https://skim-app.sourceforge.io) | Michael O. McCracken, Christiaan Hofman and contributors | BSD-3-Clause | Source read: the idea of keeping the annotations in a file apart; the format of its notes (`.skim`), read and written; its notes kept in extended attributes |
| [PDFCraft](https://github.com/storytold/pdfcraft) | ArtCraft Team and the PdfCraft contributors | MIT OR Apache-2.0 | Source read: the navigation (bookmarks, links, history, tabs, split view, reloading), security, combining files and PDFs of pictures, the names of menus and tools, the steps of Escape, ideas for large documents |
| [calibre](https://calibre-ebook.com) | Kovid Goyal and contributors | GPL-3.0-only | Source read: its themes and icon themes, the palette of tooltips, the dialog of errors, Qt's Fusion style under colours of its own. Copied and made longer: its list of the kinds of files that run when opened (`core/runnable.py`) |
| [Visual Studio Code](https://github.com/microsoft/vscode) | Microsoft and contributors | MIT | An idea only: the find bar that slides down from the top, and Ctrl+Shift+P |
| [KDE Plasma](https://kde.org/plasma-desktop/) (System Settings) | KDE | GPL-2.0-or-later | An idea only: the button Apply of the Settings dialog, off until something changes |


Building, testing and packaging
-------------------------------

Used to make py-pdftools, not by it when it runs.

| Software | Licence | For |
|---|---|---|
| [uv](https://github.com/astral-sh/uv) | MIT OR Apache-2.0 | The environment, the wheel and the source package |
| [pytest](https://docs.pytest.org) (with iniconfig, pluggy, Pygments) | MIT (Pygments: BSD-2-Clause) | The tests |
| [qpdf](https://github.com/qpdf/qpdf), [Poppler](https://poppler.freedesktop.org) utilities | Apache-2.0; GPL-2.0-or-later | Checks in the tests |
| [python-appimage](https://github.com/niess/python-appimage) | GPL-3.0 | The Python inside the AppImage |
| [appimagetool](https://github.com/AppImage/appimagetool), [type2-runtime](https://github.com/AppImage/type2-runtime) | MIT | Making the AppImage |
| RPM, rpmdevtools, Fedora Copr | GPL-2.0-or-later | The Fedora package |
| [Xvfb](https://www.x.org) | MIT | A screen for the tests of the window |
