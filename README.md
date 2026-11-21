py-pdftools
===========

*(Español: [README_es.md](README_es.md))*

py-pdftools edits PDF documents. It annotates them, redacts them, changes
their page labels, headers, footers, watermarks and the order of their
pages, imposes them for printing, and reads the text of their scanned
pages. It brings together, in one window and one command line, what six
earlier programs of mine did apart:

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
  step and repeat, bleeds and crop marks, sequences and hot folders;
* [py-pdfocr](https://github.com/nivaca/py-pdfocr): the text of scanned
  pages, read by tesseract and written into the PDF, invisible, under their
  pictures (OCR), with tesseract's languages and their more accurate
  models;
* [pdf-word-finder](https://github.com/nivaca/pdf-word-finder): on which
  pages each word, phrase or pattern of a list appears, by the numbers
  printed on them (the page labels), as lines ready for an index.

The window and the command line are in English and in Spanish. It runs on
Linux, and its installers also install it on Windows and macOS. This is
version 1.8.3.

The user manual, with pictures of the window and its dialogs, explains it
all at length: [docs/MANUAL_en.pdf](docs/MANUAL_en.pdf) (in Spanish,
[docs/MANUAL_es.pdf](docs/MANUAL_es.pdf)).

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

The mode Foliate: no label on the title page, then 1, 2, 3, and the label in
the footer:

![Pages](docs/img/pages_en.png)

The mode Impose: a booklet:

![Impose](docs/img/impose_en.png)

Where it comes from
-------------------

py-pdftools grew out of six programs I wrote earlier, each for one kind of
work on PDF documents. When they had grown side by side for a while, it
was clear that they shared much (the way the interface is translated, the
configuration, the conversion to PDF/A and PDF/X, the packaging) and that
the same document often went through more than one of them: annotated,
then redacted, then given its page labels, then imposed for printing. So I
brought them together. Their code was copied into py-pdftools, not used
from them: py-pdftools doesn't need them installed, and they stay as they
were, each with its own repository and releases.

    py-annotate 1.1.0      the mode Annotate; the window itself (its pages,
                           thumbnails and panels) is py-annotate's
    py-redact 1.0.9        the mode Redact
    py-foliation 1.0.1     the mode Foliate, and the commands labels, view,
                           header-footer, watermark and pages
    py-imposition 0.10.3   the mode Impose, and the commands under impose
    py-pdfocr 1.0.3        the mode OCR, and the command ocr
    pdf-word-finder 1.6    Edit > Word index, and the command find-words

What changed when they were brought together:

* One window, with a bar of modes, instead of four windows; and one
  history, so that Undo goes back through everything done to the document.
* The boxes of py-redact are now the PDF's own redaction marks: they are
  saved in the document, not applied, until the redacted copy is written.
* The changes of the mode Foliate are made at once, and shown, instead of
  waiting, as in py-foliation, until the file is saved.
* One command line, with groups: the labels of py-foliation are under
  `labels`, and every command of py-imposition under `impose`.
* One configuration folder. The settings of the old programs are not read;
  the redaction codes of py-redact (`codes.xml`) and the profiles of
  headers, footers and watermarks of py-foliation (`header-footer.json`,
  `watermark.json`) can be copied from their folders into that of
  py-pdftools (see "Settings").

A fifth program of mine came in whole:
[pdf2iso](https://github.com/nivaca/pdf2iso), which makes the copies as
PDF/A and PDF/X. It is no longer a program to install apart: the window,
the commands with `--conform`, and `py-pdftools pdf2iso`, which is pdf2iso's
own command line, all use the one in py-pdftools. Only Ghostscript, which
does the conversion, must be installed.

The documents the old programs made are read as before: the keys they wrote
in a PDF (tags and categories of annotations, layers of headers, footers
and watermarks, the history of an imposition) kept their names, and the
JSON files of annotations exported by py-annotate can be imported. How the
four were brought together, and what was found on the way, is told in
[docs/DESCRIPTION.md](docs/DESCRIPTION.md).

Installation
------------

Every version is in the [releases](https://github.com/nivaca/py-pdftools/releases),
on GitHub and on [Codeberg](https://codeberg.org/nivaca/py-pdftools/releases),
with these files:

    py-pdftools-VERSION.zip                 the source, with the installers
    py-pdftools-VERSION-x86_64.AppImage     the AppImage (Linux)
    py-pdftools_VERSION-1_amd64.deb         the Debian and Ubuntu package
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

**Debian and Ubuntu.** The `.deb` of each release, for Debian 12, Ubuntu
22.04 and later, installs the commands `py-pdftools` and `py-pdftools-gui`,
a menu entry and the manual. Debian has no Python 3.14 yet, so the package
brings its own, with Qt and the libraries, in `/opt/py-pdftools` (as the
AppImage does):

    $ sudo apt install ./py-pdftools_*_amd64.deb

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

Copies as PDF/A or PDF/X need Ghostscript, which makes them (pdf2iso, which
prepares and checks them, is part of py-pdftools: see "Where it comes
from"). For OCR, the tesseract program, with the languages of the
documents (`tesseract-langpack-…` on Fedora, `tesseract-ocr-…` on Debian
and Ubuntu).
Digital signatures need pyHanko: the AppImage and the installers bring it;
elsewhere, `pip install 'py-pdftools[signatures]'` (Fedora doesn't package
it, so the RPM goes without; the menu then says how to add it).

The window
----------

A document is opened with File > Open, or dropped on the window. Its pages
are shown one under the other, with their thumbnails on the left. The bar
of modes, at the top (or Ctrl+1 to Ctrl+6), chooses what the window does,
and how it is arranged:

* **Read**: only the pages and their thumbnails, with the toolbars to open,
  find, move through the pages and zoom; the mouse moves the pages;
* **OCR**: the text of scanned pages, read by tesseract; its panel chooses
  the pages, the languages and how to read them (see below);
* **Redact**: the tool Redact (dragging over text marks it; elsewhere, or
  with Ctrl, it draws a box), Find and redact, redaction codes, and the
  panel of the boxes;
* **Annotate**: the tools of py-annotate, in the second toolbar and the
  menu Tools; the panel of the annotations on the right, which can be
  searched, filtered and sorted;
* **Foliate**: the ranges of labels and the list of the pages with their
  labels, on the right; the actions on the pages chosen in the toolbar and
  in their right-click menu; headers and footers, watermarks and the view
  when the document is opened, in the menu Pages;
* **Impose**: py-imposition's workspace, with its basic form, the forms of
  every command, the sequence and the log, in place of the pages.

Each mode keeps its own arrangement of the window: which toolbars and
panels are shown, where they are, the thumbnails and the width of the
pages beside them. Arrange a mode once (drag its toolbars and panels,
hide them with a right click on them) and choosing it again brings that
arrangement back, also the next time the program is opened.

The tool Select text (X), beside Hand in every mode, selects text as in a
text editor: drag over it (across pages too), Alt+drag for a column,
double-click a word, triple-click a line, Shift+click to extend. Ctrl+C
copies it, Ctrl+A selects the text of the page, and a right click offers
to highlight, underline or strike it out, to mark it for redaction, or to
find it.

Settings > General > Keep running in the background makes documents open
faster: when the last window is closed, py-pdftools goes on running, with
its pages ready to be drawn and an icon in the tray (where the desktop has
one), and py-pdftools-gui started again opens its files in it, at once.
File > Quit ends it. A window is kept ready, hidden, for the next document,
which then opens in a few hundredths of a second. With Settings > General >
Start with the session, py-pdftools starts when you log in, in the tray and
without a window (`py-pdftools-gui --background`), so that the first
document of the day opens at once too.

Settings > Performance sets how much memory the window may use (Low,
Normal, High, or All pages, which keeps every page and thumbnail drawn,
within half of the free memory), whether selections are drawn with
transparency or as outlines, and whether text and graphics are smoothed
(antialiasing).

Moving through a document works in every mode. The quick find box, on
the toolbar Find (Ctrl+Shift+F), goes from one place of a text to the next
with Enter (Shift+Enter, back), without minding capitals or accents. View > Bookmarks (F5)
shows the document's bookmarks (hidden until it is asked for) as a tree that can be filtered; its right
click adds, renames, moves, indents and styles them, or makes them from
the headings. Links are followed with a click (with Select, Ctrl+click),
web and mail addresses written in the text too, and Alt+Left and
Alt+Right go back and forth through the places jumped to. A document
opens where it was left, or as it asks (its page, zoom and thumbnails), and
`py-pdftools-gui book.pdf#page=12` or `#nameddest=intro` opens it at a
place. The menu View has two pages side by side (Ctrl+Shift+2, with the
first alone as a cover if wished), the zooms (fit the page, the width, the
height, or the inked area; actual size; a percentage typed in the box of
the zoom; and the tool Zoom to area, Z), the view turned without changing
the file (Ctrl+] and Ctrl+[), reading colours (white, yellow or green on
black, or one's own), the gaps between the pages hidden, and Full screen
(F11) as a presentation. File > Open in a new tab (Ctrl+T) puts documents
in tabs of one window (the bar of the tabs shows from the second one on,
or always, with a setting), and View > Split the view (`Ctrl+\`) shows two
side by side. A document changed by another program opens again by itself.
Space held turns any tool into Hand, and the middle button scrolls by
itself. The toolbar Page navigation, at the bottom of the window, goes to
the first, previous, next and last page, and its box takes a page number
or label; like the other toolbars, it can be changed in Customize the
toolbars. The box of the page and that of the zoom are on the toolbar Page
and zoom, which can be moved anywhere or hidden. File > PDF properties
shows what a document is (its metadata, file, pages, security) and the
fonts it uses.

Edit > Word index (from pdf-word-finder) finds the words, phrases or
regular expressions of a list, typed or read from a file, and gives the
pages where each appears, by their labels, as lines ready for the index of
a book (`Sharahzad 3, 5, 23, 34`), or in detail, with how many times and
a fragment of text around each place; the result is copied, or saved as
text or CSV. Words split by a hyphen at the end of a line are joined
first, and accents can be ignored. From the command line:
`py-pdftools find-words book.pdf --words-file terms.txt --txt index.txt`.

Redact > Find text only covered looks for text that only seems redacted:
still in the file under a black or white box, a picture or an annotation
drawn over it, where anyone can copy it; boxes put over what it finds take
it out in the redacted copy. Remove hidden information also takes out the
layers switched off, with what they hold. File > Protect with passwords
sets a password to open the document, one for its permissions (printing,
copying, changing it), or both, encrypted with AES-256; only the
permissions password changes or removes them. Settings > Toolbars sets how the toolbars look, as in KDE: the
position of their text (icons only, text only, beside or under the icons),
the size of their icons, and whether they stay where they are; the right
click on any toolbar sets them for all of them. Customize the toolbars chooses
the buttons of each toolbar and their order, and adds toolbars of one's
own. The menus File, Edit and View are in submenus (File > New, Export,
Import, Security; View > Panels, Go to, Zoom, Page layout...).

File > Combine files makes one PDF of several, or of some of their pages
in an order (`1-3, 7`), with their links, annotations, form fields and
bookmarks; the files are dropped on its list or added, and put in order
by dragging them. File > New PDF from pictures makes a PDF of photographs
or scans, a page for each, as big as each picture or on paper with a
margin, and can open it in the mode OCR to read its text. From the
command line: `py-pdftools combine a.pdf b.pdf:2-5 -o all.pdf` and
`py-pdftools from-images *.jpg -o scans.pdf --paper A4`.

File > Export saves the pages as pictures (PNG, JPEG or TIFF, at a
resolution, in grey if wished), the pictures of the document, or its text
(Markdown, with its headings guessed, HTML or plain text); File > Save a
copy > With another PDF version makes a copy that says it is PDF 1.3 to
2.0, naming what the document uses that the version chosen doesn't have.
Pages > Arrange pages > Split cuts a document every so many pages (one per
page, named after their labels), at given pages, at its bookmarks (each
part named after its bookmark), or so that no part is bigger than a size.
From the command line: `py-pdftools export pages | images | text`,
`py-pdftools pdf-version`, and `py-pdftools pages --split-bookmarks 1` or
`--split-size 10`.

File > Save a copy > Smaller makes a copy that takes less space: its
pictures drawn again at a lower resolution (only those shown above it),
its fonts reduced to the characters used, what nothing uses taken out;
the dialog shows where the bytes go. The tool Link (J, in Annotate) draws
a link to a page, an address or another PDF, and a click on a link changes
or removes it; Edit > Links makes links of the addresses in the text.

Forms are filled in the panel Form (F6), which opens by itself with a
document that has one, or with clicks on the page. What most forms ask is
done without JavaScript: numbers and dates checked and shown in their
format, sums worked out. The panel exports and imports the values (JSON,
CSV, XFDF, FDF), and `py-pdftools form` shows, fills, tabulates and
flattens forms from the command line. File > Digital signatures signs the
document with a digital ID, visibly or not (and makes an ID of one's own),
and checks its signatures: whether each is intact and valid, who signed
and whether they are trusted, and what changed after it.

Help > Tips for this mode (F1) shows, over the bottom of the pages, a hint
on what can be done in the mode chosen; Settings > Appearance can show it
whenever a mode is chosen, and can turn on the tooltips (both are off at
first). The tooltips of the toolbars show always.

The mode OCR (Ctrl+Shift+O, or its button Recognise text) reads the text of
scanned pages with tesseract and writes it into the document, invisible, under their
pictures, so that it can be found, copied and marked; it is a change of
the document, undone and saved like the others. It reads the scanned
pages, those chosen in the thumbnails or a list of them, in the languages
ticked in its panel (the main one first), and can turn first the pages scanned sideways or upside down.
The words tesseract was not sure of are shown beside their pictures, to
be corrected before the text is written (how sure is sure enough is set in
the panel). OCR > Languages lists every language tesseract can read, and
downloads, updates or removes its more accurate models (tessdata_best), and
osd, which finds how pages are turned (this needs the internet, once). In
the other modes, the menu of the thumbnails reads the pages chosen. From the
command line: `py-pdftools ocr scan.pdf -l lat+spa --rotate --report`.

Each mode works on its own annotations: in Annotate, the redaction boxes are
shown, but the mouse goes through them, and in Redact the annotations are.
Undo goes back through everything done to the document, in any mode.

**Saving.** File > Save writes the document: its annotations, its redaction
boxes (as the PDF's redaction marks, not yet applied), and the changes of
the modes Foliate and Impose. Those changes are made at once on a working
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
    $ py-pdftools find-words book.pdf amor "re:virtu(s|tem|tis)" --sort
                                                       the pages of each term

`py-pdftools COMMAND -h` explains each command. `py-pdftools completion
bash|fish|zsh` prints a completion script for the shell. The commands are
those of py-foliation and py-imposition, which their READMEs explain at
length; `labels` holds py-foliation's `show`, `set`, `clear` and `copy`.

Settings
--------

The language of the interface is chosen in Settings > Language (or
Settings > Appearance), or with `py-pdftools interface es`. Settings >
Appearance also sets the colours of the interface (as the system, light or
dark), its size, how sharp the text of the pages is drawn, the hints shown when a mode is chosen, and how the
toolbars look; Settings > Documents, how a document opened for the first
time is shown, whether each opens where it was left, whether to ask before
opening a web address, how many recent documents File > Open recent shows,
and where the file dialogs start. The settings are kept in a file, `config.toml`,
in the user's configuration folder: `~/.config/py-pdftools/` on Linux,
`~/Library/Application Support/py-pdftools/` on macOS, `%APPDATA%\py-pdftools\`
on Windows (or the folder `$PY_PDFTOOLS_CONFIG` names). Each setting is
checked when it is read, so a file edited by hand can't stop the program.

Tests
-----

    $ uv run pytest

There are 591 tests: those of the four programs, and those of what is new
(the command line as a whole, the modes of the window, the redaction boxes,
the working copies, OCR, navigation, security, the menus and toolbars,
combining files and PDFs of pictures, smaller copies, links, forms,
signatures, exports, splitting, the PDF version, the Spanish interface, the
packaging). Their
windows are drawn on an X server of their own (Xvfb), if it is installed,
else offscreen; `PY_PDFTOOLS_TEST_DISPLAY=offscreen` or `=screen` (to
watch them on the desktop) choose otherwise. See
[docs/DESCRIPTION.md](docs/DESCRIPTION.md) for how the program was made.

Licensing
---------

py-pdftools is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option)
any later version (see [LICENSE](LICENSE)). It uses PyMuPDF (GNU AGPL 3),
pikepdf (Mozilla Public License 2.0), reportlab (BSD) and PySide6 (GNU LGPL
3). All the open-source software it uses, with its licences, is listed in
[docs/THIRD-PARTY.md](docs/THIRD-PARTY.md).
