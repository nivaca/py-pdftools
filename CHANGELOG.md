# Changelog

All notable changes to py-pdftools. The releases, with the AppImage, the
RPM, the wheel and the source, are on
[Codeberg](https://codeberg.org/nivaca/py-pdftools/releases) and
[GitHub](https://github.com/nivaca/py-pdftools/releases).

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
