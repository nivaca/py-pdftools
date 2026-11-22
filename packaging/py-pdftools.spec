# py-pdftools, which edits PDF documents: annotates, redacts, labels, stamps, arranges and imposes them.
# Copyright (C) 2026 Nicolas Vaughan <nicolasvaughan@proton.me>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed WITHOUT ANY
# WARRANTY; see the LICENSE file, or <https://www.gnu.org/licenses/>.
#
# Build with packaging/build-rpm.sh, which makes the source tarball.

Name:           py-pdftools
Version:        1.8.13
Release:        1%{?dist}
Summary:        Edit PDF documents: annotate, redact, label, stamp, arrange and impose their pages

License:        GPL-3.0-or-later
URL:            https://github.com/nivaca/py-pdftools
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
BuildRequires:  /usr/bin/appstreamcli
# For %%check: the tests run the window (headless).
BuildRequires:  python3-pytest
BuildRequires:  python3-pyside6
# (the tests of imposition check each result with qpdf, and some tests read pages with pdftotext)
BuildRequires:  qpdf
BuildRequires:  poppler-utils
# (the tests of OCR read scans with it)
BuildRequires:  tesseract
BuildRequires:  tesseract-langpack-eng

# PyMuPDF, pikepdf and reportlab come from the package's metadata (pyproject.toml).
# The window: Fedora's PySide6 (pyproject.toml names the PyPI wheel, pyside6-essentials).
Requires:       python3-pyside6
# (for copies as PDF/A and PDF/X: Ghostscript makes them, for the pdf2iso py-pdftools includes)
Recommends:     ghostscript
Requires:       hicolor-icon-theme
# (for OCR: the tesseract program, and its English; the other languages as needed)
Recommends:     tesseract
Recommends:     tesseract-langpack-eng

%description
py-pdftools edits PDF documents. It brings together, in one window and one
command line, five programs: py-annotate (highlights, notes, text boxes,
shapes, drawings and stamps, written as ordinary PDF annotations), py-redact
(boxes over what is to be removed, and a redacted copy in which it is removed
for good, and checked), py-foliation (page labels, headers and footers,
watermarks, the view when the document is opened, and the order of the
pages), py-imposition (booklets, n-up, step and repeat and the rest of
imposition for printing, with sequences and hot folders) and py-pdfocr (the
text of scanned pages, read by tesseract and written under them).

The window and the command line are in English or Spanish.

%prep
%autosetup -n %{name}-%{version}
# (Fedora's PySide6 is python3-pyside6, which doesn't provide pyside6-essentials)
sed -i '/"pyside6-essentials/d' pyproject.toml

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l py_pdftools
desktop-file-install --dir=%{buildroot}%{_datadir}/applications packaging/py-pdftools.desktop
install -d %{buildroot}%{_datadir}/icons
cp -pr src/py_pdftools/icons/linux/hicolor %{buildroot}%{_datadir}/icons/
install -Dpm 0644 packaging/io.github.nivaca.py-pdftools.metainfo.xml \
    %{buildroot}%{_metainfodir}/io.github.nivaca.py-pdftools.metainfo.xml
install -Dpm 0644 packaging/man/py-pdftools.1 %{buildroot}%{_mandir}/man1/py-pdftools.1
install -Dpm 0644 packaging/man/es/py-pdftools.1 %{buildroot}%{_mandir}/es/man1/py-pdftools.1

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/py-pdftools.desktop
appstreamcli validate --no-net %{buildroot}%{_metainfodir}/io.github.nivaca.py-pdftools.metainfo.xml
%pyproject_check_import -e 'py_pdftools.gui*'
# The whole test suite, on the installed package, with no settings of the
# builder's and the window drawn offscreen.
export HOME="$PWD/check-home" PY_PDFTOOLS_CONFIG="$PWD/check-home/config" QT_QPA_PLATFORM=offscreen
%pytest -q tests
%{py3_test_envvars} %{buildroot}%{_bindir}/py-pdftools --version | grep -q '%{version}'
%{py3_test_envvars} %{buildroot}%{_bindir}/py-pdftools-gui --version | grep -q '%{version}'

