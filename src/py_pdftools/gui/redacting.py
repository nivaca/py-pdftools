"""The mode Redact of the window (from py-redact): boxes over what is to be
removed, and the redacted copy, in which it is removed for good.

A box is an annotation of kind ``redact`` (the PDF's redaction mark, see
annotate/annots.py): it is drawn, selected, moved, undone and saved with the
document like any other annotation, but only in this mode. Nothing is removed
until the redacted copy is written (Redact ▸ Save the redacted copy): a new
file, never the one open, made from the document as it was last saved, with
the boxes applied by py-redact's engine (redact/redact.py) in a process of
its own, then checked (what can still be read under the boxes, the bookmarks
that give it away). A box may also go on other pages (its *pages*): it is
then shown on each of them, at the same place.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt, QSize
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QDialog, QDockWidget, QFileDialog, QFormLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QToolBar,
    QToolButton, QVBoxLayout, QWidget,
)

from ..annotate.annots import Annotation, Rect, nearest_word, text_rects
from ..core import conform
from ..core.interface import ntr, tr
from ..core.pagesel import check
from ..redact import codes, hidden, metadata
from ..redact import settings as rsettings
from ..redact.redact import (
    Match, RedactError, bookmark_leaks, box_of, check_redacted, find_text, image_at, open_pdf, remove_bookmarks,
    sanitize, under, words, write_redacted,
)
from .modes import Mode
from .paint import set_redaction_look
from .redact import background
from .redact.background import Cancelled
from .redact.codes_dialog import CodesDialog
from .redact.common import REPEATS, SWATCHES, color_name, mm, swatch
from .redact.find import FindDialog
from .redact.hidden_dialog import HiddenDialog
from .redact.meta_dialog import MetadataDialog
from .redact.prefs import SettingsDialog
from .redact.props import PropertiesDialog

KIND = "redact"
PAD = 1.0  # points: a box over text is this much larger than its words, on each side (as in py-redact)


class RedactMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    # ----------------------------------------------------------------- construction

    def _build_redact(self) -> Mode:
        from .window import icon

        self.redact_prefs = rsettings.load()
        self.redact_texts: dict = {}  # page -> its text as the search reads it (see redact.find_all), kept
        self.redact_finder: FindDialog | None = None
        self.redact_meta: metadata.Metadata | None = None  # the metadata the copy gets (None: the document's)
        self._redact_rows: list[int] = []  # row of the table of boxes -> index of its box in the annotations
        self._redaction_look()

        # the tool: added to those of the window (it is chosen with set_tool, as they are)
        act = QAction(icon("edit-select-text"), tr("Redact (text or area)"), self, checkable=True)
        act.setShortcut(QKeySequence("R"))
        act.setToolTip(tr("Over text, dragging selects it and a box is made over each of its lines; elsewhere it "
                          "draws a box (Ctrl+drag always draws one). Double-click a word or an image to mark only "
                          "that"))
        act.setStatusTip(act.toolTip())
        act.triggered.connect(lambda: self.set_tool(KIND))
        self.tool_actions["select"].actionGroup().addAction(act)
        self.tool_actions[KIND] = act

        m = QMenu(tr("&Redact"), self)
        m.setToolTipsVisible(True)
        self.m_redact = m
        m.addAction(act)
        self.a_redact_find = self._action(m, tr("Find and redact…"), lambda: self.redact_find_dialog(),
                                          tip=tr("Find a text, or a regular expression, on some or all pages, and "
                                                 "put boxes over it"))
        self.a_redact_result = QAction(icon("view-preview"), tr("Show the result"), self, checkable=True)
        self.a_redact_result.setShortcut(QKeySequence("Ctrl+R"))
        self.a_redact_result.setToolTip(tr("The boxes as they will look once applied: opaque, with their text "
                                           "(they can still be changed)"))
        self.a_redact_result.toggled.connect(lambda _: self._redaction_look())
        m.addAction(self.a_redact_result)
        m.addSeparator()
        self.a_redact_props = self._action(m, tr("Properties of the boxes…"), self.redact_properties_dialog)
        self.a_redact_pages = self._action(m, tr("Pages of the boxes…"), self.ask_redact_pages,
                                           tip=tr("The pages the selected boxes go on, besides their own"))
        self._action(m, tr("Redaction codes…"), lambda: CodesDialog(self).exec())
        m.addSeparator()
        self.a_redact_save = self._action(m, tr("Save the redacted copy…"), lambda: self.save_redacted_dialog(),
                                          "Ctrl+Shift+R",
                                          tr("Write a copy of the document with what is under the boxes removed, "
                                             "as a plain PDF (or PDF/A, PDF/X: Save the redacted copy as)"))
        self.a_redact_save.setIcon(icon("document-save-as"))
        self.m_redact_output = m.addMenu(tr("Save the redacted copy as"))
        self.m_redact_output.setToolTipsVisible(True)
        self.redact_output_actions: dict[str, QAction] = {}
        for value, name in conform.STANDARDS:
            out = QAction(tr(name) + "…", self)
            out.triggered.connect(lambda _=False, v=value: self.save_redacted_dialog(v))
            self.m_redact_output.addAction(out)
            self.redact_output_actions[value] = out
        self.a_redact_clean = QAction(tr("Also remove metadata, hidden text, attachments and scripts"), self,
                                      checkable=True, checked=self.redact_prefs.clean)
        self.a_redact_clean.setToolTip(tr("Remove as well what the document holds besides its pages: its title, "
                                          "author and other metadata, text that isn't shown, attached files, "
                                          "JavaScript and links"))
        self.a_redact_clean.toggled.connect(
            lambda on: self.set_redact_prefs(dataclasses.replace(self.redact_prefs, clean=on)))
        m.addAction(self.a_redact_clean)
        self.a_redact_meta = self._action(m, tr("Metadata…"), self.redact_metadata_dialog, "Ctrl+Shift+M",
                                          tr("See and change the title, author, dates and the rest of the metadata "
                                             "the redacted copy will have, or remove them"))
        m.addSeparator()
        self.a_redact_hidden = self._action(m, tr("Remove hidden information…"), self.redact_hidden_dialog,
                                            tip=tr("See what the document holds besides its pages (metadata, "
                                                   "attachments, bookmarks, comments, hidden text…), and save a "
                                                   "copy without what you choose"))
        self.a_redact_sanitize = self._action(m, tr("Sanitize the document…"), lambda: self.sanitize_dialog(),
                                              tip=tr("Save a copy without metadata, hidden text, attachments, "
                                                     "scripts and links, and with nothing else changed (the boxes "
                                                     "aren't applied)"))
        m.addSeparator()
        self._action(m, tr("Settings of redaction…"), self.redact_settings_dialog)
        self.menuBar().insertMenu(self.m_layers.menuAction(), m)

        bar = QToolBar(tr("Redaction"))
        bar.setObjectName("redaction")
        bar.setIconSize(QSize(22, 22))
        for a in (self.tool_actions["select"], self.tool_actions["hand"], act, None, self.a_redact_result, None,
                  self.a_redact_save):
            if a is None:
                bar.addSeparator()
            else:
                bar.addAction(a)
        self.addToolBar(bar)
        self.redact_bar = bar

        dock = QDockWidget(tr("Boxes"), self)
        dock.setObjectName("boxes")
        dock.setWidget(self._redact_panel())
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.redact_dock = dock
        self.hints[KIND] = tr("Drag over text to mark it, or elsewhere to draw a box (Ctrl+drag: always a box); "
                              "double-click a word or an image to mark it. Drag a box to move or resize it; "
                              "double-click it for its properties, right-click it for more.")
        return Mode(KIND, lambda a: a.kind == KIND, bars=[bar], docks=[dock], menus=[m.menuAction()],
                    actions=[act, self.a_redact_result], entered=self._redact_entered, left=self._redact_left)

    def _redact_panel(self) -> QWidget:
        """The list of the boxes, and the colour and pages of those selected (or of new ones)."""
        self.redact_table = table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels([tr("Page"), tr("Goes on"), tr("Colour"), tr("Size (mm)")])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.itemSelectionChanged.connect(self._redact_table_selected)
        table.doubleClicked.connect(lambda _: self.redact_properties_dialog())
        self.redact_title = QLabel()
        self.redact_color = button = QToolButton()
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        menu = QMenu(button)
        for value, name in SWATCHES:
            menu.addAction(swatch(value), tr(name), lambda v=value: self.set_redact_color(v))
        menu.addSeparator()
        menu.addAction(tr("Other colour…"), self.choose_redact_color)
        button.setMenu(menu)
        self.redact_repeat = QComboBox()
        for value, name in REPEATS:
            self.redact_repeat.addItem(tr(name), value)
        self.redact_repeat.activated.connect(self._redact_repeat_chosen)
        self.redact_pages = QLineEdit()
        self.redact_pages.setPlaceholderText(tr("1-5, 8, 10-"))
        self.redact_pages.setToolTip(tr("Pages and ranges, separated by commas: 3, 5-9, 12- (to the end), LAST, "
                                        "LAST-1"))
        self.redact_pages.editingFinished.connect(self._redact_pages_typed)
        self.redact_delete = QPushButton(tr("Delete"))
        self.redact_delete.clicked.connect(self.delete_selected)
        form = QFormLayout()
        form.addRow(tr("Colour:"), button)
        form.addRow(tr("Pages:"), self.redact_repeat)
        form.addRow("", self.redact_pages)
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(table, 1)
        lay.addWidget(self.redact_title)
        lay.addLayout(form)
        lay.addWidget(self.redact_delete, 0, Qt.AlignmentFlag.AlignRight)
        panel.setMinimumWidth(280)
        return panel

    def _redact_entered(self):
        self.set_tool(KIND)
        self.a_find.setText(tr("Find and redact…"))
        self._redaction_look()

    def _redact_left(self):
        self.a_find.setText(tr("Find and highlight…"))
        if self.a_redact_result.isChecked():
            self.a_redact_result.setChecked(False)

    # ----------------------------------------------------------------- settings

    def _redaction_look(self):
        p = self.redact_prefs
        set_redaction_look(p.mark_outline, p.mark_opacity,
                           hasattr(self, "a_redact_result") and self.a_redact_result.isChecked())
        if hasattr(self, "canvas"):
            self.canvas.viewport().update()
            for item in self.canvas.items_:
                item.update()

    def set_redact_prefs(self, prefs: rsettings.Settings):
        """Use PREFS for redacting, and keep them in the configuration file."""
        self.redact_prefs = prefs
        try:
            rsettings.save(prefs)
        except (OSError, ValueError) as e:
            self.status(tr("Could not keep the setting: {error}", error=e), error=True)
        self.a_redact_clean.blockSignals(True)
        self.a_redact_clean.setChecked(prefs.clean)
        self.a_redact_clean.blockSignals(False)
        self._redaction_look()
        self._show_redact_panel()

    def redact_settings_dialog(self):
        dialog = SettingsDialog(self.redact_prefs, swatch, color_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_redact_prefs(dialog.settings())

    # ----------------------------------------------------------------- the boxes

    def new_box(self, page: int, rect: Rect) -> Annotation:
        """A box with the look of new boxes (Settings of redaction, or Save as default)."""
        p = self.redact_prefs
        return Annotation(KIND, page, rect, color=p.text_color, fill=p.color, overlay=p.text,
                          overlay_repeat=p.repeat_text, font_size=p.font_size, align=p.align,
                          author=self.prefs.author, width=0)

    def boxes(self) -> list[int]:
        """The indices of the boxes, among the annotations."""
        return [i for i, a in enumerate(self.annotations) if a.kind == KIND]

    def box_pages(self, a: Annotation) -> list[int]:
        """The pages (0-based) the box A goes on."""
        return box_of(a).pages(self.count)

    def canvas_items(self, shown: list[int]) -> list[tuple[int, Annotation]]:
        """What the canvas shows of the annotations SHOWN: each one, and a box again on each of its pages."""
        items = []
        for i in shown:
            a = self.annotations[i]
            items.append((i, a))
            if a.kind == KIND and a.repeat.strip():
                items += [(i, dataclasses.replace(a, page=p)) for p in self.box_pages(a) if p != a.page]
        return items

    def add_redact_text(self, page: int, rects: list[Rect]):
        """A box over each line of the text selected (RECTS: those of its words, which the boxes cover with
        PAD to spare)."""
        new = [self.new_box(page, (round(x0 - PAD, 2), round(y0 - PAD, 2), round(x1 + PAD, 2), round(y1 + PAD, 2)))
               for x0, y0, x1, y1 in rects]
        self.change(self.annotations + new, list(range(len(self.annotations), len(self.annotations) + len(new))))
        self.status(ntr("{count} line of text marked", "{count} lines of text marked", len(new)))

    def redact_double_clicked(self, index: int, page: int, point: tuple):
        """A box: its properties. A word: a box over it. An image: a box over all of it."""
        if index >= 0:
            self.redact_properties_dialog()
            return
        found = self.canvas.page_words(page)
        i = nearest_word(found, *point)
        if i is not None:
            x0, y0, x1, y1 = found[i][0]
            if x0 - 2 <= point[0] <= x1 + 2 and y0 - 2 <= point[1] <= y1 + 2:
                self.add_redact_text(page, text_rects(found, i, i))
                return
        image = image_at(self.doc[page], *point) if self.doc is not None else None
        if image is not None:
            self.add(self.new_box(page, image))
            self.status(tr("The image is marked"))

    def _change_boxes(self, **changes):
        """CHANGES given to the boxes selected."""
        annotations = list(self.annotations)
        for i in self.selected:
            if annotations[i].kind == KIND:
                annotations[i] = dataclasses.replace(annotations[i], **changes)
        self.change(annotations, self.selected)

    def redact_properties_dialog(self):
        chosen = [i for i in self.selected if self.annotations[i].kind == KIND]
        if not chosen:
            return
        dialog = PropertiesDialog([box_of(self.annotations[i]) for i in chosen], swatch, color_name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        annotations = list(self.annotations)
        for i in chosen:
            box = dialog.apply(box_of(annotations[i]))
            annotations[i] = dataclasses.replace(
                annotations[i], fill=box.color, overlay=box.text, color=box.text_color, font_size=box.font_size,
                align=box.align, overlay_repeat=box.repeat_text, contents=box.note, locked=box.locked,
                repeat=box.repeat)
        self.change(annotations, self.selected)
        if dialog.as_default.isChecked():
            first = box_of(annotations[chosen[0]])
            self.set_redact_prefs(dataclasses.replace(
                self.redact_prefs, **{k: getattr(first, k) for k in rsettings.APPEARANCE}))
            self.status(tr("New boxes will look like these"))

    def set_redact_color(self, color: str):
        """The colour of the boxes selected; with none selected, of new boxes."""
        if any(self.annotations[i].kind == KIND for i in self.selected):
            self._change_boxes(fill=color)
        else:
            self.set_redact_prefs(dataclasses.replace(self.redact_prefs, color=color))
            self.status(tr("New boxes will be {color}", color=color_name(color)))

    def choose_redact_color(self):
        chosen = [self.annotations[i] for i in self.selected if self.annotations[i].kind == KIND]
        current = chosen[0].fill if chosen else self.redact_prefs.color
        color = QColorDialog.getColor(QColor(current or "#000000"), self, tr("The colour of the boxes"))
        if color.isValid():
            self.set_redact_color(color.name())

    def set_redact_repeat(self, repeat: str):
        error = check(repeat) if repeat.strip() else ""
        if error:
            self.status(error, error=True)
            self._show_redact_panel()
            return
        if self.selected:
            self._change_boxes(repeat=repeat)
        else:
            self._show_redact_panel()

    def ask_redact_pages(self):
        chosen = [self.annotations[i] for i in self.selected if self.annotations[i].kind == KIND]
        if not chosen:
            return
        current = chosen[0].repeat
        if current.lower() in ("", "all", "odd", "even"):
            current = f"{chosen[0].page + 1}-"
        while True:
            text, ok = QInputDialog.getText(self, tr("Pages"),
                                            tr("Pages and ranges, separated by commas: 3, 5-9, 12- (to the end), "
                                               "LAST, LAST-1"), QLineEdit.EchoMode.Normal, current)
            if not ok or not text.strip():
                return
            error = check(text)
            if not error:
                self.set_redact_repeat(text.strip())
                return
            self.warn(tr("Pages"), error)
            current = text

    def _redact_repeat_chosen(self, row: int):
        value = self.redact_repeat.itemData(row)
        if value != "*":
            self.set_redact_repeat(value)
            return
        chosen = [self.annotations[i] for i in self.selected if self.annotations[i].kind == KIND]
        if not chosen:
            return
        current = chosen[0].repeat
        if current.lower() in ("", "all", "odd", "even"):
            current = f"{self.page + 1}-"
        self.redact_pages.setText(current)
        self.set_redact_repeat(current)
        self.redact_pages.setFocus()
        self.redact_pages.selectAll()

    def _redact_pages_typed(self):
        if self.redact_repeat.currentData() == "*" and self.redact_pages.isEnabled():
            text = self.redact_pages.text().strip()
            if text:
                self.set_redact_repeat(text)

    def toggle_code(self, code: str):
        """Add CODE to the text of the boxes selected, or take it out if they all have it."""
        chosen = [i for i in self.selected if self.annotations[i].kind == KIND]
        have = all(code in codes.codes_of(self.annotations[i].overlay) for i in chosen)
        annotations = list(self.annotations)
        for i in chosen:
            current = codes.codes_of(annotations[i].overlay)
            if have:
                current.remove(code)
            elif code not in current:
                current.append(code)
            annotations[i] = dataclasses.replace(annotations[i], overlay=codes.SEPARATOR.join(current))
        self.change(annotations, self.selected)

    # ----------------------------------------------------------------- find and redact

    def _redact_find(self, text: str, pages: list[int] | None) -> list[Match]:
        if self.doc is None:
            return []
        return find_text(self.doc, text, pages, whole_words=True, texts=self.redact_texts)

    def redact_find_dialog(self, text: str = ""):
        if self.doc is None:
            return
        if self.redact_finder is None:
            self.redact_finder = FindDialog(self)
            self.redact_finder.show_match.connect(self.show_redact_match)
            self.redact_finder.mark.connect(self.mark_redact_matches)
        self.redact_finder.start(text)

    def show_redact_match(self, match: Match):
        self.show_page(match.page)
        for rect in match.rects:
            self.canvas.flash(match.page, rect)

    def mark_redact_matches(self, matches: list[Match]):
        """A box over each line of each place in MATCHES (not twice over the same place)."""
        have = {(a.page, a.rect) for a in self.annotations if a.kind == KIND}
        new = []
        for m in matches:
            for r in m.rects:
                if (m.page, r) not in have:
                    have.add((m.page, r))
                    new.append(self.new_box(m.page, r))
        if not new:
            self.status(tr("Those places are marked already") if matches else tr("Not found"))
            return
        pages = len({b.page for b in new})
        self.change(self.annotations + new, list(range(len(self.annotations), len(self.annotations) + len(new))))
        self.status(ntr("{count} box added", "{count} boxes added", len(new))
                    + ntr(", on {count} page", ", on {count} pages", pages))

    # ----------------------------------------------------------------- the right-click menu

    def box_menu(self, index: int, where, page: int = -1, point=None):
        """The right-click menu of the mode: of the boxes selected (INDEX: the one clicked), or of the
        page (INDEX -1), with what makes sense where it was clicked."""
        from .window import icon

        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        boxes = self.boxes()
        if boxes:
            act = menu.addAction(icon("document-save-as"), ntr("Apply the redaction…", "Apply all {count} redactions…",
                                                                len(boxes)), lambda: self.save_redacted_dialog())
            act.setToolTip(tr("Save the redacted copy: what is under the boxes is removed for good"))
            menu.addSeparator()
        chosen = [self.annotations[i] for i in self.selected if self.annotations[i].kind == KIND]
        if index >= 0 and chosen:
            if len(chosen) == 1:
                a = chosen[0]
                menu.addSection(tr("Box drawn on page {page} — {pages}", page=a.page + 1,
                                   pages=self._covers(a).lower() if a.repeat.strip() else tr("only there")))
            else:
                menu.addSection(ntr("{count} box", "{count} boxes", len(chosen)))
            repeats = {a.repeat.strip().lower() for a in chosen}
            pages = menu.addMenu(tr("Pages"))
            group = QActionGroup(pages)
            for value, name in REPEATS[:4]:
                act = pages.addAction(tr(name), lambda v=value: self.set_redact_repeat(v))
                act.setCheckable(True)
                act.setChecked(repeats == {value})
                group.addAction(act)
            pages.addSeparator()
            first = chosen[0].page + 1
            if first < self.count:
                pages.addAction(tr("From page {page} to the end", page=first),
                                lambda: self.set_redact_repeat(f"{first}-"))
            if first > 1:
                pages.addAction(tr("Up to page {page}", page=first), lambda: self.set_redact_repeat(f"1-{first}"))
            custom = {r for r in repeats if r not in ("", "all", "odd", "even")}
            act = pages.addAction(tr("These pages ({pages})…", pages=chosen[0].repeat) if len(repeats) == 1 and custom
                                  else tr("These pages…"), self.ask_redact_pages)
            act.setCheckable(True)
            act.setChecked(len(repeats) == 1 and bool(custom))
            group.addAction(act)
            fills = {a.fill for a in chosen}
            fill = fills.pop() if len(fills) == 1 else None
            self._swatch_menu(menu, tr("Colour"), fill, lambda v: self._change_boxes(fill=v))
            if fill is not None and fill != self.redact_prefs.color:
                menu.addAction(swatch(fill), tr("Make {color} the colour of new boxes", color=color_name(fill)),
                               lambda: self.set_redact_prefs(dataclasses.replace(self.redact_prefs, color=fill)))
            if len(chosen) == 1 and page >= 0:
                text = " ".join(under(words(self.doc[page]), chosen[0].rect)) if self.doc is not None else ""
                if text:
                    menu.addSeparator()
                    short = text if len(text) <= 30 else text[:28] + "…"
                    act = menu.addAction(tr("Redact “{text}” wherever it is…", text=short),
                                         lambda: self.redact_find_dialog(text))
                    act.setToolTip(tr("Find the text under this box on every page, and mark it"))
            self._codes_menu(menu, chosen)
            menu.addSeparator()
            menu.addAction(tr("Properties…"), self.redact_properties_dialog)
            locked = all(a.locked for a in chosen)
            menu.addAction(tr("Unlock") if locked else tr("Lock"), lambda: self._change_boxes(locked=not locked))
            act = menu.addAction(icon("edit-delete"), ntr("Delete the box", "Delete the {count} boxes", len(chosen)),
                                 self.delete_selected)
            act.setEnabled(not locked)
        else:
            word = self.canvas.word_at(page, point) if page >= 0 and point is not None else ""
            if word:
                menu.addSection(f"“{word}”")
                menu.addAction(tr("Redact it on this page"),
                               lambda: self.mark_redact_matches(self._redact_find(word, [page])))
                menu.addAction(tr("Redact it on every page…"), lambda: self.redact_find_dialog(word))
                menu.addSeparator()
            menu.addAction(self.a_redact_find)
            menu.addAction(self.tool_actions[KIND])
            menu.addSeparator()
            self._swatch_menu(menu, tr("Colour of new boxes"), self.redact_prefs.color,
                              lambda v: self.set_redact_prefs(dataclasses.replace(self.redact_prefs, color=v)))
            here = [i for i in boxes if page >= 0 and page in self.box_pages(self.annotations[i])]
            if here:
                menu.addSeparator()
                menu.addAction(ntr("Select the box of this page", "Select the {count} boxes of this page",
                                   len(here)), lambda: self.pick(here, False))
            menu.addSeparator()
            menu.addAction(self.a_redact_result)
            menu.addAction(tr("Settings of redaction…"), self.redact_settings_dialog)
        self.show_menu(menu, where)

    def _swatch_menu(self, menu: QMenu, title: str, current: str | None, choose) -> QMenu:
        """A menu of the colours of boxes (CURRENT ticked), each given to CHOOSE."""
        sub = menu.addMenu(swatch(current) if current else QIcon(), title)
        group = QActionGroup(sub)
        for value, name in SWATCHES:
            act = sub.addAction(swatch(value), tr(name), lambda v=value: choose(v))
            act.setCheckable(True)
            act.setChecked(value == current)
            group.addAction(act)
        sub.addSeparator()
        other = sub.addAction(tr("Other colour…"), self.choose_redact_color)
        if current and current not in [v for v, _ in SWATCHES]:
            other.setText(tr("Other colour ({color})…", color=current))
            other.setIcon(swatch(current))
        return sub

    def _codes_menu(self, menu: QMenu, chosen: list[Annotation]):
        """Redaction codes: each set, with its codes ticked if all the boxes have them."""
        sub = menu.addMenu(tr("Redaction code"))
        sub.setToolTipsVisible(True)
        for name, entries in codes.all_sets().items():
            group = sub.addMenu(name)
            for code in entries:
                act = group.addAction(code, lambda c=code: self.toggle_code(c))
                act.setCheckable(True)
                act.setChecked(all(code in codes.codes_of(a.overlay) for a in chosen))
        sub.addSeparator()
        if any(a.overlay for a in chosen):
            sub.addAction(tr("No code (no text)"), lambda: self._change_boxes(overlay=""))
        sub.addAction(tr("Edit the codes…"), lambda: CodesDialog(self).exec())

    # ----------------------------------------------------------------- the panel

    def _covers(self, a: Annotation) -> str:
        for value, name in REPEATS[1:4]:
            if a.repeat.strip().lower() == value:
                return tr(name)
        return a.repeat if a.repeat.strip() else tr("Its page")

    def fill_redact_panel(self):
        """The table of the boxes, as they are now."""
        if self.mode != KIND:
            return
        order = sorted(self.boxes(), key=lambda i: (self.annotations[i].page, self.annotations[i].rect[1],
                                                    self.annotations[i].rect[0]))
        self._redact_rows = order
        table = self.redact_table
        table.blockSignals(True)
        table.setRowCount(len(order))
        for row, i in enumerate(order):
            a = self.annotations[i]
            x0, y0, x1, y1 = a.rect
            cells = [QTableWidgetItem(str(a.page + 1)), QTableWidgetItem(self._covers(a)),
                     QTableWidgetItem(swatch(a.fill), color_name(a.fill)),
                     QTableWidgetItem(f"{mm(x1 - x0)} × {mm(y1 - y0)}")]
            cells[3].setToolTip(tr("{width} × {height} mm, {left} mm from the left and {top} mm from the top",
                                   width=mm(x1 - x0), height=mm(y1 - y0), left=mm(x0), top=mm(y0)))
            for col, cell in enumerate(cells):
                table.setItem(row, col, cell)
        table.resizeColumnToContents(0)
        table.blockSignals(False)
        self._select_redact_rows()
        self._show_redact_panel()

    def _select_redact_rows(self):
        """Select in the table the rows of the boxes selected, all at once."""
        chosen = set(self.selected)
        table = self.redact_table
        model = table.model()
        last = table.columnCount() - 1
        selection = QItemSelection()
        start = None
        for row, i in enumerate(self._redact_rows + [None]):
            if i is not None and i in chosen:
                if start is None:
                    start = row
            elif start is not None:
                selection.select(model.index(start, 0), model.index(row - 1, last))
                start = None
        table.blockSignals(True)
        table.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        table.blockSignals(False)

    def _redact_table_selected(self):
        rows = sorted({i.row() for i in self.redact_table.selectedIndexes()})
        chosen = [self._redact_rows[r] for r in rows if r < len(self._redact_rows)]
        if chosen == self.selected:
            return
        self.selected = chosen
        if chosen and not any(self.page in self.box_pages(self.annotations[i]) for i in chosen):
            self.show_page(self.annotations[chosen[0]].page)
        self.refresh(pages=False, table=False)

    def _show_redact_panel(self):
        """The colour and pages of the boxes selected, or of new boxes if none is selected."""
        if not hasattr(self, "redact_table"):
            return
        chosen = [self.annotations[i] for i in self.selected
                  if i < len(self.annotations) and self.annotations[i].kind == KIND]
        if chosen:
            self.redact_title.setText("<b>" + ntr("{count} box selected", "{count} boxes selected", len(chosen))
                                      + "</b>")
            fills = {a.fill for a in chosen}
            repeats = {a.repeat.strip() for a in chosen}
        else:
            self.redact_title.setText("<b>" + tr("New boxes") + "</b>")
            fills, repeats = {self.redact_prefs.color}, {""}
        fill = fills.pop() if len(fills) == 1 else None
        self.redact_color.setIcon(swatch(fill) if fill is not None else QIcon())
        self.redact_color.setText(color_name(fill) if fill is not None else tr("(several)"))
        self.redact_color.setEnabled(self.doc is not None)
        repeat = repeats.pop() if len(repeats) == 1 else None
        values = [v for v, _ in REPEATS]
        key = repeat.lower() if repeat is not None else None
        row = values.index(key) if key in values else (values.index("*") if repeat else -1)
        self.redact_repeat.blockSignals(True)
        self.redact_repeat.setCurrentIndex(row)
        self.redact_repeat.blockSignals(False)
        typed = row == values.index("*")
        self.redact_pages.setText(repeat if typed else "")
        # (new boxes are only on their own page: their pages are given once they are there)
        self.redact_repeat.setEnabled(self.doc is not None and bool(chosen))
        self.redact_pages.setEnabled(typed and bool(chosen))
        self.redact_delete.setEnabled(bool(chosen) and not all(a.locked for a in chosen))
        self.a_redact_props.setEnabled(bool(chosen))
        self.a_redact_pages.setEnabled(bool(chosen))
        has = self.doc is not None
        for act in (self.a_redact_find, self.a_redact_hidden, self.a_redact_sanitize, self.a_redact_meta,
                    self.tool_actions[KIND]):
            act.setEnabled(has)
        can = has and (bool(self.boxes()) or self.redact_meta is not None)
        self.a_redact_save.setEnabled(can)
        have = conform.available()
        self.m_redact_output.setEnabled(can)
        for act in self.redact_output_actions.values():
            act.setEnabled(have)
            act.setToolTip("" if have else tr("Needs {command}: install it, or say where it is in Settings",
                                              command=conform.COMMAND))

    # ----------------------------------------------------------------- metadata and hidden information

    def redact_metadata_dialog(self) -> bool:
        if self.doc is None:
            return False
        original = metadata.read(self.doc)
        dialog = MetadataDialog(self.redact_meta if self.redact_meta is not None else original, original, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        meta = dialog.metadata()
        self.redact_meta = None if meta == original else meta
        self._show_redact_panel()
        if self.redact_meta is None:
            self.status(tr("The copy will have the document's own metadata"))
        elif self.redact_meta.is_empty():
            self.status(tr("The copy will have no metadata"))
        else:
            self.status(tr("The copy will have the metadata chosen"))
        return True

    def redact_hidden_dialog(self) -> bool:
        if self.path is None:
            return False
        try:  # (from the file: the document of the window has no annotations, which it draws itself)
            doc = open_pdf(self.path, self.password)
        except RedactError as e:
            self.status(str(e), error=True)
            return False
        try:
            found = hidden.inspect(doc)
        finally:
            doc.close()
        dialog = HiddenDialog(found, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self.sanitize_dialog(dialog.kinds())

    def sanitize_dialog(self, kinds: set[str] | None = None) -> bool:
        if self.path is None:
            return False
        default = Path(self.last_dir()) / f"{self.path.stem}-sanitized.pdf"
        name, _ = QFileDialog.getSaveFileName(self, tr("Sanitize the document"), str(default),
                                              tr("PDF files (*.pdf)"))
        if not name:
            return False
        target = Path(name)
        if target.resolve() == self.path.resolve():
            self.status(tr("Choose another name: the document stays open"), error=True)
            return False
        try:
            background.run(self, tr("Writing the sanitized copy…"), sanitize, self.path, target, self.password, kinds)
        except RedactError as e:
            self.status(str(e), error=True)
            return False
        self.status(tr("Saved {path}, sanitized", path=target))
        return True

    # ----------------------------------------------------------------- the redacted copy

    def _ask_save_first(self) -> bool:
        """The redacted copy is made from the file: if the document has changes other than its boxes,
        whether to save them first. False: don't go on."""
        def others(items):
            return [a for a in items if a.kind != KIND]

        if others(self.annotations) == others(self.saved) and not self.is_modified_besides_annotations():
            return True
        box = QMessageBox(QMessageBox.Icon.Question, tr("Unsaved changes"),
                          tr("The redacted copy is made from the document as it was last saved. Save its other "
                             "changes first?"),
                          QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Ignore
                          | QMessageBox.StandardButton.Cancel, self)
        box.button(QMessageBox.StandardButton.Ignore).setText(tr("Make it without them"))
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        answer = box.exec()
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Ignore

    def is_modified_besides_annotations(self) -> bool:
        """Whether the document has changes that are not of its annotations (the modes Pages and
        Impose make such changes)."""
        return False

    def save_redacted_dialog(self, standard: str = "") -> bool:
        """Save the redacted copy, as a plain PDF or, this once, as STANDARD ('a-2b', 'x-4'...)."""
        if self.path is None:
            return False
        self.canvas.commit_text()
        boxes = [box_of(self.annotations[i]) for i in self.boxes()]
        if not boxes and self.redact_meta is None:
            self.status(tr("There is nothing to save: no boxes, and the metadata is the document's own"),
                        error=True)
            return False
        bad = [b for b in boxes if b.repeat.strip() and check(b.repeat)]
        if bad:
            self.status(tr("A box has pages that can't be read: {error}", error=check(bad[0].repeat)), error=True)
            return False
        if not self._ask_save_first():
            return False
        default = Path(self.last_dir()) / f"{self.path.stem}-redacted.pdf"
        title = tr("Save the redacted copy") if not standard \
            else tr("Save the redacted copy as {standard}", standard=conform.label(standard))
        name, _ = QFileDialog.getSaveFileName(self, title, str(default), tr("PDF files (*.pdf)"))
        if not name:
            return False
        target = Path(name)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        return self.save_redacted(target, boxes, standard)

    def save_redacted(self, target: Path, boxes: list, standard: str = "") -> bool:
        """Write the redacted copy of the file, with BOXES (redact.Box), as TARGET: a plain PDF or STANDARD."""
        if target.resolve() == self.path.resolve():
            self.status(tr("Choose another name: the document stays open"), error=True)
            return False
        p = self.redact_prefs
        # (in a process of its own, which can be stopped: see redact/background.py; until the copy is
        # complete, it is written as PART, next to it)
        part = target.with_name(f".{target.name}.part")
        try:
            done = background.run(self, tr("Writing the redacted copy…"), write_redacted, self.path, boxes, target,
                                  self.password, p.clean, p.images, p.drawings, self.redact_meta, part, cancel=True)
        except (RedactError, Cancelled) as e:
            part.unlink(missing_ok=True)
            if isinstance(e, Cancelled):
                self.status(tr("Saving was stopped: nothing was written"))
            else:
                self.status(str(e), error=True)
            return False
        # (before PDF/A or PDF/X: changing the copy afterwards could undo its conformance)
        bookmarks = self.check_redacted_bookmarks(target, boxes)
        check_ = ""
        if standard and not conform.available():
            self.warn(conform.label(standard), tr("The redacted copy was saved as a plain PDF: {command} is not "
                                                  "installed (or not where Settings say)", command=conform.COMMAND))
            standard = ""
        if standard:
            try:  # (another program: in a thread, which waits for it)
                check_ = background.run(self, tr("Making {standard} with {command}…",
                                                 standard=conform.label(standard), command=conform.COMMAND),
                                        conform.convert, target, target, standard, self.password, thread=True)
            except conform.ConformError as e:
                self.warn(conform.label(standard),
                          tr("The redacted copy was saved as a plain PDF, but it could not be made "
                             "{standard}:\n\n{error}", standard=conform.label(standard), error=e))
                standard = ""
        self.settings.setValue("last_dir", str(target.parent))
        try:
            leaks = background.run(self, tr("Checking that nothing under the boxes can be read…"), check_redacted,
                                   self.path, target, boxes, self.password)
        except RedactError as e:
            self.status(str(e), error=True)
            leaks = []
        message = ntr("Saved {path} ({count} area redacted)", "Saved {path} ({count} areas redacted)", done,
                      path=target)
        if standard:
            message += " — " + conform.label(standard) + (f" ({check_})" if check_ else "")
            if self.password:
                message += " — " + tr("PDF/A and PDF/X can't be protected: the copy has no password")
        if leaks:
            self.warn(tr("Check the redacted copy"),
                      tr("Some text can still be read under the boxes of {name}:", name=target.name)
                      + "\n\n" + "\n".join(tr("Page {page}: {context}", page=pg + 1, context=t) for pg, t in leaks[:10]))
        else:
            message += " — " + tr("checked: nothing under the boxes can be read")
        if bookmarks:
            message += " — " + bookmarks
        self.status(message)
        return True

    def check_redacted_bookmarks(self, target: Path, boxes: list) -> str:
        """Look for bookmarks of TARGET that give away what was redacted, and take them out if the user
        wants. Returns what was done, for the status bar."""
        try:
            leaks = background.run(self, tr("Checking the bookmarks of the copy…"), bookmark_leaks, self.path,
                                   target, boxes, self.password)
        except RedactError as e:
            self.status(str(e), error=True)
            return ""
        if not leaks:
            return ""
        choice = self.ask_bookmarks(target.name, leaks)
        if not choice:
            return ntr("{count} bookmark that gives away what was redacted was kept",
                       "{count} bookmarks that give away what was redacted were kept", len(leaks))
        try:
            background.run(self, tr("Removing the bookmarks…"), remove_bookmarks, target,
                           None if choice == "all" else {i for i, _, _ in leaks}, self.password)
        except RedactError as e:
            self.status(str(e), error=True)
            return ""
        return tr("all the bookmarks were removed") if choice == "all" \
            else ntr("{count} bookmark was removed", "{count} bookmarks were removed", len(leaks))

    def ask_bookmarks(self, name: str, leaks: list[tuple[int, str, str]]) -> str:
        """What to do with bookmarks that give away what was redacted: 'these' (remove them), 'all'
        (remove all the bookmarks) or '' (keep them)."""
        box = QMessageBox(QMessageBox.Icon.Warning, tr("Check the redacted copy"),
                          ntr("A bookmark of {name} may give away what was redacted:",
                              "{count} bookmarks of {name} may give away what was redacted:", len(leaks),
                              name=name)
                          + "\n\n" + "\n".join(f"• “{title}”: {why}" for _, title, why in leaks[:12]),
                          QMessageBox.StandardButton.NoButton, self)
        these = box.addButton(ntr("Remove it", "Remove them", len(leaks)), QMessageBox.ButtonRole.AcceptRole)
        everything = box.addButton(tr("Remove all the bookmarks"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Keep them"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(these)
        box.exec()
        clicked = box.clickedButton()
        return "these" if clicked is these else "all" if clicked is everything else ""
