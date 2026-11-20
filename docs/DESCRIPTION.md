How py-pdftools was made
========================

py-pdftools is a program for editing PDF documents: it annotates them,
redacts them, changes their page labels, headers, footers, watermarks and
the order of their pages, and imposes them for printing. Nicolas Vaughan
made it in November 2026 by bringing together four programs of his, each
of which did one of those things: py-annotate, py-redact, py-foliation and
py-imposition. Here I explain how it was made, in eleven stages.

It is free software, under the GNU General Public License, version 3 or
later. The pages, the annotations and the redaction are the work of
PyMuPDF (GNU AGPL 3); the page labels, the layers and the imposition, of
pikepdf (Mozilla Public License 2.0), with reportlab (BSD) for the text of
imposition; the window is made with PySide6 (GNU LGPL 3).

Nicolas Vaughan is Associate Professor of Literature at the School of Arts
and Humanities of the Universidad de los Andes, Bogotá, Colombia.

1. A plan
---------

The four programs had grown side by side and shared much: the same way of
translating the interface, the same configuration file, the same call to
pdf2iso for PDF/A and PDF/X, the same packaging. But they were not made
alike. py-annotate and py-redact work with PyMuPDF, py-foliation and
py-imposition with pikepdf; py-annotate saves in the document, py-redact
always writes a new file, py-foliation keeps its changes in memory until
the file is saved; only py-foliation and py-imposition have a command line.

Before writing any code, these differences were settled. py-pdftools would
be a new package, with the code of the four copied into it, not a program
that depends on them; the old programs stay as they are. Both libraries
would stay, each doing what it already did well, instead of porting tested
code from one to the other. The window would be py-annotate's, whose pages
scroll one after the other, with a bar of modes on top: Annotate, Redact,
Pages, Impose. Saving would write the document in place, except for
redaction, which always writes a copy, as py-redact did. The plan was
written down in stages, and each stage was finished only when the tests of
the code it brought in passed.

2. The engines in one package
-----------------------------

The engines of the four programs went into four subpackages, `annotate`,
`redact`, `pages` and `impose`, with a script that copied each module and
rewrote its imports. What they shared went into `core`: the interface, the
configuration, the conversion to PDF/A and PDF/X, the rendering of pages in
processes of their own, and the reading of page lists. Of these, two had
the same name but did not do the same thing. py-imposition's page lists
refused a page beyond the last one and could keep the order of a list,
while py-redact's left such pages out and took open ranges (`12-`). The
module in `core` does both, with an argument for py-redact's way.

The four Spanish translations were put together in one file, about 2,250
texts. Thirty-five English texts had two different translations; most of
them were small differences of wording, but some were of meaning. "Left"
was *izquierda* as an alignment and *izquierdo* as a margin, and since a
text is found by its English, the margins now have their own text, "Left
side". The keys the old programs write in a PDF (their tags, their layers,
the history of an imposition) kept their names, so that the documents they
made are still read. At the end of this stage, 250 tests of the four
programs passed in the new package.

3. One command line
-------------------

py-foliation had ten commands and py-imposition thirty. The command line of
py-pdftools has groups: `labels show`, `labels set`, `view`,
`header-footer`, `watermark`, `pages`, and `impose` followed by any command
of py-imposition. I first wanted to spread py-imposition's commands into
the other groups (its stamps with the watermarks, its deleting and moving
of pages with `pages`), but its sequences and its `replay` name the
commands as they are, and they would break. So they stay together under
`impose`.

The two parsers were not written again. Their commands were put into one
tree, which gives the help and the completion scripts, and each command
still runs where it did. The completion scripts of py-foliation knew one
level of commands; now they know two. The scripts for fish needed a
function of their own, because py-imposition has a command called `impose`,
the same as its group, and the usual conditions of fish could not tell
"impose" from "impose impose".

4. A window with modes
----------------------

The window of py-annotate came first, with its tests, and then the bar of
modes. A mode brings its toolbars, its panels and its menus, which are
shown while it is on, and says which annotations are its own. The canvas
lets the mouse go through the others: they are shown, but they can't be
selected, moved or erased, and the list, the Edit menu and the selection
work only on those of the mode.

5. Redaction boxes as redaction marks
-------------------------------------

py-redact kept its boxes in a list of its own and drew them on a canvas of
its own. Looking at what a box holds (a rectangle, a fill, a text to write
over it, its alignment, whether the text repeats), I saw that it is almost
exactly the redaction annotation of PDF itself, `/Redact`, which marks what
is to be removed without removing it. So a box became an annotation of a
new kind, `redact`, with three new fields: the text written over it, whether
it repeats, and the pages it goes on, kept in a key of its own. The canvas
of py-annotate draws, moves, resizes and undoes them like any annotation;
saving the document keeps them in it, not applied; and the marks made by
other programs are read as boxes. A box that goes on other pages is shown
on each of them.

Some details came out of this. py-redact's engine applied every redaction
mark of a page, and a box saved in the document would have been applied
twice; now the marks are taken out before the boxes are applied. A copy
with the annotations flattened into the pages would have painted a box
over text that was still in the file, which looks redacted and is not, so
flattened, OCR and printed copies leave the boxes out. The redacted copy is
made from the file, as py-redact made it, and so the window asks to save
the other changes first. It is never written over the document open.

6. Working copies
-----------------