%files -f %{pyproject_files}
%doc README.md README_es.md docs/DESCRIPTION.md docs/DESCRIPCIÓN_es.md
%{_bindir}/py-pdftools
%{_bindir}/py-pdftools-gui
%{_datadir}/applications/py-pdftools.desktop
%{_datadir}/icons/hicolor/*/apps/py-pdftools.*
%{_metainfodir}/io.github.nivaca.py-pdftools.metainfo.xml
%{_mandir}/man1/py-pdftools.1*
%lang(es) %{_mandir}/es/man1/py-pdftools.1*

%changelog
* Sun Nov 22 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.13-1
- The toolbars at first in one row, with small icons; toolbars dragged out
  of a window in tabs hide with their tab

* Sun Nov 22 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.12-1
- A quicker start; documents with many links open faster; Help > Check for
  a new version; the Windows installer takes --uninstall and the like

* Sun Nov 22 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.11-1
- Word index also on the toolbar Find, with an icon of its own

* Sun Nov 22 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.10-1
- pyHanko installed with pip --user is found by the RPM; Check the configuration
  in Help and on the settings' buttons; colours shown as colours; animated zoom
  keeps its point

* Sun Nov 22 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.9-1
- Left and Right turn the pages; icon themes found by their exact name on
  Windows and macOS

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.8-1
- Light and dark themes that work under KDE; faster long documents; animated
  zoom and smooth wheel; one page box; Windows rename retries

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.7-1
- Check the configuration reports OCR languages not installed instead of failing

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.6-1
- Centered thumbnails; labels or numbers, not both; configuration check; OpenGL
  drawing option; F5 in Impose

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.5-1
- Bookmarks hidden until asked for; tooltips always on the toolbars; quick find
  box; room before the page count

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.4-1
- A Debian package for Debian 12, Ubuntu 22.04 and later, made from the AppImage

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.3-1
- Version 1.8.3: on Windows, protecting a document open and the CSVs of forms;
  the tests pass again on GitHub.

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.2-1
- Version 1.8.2: a change of the toolbars reaches every window open.

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.1-1
- Version 1.8.1: OCR from the thumbnails in every mode; extracted pages open in
  a new tab.

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.8.0-1
- Version 1.8.0: Word index (from pdf-word-finder) and the command find-words;
  the toolbar Page and zoom; a setting for the bar of the tabs; the Settings
  tabs scroll; no field for another pdf2iso; Previous and Next page only on Page
  navigation.

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.7.0-1
- Version 1.7.0: the toolbar Page navigation; File > PDF properties; sharper
  text (an unsharp mask); hints and tooltips off at first; an index in the user
  manuals.

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.6.2-1
- Version 1.6.2: the user manual, in English and Spanish, with pictures
  (docs/MANUAL_en.pdf, docs/MANUAL_es.pdf).

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.6.1-1
- Version 1.6.1: sharper text on the pages (a setting); the list of the
  open-source software used

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.6.0-1
- Version 1.6.0: starting with the session, in the tray; a window kept ready;
  Settings > Appearance and Documents; fixes

* Sat Nov 21 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.5.0-1
- Version 1.5.0: menus in groups; toolbars set up as in KDE; exports of pages,
  pictures and text; splitting at bookmarks and by size; the PDF version

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.4.0-1
- Version 1.4.0: smaller copies; links made and changed; forms filled in, with
  their formats and sums, and their data; digital signatures (with pyHanko, when
  it is installed)

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.3.0-1
- Version 1.3.0: combining files; new PDFs from pictures

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.2.0-1
- Version 1.2.0: security (text only covered, hidden layers, passwords); icons
  on the buttons of the modes; editable toolbars

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.1.0-1
- Version 1.1.0: moving through a document (bookmarks, links, history, views,
  tabs, reloading)

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.0.0-1
- The mode OCR and its languages; the tool Select text; running in the
  background; Settings > Performance; the menu of pages in groups

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 0.5.0-1
- Several thumbnails chosen at once, with the menu of pages in any mode; the
  page box shows page labels; a manager of OCR languages

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 0.4.0-1
- OCR with the tesseract program, into the document; the hints of the modes over
  the pages

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 0.3.0-1
- Large documents: several rendering processes, a time limit per page,
  thumbnails only near view, deep zoom in tiles, working copies on disk

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 0.2.0-1
- Modes Read, Redact, Annotate, Foliate and Impose, each with its own
  arrangement of the window; pdf2iso included (only Ghostscript is needed for
  PDF/A and PDF/X); fixes, and the duplicated code joined

* Fri Nov 20 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 0.1.0-2
- The tests need qpdf and pdftotext to build (Copr)

* Thu Nov 19 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 0.1.0-1
- First package: py-annotate, py-redact, py-foliation and py-imposition in one
  window, with the modes Annotate, Redact, Pages and Impose, and one command
  line (py-pdftools)
