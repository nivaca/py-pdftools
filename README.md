py-pdftools
===========

*(Español: [README_es.md](README_es.md))*

py-pdftools edits PDF documents. It annotates them, redacts them, changes
their page labels, headers, footers, watermarks and the order of their
pages, and imposes them for printing. It brings together, in one window
and one command line, what four earlier programs of mine did apart:

* [py-annotate](https://github.com/nivaca/py-annotate): highlights, notes,
  text boxes, shapes, drawings and stamps, written as ordinary PDF
  annotations;
* [py-redact](https://github.com/nivaca/py-redact): boxes over what is to be
  removed, and a redacted copy in which it is removed for good, and checked;
* [py-foliation](https://github.com/nivaca/py-foliation): page labels (roman
  numbers, folios, prefixes), headers and footers with Bates numbers,
  watermarks, the view when the document is opened, and the order of the
  pages;
* [py-imposition](https://github.com/nivaca/py-imposition): booklets, n-up,
  step and repeat, bleeds and crop marks, sequences and hot folders.

The window and the command line are in English and in Spanish. It runs on
Linux, and its installers also install it on Windows and macOS. This is
version 0.1.0.

I am Nicolas Vaughan (<nicolasvaughan@proton.me>), and I wrote it in 2026.
It is free software, under the GNU General Public License, version 3 or
later (see "Licensing").

Screenshots
-----------

The mode Annotate:

![Annotate](docs/img/annotate_en.png)

The mode Redact: a box over a line, which goes on every page from the
second:

![Redact](docs/img/redact_en.png)

The mode Pages: no label on the title page, then 1, 2, 3, and the label in
the footer:

![Pages](docs/img/pages_en.png)

The mode Impose: a booklet:

![Impose](docs/img/impose_en.png)

Installation
------------

Every version is in the [releases](https://github.com/nivaca/py-pdftools/releases),
on GitHub and on [Codeberg](https://codeberg.org/nivaca/py-pdftools/releases),
with these files:

    py-pdftools-VERSION.zip                 the source, with the installers
    py-pdftools-VERSION-x86_64.AppImage     the AppImage (Linux)
    py-pdftools-VERSION-1.fc45.noarch.rpm   the Fedora package, signed
    RPM-GPG-KEY-py-pdftools                 the key that signs it
    py_pdftools-VERSION.tar.gz              the source package, for Python
    py_pdftools-VERSION-py3-none-any.whl    the wheel, for Python

**Fedora.** From [Copr](https://copr.fedorainfracloud.org/coprs/nivaca/py-pdftools/),
for Fedora 45 and later, with Fedora's own Python, PyMuPDF, pikepdf,
reportlab and PySide6, a menu entry and the manual (`man py-pdftools`):

    $ sudo dnf copr enable nivaca/py-pdftools
    $ sudo dnf install py-pdftools

Updates then come with `sudo dnf upgrade`. The RPM of each release can also
be installed by hand, after importing its key: `sudo rpm --import
RPM-GPG-KEY-py-pdftools`.

**AppImage (any Linux).** It needs nothing else: it brings its own Python,
Qt and libraries, and runs with glibc 2.34 or later (Ubuntu 22.04, Debian
12, Fedora 35 and later). Make it executable and run it:

    $ chmod +x py-pdftools-*-x86_64.AppImage
    $ ./py-pdftools-*-x86_64.AppImage [file.pdf]                 the window
    $ ./py-pdftools-*-x86_64.AppImage impose booklet book.pdf    a command

**With the installers (Linux, macOS, Windows).** They need Python 3.14 or
later. From the folder of the source:

    $ install/install.sh                Linux and macOS: install, or update
    $ install/install.sh --uninstall
    > install\install.bat               Windows: install, or update
    > install\install.bat -Desktop      also a shortcut on the desktop
    > install\install.bat -Uninstall

Each one makes a Python environment of its own for py-pdftools, installs it
there with PyMuPDF, pikepdf, reportlab and PySide6 (downloaded from PyPI, so
it needs internet the first time), links the commands `py-pdftools` and
`py-pdftools-gui`, and adds the window to the menu of the system. Nothing
needs administrator rights, and the settings are never touched.

**From the source**, with [uv](https://docs.astral.sh/uv/):

    $ git clone https://github.com/nivaca/py-pdftools.git
    $ cd py-pdftools
    $ uv run py-pdftools-gui [file.pdf]       the window
    $ uv run py-pdftools --help               the command line

To save copies as PDF/A or PDF/X, [pdf2iso](https://github.com/nivaca/pdf2iso)
is needed too, with Ghostscript. For searchable copies of scanned pages,
Tesseract.

The window
----------

A document is opened with File > Open, or dropped on the window. Its pages
are shown one under the other, with their thumbnails on the left. The bar
of modes, at the top (or Ctrl+1 to Ctrl+4), chooses what the window does:

* **Annotate**: the tools of py-annotate, in the second toolbar and the
  menu Tools; the panel of the annotations on the right, which can be
  searched, filtered and sorted;
* **Redact**: the tool Redact (dragging over text marks it; elsewhere, or
  with Ctrl, it draws a box), Find and redact, redaction codes, and the
  panel of the boxes;
* **Pages**: the ranges of labels and the list of the pages with their
  labels, on the right; the actions on the pages chosen in the toolbar and
  in their right-click menu; headers and footers, watermarks and the view
  when the document is opened, in the menu Pages;
* **Impose**: py-imposition's workspace, with its basic form, the forms of
  every command, the sequence and the log, in place of the pages.

Each mode works on its own annotations: in Annotate, the redaction boxes are
shown, but the mouse goes through them, and in Redact the annotations are.
Undo goes back through everything done to the document, in any mode.

**Saving.** File > Save writes the document: its annotations, its redaction
boxes (as the PDF's redaction marks, not yet applied), and the changes of
the modes Pages and Impose. Those changes are made at once on a working
copy, and shown, but the file stays as it was until it is saved.

**Redacting.** Nothing under the boxes is removed until the redacted copy is
written, with Redact > Save the redacted copy (Ctrl+Shift+R): a new file,
never the one open, in which what is under the boxes is removed for good.
It is checked as it is written: if any text under a box can still be read,
or a bookmark gives it away, the window says so. The copy is made from the
document as it was last saved, so the window offers to save the other
changes first. Copies that make the annotations part of the pages
(flattened, searchable, printed) leave the boxes out, since a box painted
there would hide what is still in the file.

**Imposing.** The mode Impose imposes the document as it is in the window.
Preview runs the command and shows the result; Save writes the result as a
new file; Apply makes the result the document (Undo takes it back).

The command line
----------------

    $ py-pdftools labels set book.pdf 1:r 9:D -i       i, ii ... from page 1; 1, 2 ... from page 9
    $ py-pdftools labels book.pdf                      the labels of a file
    $ py-pdftools header-footer book.pdf --footer-center 'Page $pagelabel' -i
    $ py-pdftools watermark book.pdf --text DRAFT --opacity 30% -i
    $ py-pdftools pages book.pdf --move 201-214 9 --delete LAST -i
    $ py-pdftools view book.pdf --layout cover --open-at 9 -i
    $ py-pdftools impose booklet book.pdf -o booklet.pdf
    $ py-pdftools impose --help                        the commands of imposition

`py-pdftools COMMAND -h` explains each command. `py-pdftools completion
bash|fish|zsh` prints a completion script for the shell. The commands are
those of py-foliation and py-imposition, which their READMEs explain at
length; `labels` holds py-foliation's `show`, `set`, `clear` and `copy`.

Settings
--------

The language of the interface is chosen in Settings > Language, or with
`py-pdftools interface es`. The settings are kept in a file, `config.toml`,
in the user's configuration folder: `~/.config/py-pdftools/` on Linux,
`~/Library/Application Support/py-pdftools/` on macOS, `%APPDATA%\py-pdftools\`
on Windows (or the folder `$PY_PDFTOOLS_CONFIG` names). Each setting is
checked when it is read, so a file edited by hand can't stop the program.

Tests
-----

    $ uv run pytest

There are 399 tests: those of the four programs, and those of what is new
(the command line as a whole, the modes of the window, the redaction boxes,
the working copies, the Spanish interface, the packaging). See
[docs/DESCRIPTION.md](docs/DESCRIPTION.md) for how the program was made.

Licensing
---------

py-pdftools is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option)
any later version (see [LICENSE](LICENSE)). It uses PyMuPDF (GNU AGPL 3),
pikepdf (Mozilla Public License 2.0), reportlab (BSD) and PySide6 (GNU LGPL
3).