py-foliation kept its changes in memory and made them only when the file
was saved, with a temporary copy to preview them. In py-pdftools the pages
are drawn by PyMuPDF, with the annotations on top, and a change of the
labels or of the order of the pages has to show at once, with the
annotations going with their pages. So each change of the document itself
is made on a working copy: the document, with its annotations as they are
in the window, is written to a file of the window's own, the change is made
there with pikepdf, and the window goes on with that file. Save writes it
as the document. Each change is a step of the history, so Undo goes back
through them as it goes back through the changes of the annotations.

The first test of this found a fault: after a change and its undo and redo,
saving wrote an annotation twice. When it saves, the window passes on the
annotations it read from the document, so that they are not read again; with
a working copy, those were the annotations of the original file, not of the
copy, which already had the new one. With a working copy, the file is now
read.

7. The mode Pages
-----------------

The dialogs of py-foliation (headers and footers, watermarks, arranging the
pages, several files at once) came across nearly as they were. Their
preview used QtPdf, which py-pdftools does without, and is now drawn with
PyMuPDF, as the window draws its pages. The panel has the table of the
ranges of labels and the list of the pages with their labels; the labels,
the view when the document is opened and the headers and footers are read
from the document as it is, not kept apart. The actions on pages needed a
few icons py-annotate didn't have, and they were drawn in the same plain
style as its own.

8. The mode Impose
------------------

py-imposition's window has its own layout: a tree of commands, a form made
from the command line, and the document beside the result. Rather than
taking it apart, the whole window lives in the window of py-pdftools, as a
widget that takes the place of the pages while the mode is on. It imposes
the document open, with its unsaved annotations and changes written to a
copy first, and runs each command as `python -m py_pdftools impose` in a
process of its own. Apply makes the result the document, a step of the
history; Undo apply is the window's Undo.

9. Packaging
------------

The packaging is py-annotate's, with two commands now: `py-pdftools`, the
command line, and `py-pdftools-gui`, the window. The installers link both;
the AppImage starts the window, or the command line if its first argument
is a command. The icon shows a page with what the four programs do to it:
a line highlighted, a line blacked out, its number on a label tag, and the
crop marks of a sheet. The manual pages are made from the help of the
command line, in English and Spanish, so they can't say what the program
doesn't.

Building the RPM brought out the last fault. Fedora's PyMuPDF, version
1.28, reads the optional `/Type /PageLabel` of a range of labels as its
prefix, so the labels came out as "ageLabeli", "ageLabelii"; PyMuPDF 2.1,
the one the program installs from PyPI, reads them right. The window and
the exports now read the labels with py-foliation's engine, which reads the
label tree as it is.

10. Faster changes
------------------

With a book of 300 pages and 3,000 annotations, a change of the page labels
took almost two seconds, and Undo and Redo one each. Measuring showed why:
the annotations were read twice for each change, about a second each time,
once to write them into the document and once to read them back from the
new file. Both readings could be spared. The window now keeps the
annotations as the file it shows has them, checked against the time and
size of that file, and passes them on, so the file is not read before it is
written. Page labels, which are only an entry of the catalog, are written
by PyMuPDF while the annotations are written, as direct objects, and since
PyMuPDF keeps the numbers of the objects, the annotations are not read
again either. Undo and Redo take the annotations from the history instead
of reading them from the file.

Two more things were slow with many annotations: taking them out of the
copy of the document the window draws from (each one loaded and deleted
apart), and reading them, which loaded every annotation even when it was
known. Now both go by the numbers of the objects: the list of annotations
of each page is written anew, and only the annotations not known are
loaded. A test compared the old and the new ways on a document with every
kind of annotation, replies, groups, a link and a pop-up: the same
annotations, and pages drawn alike to the pixel. A change of labels now
takes 0.3 seconds, Undo and Redo less than a tenth, saving 0.3 instead of
1.2, and the tests run in 28 seconds instead of 42.

11. pdf2iso, included
---------------------

The copies as PDF/A and PDF/X were made, from the start, by pdf2iso,
another program of mine: a single script that prepares a PDF with pikepdf,
has Ghostscript convert it, and checks the result. Until now it had to be
installed apart, and was looked for on the PATH and in `~/bin`. Now it is a
module of the package, `core/pdf2iso.py`, run in a process of its own with
the program's own Python, and a command, `py-pdftools pdf2iso`, with its own
options. Two things had to change in it. As a script, it stopped the
program when pikepdf was missing or too old, and a module must never do
that when it is imported; and its parser was taken out of its `main`, so
that the command line of py-pdftools can include it. Only Ghostscript is
still a program apart, and the window now says that it is Ghostscript that
is missing, not pdf2iso. The setting that named a pdf2iso remains, for
another one, and the tests use it to put fake ones in its place.

Testing
-------

The program has 399 tests (`uv run pytest`): those of the four programs,
moved into the new package (96 of annotations, 71 of redaction, 115 of
pages, labels and layers, 87 of imposition), and those of what is new: the
command line as a whole and its completion in bash and fish, the modes of
the window, the boxes as redaction marks, the working copies with their
undo and redo, the page labels written by PyMuPDF as pikepdf writes them, the Spanish interface (every text translated, and none left
over) and the packaging. The windows of the four modes are tested as a user
would use them, with mouse events on the pages; the redacted copy is also
written in a process of its own, as the window does it, and imposition runs
its commands in one. The window was checked by eye as well, with
screenshots of each mode in both languages. The RPM runs all the tests
again with Fedora's packages. The Linux installer was run in a home folder
made for the test. The program has 99 files of Python, around 27,700
lines, and 2,214 texts of the interface in Spanish.
