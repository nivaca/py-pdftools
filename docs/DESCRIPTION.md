How py-pdftools was made
========================

py-pdftools is a program for editing PDF documents: it annotates them,
redacts them, changes their page labels, headers, footers, watermarks and
the order of their pages, imposes them for printing, reads the text of
their scanned pages, and finds the pages of words for an index. Nicolas
Vaughan made it in November 2026 by bringing together six earlier programs
by the same author, each of which did one of those things: py-annotate,
py-redact, py-foliation, py-imposition, py-pdfocr and pdf-word-finder. Here
I explain how it was made, in eighty-nine stages.

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

12. Modes as arrangements
-------------------------

At first the modes were four, one for each program. A fifth came first in
the bar, Read, with only the pages and their thumbnails, and the mode
Pages was named Foliate (its key in the settings stayed `pages`, so that
the mode a user left the window in is still found). The modes are now in
the order of the work done on a document: Read, Redact, Annotate, Foliate,
Impose. And each mode keeps its own arrangement of the window: when it is
left, the state of the toolbars and panels (Qt's own), the thumbnails and
the width of the pages beside them are kept in the settings, and given back
when the mode is chosen again, then made to show only what belongs to the
mode, whatever the state says. The tests showed something unrelated on the
way: Qt reads where the settings are only once in a process, so all the
tests shared them, and the mode one test left the window in was the first
mode of the next. Each test now starts with them cleared.

13. Fixes, and one copy of each thing
-------------------------------------

When I commented the code, I marked as TODO what looked wrong, and then
fixed the worst of it, each with a test that failed first. The parts of a
document split by `pages --split-every` lost its password, and ignored
`--conform`. The summary of the comments made pages without end when one
comment was longer than a page. In Impose, two methods had one name, so
choosing another output of a command didn't show it. A process that drew a
page without its annotations then drew it so also when they were wanted.
Changing the language of the interface lost the changes not yet saved in
Foliate. And the dialogs of headers and footers accepted a setting typed
just before OK without checking it.

Then I looked for duplicated code, with pylint and with a comparison of
the syntax of every function. The four programs had brought copies of the
same things: opening a PDF, rectangles and colours, the words under the
mouse (annotate and redact), the matrices of PDF (three copies, in
imposition and the stamps), the command `interface`, the fields shared by
headers, footers and watermarks, the field of pdf2iso in three settings
dialogs, a colour button, a colour menu, and the question about unsaved
changes. Each is now in one place: `core/pdfdoc.py`, `core/matrix.py`,
`core/interface.py`, `stamps.StampSettings`, `gui/conform_field.py`,
`gui/props.py`, `gui/colors.py` and `gui/files.py`.

The tests on GitHub had failed from the start, which I had not seen. On
Ubuntu qpdf and pdftotext were missing; on Windows, also a file still open
can't be removed with its folder, `SIGALRM` doesn't exist, and pdftotext
read a rotated text in another order. The workflow now installs the tools,
the tests that need them are skipped where they are missing, the text of
headers and watermarks is read with PyMuPDF, and the temporary folders are
removed even with a file still open.

14. Large documents
-------------------

I was told that large documents gave trouble, and could not see it at
first: a document of 5,000 pages opened in half a second, and one of 1 GB of
scanned pages in two hundredths, since PyMuPDF reads the pages only when it
needs them. What was slow came after. The thumbnails of 200 scanned pages
took 30 seconds, one at a time, each decoding the whole picture of its page.
At a deep zoom a page was drawn whole, up to 40 million pixels, and enlarged
beyond that, so it went blurred. A page that took too long held its process,
and one that made the process die sent every later page to be drawn in the
window itself, which could die with the next. And, the worst of it, the
working copies were in /tmp, which on Fedora is in memory: each change of a
1 GB document kept another gigabyte of RAM, for undo.

To see how another editor does it I read the code of PDFCraft, an editor
written in Rust, with four agents, one for each part. It holds the whole
file in memory (two or three copies while it edits), which py-pdftools
needn't do; but it orders its work better, and I took four things from it.
Each lane of the rendering processes now has several, and a page that takes
more than 20 seconds, or makes its process die, is shown grey with the
reason, its process replaced, and is not tried again. Only the thumbnails
near those in view are made, after the pages in view, and those far away
are forgotten beyond 400: the ones in view are ready in less than a second.
A page that would be longer than 4,096 pixels is drawn whole at most 2,048
pixels long, and the part in view in tiles of 1,024 pixels at the full
scale. The working copies went to the cache folder, on disk; a change made
with pikepdf starts from the file shown when it has the annotations already,
one write of the whole document less; and the history keeps the last ten
changes of the document.

On the way I found that the scripts of the virtual environment still named
the folder where the project was before, so `pytest` ran with the system's
Python and the installed package, not this one; `uv sync --reinstall`
wrote them again.

15. OCR
-------

There was OCR already, from py-annotate: a searchable copy, read through
PyMuPDF, which carries its own Tesseract and needs only its languages. I
wanted the newest Tesseract, the one the system installs (5.5.4), and the
confidence of each word, which PyMuPDF does not give; so py-pdftools now
runs the tesseract program itself, page by page, in processes of its own,
several at once. Each page is drawn at 300 dpi and read as a table of words
(TSV), with their places and their confidence. The first try returned no
words at all: given a folder of languages of its own (--tessdata-dir), as
py-pdftools gives it, tesseract no longer finds its configuration file for
the table, and quietly gives plain text; the table is asked for with a
setting instead.

The text now goes into the document itself (the mode OCR, of its own,
between Read and Redact, since marking text needs it), as a
change of it, undone and saved like the others; the searchable copy stays.
The pages can be chosen, and those lying sideways turned first, with
Tesseract's model of orientation, osd; I checked by turning a page every
way that its "Rotate" is clockwise, as PDF's own. The words it was unsure
of are shown beside a picture of themselves, to be corrected before the text
is written. The settings download its more accurate models (tessdata_best)
into a folder of py-pdftools, and for each run a folder of links gives
tesseract, for each language, the better model if there is one. The command
line has `py-pdftools ocr`. Tesseract is optional: without it, there is no
OCR, and its tests are skipped. The OCR is that of py-pdfocr, my program
that reads scanned pages on the command line: the same engine, the same
command, the same languages and models; only the window, and the words
corrected beside their pictures, are py-pdftools' own.

16. The window, as one works in it
-----------------------------------

The last requests were about working in the window, and for most of them I
read again how PDFCraft does it. The thumbnails take several pages now, with
Ctrl and Shift, without moving the view, in any mode, and their right click
gives the menu of pages Foliate had: the pages chosen there and in Foliate's
list are the same. The box of the page shows its label (iv, 12v), and takes a
label, (n) for the n-th page, or a number. OCR became a mode of its own,
between Read and Redact, since marking text needs the text first: its panel
chooses the pages, ticks and orders the languages, and sets how sure is sure
enough; a manager of languages lists every one tesseract can read, and
downloads or removes its better models. A tool to select text, beside Hand
in every mode, selects as in a text editor: by dragging, across pages too, a
column with Alt, a word or a line with two or three clicks, and offers to
copy, mark, redact or find what it selected.
The menu of the pages, long by then, went into groups: the actions used most
at its top, and submenus for moving, inserting, labels, headers and
watermarks, and the view on opening, under a heading that names the pages.

Two settings came from the help of other programs. One keeps py-pdftools
running when its last window closes, with an icon in the tray, so that the
next document opens at once: a second start gives its files to the program
running through a local socket. Its test failed while the second start was
a thread of the test itself, and passed once it was a process of its own,
as it really is; and a socket's path in a long folder was refused, which a
short name now avoids. The other is a page of performance: how much memory
the window may use (the pages and thumbnails it keeps, how far ahead it
draws, how many processes draw), whether selections are drawn with
transparency, and whether text and graphics are smoothed, which MuPDF lets
set apart.

I also learnt to keep my hands off the files while a release is being made:
it packages the folder as it is, and I had started on the next change during
its tests.

17. Moving through a document
-----------------------------

Then I read PDFCraft's code once more, this time for what a reader of
PDFs expects when moving through a long document, and made fifteen
changes, one commit each. The bookmarks became a panel common to every
mode, a tree with a filter, and they can be edited there: added at the
place shown, renamed, moved, indented, made bold or coloured, or made
from the headings, which are the lines in the three largest sizes above
the size of the body. Links are followed, and also the web and mail
addresses written in the text, which most documents don't make links; a
web address is opened only after asking. Every jump (a link, a bookmark,
the page box, Find) goes into a history, gone through with Alt+Left and
Alt+Right as in a browser. A document opens where it was left, or as it
asks to be opened, and `book.pdf#page=12` opens it at a page.

The view got two pages side by side, with the first one alone as a cover
if wished, which made the canvas lay out rows of pages and not pages; more
zooms, one of them to the inked area of the page, found on a small grey
drawing of it; the pages turned in the view only; reading colours, made
with PyMuPDF's tint_with, for the pages in view and not the thumbnails;
full screen as a presentation, where a page with a display time turns by
itself; the details of a page on its thumbnail; Space as Hand for a
moment and the middle button for scrolling; and the gaps between the
pages, which can be hidden.

Tabs were the largest change. Each tab is a whole window of its own,
with its menus, panels and undo, put inside a window of tabs, which can
show two of them side by side. Two problems came out. With two windows in
view, their shortcuts were the same keys in the same window, so they now
act only where the focus is. And the window of tabs, when it closed,
deleted the windows inside it, which other tests still found in the list
of windows: a tab closed now leaves its window as a closed window stays,
hidden. Reloading a file changed by another program was simple, but its
first version named an attribute `_stamp`, which hid the method that
makes stamp annotations; one test of annotations found it.

18. Security, and toolbars to measure
------------------------------------

From the same reading of PDFCraft came three things about security, and
the Redact mode had already done half of them. Removing hidden
information was there, so it only got one kind more: hidden layers.
PyMuPDF has no function that takes out what a layer switched off holds,
so I wrote one. It reads each content stream with pikepdf, drops what is
marked with a hidden layer (also through the combinations of layers that
PDF allows), and the pictures and forms drawn with one; then it removes
the annotations of those layers and the layers themselves, since their
names can say too much. The redacted copy, when it is cleaned, does the
same. A small surprise was that PyMuPDF reports every layer as switched
on, so which ones are off is read from the catalog.

The check for text only covered is new. Many documents are "redacted"
by drawing a black box over the text, and the text stays in the file,
where anyone can copy it. The check follows the order in which the page
is drawn: a box drawn after a text, and over it, covers it; one drawn
before is a background. Only black or white boxes count, and nearly so,
since one of a colour is likely a highlight, through which the text shows;
pictures and annotations that hide what is under them count too. The
first version took the annotations from PyMuPDF's list of annotations,
and then found each of them a second time among the drawings, because
the drawings of a page include those of its annotations; a yellow
highlight came out as a box. Now whatever is drawn inside an annotation
belongs to it, and the annotation decides. I ran the check on fifty-two
PDFs I had at hand, and it found nothing in any of them, which is what it
should find. What is found can be covered with redaction boxes at once,
and the redacted copy takes it out.

Passwords are set from File: one to open the document, one for its
permissions, or both, with AES-256 through pikepdf. The protection is
changed or removed only with the permissions password. Writing this, I
found that a file with only a permissions password lost it when its
annotations were saved, because the program kept the encryption only of
files that ask for a password to open; it now keeps it for these too.

Last, the buttons of the modes got icons, and so did the few buttons
left without one, and the toolbars became editable: the buttons of each one and their order, from
every action of the menus, and toolbars of one's own. Each action is kept
by the name of its attribute in the window, which doesn't change with the
language. The first icons I drew had names that the icon theme of the
desktop also had, so the theme put its own in their place, the same gear
for two different buttons; they have names of their own now.

19. Combining files, and PDFs of pictures
----------------------------------------

The next two things from PDFCraft were about making a new PDF out of
others. Combining files was simple with PyMuPDF, which copies the pages
of one document into another with their links, annotations and form
fields, and renames the fields when two files have one of the same name.
What it does not carry over are the bookmarks and the page labels, so I
made those myself. When only some pages of a file are taken, the file is
first reduced to them in memory, which keeps the links between them; but
that also drops all of its bookmarks, so they are read before and moved
to the new places of their pages, and the levels are mended where a
bookmark of a page left out had others under it. The page labels are
read page by page and written again as ranges: numbers that follow one
another make one range, and any other label a range of one page.

A PDF of pictures was simpler than I expected. I meant to turn
photographs by the orientation the camera writes in them, and found that
MuPDF already does it when it opens a picture. Each picture becomes a
page as big as itself, or is put on paper of a size, as large as fits
within a margin; and the new PDF can be opened in the mode OCR, since a
PDF of scans is usually wanted for its text. Both are also commands,
`py-pdftools combine` and `py-pdftools from-images`; in the first,
`book.pdf:1-3,7` takes only those pages of a file.

20. Smaller files, links, forms and signatures
---------------------------------------------

The last group of things recommended by the reading of PDFCraft took
the longest. Making a file smaller was quick to write, but its first
results were odd: PyMuPDF's function for drawing pictures again only
halves them, so a picture asked for at 150 dpi came out at 300. It takes
a set of options of MuPDF itself, and with those the pictures are drawn
again at the resolution asked, cubically, and only those shown above one
and a half times it; scans in black and white keep at least 300 dpi, and
a picture that would grow is left as it was. Writing objects in streams,
which saves a good part of a file, broke files that are encrypted, so it
is done only for those that are not.

Links can now be drawn and changed with a tool of their own. PyMuPDF
gives the area of a link as the page is shown, but writes it as the page
is in the file, before it is turned; and it changed a link of a turned
page into one somewhere else. So a link changed is removed and written
anew, in the space of the file. This also showed that the program had
been turning the areas of links twice, and clicking on links of turned
pages missed them.

Forms took three steps. Filling them in is done in a panel with an
editor for each field, and with clicks on the page for check boxes and
radio buttons; each value is a change of the document, undone like the
others. PyMuPDF would not empty a text field, so text values are written
through MuPDF itself. Then the scripts: almost every form calls a handful
of standard functions, to show a number as money, to check a date, to
add up some fields. I wrote those functions in Python, reading their
calls out of the scripts, so no JavaScript engine was needed. A field
keeps its value plainly and shows it formatted, as forms do. The data of
forms goes in and out as JSON, CSV, XFDF and FDF, and the forms of many
filled copies can be put in one table.

Signatures use pyHanko, which Fedora doesn't have; it is an optional
dependency, installed by the AppImage and the installers, and the menu
says how to install it when it is missing. A digital ID of one's own is
made with the cryptography library. pyHanko places a signature in the
coordinates of the PDF, counted from the bottom, so the area dragged on
the page is turned back and moved there. It could not sign a file that
PyMuPDF had encrypted (PyMuPDF writes the encryption dictionary in a way
pyHanko doesn't read), but it signs those that pikepdf encrypts, as File
> Protect with passwords does. Checking signatures works offline: a
signer is trusted when their certificate is among those kept as trusted,
and the version a signature signed can be opened.

21. Menus in groups, toolbars as in KDE, exports
-----------------------------------------------

By then the menu File had grown to more than twenty entries, and View
nearly thirty. I didn't rewrite the code that builds them, which is
spread over the window and its parts; a module of its own takes the
actions as they were made and puts them in submenus (New, Export, Import
and Security in File; Select, Arrange and Remove annotations in Edit;
Panels, Annotations, Go to, Zoom and Page layout in View). The first
time, one menu came out with a leftover: the digital signatures, whose
actions had moved to Security, still had their own empty submenu. Now an
action the arrangement doesn't name goes at the end, so none is lost,
and a submenu whose actions are all elsewhere counts as placed. I meant
to test that a shortcut still works inside a submenu, but under a virtual
X server keys don't reach a window that isn't active, with the old menus
as with the new; the test checks instead that each of those actions is
still in a menu of the bar, which is what makes Qt find its keys.

The toolbars got the settings of KDE: the position of the text (icons
only, text only, beside or under the icons), the size of the icons and
whether they can be moved, for all of them from Settings, or for one
from its right click. The old option of labels under the icons is read
as one of these.

Then three things to do with files. The pages are exported as pictures:
PyMuPDF writes PNG and JPEG but not TIFF without Pillow, so the program
writes its TIFF files itself, a small writer of the format compressed
with Deflate, which ImageMagick reads as it should. The text is exported
as Markdown, its headings guessed from the size of the letters. Splitting
learned to cut a document at its bookmarks, naming each part after its
bookmark, and by size: a part is measured as it is written, its length
first guessed from the average size of a page and then shortened or
lengthened until it fits. Last, a copy can say it is another version of
PDF. Lowering the version only changes what the file says, so the program
names what the document uses that is newer than the version asked;
object streams, which came with 1.5, are written plainly below it, and a
document encrypted with AES-256 can't go below 1.7.

22. A quicker start, and more settings
--------------------------------------

The program could already wait in the background after its last window
closed, and a second start then handed its files to it through a local
socket. Two things were left. The first start of the day was still a cold
one, so a setting now puts py-pdftools in the desktop's own autostart (a
.desktop file on Linux, the folder Startup on Windows, a launch agent on
macOS), which starts it at login in the tray, without a window. And each
document opened from outside still built a window, about half a second;
now the program keeps one ready, hidden, and the document takes it in
about two hundredths of a second, after which another is made. A window
made before a setting changed would show it as it was, so one made with
other settings is not used. A start that only needs to know whether the
program runs asks it with a message of its own, which opens nothing.

The settings got two pages, Appearance and Documents: the colours of the
interface (Qt's own scheme where it has one, a palette of Fusion where it
is older), its size, its language, the hints of the modes, the toolbars,
and how documents open, what is remembered of them, links, the recent
ones and where the file dialogs start. A toolbar's right click now sets
all of them, as I expected it to, and not only the one clicked.

Two faults were found on the way. The launcher of the AppImage had a list
of the commands of the command line, written before eight new ones, so
those opened the window; it now gives the window only what it can open, a
file, and the rest to the command line. And the scripts with which these
changes were tried by hand, which gave the window a home folder of its
own, still wrote my own settings: the desktop sets XDG_CONFIG_HOME, which
Qt reads first. The tests had always set it; the scripts now do too, and
what they had left in my list of recent documents was taken out.

The text of the pages looked a little blurred to me. I measured first: on
my screen, at its own scale, the window showed what MuPDF draws pixel for
pixel, so the blur was not in the window but in MuPDF's way of drawing text,
which keeps the shapes of the letters exactly and does not snap them to the
pixels, as the desktop's fonts are, so their edges are grey. Fewer levels of
antialiasing changed almost nothing; a gamma that darkens those grey edges
did. It is a setting, Text on the pages, sharper by default.

Text still looked soft when the pages were zoomed out, where a letter is a
few pixels tall. I measured again, at several zooms: the window showed
MuPDF's pixels exactly, so the softness was still in the drawing. I put
eight ways of drawing the same page side by side, at 70 and 100 per cent,
and chose by eye on my own screen: the gamma followed by an unsharp mask
(Pillow's, which reportlab already brings), which makes the edges of the
letters steeper. Sharper has a light one, Sharpest a stronger one; drawing
the page larger and reducing it, or with fewer levels of grey, did less.
The mask adds about twenty milliseconds to a page, in the processes that
draw them.

23. A user manual
-----------------

The READMEs had grown into a long list of what the program does, but they
did not explain how to do it. I made two templates in LaTeX, one in English
and one in Spanish, and the manual was written in them: how to install and
start the program, the window, each mode, the work on whole files, the
settings, the command line and the keys, with a section on what to do when
something goes wrong.

Its pictures are made by a script, tools/manual_images.py, as the pictures
of the READMEs are: it makes sample documents (an essay with bookmarks and
labels, a form, a scanned page, a page with black boxes drawn over a name),
opens them in the window, offscreen, and saves the window in each mode and
the dialogs the manual explains, 34 in each language. It runs with a home
folder and a configuration of its own, so it never reads or writes mine,
and it hides the temporary folders it uses, which would otherwise show in
the status bar and in some fields. The pictures can be made again whenever
the window changes. Each manual ends with an index of about six hundred
entries, made with makeindex (latexmk runs it, with a style of its own that
puts a heading at each letter); the entries were put before the paragraphs
that name each term, from a list of terms in both languages, and the
Spanish ones sort their accented words as if they had none.

Writing the manual was also a way to check the program, since each
sentence had to be compared with the code. It found one old mistake: the
READMEs still said that the right click on a toolbar sets how that one
toolbar looks, while since stage 22 it sets all of them.

24. A bar of pages, fewer bubbles, the properties of a PDF
----------------------------------------------------------

Using the program every day, I missed three things I had in other PDF
viewers, and one thing bothered me. Moving to the first or the last page
needed the keyboard or the menu, so a toolbar now does it, at the bottom of
the window: First page, Previous page, a box with the page shown and how
many there are, Next page, Last page. Its box had to be an action of its
own, a widget action, so that it could be put on any toolbar in Customize
the toolbars, like the buttons; Qt makes a box for each toolbar it is put
on, and all of them follow the page. The bar is hidden in Impose, which has
no pages to move through.

The hints shown over the pages when a mode is chosen, and the tooltips over
every button, were more than I wanted once I knew the program. Both are
now off at first, and Settings > Appearance turns them on; F1 still shows
the hint of a mode. Qt has no switch for all tooltips at once, so an event
filter of the application drops the events that ask for them while the
setting is off. A test that applied the settings left that filter in
place, and a later test of the tips of the thumbnails failed; the tests
now take it away after each one.

File > PDF properties shows what a document is (its metadata, its file,
its pages, whether it is tagged, signed or encrypted, what it doesn't
allow) and the fonts it uses, with the pages of each. A font may be in a
file several times, one subset for each chapter, as LaTeX makes them; the
dialog shows it once, with all its pages. Looking at our own manuals with
it showed that their PDFs had no title and no author, so now they have.

25. Settings that fit, and fewer duplicates
-------------------------------------------

In a Settings window smaller than its contents, the form squeezed its rows,
and the texts under a field, which wrap, ended up under the next field. Each
tab made of a form is now in a scroll area: when the window is too short, it
scrolls; it is never narrower than its checkboxes, so it only scrolls up and
down.

The settings still had a field to name another pdf2iso, from the time when
it was a program apart; it is part of py-pdftools now, so the field was
taken out of Settings and of the settings of redaction, with a small dialog
of Impose that asked for it and that nothing opened any more. The
configuration file can still name one, which the tests use to put a script
of their own in its place.

With the new toolbar of the pages, the buttons Previous page and Next page
were twice at the top and the bottom of the window; they stay only on Page
navigation, and the toolbar Navigation keeps the history of the places
jumped to and the tools to select text, move the pages and zoom to an area.

A window of tabs with a single document showed a bar with a single tab,
which only took room. It is now hidden until there are two (Qt hides it by
itself), unless a new setting asks to show it always; with the view split
it is always shown, since the menu of each tab, which takes it back to the
other side, is on that bar.

The box of the page and the box of the zoom were fixed above the pages, in
a row of their own. They are now on a toolbar, Page and zoom, which can be
moved anywhere or hidden like the others; the widgets are the same, so all
that used them still does. Its contents can't be changed in Customize the
toolbars, which works with actions and not with widgets; the box of the page
can go on any toolbar through Page navigation.

26. A word index, from pdf-word-finder
--------------------------------------

pdf-word-finder, another program of mine, finds the words of a list in a
PDF and gives the pages where each appears by their labels, as lines for
the index of a book. It was small and well divided (the text, the
patterns, the search, the report), so its search and its report were
copied into one module, pages/wordfinder.py, with their rules unchanged:
whole words by default, phrases that may be split across lines, words
split by a hyphen joined again, regular expressions after re:, accents
ignored if wished, the Spanish alphabetical order. Three things changed.
It read the PDF with pypdf, and its labels from pypdf too; here the text
comes from PyMuPDF and the labels from the same reader as the rest of the
program, and the window passes its own labels, so that the search follows
what Foliate shows, saved or not. Its messages were in Spanish only; here
they are in English, translated as the rest. And its window, in tkinter,
became a dialog of the window, Edit > Word index, while its command line
became py-pdftools find-words, with the same options. Its tests came with
it, on a document made with PyMuPDF instead of pypdf.

27. The menu of the thumbnails, in every mode, and extracted pages in a tab
------------------------------------------------------------------------

The right click on the thumbnails offers to read the pages chosen with OCR
in every mode, as the READMEs said; but the item was grey everywhere except
in the mode OCR. It took its state from the action Recognise text, which
belongs to that mode, and the window turns off the actions of a mode while
another one is on. It now looks at what it needs, a document and tesseract.
A test opens the menu in three modes.

In the same menu, Extract to a new PDF wrote the new file and said where;
it now also opens it, in a new tab beside the document, since one usually
wants to see what was extracted.

A change of the toolbars seemed not to be kept: text beside the icons,
chosen with a right click, was gone after closing the window and opening
another document. It was kept; but only the window where it was chosen
showed it, and the others open, in tabs or windows of their own, went on
showing the toolbars as they were, until the program started again. A
change of their look, of their lock or of their buttons now goes to every
window open, and is written to the disk at once.

28. Green again on Windows and Ubuntu
-------------------------------------

The tests also run on GitHub, on Ubuntu and on Windows, against the program
installed by its installers. Every run had failed for a long while, and the
mails of GitHub said so. On Ubuntu, Python aborted at the first window: the
tests start an X server of their own where Xvfb is installed, and the
runners have it, but not the libraries of Qt's plugin for X; they now draw
offscreen there.

Windows found more, two of them faults of the program. The CSV of the data
of a form, and the table of many forms, had an empty line after each row:
csv ends its lines with \r\n, and saving the text as text made them
\r\r\n. Protect with passwords failed: it writes the protected file over
the document, which the window kept open, and Windows doesn't let a file
open be replaced. It now closes the document first, as saving does, and
shows it again if the protection fails. Looking for what else kept the
file open, I found the processes that draw the pages: each keeps a few
documents open, so on Windows saving could fail too, once a page had been
drawn. There they now read the document into memory and let the file go.
The other three faults were of the tests: one wrote over a file it still
had open, one expected the place where Linux starts programs with the
session, and one replaced, as another program would, a file the window
had open, which Windows doesn't allow.

29. A package for Debian and Ubuntu
-----------------------------------

The AppImage runs on Debian and Ubuntu, but it doesn't install itself: no
menu entry, no manual, no command in the PATH. I made a `.deb` as well
(`tools/bundle-deb.py`). The usual way, a package that depends on the
system's Python, was closed: Debian 12 has Python 3.11 and Ubuntu 22.04
has 3.10, and py-pdftools needs 3.14. So the package is made from the
AppImage, unpacked: its Python, with Qt and the libraries, goes to
`/opt/py-pdftools`, and two small scripts in `/usr/bin` start the command
line and the window with it. The menu entry, the icons, the metainfo and
the manual pages (in English and Spanish) go where Debian expects them. It
depends only on the system libraries Qt needs, and recommends tesseract and
Ghostscript.

Debian's own tools aren't on Fedora, where I make the releases, so the
script writes the package itself: a `.deb` is an ar archive of three
members, the version of the format and two tars (the control files and the
files to install), which GNU tar makes with root as the owner of every
file. I installed it in containers of Debian 12 and Ubuntu 22.04: the
command line imposed a booklet, the window opened a document, and removing
the package left nothing behind. `tools/release.py` now makes it after the
AppImage and attaches it to each release.

30. Bookmarks only when asked for
---------------------------------

The bookmarks panel kept appearing by itself. Two things showed it: many
PDFs ask, in their catalog (`/PageMode /UseOutlines`), to open with their
bookmarks shown, and the window obeyed; and each mode kept its own
arrangement of panels, so a panel opened once came back in the next
session. Now the panel is hidden when the program starts, a document's
request no longer opens it, and changing modes leaves it as it was. Only
F5, or View > Panels > Bookmarks, opens it. Later, the check of the
configuration (stage 34) found that F5 was also Preview in Impose, where
both actions were on at once, so Qt ran neither; in Impose, which shows no
pages, the bookmarks panel is now put away, and comes back on leaving it.

31. Tooltips on the toolbars
----------------------------

The setting Show tooltips, off at first, hid every tooltip, those of the
toolbars too, and most of their buttons have only an icon. The filter of
the application that drops the requests for tooltips now lets through
those of any widget inside a toolbar, so the setting governs only menus,
fields and dialogs. A script that went through every toolbar found the
items with no tooltip of their own: the count of pages, the fields of the
toolbar of Impose and their labels, and Undo apply. Each has one now. The
count of pages beside the box of the page also got a little room before
it: the two touched.

32. Quick find
--------------

Find and highlight is a dialog: good for marking what is found, slow for
only looking for a word. I added a box to the toolbar Find
(`gui/quickfind.py`), which uses the same search (`annotate/search.py`,
here without minding capitals or accents). Enter goes to the next place,
from the page shown, Shift+Enter to the previous one, and each place is
shown for a moment, as the dialog shows it; beside the box, "3/17". The
box is an action of its own, like the box of the page, so it can be taken
off a toolbar or put on another one. Ctrl+Shift+F puts the cursor in it;
if no toolbar shows it, the dialog opens instead. Esc had to be claimed by
the box itself, since a shortcut of the window took it first.

33. Thumbnails in the middle
----------------------------

The thumbnails are a list in its icon mode, one column, each cell as wide
as a thumbnail and its margin; a panel made wider left the column on its
left side. The list doesn't center an item in a wider cell, so both must
grow: the cells are now as wide as the panel, laid out again when it
changes width, and a delegate of the list makes each item as large as its
cell, which the list then draws in the middle. A first try that changed
the size of each item was dropped: with thousands of pages, it would run
through all of them at each change of width.

The thumbnails also stopped showing a page's number in the file beside its
label ("2  1"), and the count by the box of the page stopped showing it
("2/5"): two numbers for one page were confusing. A page is now shown by
its label, or by its number if it has none. Only Foliate's list of pages,
which is for setting the labels, keeps both.

34. A check of the configuration
--------------------------------

Settings > General has now a button, Check the configuration, that lists
what py-pdftools needs and whether it has it, each item with its status and
what to do. The checks that need no window are in `core/health.py`: the
version of Python and of the libraries, pyHanko, the configuration file
(whether it can be read, whether its folder can be written to, and which of
its values aren't valid or known to this version), tesseract and the OCR
languages chosen, Ghostscript, and the free space of the temporary folder.
Two details needed care. PySide6 is installed as `PySide6_Essentials`, so
asking the package metadata for "PySide6" said it was missing; the
versions are now read from the modules. And the values of the file are
checked by the same rules the program uses when it reads them (those of
`annotate/settings.py`), so the check never disagrees with what the
program does.

The window adds the keyboard shortcuts (`gui/health_dialog.py`). A first
version guessed, for each action, the mode it works in, and found clashes
that didn't exist; Qt doesn't count an action whose menu is hidden. The
check now follows Qt's own rule: an action counts when it is enabled and
reachable, in a menu shown in the menu bar, a toolbar shown or the window.
It also looks at the shortcuts changed in Settings, against every other
action. On its first run it found a real clash, F5 in Impose (see stage
30).

The tests on GitHub then found a fault of the check itself. To know the OCR
languages chosen it used the function that parses them for OCR, which
raises an error for a language not installed: the very case the check is
there to report. On my computer Latin is installed, so the test passed;
GitHub's computers have only English. The check now splits the list
itself, and the test makes the computer look as if it had only English.

35. Drawing with the graphics card
----------------------------------

The page view is a Qt graphics view, which the processor draws. Qt can give
it an OpenGL surface instead (`QOpenGLWidget` as its viewport), and then the
graphics card moves and scales the pictures of the pages, which makes
scrolling and zooming smoother. It can't make pages appear sooner: MuPDF
still turns them into pictures on the processor, in the processes that draw
them. So it is a setting, in Settings > Performance, off at first and in
effect from the next start, since the viewport is chosen when the window is
made.

The risk is the driver. On the display the tests use without an X server
(offscreen), the first try gave a view that drew nothing, with a stream of
messages from QPainter. Before using OpenGL the program now makes a small
context of its own and makes it current; where that fails, or the display
has no OpenGL, the view stays as it was, and Check the configuration says
why. With OpenGL the whole view is drawn each time, as partial updates of an
OpenGL surface cost more than they save. I checked it in Xvfb, whose
OpenGL is done in software: a capture of the screen showed the pages as
usual (a capture of the surface itself came out white, which is a matter of
how it is read, not of what is shown).

36. Replacing a file on Windows
-------------------------------

A test of the passwords failed on Windows now and then: the same commit
passed on one run and failed on the next. It protects a file, which the
window opens again, and at once writes over it again. Every write over a
file is made as a new file in the same folder, renamed over the old one
(`os.replace`), so that a failure never leaves half a file. On Windows that
rename fails while another process holds the old file, even for a moment;
here it was probably the processes that draw the pages, which read the
document just opened into memory, and it could as well be the antivirus.
The rename is now tried again, for up to two seconds, on Windows only
(`core/replacing.py`), wherever a document of the user is written over:
saving, passwords, combining, PDF/A and PDF/X, form data, the codes of
redaction. On Linux and macOS a refusal is a real one, and is reported at
once.

37. One box of the page
----------------------

The box of the page was on two toolbars: Page navigation, at the bottom,
and Page and zoom, at the top, which had kept it since it was moved out of
its fixed row above the pages. The same page in two boxes, with two counts,
only took room. The one at the top is gone; the toolbar keeps its object
name, so that it stays where it was put, but it is now called Zoom box and
has the zoom alone. The details of the page that its count gave as a tip
(the label, the size and paper, the orientation) are now the tip of the
count of Page navigation.

38. Light and dark, whatever the desktop
---------------------------------------

The setting of the colours of the interface, light or dark, did nothing on
my own computer. It asked Qt for a scheme of colours, and Qt passes that
request to the desktop's theme; under KDE the theme comes through the
desktop portal, which keeps the colours of the desktop and ignores the
request. Light and Dark now set a whole palette, every role of it,
disabled text included, so that the style has nothing to fill in with the
colours of the other theme. The view behind the pages took its grey from
the palette once, when it was made; it now takes it again whenever the
palette changes. The icons were the other half of the problem: a dark icon
theme on a light palette leaves light icons on light buttons. So the
variant of the desktop's icon theme is chosen too (breeze and breeze-dark,
Papirus-Light and Papirus-Dark), when it is installed. System gives back
the palette and the icons of the desktop.

39. Long documents, faster
--------------------------

Asked whether the graphics card could do more, I measured first, on a
document of 2,000 pages. The drawing was not the problem: the whole view is
painted again in less than a millisecond. What made the window slow with
long documents was Python, run at each step. The zoom is fitted again
whenever the window or a panel changes its size, and the fit looked for the
row of every page by building the list of all the rows again, so that its
time grew with the square of the pages: 300 ms with 2,000 pages, at each
step of a resize. The row of a page is now worked out, not searched for, and
the sizes of the pages are kept when they are laid out instead of being
asked of MuPDF again: the fit takes 7 ms, a step of a resize 15, and two
pages side by side are turned on in 96 ms instead of 690.

Scrolling had the same fault on a smaller scale. At each step, the page in
view (the one under the middle of the window) and the pages to draw were
found by asking every page for its place: 3.3 ms with 2,000 pages, a fifth
of the time a frame has at 60 per second. The tops of the rows are now kept,
in order, when the pages are laid out, and a bisection finds the rows about
the view; only their pages are looked at, and the step takes 0.01 ms. A test
compares the answer with the old one, page by page, with one or two pages in
a row, turned and without gaps.

Laying the pages out, when a document opens or the view changes, cost
133 ms. Three quarters of it was MuPDF loading every page twice to read its
size: once for the size and once more to turn it, if the view is turned. It
is now read once. The rest was items: each page had, from the start, an item
for its rendering and a layer for the tiles of a deep zoom, which a page far
down a long document never uses. They are now made when the page is first
drawn, with their order set by their z values, since they may no longer be
made in order. The layout takes 31 ms, and two pages side by side 37.

What the graphics card can really add is movement. The page pictures are
already drawn; scaling them on the way to a new zoom costs it nothing, and
the processor not much more. So a step of the zoom is now an animation of a
sixth of a second: the transform of the view goes from one scale to the
other, eased, and the sharp pictures are asked for only when it stops, as
before. With the wheel, the point under the pointer is kept under it by
moving the scroll bars after each frame, instead of relying on Qt's anchor,
which only knows the real place of the mouse and would not do for the
keys. A second step asked during the first goes on from where the first
was going, so that three quick turns of the wheel make three steps, not
fewer. Any zoom or jump of the program ends the animation first.

The wheel got the same treatment. A turn of it scrolled three lines at
once; it now glides there in a seventh of a second, and further turns add
to where it is going. Only the wheel of a mouse is animated: a touchpad
sends pixels, already smooth, and goes on to Qt as before, as do Shift and
Ctrl with the wheel. The keys that go a page at a time are left as jumps,
since they are a way of going somewhere, not of scrolling. Both animations
are one setting, in Settings > Performance.

One small cost was left on the window's own thread. MuPDF draws in RGB,
three bytes a pixel, and each page arriving was first copied into a QImage
of that format and then, to be shown, converted into the screen's, four
bytes a pixel: two passes over some 18 MB for a page at 300 %. A single
conversion as the page arrives does both, and the QPixmap is then made from
it for nothing: 1.3 ms instead of 3. I tried drawing straight into the
screen's format with MuPDF, in BGRA, but the gain was a millisecond, the
background came out transparent, and the sharpening and the reading colours
work on RGB; I left it. The thumbnails keep RGB, a quarter smaller, since
many of them are kept at once.

40. Left and Right
-----------------

Left and Right now turn the pages, as in most readers. They are keys of the
view of the pages, not shortcuts of the window: as shortcuts they would be
taken from the list of thumbnails and from the tables, where the arrows move
the current row. They give way to what used them before: with annotations
selected they still move them, a point or ten at a time, and when the zoom
makes the pages wider than the view they still scroll sideways, since
otherwise nothing would reach the sides of the page. With two pages side by
side, they go a pair at a time, like PgUp and PgDown.

41. Things in sight
------------------

Two settings were there but not seen. The check of the configuration was a
button at the foot of the tab General, below the pen, the OCR and where the
settings are kept: in a dialog of ordinary height, one had to scroll to find
it, and nobody does. It is now on the row of OK and Cancel, where every tab
shows it, and in the menu Help, where one looks when something goes wrong.

The other was the tab Colours of the settings. Each colour was a button with
its name and meaning, "Yellow — Important", beside a field that said
"Important" again, so that the colour itself was a small square at the
start of a line of text. The buttons there now show only the colour, as a
wide patch, with the name in the tip; the button keeps its menu of the other
colours.

The third was pyHanko, with the RPM. Fedora doesn't package it, and the
check told users to run pip; I did, and the check still said it was
missing. The launcher that the RPM installs starts Python with `-s`, as
Fedora's rules want, and `-s` leaves out the user's own packages, which is
exactly where pip puts them; there was nothing a user could install that the
program would see. It now looks there for pyHanko when it isn't among the
system's packages, adding that folder at the end of the path, so that
nothing of the system is replaced. The signature tests pass that way with
Fedora's Python and its own cryptography. The hint changed with it: for the
RPM, `python3 -m pip install --user pyhanko`, not the extra of a package
that pip doesn't know.

Last, the word index got a button. It had been only in the menu Edit since
it came from pdf-word-finder; it now sits on the toolbar Find, beside the
quick find box, with an icon of the program's own: a list of terms with
their pages in blue, which shows on a light toolbar and on a dark one, and a
magnifier. Its name is one no icon theme has, so the desktop's theme can't
put another in its place.

42. A quicker start
------------------

I measured where the start went, without a document: about a third of a
second before the window could be shown, half of it loading modules and the
rest building the window. Much of that building was for things a user may
never open. The workspace of Impose, with a form for each of its commands and
the parser of its command line, was made at every start, and pikepdf was
loaded for it; it is now made the first time the mode is entered, and until
then its menu waits in the menu bar, empty, where only that mode shows it.
The window also ran two programs before it appeared: tesseract, to know
where its languages are, and Ghostscript, to know whether PDF/A and PDF/X can
be made. Tesseract is now asked in another thread as soon as the program
starts, while Python loads the rest, and Ghostscript only when the menu Save
as opens. The names of the languages of the interface were found by parsing
each file of translations whole, three times; only its first element is read
now. The start went from about 330 to 240 milliseconds.

Opening a document had its own cost. To list the links with the other
annotations, the program asked PyMuPDF for the links of each page, and
PyMuPDF, to say which object each link is, lists the annotations of the page
again for every link: on a page with a hundred links, ten thousand steps.
The links are now read from their own objects, their address or the page
they go to, and the named destinations are resolved only if a link uses
one. On the manual of the program, with 590 links, reading the annotations
went from 55 to 18 milliseconds. I compared the old reading with the new on
every PDF of my machine, 21 files with more than twelve thousand links. They
gave the same, except a few links whose addresses PyMuPDF doesn't take as
web addresses (`file://…`, or written oddly): these showed nothing, and now
show the address.

43. A new version, asked for
----------------------------

The menu Help has an item to check for a new version. It asks GitHub for the
latest release, only when the item is chosen: a program that edits private
documents should not call anywhere by itself, and the question carries
nothing but the name of the program. The answer is compared with the
version running, as numbers (1.8.10 is newer than 1.8.9, which as text it
isn't), and the question waits in another thread, behind a dialog that can
cancel it, so that a slow network doesn't freeze the window.

Saying that a new version exists is the easy part; what helps is saying how
to install it, and that depends on how this copy came. The program looks at
where it runs from: under /opt/py-pdftools it is the Debian package, with
APPIMAGE set it is the AppImage, under /usr/lib it is the RPM (not
/usr/local, where pip puts what root installs), in a folder py-pdftools/venv
it was made by the installers, and in a clone with its pyproject.toml it is
the source. Each gets its own instruction, with the name of the file to
download where there is one.

44. Options, as on Linux
------------------------

The first time the installer for Windows was run by someone other than the
tests, it was run with `--uninstall`, as install.sh is, and it answered that
py-pdftools needs Python 3.14, which was installed. PowerShell knows options
only by a single dash; a word it doesn't know is given to the first
parameter that takes one by its position, and the first one was the Python
to use. The script then tried to run a program called `--uninstall`. The
parameters are no longer taken by position. The words left over are read
by the script itself: `--uninstall`, `--desktop`, `--python` and `--help`
do what their PowerShell forms do, and any other word is said to be an
unknown option, by its name. A Python given and not usable is now named as
such, instead of being reported as Python missing. The tests on GitHub's
Windows now uninstall with `--uninstall`, and give the installer the same
misspelt option, to see that it says so.

45. The toolbars, as I use them
-------------------------------

After some weeks with the program, my own toolbars had settled, and I made
them the ones it starts with. The icons are small (16 points), the bar of
the modes too: it showed the name of each mode beside its icon, which made
it as long as half the row, and the icons are told apart easily; the tip of
each button says the name of the mode, its key and what it is for. Page
navigation moved from the bottom of the window to the row of the toolbars
of every mode, between Navigation and Zoom, where the eye already is. Print
left the toolbar File: it is in the menu, with Ctrl+P, and nobody prints
often enough to want a button. A toolbar that was moved or changed keeps
its place and its buttons, since those are saved; only a new configuration
starts with these. The pictures of the manuals were made again.

46. Toolbars left behind
------------------------

Closing the window left one of my toolbars on the screen, alone, with an
icon of its own in the taskbar. It was the toolbar OCR, which I had dragged
out of the window at some point; floating, a toolbar is a small window of
its own. A window of Qt hides its floating toolbars and panels when it is
hidden, but only when it is a window itself, and with tabs on, mine are not:
each document's window is a widget inside the window of tabs. So the bar
stayed when the window of tabs was closed, and also when another tab came
to the front, showing tools for a document that wasn't in view. The window
of each document now hides its floating parts when it is hidden as a tab,
and shows them again when it comes back; the place saved for the next time
is taken before, so the bar still opens floating where it was.

The test of this cost me a release. All the tests passed, here and on
GitHub, and then Python crashed when it ended, on Linux, macOS and Windows,
and in the build of the RPM on Copr, so 1.8.13 never reached Fedora. Here
it did not happen with uv, only with the program installed as the
installers install it, which is how GitHub runs the tests. The cause was in
the test, not in the program: it used the window of a fixture, shown first
as a window of its own and then put in a tab, and the offscreen display of
the tests crashed when PySide destroyed that window at the end. I had first
blamed the panel left floating, and then the window's hideEvent, and
changed both for nothing; what found it was installing the program as
GitHub does and cutting the test down, step by step. The test now makes
its windows as tabs from the start.

47. Windows and macOS, each in its own way
------------------------------------------

Running in the background used Qt's pieces only, the tray icon and a local
socket, and these work on the three systems. What was not the same was the
way each system starts a program and gives it its documents. On Windows,
the start with the session was a .cmd file in the folder Startup, which
showed a console for a moment at every login; it is now a value in the key
Run of the user's registry, which starts the window directly, and the .cmd
of an older version is removed. The tests use a key of their own, and a
small registry made in the test checks the same code on Linux.

macOS needed more. The application made by the installer did not say that
it opens PDFs, so the Finder never offered it; now its Info.plist declares
them, and the installer registers it. And macOS does not start a second
copy to hand a document over, as the others do: it sends the document, as
an event, to the program already running, which ignored it. The program now
listens for these events, and also for the click on the icon of the Dock,
which opens a window if none is on the screen; an activation in the first
two seconds after a start with the session is the start's own, and opens
nothing. The tray icon, in colour, looked out of place in the menu bar,
where the icons are black and the system colours them; there is now one
drawn for it. I could test the events in the tests, but not the Finder
itself, which needs a real Mac.

48. One file of configuration
-----------------------------

There were two files in the folder of configuration: config.toml, with the
settings, and py-pdftools.conf, where Qt's QSettings kept what the window
remembers of itself, its size, the arrangement of each mode, the toolbars,
the recent documents. Two files for one program is one too many, and on
Windows and macOS the second one was not even a file (the registry, a
.plist). So the window's memory went into config.toml too, after the
settings, in the tables [window] and [impose]. A small class takes the
place of QSettings, with the few methods the program used, and gives the
values back as QSettings gave them, with booleans as text and the states of
Qt's widgets as bytes, here written in base64, so that the rest of the code
did not change. The writer of config.toml kept only the table of the
settings and lost every other one, a known gap with a comment of its own;
now it writes all the tables. What QSettings had is moved at the first
start, and its file removed, but only for the user's own configuration:
with another folder of configuration, as in the tests, QSettings belongs to
the user and is not touched. The spare window used to compare the whole
file to see if the settings had changed; now it compares only the
settings, or every move of the window would have made it useless.

49. Names, as others say them
-----------------------------

Many names of the menus were written as I would say them in Spanish:
"Fit the width", "The thumbnails of the pages", "Check the signatures",
"Make links of the addresses in the text". They were clear, but longer than
needed, and not the words a user of other PDF programs looks for. I compared
them with the names of PDFCraft, item by item, and changed about ninety of
them, in English and in Spanish: "Fit width", "Page thumbnails", "Validate
signatures", "Create links from web addresses", "Mark for redaction" for the
tool that only marks, "Redaction marks" for the panel that was called
"Boxes". Where the same thing had two names, as Insert from a PDF and Insert
pages of a PDF before these, it now has one. A dialog keeps the name of the
item that opens it. Some names stayed: Foliate, the name of a mode, and
"tabbar", as one word. The texts of the interface are their own keys in the
file of the Spanish translation, so each change went there too, and the
pictures of the manuals were made again.

50. A list of languages to download
-----------------------------------

OCR > Languages could already download the more accurate models of
Tesseract, but only of the rows chosen in the table, and a choice of
several rows, with Ctrl and the mouse, is easy to lose when the table is
filtered to find the next language. Each language now has a box. The
languages ticked make a list, which stays while the table is filtered and
is shown under it, by name, and Download takes them one after another, in
the order they were ticked. A model is about a dozen megabytes, so a list of
several takes a while, and the connection may fail on one: that one stays
in the list, the others are downloaded, and what failed is said at the end.
Stop keeps in the list what was not yet downloaded.

51. Deeper zoom
---------------

The zoom stopped at 1600 %, and other viewers go to 10000 %, which is useful
for a detail of a map or of a scanned manuscript. The limit was a number in
two places, and it is now in one. The real question was the drawing: at
10000 % a page of A4 would be about sixty thousand pixels wide. But the deep
zoom was already drawn in tiles, only the part in view at the full scale,
over the whole page drawn small, so the limit could go up without more
memory: at 10000 % the window shows a handful of tiles, and the process
stays near the 200 MB it uses at 1600 %. The scroll bars, which count in
whole pixels, stay far from their limit even for a long document. The box
of the zoom offers 3200, 6400 and 10000 % too.

52. Every release signed
------------------------

Only the RPM was signed, and only when the release was asked for it; the
wheel, the source, the AppImage and the Debian package went out with
nothing to show where they came from, and so did the tag. Now the RPM is
always made, and a release signs everything with the same key: a detached
signature for each file, a list of their SHA-256 sums with its own
signature, and the tag, signed by git. A signature nobody checks proves
little, so the release checks each one before publishing, the way a user
would, in a keyring of its own that holds only the public key published
with the files; the build of the RPM already did the same for the RPM. A
file changed after signing, or a published key that is not the one that
signed, stops the release. The tests sign with a key made for them, in a
folder of their own, never with mine.

53. Toolbars that stay together
-------------------------------

Moving a toolbar was clumsy, and a toolbar moved along its row left an
empty space behind. Qt keeps the place where a toolbar is let go, and
stretches the toolbar before it up to there, so the space was in fact a
toolbar too wide, and the ones after it were squeezed. Now, when a toolbar
is let go, the toolbars of each row are put again side by side from its
start, in their order, each in the row it was in; this is also done when a
mode brings back its arrangement, which may keep the spaces of an older
drag, and when the size of the icons changes. A toolbar hidden in that row
(of another mode) keeps its row. Where an empty space is wanted, a spacer
can be added in Customize the toolbars, beside the separator, as KDE's
toolbars have one. The handles, by which a toolbar is dragged, are wider
too: Fusion draws them nine pixels wide, which is hard to take hold of.

I was asked to arrange the toolbars as Okular does. Okular's toolbars come
from KDE's own library, which has no binding for PySide6, so I took from
it what could be done here: the handle, the spacer, the lock and the menu of
the right click; and I left out dragging a toolbar by any empty part of it,
which I had tried, since KDE's style uses that part to drag the whole
window.

54. Okular's keys
-----------------

I was then asked to give the program the keys of Okular where they do the
same thing, beginning with F7 for the thumbnails, which had F3. I read
Okular's sources for its defaults and took the ones that match an action
here and take no key from another: F7 for the panel of the thumbnails (in
Okular it shows its sidebar, where they are); F3 and Shift+F3 for the next
and the previous place of the quick find, which is what F3 does in KDE's
programs, and which puts the cursor in the box while it is empty; / for the
quick find, as Okular's find bar; Ctrl+Shift+P for the presentation, beside
F11; and, in it, B for a black screen, which any other key takes away. The
old keys stay where Okular has none of its own. Others I left as they were,
because here they belong to something else: Ctrl+G groups annotations
(Okular goes to a page with it), Ctrl+0 fits the page (Okular shows the
actual size) and Ctrl+1 to Ctrl+6 choose the modes (in Okular, the tools of
the mouse).

55. More from Okular
--------------------

Then came the rest of what Okular has and this program lacked, one piece
at a time. First the bookmarks: Ctrl+B adds one at the place shown, as
KDE's programs add a bookmark, and View > Go to has the next and the
previous bookmark, in the order of the pages rather than of the tree. Near
the end of a document the view cannot always scroll as far as a bookmark's
place, so the next bookmark was found again and again; now it counts from
the last bookmark reached while the view has not moved. Ctrl+B is also
bold in a text box being written, so the box claims Ctrl+B, Ctrl+I and
Ctrl+U for itself before the window sees them.

Then the tabs. Ctrl+Shift+T opens again the last tab closed, at the page
where it was left (the program keeps the last twenty, and skips a file that
is no longer there), and Alt+Shift+1 to Alt+Shift+9 go to a tab, the ninth
being always the last, as in Okular. These nine keys are in no menu: each
window gives them to its tab, like its other keys.

Ctrl+Shift+C copies the text selected without its line breaks, which is
what one wants when quoting from a PDF: the lines are joined with spaces,
and a word cut by a hyphen at the end of a line is joined again when the
next line goes on in lower case. Before a capital the hyphen stays, since
"Anglo-" and "Saxon" make "Anglo-Saxon", not "AngloSaxon".

The tool Magnifier (Shift+Z; Okular's Ctrl+6 chooses a mode here) is in
every mode, beside Zoom to area (`gui/magnifier.py`). While the mouse
button is held down on a page, a round lens follows the pointer and shows
that part of the page three times nearer than the view. It is not the
picture on the screen made bigger, which would be blurred: only that piece
of the page is drawn again, at the lens's scale, in the reading colours,
and turned as the view turns the pages; beyond the edge of the page the
lens is grey. The view and its zoom do not change.

Last, View > Page layout > Trim margins, Okular's Trim View: each page shows
only its inked part, so that a page fitted to the window shows its text
larger. Finding the ink of every page would mean drawing every page of a
long document, so the part is found on a dozen pages spread through it
(with the page asked for, and leaving out the blank ones), and the same
part is shown on all the pages of that size; this also keeps the text from
jumping from page to page. A page item keeps the coordinates of the whole
page, and only its rectangle becomes the part shown, which clips what is
drawn on it: the annotations, the rendering and its tiles stay where they
were on the page, and nothing that works on the page had to change.

56. A panel of search results
-----------------------------

The quick find goes through the places of a text one at a time, which is
slow when one wants to see them all. View > Panels > Search results (F8,
`gui/results.py`) lists every place, each with its page label and some
words around it, the text found in bold, and goes to each with a click,
Enter or the arrows. It uses the same search as the quick find and the
dialog (`annotate/search.py`), without minding capitals or accents, or
matching case or whole words. When it opens it takes the text of the quick
find, and Tools > Find all opens it with that text. Qt's lists don't draw
bold inside a cell, so a small delegate draws the context as HTML, in the
colours of the row. In a narrow panel the found text fell out of view, so
only a few words before it are kept, after an ellipsis. The list is emptied
when the document changes, since its places may be gone.

57. A command palette
---------------------

The menus are deep now, with submenus in File, Edit and View, and a command
can be hard to find. Help > Find a command (Ctrl+Alt+I, the key of KDE's
command bar; `gui/palette.py`) opens a box over the window, with a list of
every command of the menus that can be used at that moment, each with its
path in them and its key. Any word of the path finds it, in any order,
without minding capitals or accents, and those whose own name begins with
the first word come first. The menus that are filled only when they open
are filled for it. Some commands are on a toolbar only (the modes, Hand,
Zoom to area, the Magnifier), so the toolbars shown are read too. The list
shows the icon of each command, and an empty one where there is none,
since otherwise the names did not begin in one column. The command runs
after the palette has closed, so that a dialog it opens is not under it.

58. Comparing what is seen
--------------------------

Compare with another version compares words. Two printings of a book, or a
plan and its revision, can differ in what has no words: a picture, a line,
where a block stands. File > Compare > Compare visually (`pages/visual.py`,
`gui/visualcompare.py`) shows this document, as saved, and another PDF
page by page. Each pair of pages is drawn in grey at 72 dpi on sheets of
the same size, and the pixels that differ are looked for. There is no
numpy here, so the rows are compared as whole byte strings, and only a row
that differs is looked into: the two rows, reduced to a few levels of grey
so that the smoothing of edges doesn't count, are made into integers and
XOR-ed, and a regular expression finds the runs of bytes that are not
zero; all of it runs in C, about three milliseconds a page. The differing
pixels go into cells of six pixels, and neighbouring cells become one
rectangle, which is framed on both pages, side by side. The overlay draws
this document with its black turned red and the other with it turned blue
(PyMuPDF's tinting), multiplied one over the other, so that what both have
is black. The pages that differ are looked for only when Next difference
asks for them, so a long document opens at once. The password loop that
Compare with another version had was made a method of its own, for both.

59. Accessibility
-----------------

Last, the window was made easier to use without the mouse and with a screen
reader (`gui/access.py`). A screen reader says the name of a field or a
list, and most of them had none: a test now looks at every field, list and
view of the window, in every mode, and fails on one without a name. Rather
than naming the eighty or so by hand, those without one take it from their
placeholder text, or from the first clause of their tooltip, or from the
label beside them in their layout (the row of a form, the cell to the left
in a grid, with the title of their group); a field wrapped in a widget of
its own, as in Impose, takes its wrapper's. The pages, the lists and the
trees with none of these got names of their own. This runs when the window
opens and when a mode is chosen, since some panels are made only then. A
combo box's popup list is a window of its own, and its layout could vanish
under PySide while it was read, so it is left out, and named by its box.

View > Next panel (Ctrl+F6) and Previous panel (Ctrl+Shift+F6) take the
keyboard from the thumbnails to the pages and to each panel shown, from left
to right, going round, and the status bar says where it went.

Settings > Appearance > Theme has a High contrast theme: white on black,
yellow for what is chosen, cyan links. The palette alone was not enough,
since some styles draw the frames of the fields in colours close to the
background, so this theme adds a short style sheet: a white border around
each field and list, and a thicker yellow one around the one with the
focus. With that style sheet set, the program crashed now and then as it
ended, when Qt destroyed it after the application; it is now removed when
the program is about to quit, and the crash, six times in eight before, did
not come back in eight tries.

60. A panel of attached files
-----------------------------

A PDF can carry files: attached to the whole document (its
`/EmbeddedFiles`) or to a page, as an annotation. The program showed the
second kind, as annotations, and nothing of the first. View > Panels >
Attached files (F9, `gui/attachments.py`) lists both, the document's first,
each with its size, where it is and its description, and opens a file with
the desktop's program for it (a copy in a folder of its own), saves those
chosen (several into a folder, a number added to a name already there, so
nothing is overwritten), attaches files to the document, and removes those
chosen. Adding and removing go through the same steps as any change of the
document, so they are undone with Ctrl+Z; a name the document already has
gets a number, since it can't hold two the same. PyMuPDF gives a file's
name as its description when it has none, which only repeated the name, so
that is left out. The list is filled only while the panel is shown, and
again when the annotations change, since those of the pages are annotations.

61. A page sorter
-----------------

The thumbnails are a narrow strip, good for going to a page and poor for
putting three hundred of them in order. View > Page sorter shows every page
in a grid of large thumbnails, in a dialog that fills most of the window,
where the pages are dragged to their new places, several at once, and
turned, duplicated or deleted. Nothing happens to the document while the
dialog is open: it keeps its own order of the pages, and OK makes all of it
as one operation (arrange.Sort: the new order, pages left out deleted, then
the turns by the new places), one step that Undo takes back. The operation
has to know how many pages the document had, since a page left out is a
page deleted, and the labels must then follow their pages. A grid of a
long book would take a while to draw, so a thumbnail is drawn only when it
comes into view, one at each turn of the event loop.

62. A menu Tools
----------------

The utilities that work on the document as a whole had been put wherever
there was room: the word index in Edit, the page sorter in View, the
comparisons in File, and File was about to pass the sixteen items a test
allows it. They are now in a menu of their own, Tools, which every mode
shows, between View and Settings, as KDE's programs have one. The menu that
the mode Annotate already called Tools, which holds the tools of
annotation, is called Annotate now, as the other modes name their menus
after themselves. Each action is in one menu only: the menus are filled in
order, and what Tools takes is not put back at the end of the menu where
it was made.

63. Steps on several files
--------------------------

Headers, footers and watermarks could already be put on several files at
once, but a folder of scans usually needs more: its text read, its pages
numbered, a smaller size, PDF/A. Tools > Run steps on several files does
any of these, in the order chosen, on each file of a list. Each step is a
command of the command line, the same that was tested by itself, run in the
program on a temporary file and writing the next one, so the dialog adds no
second way of doing what the commands do; the last file goes to the folder
chosen, with an ending after its name, never over the original nor over a
file already there. A file that fails stops only itself, and the message
names it rather than the temporary file that failed. The work runs in a
thread, which can be stopped between two steps, and the steps chosen, with
their settings, are kept under a name, in recipes.json beside the settings.

64. A panel of the history
--------------------------

Undo went back through everything done to a document, but blindly: one
step at a time, with no way to see what the next step would undo. The
panel History lists every step since the document was opened, with the
one where it is now in bold and those that Redo can bring back below it,
and a click on a step undoes or redoes up to there. The history kept no
description of its steps, and I didn't want a second list to keep in step
with it everywhere it is changed. A change of the document itself already
had its message, for the status bar, which its state now keeps (and carries
from undo to redo and back). A change of the annotations is described by
comparing it with the state after it: a change makes a new list that holds
the same objects as before but those it changed, so comparing by identity
tells what was added, deleted or changed, quickly, even with thousands of
annotations; one changed is told from one deleted and another added by its
kind and the time it was made.

65. Stamps of one's own
-----------------------

The Stamp tool had the standard stamps and one made of a text, but an
office or a department usually has its own seal, or a logo, and wants to
put that. A stamp with a picture and no standard name was already one the
program could read, show and write, so the new stamps needed no change of
the annotations: only a library of pictures (the folder stamps of the
settings, with each one's size in points in stamps.json) and a menu to
choose, add and remove them. A picture is taken to be printed at 150 dpi,
and made narrower if it would be very wide. A page of a PDF is better: it
is drawn on a transparent background, and only what is painted on it is
taken. My first try measured that with the boxes the page reports for
what it draws, but the box of a curve includes its control points, and a
circle of 120 points came out as 200; it is now measured on the page
itself, drawn at 72 dpi, by the rows and columns that are not
transparent. A stamp removed from the library while it is the one chosen
gives way to a standard one, and the window says why.

66. Finding as you type
-----------------------

The quick find box searched only when Enter was pressed, and showed one
place at a time. I added a toolbar, always at the bottom of the window,
that searches at every letter, highlights every place found, and keeps the
last texts searched; it has its own options for capitals and accents, and
two buttons that take its text to the other searches, which stay as they
were. It had to be very fast, and the search that the dialogs use was not:
in a document of a thousand dense pages it took almost a second for each
search, even with the text of the pages already read, because it took
the accents off every character again each time, and reading the pages the
first time took nineteen seconds. Measuring showed where: MuPDF gives the
characters of a page with their boxes in less than a millisecond, and the
other fifteen were spent in Python, turning a rectangle for each character
as the page is shown. So the bar has an index of its own
(annotate/textindex.py). It reads each page once, following the same rules
(a word cut with a hyphen at the end of a line is one word), keeps the
boxes as plain numbers, unturned, and keeps the text also without accents
and in lower case; a search is then only a search of a string. A place
found is only its page and where it starts and ends: its rectangles are
worked out when it is shown, and only the pages in view are highlighted.
When the text typed goes on from the one before, only the pages where that
one was are searched again. The pages are read ahead, a few at a time,
while the bar is open. Now reading the thousand pages takes a second and a
half, and a search a few milliseconds; a test checks that the index finds
exactly what the old search finds, with and without capitals and accents,
also on turned pages.

67. The find bar, alone and instantaneous
-----------------------------------------

Used on real documents, the bar was not what it should be, and the
complaint was right on both points. It sat above the status bar, and it
should be alone at the bottom of the window; Qt always keeps the status
bar last, below every toolbar, so while the bar is open the status bar is
hidden and its messages are shown at the right end of the bar. And it
took time before it showed anything: on a document whose text was not
read yet, each search read every page before it counted as done, and a
letter typed meanwhile started it all again. Now a search goes forward
from the page shown and stops at the first place it finds, which is shown
at once; Next and Previous search on from there in the same way. Counting
the other places, for "3 of 41" and for the highlights, is done
afterwards, in slices of a few milliseconds while the program is idle,
and the reading ahead too. On a thousand pages not read yet, the first
place of a text that is there is shown in a few milliseconds, having read
one page. A text that is not there still has to read every page to know
it, two seconds the first time, and the bar says meanwhile how far it has
got.

68. A menu Find
---------------

The searches had ended up in three places: Find and highlight, the quick
find and its next and previous place were in the menu of the mode
Annotate, which is shown only in that mode, so in the other modes they
had no menu at all, only their keys; Find all was in Tools, and Find as
you type in Edit. They are now together in a menu Find, after Edit, in
every mode; each is in that menu only, as with Tools.

69. Finding, again: from the top, and two searches only
-------------------------------------------------------

Used a while, the bar at the bottom was still not right: I wanted it
to come down from the top when called, as the find box of a code editor
does. It is now a small panel over the top right corner of the pages, which
slides down when called and slides up when closed (a QPropertyAnimation of
its position, of 160 milliseconds), and follows that corner when the window
changes size or the scroll bar comes or goes. Its options are two buttons,
Aa and á, and the rest went into a small menu. The status bar stays where
it was. And there were three searches where two were enough: the quick find
box on the toolbar did less than the panel. So it went, with its module;
Ctrl+F, the key every program gives to finding, and the slash, as in
Okular, now bring down the panel, and F3 and Shift+F3 go through its
places, while the search with every option, Find and highlight, has
Ctrl+Shift+F.

70. The toolbars, by kinds of work
----------------------------------

The toolbars had grown one button at a time, and their order no longer
said much: the word index sat beside the search box, and the tools that
choose what the mouse does (Select text, Hand, Zoom to area, Magnifier)
were in Navigation, with Back and Forward. They are now in one row by kinds
of work: File; Edit; Mouse tools; Navigation, only Back and Forward, beside
Page navigation; Zoom and its box; Find, with the dialog and Find as you
type; and Tools, as the menu Tools, with the page sorter (with an icon of
its own) and the word index. The new order had to reach those who already
had their windows arranged: Qt keeps the place of each toolbar, so a
change of the defaults alone would change nothing for them. Once, the first
time the new version starts, each arrangement kept (the window's, and that
of each mode) is opened, its toolbars at the top are put in the new order,
and it is kept again; the toolbars moved to a side and the panels stay
where they were.

71. Resetting the toolbars
--------------------------

Customize the toolbars could bring one toolbar's buttons back to how they
were at first, but not everything at once, and not their places. Reset
the toolbars does it all, after asking: the buttons of every toolbar, the
toolbars of one's own removed, their looks, and their places, in the
program's order, in the arrangement kept for each mode, which is opened
and kept again as when the order changed (stage 70). The panels are left
where they are; a reset of the toolbars has no business with them.

72. Apply, in Settings
----------------------

The window Settings had only OK and Cancel, so seeing a change in effect
meant closing it and opening it again. It now has Apply too, as in KDE
Plasma: off until something changes in any of its pages (every check box,
list, field, number, key and colour of the dialog turns it on), it puts the
changes in effect and leaves the window open, and Cancel afterwards keeps
what was applied. OK and Apply do the same work, which was moved out of
accept() into a method of its own. The one exception is the language: a
new one makes every window of the program again, which can't be done with
the dialog still open on one of them, so it comes when the dialog closes,
whichever button closes it.

73. The tests at once
---------------------

The tests had grown to over seven hundred, and ran in more than a minute,
one after the other, while the computer has many processors. As in
py-words, tools/test.py runs each file of tests in a pytest process of its
own, as many at once as there are processors, the slowest first, so that
the suite takes about as long as its slowest file: some twenty seconds.
Each test already had a configuration folder of its own, and each process
its own virtual display; each process also needs its own home folder, its
own temporary folder of pytest, which would otherwise be cleaned by
another, and its own folder for the socket of the program in the
background. One file looked as if it had run no tests: Qt wrote a line
after pytest's summary, and the runner read the last line; it now reads
the summary, wherever it is. The release runs the tests this way too; the
%check of the RPM still runs them one after the other.

74. Signing, said plainly
-------------------------

The dialog to sign digitally asked first for a "Digital ID" (the path of a
file) and its password, then for a reason, a place, a contact, where the
signature goes, certifying, locking and a timestamp server, all at once;
someone who had never had a digital ID couldn't tell what to do, and the
way to make one was another item of the menu. It now goes in three steps,
said plainly. The first is the digital ID: without one, the dialog says
what it is and offers to create it there, or to use one already had; with
one, it says whose it is and until when it is valid, read from the
certificate saved beside it, so no password is needed for that, and the
password is checked as it is typed (a check mark, or "wrong password"), so
the button to sign is on only when signing can work. The second is where
the signature appears, as three choices in words; the third, why one
signs. The rest went under More options. The dialog to create an ID marks
what is optional and says what the two files it makes are for.

75. A signature from a picture
------------------------------

The handwritten signature could only be drawn in the program, with a pen
or the mouse, and many people already have theirs scanned, or can
photograph it. The dialog My signature can now take a picture. A photo of
a signature is mostly paper, and paper is never quite white; put on a page
as it is, it would be a grey box with a signature in it. So the paper is
made transparent: each pixel becomes as transparent as it is light, all
of it paper above a certain grey, all of it ink below a darker one, and
the edges of the strokes in between stay soft. MuPDF's pixmaps do this
with a table of 256 values applied to all the pixels at once, in a few
tens of milliseconds, and the picture is then cut to the rows and columns
that have ink. My first version took those two greys as fixed, a light
one and a dark one, and a photo taken under a lamp, its paper grey and
bluish, came out as a blue-grey box: none of its paper was light enough.
Now they are measured in each picture: most of a picture of a signature is
paper, so the median grey is the paper's, and the two thresholds are set
below it; and only what is clearly dark counts when the picture is cut, so
that a few faint specks of the paper don't widen it. A picture that was
transparent already came out as its negative: under its transparent
pixels it kept black, which is not seen until the transparency is taken
away; it is now put on white first, as a page would show it. And the
signature can be any size: a box dragged with the tool sets its width,
and My signature the width of a click, in centimetres. The Signature tool puts the
drawing or the picture, whichever was chosen last; the picture goes as an
image stamp, which the program already knew how to read and write.

76. The picture in a digital signature
--------------------------------------

A visible digital signature showed only text, framed: the signer, the time
and the reason. Many people expect to see their signature there, as on
paper, so the picture of My signature can now go in it. pyHanko, which
makes the signatures, draws their look with a style that takes a
background picture; the picture fills the box above, on no background and
with no frame, and the text goes small under it, with room enough for its
lines so that the lowest stroke of the signature is not crossed. The
picture is the same as the Signature tool's, kept once; the dialog to sign
offers to choose one when there is none.

77. Several signatures
----------------------

One signature was not enough: people sign some papers in full and initial
others, and a scanned signature and a drawn one may both be useful. My
signature became My signatures, a list: each one has a name, is drawn or
comes from a picture, and has its own width on the page; the one selected
when the dialog is closed is the one the Signature tool puts, and the
right click on the tool lists them all, to choose another without opening
the dialog. A digital signature can show any of them, chosen in its
dialog; a drawn one is painted into a picture first, with the same curves
it has on the page. The list goes in the configuration, and the pictures
in a folder of their own, one file for each, so that deleting a signature
deletes its picture. The one signature of the earlier versions goes into
the list the first time, and is left where it was, for an older version
to find. That first time also brought out a problem. A picture kept before
the fix of the transparent PNGs was kept as its negative, and signing
reused it as it was; such a picture, mostly dark and opaque where the
paper should be, is not taken, and the program asks for the picture
again. The dialog also made the tests crash at exit: a button connected to
a lambda that held the dialog freed it a second time when Qt let go of
the connections, and the buttons are connected to methods now. A box
dragged with the Signature tool sets the width of the signature, but
nothing was seen while it was dragged; it shows now as a frame of dashes,
as the one that selects.

78. The key of the command palette
----------------------------------

Find a command had Ctrl+Alt+I, the key of KDE's command bar; for those who
come from VS Code, the key is Ctrl+Shift+P, and they press it without
thinking. It was the second key of Full screen, taken with Okular's keys;
it opens Find a command now, which keeps Ctrl+Alt+I too, and Full screen
keeps F11.

79. Every search as quick as the find bar
-----------------------------------------

Measured on a document of a thousand pages, almost everything took less
than a tenth of a second, and Find all took nearly half a minute, with the
window still. A profile showed why: nine tenths of the time went into
reading the text of the pages, where each character became a rectangle
turned as the page is shown, two million of them; the same fault the find
bar had (stage 66), which its index had avoided only for itself. Find and
highlight, Find and redact's search for words and Find all still went
through the old reader. Now find_text reads the pages as the index does,
keeps the text also without accents, turns only the boxes of what it finds,
and gives exactly the same places, as a test checks against the old way on
turned pages and with every option. And the window keeps one index for the
document shown, which all the searches share: a page read by one is read
for all. Find all on a thousand pages takes now under two seconds the first
time, and a tenth of a second after. Find all also stopped freezing the window: it
puts the places of each page in its list as soon as that page is searched
(the first ones show within a fifth of a second), a new search or the
panel closed stops the one running (before, a second search could start
inside the first, which then wrote its stale list over it), and the panel
reads the pages ahead while it is open. The same measure found the mode OCR slow to
open, almost half a second on a thousand pages: to tell which pages are
scans without text it read the text of every page. It now looks first for
images, which is cheap, and reads the text only of the pages that have
some; a book made of text opens the mode in a twentieth of a second.

80. Starting without the tray
-----------------------------

To try a version from the source code I had to quit the one installed
first, every time: with Keep running in the background on, a new start
gives its files to the program already running and ends, so the source
code never ran, and the window I saw was the old one; that is how a fixed
picture of a signature seemed still wrong. py-pdftools-gui --no-tray starts
a program of its own that time, whatever the setting says: it doesn't give
its files to the program running, doesn't go into the background, and ends
with its last window. The setting is left as it is.

81. An APT repository
---------------------

On Fedora, Copr brings each new version with `dnf upgrade`; on Debian and
Ubuntu, the `.deb` of each release had to be downloaded by hand. A
Launchpad PPA, the usual answer there, builds only from source packages,
without internet, and this package carries its own Python, made from the
AppImage. So I made a repository of the packages already built and signed,
for all my programs that have one: github.com/nivaca/apt, a project of its
own. It is a flat APT repository whose files are those of a release on
GitHub, since page sites take no file over 100 MB and this package has
161. The release script now adds the new `.deb` to it, with that project's
tool, which signs the index with the same key and checks it before
uploading (--no-apt leaves it out). Tried in containers of Ubuntu 24.04 and
26.04, `apt install py-pdftools` installed it and it ran.

82. Tools in groups, and comments that show
-------------------------------------------

The menu Annotate had grown into a column of more than thirty tools. It is
now in submenus, the same groups as the toolbars, with their names and
icons; each tool keeps its key. And a comment written on a box, a line or
a highlight could only be found by pointing at the annotation, with
nothing to say it was there. Such an annotation now has a small speech
balloon beside its top right corner, in its colour. I first drew it with
the annotation, at a fixed size on the screen, but an item is repainted
only within its bounds, given in points of the page, and at a small zoom
the balloon went out of them; enlarging the bounds would have made the
tooltip of the comment appear far from the annotation. So it is an item of
its own, which ignores the zoom of the view and carries the same tooltip.

83. Annotations on pages larger than paper
------------------------------------------

On some PDFs the comments came out minuscule. Their pages were much
larger than paper: a scan put in the PDF at one point to the pixel, so
that a page scanned at 300 dots per inch measures 2480 by 3508 points,
over a metre; a text box of 12 points is a speck on it. The program now
measures each page against a Letter page, and on one at least one and a
half times as large in both directions (no paper is: A3 and tabloid stay
as they are) it makes new annotations larger in proportion, about four
times for that scan: their font, their lines, the size of a text box, a
callout, a check mark, a stamp or a signature made with a click. The
sizes kept in the settings stay the same.

That was not enough for notes, the first thing tried on such a page. The
text of a note is not drawn on the page; it is written in a field beside
its icon, and that field had a fixed size and a font of 10 points of the
page. Now it grows with the page as the rest, and is never smaller on the
screen than at a zoom of 100 %, on any page. The icon was a worse problem:
MuPDF gives a note's icon 16 points, whatever is asked (changing its
rectangle crashed it), and with a whole scan in view 16 points are two
pixels. So the canvas draws the icons of notes and attachments at no less
than 16 pixels, from their corner, and a click finds them there; the PDF
keeps them as they are, as other readers draw them at a fixed size too.

84. Pages measured in larger units
----------------------------------

Looking at how another free PDF program sizes its comments, I thought of
the pages of large format that declare a unit larger than a point (a
`/UserUnit` of 4, say, so that their numbers stay small), and tried one.
MuPDF gives the places on such a page in points, its real size, so the
measure of large pages already saw it as it is. But it writes and reads
the size of a font and the width of a line as they are, in the page's
units: a text of 48 points came out four times as tall, and a line of 8
points 32 pixels thick. Now the program converts them where annotations
are written and read, and inside it every size is in points. The check
after a change compares in the page's units, as it reads there.

The same reading showed that that program writes notes and attachments
with two flags of PDF, NoZoom and NoRotate, which ask a reader to draw
their icon at one size and upright, whatever the zoom or the turn of the
page. Ours now have them too, so that other readers show their icons as
the canvas does; and the canvas, which had only kept them from shrinking
below 16 pixels, now draws them at 16 pixels at every zoom, as the flag
asks, so that zooming in on a page no longer makes a note's icon cover
the text under it.

85. Installers for Windows and macOS
------------------------------------

Until now, on Windows and macOS py-pdftools was installed from its source,
by `install.bat` or `install.sh`, which need a Python 3.14 and the
internet. py-slowdown already had installers that need nothing, and I
made the same here. `tools/bundle-installer.py` takes a Python 3.14 of
python-build-standalone, pinned with its SHA-256, installs py-pdftools
into it with its libraries and pyHanko, trims Qt as the AppImage does,
and runs `packaging/installer/check.py` with it: an annotation and page
labels written and read, a PDF made with reportlab, a document opened in
the window. On Windows, Inno Setup makes of that folder an installer for
the user or for everyone, with a Start-menu entry and py-pdftools in
"Open with" of PDF documents (a type of its own, so that it takes no one's
default program); on macOS, an application in a disk image, which the
Finder offers for PDFs. GitHub makes both, each on its own system, with
every tag, installs each, runs the check again, uninstalls it and adds
them to the release; `tools/release.py --installers` then signs them
here and copies them to Codeberg.

The first try for macOS failed: no build of pikepdf for the Mac. Since
version 10.14 pikepdf publishes its Mac builds only for Apple Silicon and
macOS 15, and PyMuPDF only for Apple Silicon too. So there is one image,
for Apple Silicon, which asks for macOS 15, and none for Intel, where
py-slowdown has two. The packages are never compiled on the way
(`--only-binary`): without a build for the system, the installer is not
made.

86. Pages as pictures
--------------------

The user asked for a tool that takes the text out of a document by making
its pages pictures, all of them or some. It is in File > Save a copy > With
pages as pictures, and on the command line as `py-pdftools rasterize`
(`pages/rasterize.py`). Like a smaller copy, it is made from the file as
saved, and never over the document open; once written, it opens in a
new tab beside the document, as the user asked.

Each page chosen is drawn by MuPDF, with its annotations and fields, at the
resolution asked (300 dpi by default). Then the page receives a new, empty
content stream and empty resources, and the picture is put on it as PNG or
JPEG. I did not empty the old streams: in a PDF two pages may share their
content or their resources, and emptying them would have blanked a page
that was not chosen. The objects nobody uses any longer, the fonts among
them, go when the copy is saved; a test looks in every object and stream
of the file to see that the words of those pages are not there. The
annotations and the fields of a page are deleted once they are in its
picture, or they would show twice, and a field would keep its value as
text.

Two cases needed care. A turned page is drawn unturned and turned again
afterwards, so that the picture fills the page as stored and `/Rotate`
still shows it as before; and a page with a crop box keeps its visible
size. A very large page (a map, a poster) would pass a thousand million
pixels at 600 dpi, so above 120 million it is drawn at the resolution that
fits. Bookmarks, page labels, links, the pages not chosen and the
protection of the file stay as they were.

87. A lower properties dialog
----------------------------

With a single annotation, the properties dialog had grown taller than a
laptop's screen, and most of its height went to the part Textual
criticism, which few annotations use. The user asked to make it
collapsible. Its fields now fold under one line that shows the entry as
in an apparatus (`Conjecture: lemma ] reading A`), cut at sixty
characters with the whole of it in the tooltip; an arrow unfolds them, and
ticking the part unfolds them as well, since then they have to be filled.
The dialog is about 250 pixels lower. Making it lower again on folding
needed the layouts to be done anew by hand, after Qt's own pass: before
that, the minimum height still counted the folded fields.

88. Resetting all settings
--------------------------

The user asked for a way to reset all the settings from the Help menu,
with a confirmation and a backup. All of them are in one file,
`config.toml`, so the reset is to move that file aside, renamed with the
date and time (`config.reset` in `core/config.py`); a move is a copy and a
deletion at once, and the settings can never be lost without their copy.
The other files of the folder are the user's work, not settings (stamps,
signatures, digital IDs, recipes, profiles), and stay.

The order mattered. Each window writes what it keeps of itself (its size,
its toolbars) when it closes, so a file removed while windows were open
would come back, half written, at the end. Help > Reset all settings
therefore closes every window first, as Quit does, each asking about its
unsaved changes; if one stays open, nothing is reset. Only then is the
file moved, a message says where the copy is, and the program ends. It
does not start again by itself: that would need a different command for
the AppImage, the installers and the source, and starting it is one click.

89. A black box in a smaller copy
---------------------------------

The user sent a course programme whose smaller copy had a black block
where the university's logo was, on every page. The logo was not a
picture at all but paths, drawn over a white box, and the white of the box
was lost: in the content of the page the box is filled after `1 sc`, a fill
colour given with no colour space before it, which is legal (the colour
space at the start is DeviceGray). I looked for the step that lost it,
taking away the parts of the page one at a time, and found it in MuPDF's
`rewrite_images`, which I used to draw the pictures again. To find them, it
passes the content of every page through its filter, and the filter drops
such an `sc`. The save with `clean=True` used the same filter.

So `pages/reduce.py` now draws the pictures again itself. For each picture
it takes the highest resolution at which it is shown (a picture shown on
two pages counts at the sharpest), makes it smaller with MuPDF's scaler,
and writes it, as JPEG, into the same object, its soft mask made as small
with it. Pictures in black and white, masks and pictures MuPDF can't read
are left as they are. The content of the pages is never parsed again: it is
only compressed again, byte for byte, which gave back most of what
`clean=True` saved (the copy of the user's file is 588 KB, against 576 KB
with the fault). Pages as pictures lost `clean=True` too. A test draws the
same `1 sc` box and checks that it stays white and that the content of the
page is the same, byte for byte.

Testing
-------

The program has 820 tests (`uv run python tools/test.py` runs them at once, each file in a process of its own, in some twenty seconds; `uv run pytest`, one after the other): those of the four programs,
moved into the new package (96 of annotations, 71 of redaction, 115 of
pages, labels and layers, 87 of imposition), and those of what is new: the
command line as a whole and its completion in bash and fish, the modes of
the window, the boxes as redaction marks, the working copies with their
undo and redo, the page labels written by PyMuPDF as pikepdf writes them,
the moving through a document (bookmarks, links, the history, the views,
tabs, reloading), the security of documents (text only covered, hidden
layers, passwords), the toolbars, combining files and PDFs of pictures,
smaller copies, pages made pictures, links, forms and signatures, the menus and toolbars, the
exports, splitting and the PDF version, the start in the background and the
settings, the toolbar of the pages, the tooltips, quick find, the check of the configuration, the properties of a
PDF, the word index, what the start leaves for later, what the window keeps of itself in the file of configuration, the start with the session on Windows (in a registry made in the test) and the events of macOS, the signing of a release (with a key made in the test), the check for a new version (against an answer made in the test: the tests never go to the network), the Spanish interface (every text translated, and none left over)
and the packaging. The windows of the four modes are tested as a user would
use them, with mouse events on the pages; the redacted copy is also written
in a process of its own, as the window does it, and imposition runs its
commands in one. The window was checked by eye as well, with screenshots of
each mode in both languages, and the user manual was compared, sentence by
sentence, with the menus, the keys and the dialogs of the program. The RPM runs all the tests again with Fedora's
packages (without pyHanko, so the tests of the signatures are skipped
there). The Linux installer was run in a home folder made for the test. The
program has 180 files of Python, around 49,900 lines (about a tenth of them
comments), and 3,471 texts of the interface in Spanish.
