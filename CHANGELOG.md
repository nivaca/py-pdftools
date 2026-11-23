# Changelog

All notable changes to py-pdftools. The releases, with the AppImage, the
Debian package, the RPM, the wheel and the source, are on
[Codeberg](https://codeberg.org/nivaca/py-pdftools/releases) and
[GitHub](https://github.com/nivaca/py-pdftools/releases).

## Unreleased

- **A list of OCR languages to download**: in OCR > Languages, each language
  has a box; those ticked make a list, shown under the table, which
  Download takes one after another. One that can't be downloaded doesn't
  stop the others, and is said at the end.

## 1.8.15 — 2026-11-22

- **One configuration file**: what the window keeps of itself (its size,
  the arrangement of each mode, the toolbars, the recent documents and
  those open at the end) is now in `config.toml` too, after the settings,
  in the tables `[window]` and `[impose]`, no longer in a second file of
  Qt's (`py-pdftools.conf` on Linux, the registry on Windows, a `.plist` on
  macOS); the first start moves it there and removes the old file.
- **"The tabbar"** in place of "the bar of the tabs", in Settings > General
  and in the documentation.
- **Shorter, usual names** for about ninety menu items, panels, tools and
  settings, in English and in Spanish, after comparing them with those of
  PDFCraft: Fit page, Fit width, Two-page view, Page thumbnails, Document
  properties…, Check for updates…, Validate signatures…, Extract pages…,
  Insert pages from file…, Mark for redaction, Preview redactions, the
  panels Form fields and Redaction marks, Strikethrough, and others. The
  manuals and their pictures use the new names.

## 1.8.14 — 2026-11-22

- **The RPM on Copr**, which 1.8.13 didn't reach: one test made Python
  crash when it ended, after all of them had passed (the program was not
  affected); the test is mended.
- **Windows**: Start with the session (Settings > General) is now a value in
  the key Run of the user's registry, so no console shows for a moment at
  login; the .cmd file that older versions put in the folder Startup is
  removed.
- **macOS**: the application made by the installer opens PDFs from the
  Finder (Open With), and a document opened from there, or dropped on its
  icon in the Dock, goes to the program already running; a click on the
  Dock with no window open (in the background) opens one; the icon in the
  menu bar is in black, as the others there.

## 1.8.13 — 2026-11-22

- **The toolbars, at first**: all in one row, Page navigation among them
  (between Navigation and Zoom, no longer at the bottom of the window);
  small icons (16), the bar of the modes too, whose buttons say the name,
  the key and what the mode is for in their tip; and File without Print,
  which stays in the menu File (Ctrl+P). A toolbar already moved or changed
  keeps its place and its buttons.
- **Toolbars and panels dragged out of a window in tabs** stayed on the
  screen, each with its icon in the taskbar, after the window was closed,
  and when another tab came to the front; they now hide with their tab, and
  come back with it.

## 1.8.12 — 2026-11-22

- **A quicker start**: the workspace of Impose is made the first time the
  mode is entered, not at every start; tesseract is looked for in another
  thread while the rest loads, and Ghostscript when the menu Save as opens.
  Without a document, the window shows in about 240 ms instead of 330.
- **Documents with many links open faster**: where each link goes is read
  from the link itself (PyMuPDF listed the annotations of the page again for
  every link); the manual, with 590 links, is read three times as fast.
  Links with addresses PyMuPDF doesn't take as web addresses, which showed
  nothing in the list of annotations, now show the address.

- **Help > Check for a new version** asks GitHub for the latest version
  (only then: never by itself, and sending nothing about the user) and, if
  there is a newer one, says how to install it for the way this copy was
  installed (RPM, `.deb`, AppImage, installers, source or pip), with a
  button to the page of the release.
- **The installer for Windows** took an option written as for install.sh,
  `--uninstall`, as the Python to use, and said that Python 3.14 was
  missing; it now takes `--uninstall`, `--desktop` and `--python` as well
  as `-Uninstall`, `-Desktop` and `-Python`, says that any other word is an
  unknown option, and that a Python given with `-Python` isn't usable when
  it isn't.

## 1.8.11 — 2026-11-22

- **Word index** is also a button on the toolbar Find, with an icon of its
  own (a list of terms with their pages, and a magnifier).

## 1.8.10 — 2026-11-22

- **Check the configuration** went unseen at the foot of Settings >
  General, under a long list; it is now a button on the row of OK and
  Cancel, seen from every tab, and an entry of the menu Help.
- **Settings > Colours** shows each colour as a patch of it, with its name
  in the tip, instead of its name and meaning, which repeated the field
  beside it.
- **pyHanko with the RPM**: installed with `pip install --user`, it wasn't
  found, since the RPM starts Python with `-s`, which leaves out the user's
  packages; the program now looks there for it (after the system's), and
  Check the configuration and the menu say how to install it for each kind
  of installation.
- **Animated zoom** with Ctrl and the wheel: the place under the pointer
  drifted a pixel or two at each turn, the roundings of the scroll bars
  adding up frame by frame; it is now fixed when the zoom starts and stays
  put (found by the tests on GitHub's macOS).

## 1.8.9 — 2026-11-22

- **Left and Right** turn the pages in the view of the pages: the previous
  and the next one (a pair, with two side by side), while the pages fit
  across the view; zoomed in wider, they scroll sideways as before, and
  with annotations selected they still move them.
- **Icons on Windows and macOS**: the light or dark variant of the icon
  theme was looked for without minding capitals, which their file systems
  ignore, so a name not quite right could be taken (found by the tests on
  GitHub's Windows).

## 1.8.8 — 2026-11-21

- **Long documents, faster**: fitting the zoom (at every resize of the
  window, and when a panel opens or closes) went through every row of pages
  once for each page; with 2,000 pages it took 300 ms, now 7, and turning on
  two pages side by side 96 ms instead of 690.
- **Scrolling long documents**: the page in view, and the pages to draw,
  were found by going through every page at each step of the scroll (3.3 ms
  with 2,000 pages, a fifth of the time of a frame); they are now found by
  bisection on the rows, in 0.01 ms.
- **Opening long documents**: laying out the pages asked MuPDF for the size
  of each page twice, and gave every page the items of its rendering even if
  it was never seen; with 2,000 pages, 31 ms instead of 133, and two pages
  side by side are turned on in 37 ms.
- **Animated zoom**: Zoom in and Zoom out, and Ctrl with the wheel, grow or
  shrink the pages in a few frames instead of jumping (with the wheel, the
  place under the pointer stays under it); the sharp picture comes when the
  zoom stops.
- **Smooth wheel**: a turn of the mouse wheel glides as far as it jumped,
  in a few frames; turns meanwhile add up, and a touchpad, which already
  scrolls by pixels, is left as it is. Both are turned off in Settings >
  Performance > Animate zooming and scrolling with the wheel.
- **Pages shown sooner**: each page drawn for the view was copied and then
  converted to the format of the screen; it is now converted once, as it
  arrives (1.3 ms instead of 3 for a page at 300 %). The thumbnails stay in
  the smaller format.
- **Colours of the interface** (Settings > Appearance): Light and Dark did
  nothing where the desktop's theme keeps its own colours (KDE, through its
  portal); they now set a whole palette of the program's own, the view
  behind the pages follows at once, and the icons take the light or dark
  variant of the desktop's icon theme where it is installed. System gives
  the desktop's colours and icons back.
- **The box of the page** was shown twice, on Page navigation and on the
  toolbar at the top, beside the zoom. It is now only on Page navigation
  (or wherever it is put in Customize the toolbars); the toolbar at the top,
  now Zoom box, has the zoom alone. The details of the page (its size and
  orientation) are the tip of the count, "of 180".
- **Windows**: writing over a file (saving, protecting with passwords,
  combining, PDF/A and PDF/X, form data) waits a moment, up to about two
  seconds, when another process holds the file briefly (the antivirus, or
  the processes that draw the pages reading it), instead of failing at once
  (found by the tests on GitHub, which failed now and then).

## 1.8.7 — 2026-11-21

- **Check the configuration** stopped with an error when an OCR language
  chosen in Settings wasn't installed, the very case it should report; it
  now says which ones are missing (found by the tests on GitHub, whose
  computers have only English).

## 1.8.6 — 2026-11-21

- **Thumbnails**: in the middle of their panel, however wide it is made,
  not on its left side.
- **Page labels**: a page is shown by its label, or by its number if it
  has none, never both: the thumbnails say "1", not "2  1", and the count
  beside the box of the page says only how many pages there are ("5", not
  "2/5"). Foliate's list of pages still shows both, as it is for setting
  the labels.
- **Check the configuration** (Settings > General): a list of what
  py-pdftools needs and whether it has it (Python and its libraries,
  pyHanko, tesseract and the OCR languages chosen, Ghostscript, the space
  of the temporary folder), whether the configuration file can be read and
  written, which of its values aren't valid or known, and shortcuts used
  twice, each with what to do; the report can be copied as text.
- **Graphics card**: Settings > Performance > Draw the pages with the
  graphics card (OpenGL), off at first, from the next start, for smoother
  scrolling and zooming. Where OpenGL doesn't work, the pages are drawn as
  usual, and Check the configuration says why.
- **Impose**: F5 runs Preview again. It was also the key of the bookmarks
  panel, and with two actions on one key Qt ran neither; the bookmarks are
  put away while Impose is on (it shows no pages), and come back after.

## 1.8.5 — 2026-11-21

- **Bookmarks**: their panel is hidden by default. It opens only when asked
  for (View > Panels > Bookmarks, F5), not when a document asks for its
  bookmarks to be shown, nor from the arrangement kept from another
  session; once open, it stays in every mode until it is closed.
- **Tooltips**: those of the toolbars show always, even with Settings >
  Appearance > Show tooltips off, which now governs only the others; the
  items of the toolbars that had none (the count of pages, the fields of
  Impose's toolbar, Undo apply) have one.
- **Quick find**: a box on the toolbar Find (Ctrl+Shift+F puts the cursor
  in it) that finds a text without opening the dialog: Enter goes to the
  next place, from the page shown, Shift+Enter to the previous one, without
  minding capitals or accents; beside it, which place of how many. Esc goes
  back to the pages.
- **Page and zoom**: some room between the box of the page and the count
  of pages, which touched.

## 1.8.4 — 2026-11-21

- **Debian and Ubuntu**: each release now has a `.deb`
  (`py-pdftools_VERSION-1_amd64.deb`), for Debian 12, Ubuntu 22.04 and
  later, installed with `sudo apt install ./py-pdftools_*_amd64.deb`. It
  brings its own Python 3.14, Qt and libraries in `/opt/py-pdftools`, as
  the AppImage does, with the commands `py-pdftools` and
  `py-pdftools-gui`, a menu entry and the manual pages.

## 1.8.3 — 2026-11-21

- **Windows**: Protect with passwords failed, since it writes over the file
  the window had open, which Windows doesn't allow; the document is now
  closed first, and shown again if the protection fails. The processes that
  draw the pages read the document into memory there, so as not to keep its
  file open, which could make saving fail too.
- **Windows**: the CSV of the data of a form, and the table of many forms
  (`py-pdftools form table`), had an empty line after each row.
- The tests on GitHub pass again on Ubuntu and Windows: on Ubuntu they draw
  offscreen, and three tests now follow Windows' rules.

## 1.8.2 — 2026-11-21

- **Toolbars**: a change of their look (text beside or under the icons,
  icons only, text only, the size of the icons), of their lock or of their
  buttons now reaches every window and tab open, not only the one where it
  was made; the others went on showing the toolbars as they were, so the
  change seemed lost. It is also written to the disk at once.

## 1.8.1 — 2026-11-21

- **Recognise the text of these pages (OCR)**, in the right click on the
  thumbnails, works in every mode; it was grey everywhere but in the mode
  OCR.
- **Extract to a new PDF** opens the new file in a new tab beside the
  document.

## 1.8.0 — 2026-11-21

- **Word index** (from pdf-word-finder): Edit > Word index finds the words,
  phrases or regular expressions of a list and gives the pages where each
  appears, by their labels, as lines ready for the index of a book
  (`Sharahzad 3, 5, 23, 34`), or in detail, with how many times and the
  context; it copies the result, or saves it as text or CSV. From the
  command line: `py-pdftools find-words`, with pdf-word-finder's options.
- **The box of the page and the box of the zoom**, once fixed above the
  pages, are on a toolbar of their own, Page and zoom, which can be moved
  anywhere or hidden.
- **The bar of the tabs** is hidden while a window of tabs has only one
  document; Settings > General > Show the bar of the tabs with only one
  document open (off at first) shows it always. With the view split, it is
  always shown.
- **Settings** no longer squeezes its rows in a small window, where the
  texts under a field were covered by the next one: its tabs scroll.
- The field to name **another pdf2iso** is gone from Settings and from the
  settings of redaction: pdf2iso is part of py-pdftools.
- **Previous page and Next page** are only on the toolbar Page navigation,
  no longer also on Navigation.
- The user manuals carry the right version (1.7.0 shipped them saying 1.6).

## 1.7.0 — 2026-11-21

- **Page navigation**, a toolbar at the bottom of the window: First page,
  Previous page, the box of the page shown ("12 of 180", which takes a
  number or a label), Next page, Last page. It is edited like the others in
  Customize the toolbars, where its box can also go on any other toolbar.
- **File > PDF properties**: what the document is (title, author, dates,
  the programs that made it, PDF version, pages and page size, whether it
  is tagged, linearized, signed or encrypted, what it doesn't allow) and the
  fonts it uses, with their type, encoding, embedding and pages; Copy puts
  it all on the clipboard.
- **Sharper text**: after the gamma, an unsharp mask makes the edges of the
  letters steeper, light in Sharper and stronger in Sharpest; it shows most
  when the pages are zoomed out.
- **Fewer bubbles**: the hint of a mode is no longer shown when a mode is
  chosen, and the tooltips are off; Settings > Appearance turns either on
  (F1 still shows the hint).
- The user manuals have an index (about 600 entries in each language).

## 1.6.2 — 2026-11-21

- **The user manual**, in English and Spanish:
  [docs/MANUAL_en.pdf](docs/MANUAL_en.pdf) and
  [docs/MANUAL_es.pdf](docs/MANUAL_es.pdf), made with LaTeX from
  `docs/MANUAL_en.tex` and `docs/MANUAL_es.tex`. It explains how to install
  and start the program, the window, each mode, the work on whole files,
  the settings, the command line and the keys, with 34 pictures of the
  window and its dialogs in each language, which `tools/manual_images.py`
  makes again whenever the window changes.
- The READMEs said that the right click on a toolbar sets how that toolbar
  looks; since 1.6.0 it sets all of them.

## 1.6.1 — 2026-11-21

- **Sharper text on the pages**: Settings > Appearance > Text on the pages
  (As drawn, Sharper, Sharpest). MuPDF draws the edges of letters soft,
  not snapped to the screen's pixels as the desktop's fonts are; Sharper,
  the default, darkens those edges.
- docs/THIRD-PARTY.md (and TERCEROS_es.md): the open-source software
  py-pdftools uses, with its licences.

## 1.6.0 — 2026-11-21

- **A quicker start**: Settings > General > Start with the session puts
  py-pdftools in the desktop's autostart, in the tray and without a
  window (`py-pdftools-gui --background`); in the background a window is
  kept ready for the next document, which opens in about 20 ms instead of
  half a second.
- **Settings > Appearance**: the colours of the interface (system, light,
  dark), its size, its language, the hints of the modes, the toolbars.
- **Settings > Documents**: how a document opened for the first time is
  shown, whether it opens where it was left, asking before web addresses,
  how many recent documents are shown (and clearing them), where the file
  dialogs start.
- Fixed: a toolbar's right click sets all the toolbars, not only that one.
- Fixed: the AppImage opened the window for the newer commands of the
  command line (combine, export, form...).

## 1.5.0 — 2026-11-21

- **The menus in groups**: File, Edit and View have submenus (File > New,
  Export, Import and Security; Edit > Select, Arrange, Remove
  annotations; View > Panels, Annotations, Go to, Zoom, Page layout).
- **Toolbars as in KDE**: Settings > Toolbars (all) and the right click
  on a toolbar (that one): the position of the text (icons only, text
  only, alongside or under the icons), the size of the icons, locking
  them; the Customize dialog sets them for each toolbar too.
- **File > Export** (and `py-pdftools export`): the pages as pictures
  (PNG, JPEG, TIFF; a resolution; grey), the pictures of the document,
  and the text (Markdown, HTML, plain).
- **Splitting** at the bookmarks of a level (parts named after them) and
  by size (no part bigger than asked); one file per page named after its
  label (`py-pdftools pages --split-bookmarks`, `--split-size`).
- **The PDF version**: File > Save a copy > With another PDF version, and
  `py-pdftools pdf-version`; what the document uses that the version
  chosen doesn't have is named.
- **Page labels under the thumbnails, in every mode**: a label changed
  outside Foliate (Labels > Number this page, on the thumbnails' menu)
  was not seen, since only Foliate showed labels; the status bar now says
  which pages took which labels, or that they had them already.
- **Ctrl+A in the thumbnails** selects every page (elsewhere it still
  selects the annotations of the page); their menu has Select all the
  pages.
- Page labels are read through pikepdf when combining, exporting and
  splitting: the PyMuPDF of some distributions (Fedora's) misread some of
  them ("ageLabel2" for 2).
- py-pdfocr is named among the programs py-pdftools comes from.

## 1.4.0 — 2026-11-20

- **File > Save a copy > Smaller** (and `py-pdftools reduce`): a copy that
  takes less space, at one of four levels: pictures drawn again at 220,
  150 or 96 dpi (only those shown above it), fonts reduced to the
  characters used, what nothing uses taken out; the dialog shows where
  the bytes go.
- **Links made and changed**: the tool Link (J, in Annotate) draws a link
  to a page, an address or another PDF; a click on a link changes or
  removes it; Edit > Links makes links of the addresses in the text, or
  removes them all. Links of turned pages are now found where they are.
- **Forms filled in**: the panel Form (F6) has an editor for each field,
  and clicks on the page set check boxes and radio buttons. Numbers,
  percentages, dates and phone numbers are checked and shown in their
  format, and sums worked out, as the form's scripts ask, without
  JavaScript.
- **Form data**: exported and imported as JSON, CSV, XFDF or FDF; a copy
  with the form flattened; `py-pdftools form show | fill | table |
  flatten`.
- **Digital signatures** (File > Digital signatures; with pyHanko, an
  optional dependency): a self-signed digital ID made; the document signed
  visibly or not, certified, its fields locked, with a timestamp from a
  server if one is given; signatures checked (intact, valid, trusted, what
  changed after them), their signers trusted, the version each signed
  opened.

## 1.3.0 — 2026-11-20

- **File > Combine files** (and `py-pdftools combine`): one PDF made of
  several, or of some of their pages in an order, one file after another,
  with their links, annotations and form fields; their bookmarks under
  one for each file, as they are, or none; their page labels kept if
  wished. Protected files are read with their passwords.
- **File > New PDF from pictures** (and `py-pdftools from-images`): a PDF
  of photographs or scans, a page for each picture (each frame of a
  TIFF), as big as it is or on paper with a margin; photographs are
  turned as the camera says; it can then be opened in the mode OCR.

## 1.2.0 — 2026-11-20

- **Redact > Find text only covered**: text that is still in the file
  under a box, a picture or an annotation drawn over it, so that it looks
  redacted but can be copied or found. It is shown with what covers it,
  and boxes can be put over it, so that the redacted copy takes it out.
- **Hidden layers are removed** when sanitizing (a kind of its own in
  Remove hidden information) and when the redacted copy is cleaned: what
  the layers switched off hold is taken out of the pages, and the layers
  themselves, with their names.
- **File > Protect with passwords**: a password to open the document
  (AES-256), one for its permissions (printing, copying, comments and
  forms, pages, other changes), or both. A file protected only in its
  permissions now stays so when its annotations are saved, and in
  redacted and sanitized copies.
- The toolbars can be changed (Settings > Customize the toolbars, or a
  right click on a toolbar): their buttons and order, from every action
  of the menus, the tools and the modes; toolbars of one's own can be
  added and removed.
- Icons on the buttons of the modes, of the OCR toolbar and of the
  Impose panel.

## 1.1.0 — 2026-11-20

Moving through a document, in every mode. This release also brings the
changes of 1.0.0, which was not tagged or published by itself.

- **Bookmarks** (View > Bookmarks, F5): a panel with the document's
  bookmarks as a tree, with a filter. Its right-click menu adds a
  bookmark at the place shown, renames, moves, indents, styles or
  deletes them, or makes them from the headings of the text.
- **Links** are followed with a click (Ctrl+click with Select text): to
  their place in the document, to another PDF, or, after asking, to a
  web or mail address. Addresses written in the text are links too.
  Links that start a program are not followed.
- **Previous view and Next view** (Alt+Left, Alt+Right) go through the
  places jumped to by links, bookmarks, the page box and Find.
- **Opening at a place**: `book.pdf#page=12` or `#nameddest=intro`;
  each file opens where it was left, or as it asks; and, if the settings
  say so, the documents open at the end of the last session open again.
- **Two pages side by side** (Ctrl+Shift+2), with the first page alone as
  a cover if wished.
- More zooms: fit the height (Ctrl+8), fit the inked area (Ctrl+7),
  actual size (Ctrl+Shift+0), a percentage typed in the zoom box, and
  the tool Zoom to area (Z).
- Rotating the view (Ctrl+], Ctrl+[) without changing the file.
- Reading colours (View > Reading colours): white, yellow or green on
  black, light on dark grey, or colours of one's own.
- Full screen as a presentation (F11); pages with a display time turn by
  themselves, and those with a transition fade in.
- **Tabs and a split view**: File > Open in a new tab (Ctrl+T), or every
  document so; View > Split the view (`Ctrl+\`) shows two documents side
  by side.
- A document changed on disk by another program is opened again at the
  same place (after asking, if something is unsaved).
- The details of a page (label, size, paper, orientation, annotations)
  on hover over its thumbnail.
- Space held turns any tool into Hand; the middle button scrolls by
  itself; the gaps between the pages can be hidden.
- 466 tests.

## 1.0.0 — 2026-11-20

Not tagged; its changes were published with 1.1.0.

- **The mode OCR**, between Read and Redact (Ctrl+2): its panel chooses
  the pages, orders the languages, turns pages lying sideways, and sets
  below which confidence a word is doubtful.
- **Select text** (X), beside Hand in every mode: drag over text, across
  pages too; Alt+drag selects a column; double click a word, triple
  click a line. Ctrl+C copies it, and a right click highlights,
  underlines, strikes out, marks for redaction or finds it.
- **Running in the background** (Settings > General): when the last
  window is closed, the program goes on running with an icon in the
  tray, and `py-pdftools-gui` started again hands it its files, which it
  opens at once. File > Quit ends it.
- Settings > Performance: a memory profile (low, normal, high, or all
  pages) sets how many pages, tiles and thumbnails are kept and how many
  processes draw them; selections with transparency or as outlines; the
  antialiasing of text and of graphics.
- The menu of pages is in groups, with a heading that names the pages
  chosen, and submenus.

## 0.5.0 — 2026-11-20

- **Several thumbnails at once**: Ctrl+click and Shift+click choose
  pages without moving to them, in any mode, and a right click gives
  the menu of pages for them. They are Foliate's chosen pages too.
- The page box shows the label of the page shown and takes a label,
  (n) for the n-th page, or a number.
- A manager of OCR languages, in the settings, lists every language
  tesseract can read, and downloads, updates or removes its more
  accurate models.

## 0.4.0 — 2026-11-20

- **OCR**: Edit > Recognise text (OCR) (Ctrl+Shift+O) reads scanned
  pages with the tesseract program and writes their text, invisible,
  into the document, as one change that can be undone. Pages lying
  sideways can be turned first, and the doubtful words are shown beside
  their pictures to be corrected.
- The searchable copy uses the same engine, several pages at once.
- `py-pdftools ocr` does the same from the command line (`--lang`,
  `--pages`, `--rotate`, `--report`, `--languages`, `--download`).
- The hint of each mode shows over the pages for a few seconds, and
  again with Help > Tips for this mode (F1).
- The tests draw their windows on an X server of their own (Xvfb) when
  it is installed, not on the user's screen.

## 0.3.0 — 2026-11-20

Large documents.

- **Working copies on disk**, in `~/.cache/py-pdftools/work`, not in the
  temporary folder, which on Fedora is in memory: each change of a large
  document took as much RAM as the document. The history keeps the last
  ten changes of the document.
- A page that takes longer than 20 seconds to draw, or makes its process
  die, is shown grey with the reason and not tried again.
- Only the thumbnails near those in view are made, and at most 400 are
  kept: those of 200 scanned pages take 0.9 s instead of 30 s.
- **Deep zoom in tiles**: a large page is drawn whole at a lower
  resolution, and the part in view in sharp tiles of 1,024 pixels.
- 416 tests.

## 0.2.0 — 2026-11-19

- **Five modes**, in the order of the work on a document: Read, Redact,
  Annotate, Foliate (the former mode Pages) and Impose (Ctrl+1 to
  Ctrl+5). Each mode keeps its own arrangement of the window, also in
  the next session.
- **pdf2iso is included** (`core/pdf2iso.py`, from pdf2iso 2.1): PDF/A
  and PDF/X copies need only Ghostscript. The command line has
  `py-pdftools pdf2iso`.
- Fixes: the parts made by `pages --split-every` and `--split-at` keep
  the protection of the original and follow `--conform`; a comment
  longer than a page no longer breaks the summary of the comments; Save
  no longer fails with a TypeError after undoing a change of the
  document itself; changing the language of the interface keeps the
  unsaved changes; a page drawn without its annotations no longer loses
  them the next time.
- The code that the four programs had in several copies is now in one
  place each (`core/pdfdoc.py`, `core/matrix.py` and others). About
  1,900 comments in the code.
- The tests pass on Linux and Windows (407 tests). Manual pages.

## 0.1.0 — 2026-11-19

- First version: py-annotate, py-redact, py-foliation and py-imposition
  in one window and one command line, in English and Spanish.
- The window has four modes: Annotate, Redact (from py-redact), Pages
  (from py-foliation: page labels, headers and footers, watermarks, the
  order of the pages) and Impose (from py-imposition). Changes of the
  document itself are made on a working copy and undone with the
  annotations, in one history.
- The command line, `py-pdftools`, has `labels`, `view`,
  `header-footer`, `watermark`, `pages` and `impose`.
- Packages: an AppImage, a signed RPM for Fedora (also in Copr,
  `nivaca/py-pdftools`), and installers for Linux, macOS and Windows.
