"""The mode Pages of the window (from py-foliation): the page labels, the view
of the document when it is opened, headers, footers and watermarks, and the
order of the pages (moved, deleted, duplicated, turned, inserted, replaced,
extracted, split).

Each change is made at once on the working copy of the document (see
working.py), with py-foliation's engine (pages/), and the pages show it; Save
writes it. The labels, the view and what was added to the pages are read
from the document as it is (they are not kept apart, as py-foliation kept
them until the file was saved).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pikepdf
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDockWidget, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidgetItem, QMenu, QPushButton, QTableWidget, QVBoxLayout, QWidget,
)

from ..annotate import annots
from ..annotate.annots import AnnotateError
from ..core.interface import N_, ntr, tr
from ..pages import arrange, files, headfoot, labels, stamps, view, watermark
from ..pages.changes import Change
from ..pages.labels import LabelError, Range
from ..pages.view import View
from .modes import Mode
from .pages.arrange_dialog import PageList, ask_arrange, ask_labels
from .pages.headfoot_dialog import ask_header_footer
from .pages.watermark_dialog import ask_watermark
from .pages.widgets import FIELDS, LABELS, NumberDialog, edited_signal, fit_columns, range_row

KIND = "pages"
# The operations on the pages, each with its dialog (the menu Pages ▸ Arrange, and "More")
ARRANGE_MENU = (("rotate", N_("Rotate…")), ("delete", N_("Delete…")), ("move", N_("Move…")),
                ("duplicate", N_("Duplicate…")), ("reverse", N_("Reverse pages…")),
                ("order", N_("New order…")), (None, None),
                ("blank", N_("Insert blank pages…")), ("insert", N_("Insert pages from file…")),
                ("replace", N_("Replace pages…")),
                (None, None), ("extract", N_("Extract pages…")), ("split", N_("Split…")))


@dataclasses.dataclass(frozen=True)
class PagesState:
    """What the document has of what this mode changes (read from its file, see PagesMixin.pages_state)."""
    ranges: tuple[Range, ...] = ()
    opening: View = View()
    added: tuple[stamps.Addition, ...] = ()


def write_page_labels(doc, ranges: list[Range]) -> None:
    """Give DOC (a pymupdf.Document) these page labels, as labels.write_labels writes them with pikepdf
    (but its entries direct objects): so that the document is written with its annotations at once."""
    # pymupdf se importa aquí y no arriba: solo hace falta al escribir etiquetas, y así el módulo carga más rápido.
    import pymupdf

    items = []
    # labels.entries numera las páginas desde 1; el árbol /Nums del PDF las cuenta desde 0, de ahí el "page - 1".
    for page, style, prefix, start in labels.entries(ranges, doc.page_count):
        entry = "/Type /PageLabel"
        if style:
            entry += f" /S /{style}"
        if prefix:
            entry += f" /P {pymupdf.get_pdf_str(prefix)}"
        if start != 1:
            entry += f" /St {start}"
        items.append(f"{page - 1} << {entry} >>")
    # With no ranges left, the key is set to null, which removes /PageLabels from the catalog
    # instead of leaving an empty number tree behind.
    catalog = doc.pdf_catalog()
    doc.xref_set_key(catalog, "PageLabels", f"<< /Nums [ {' '.join(items)} ] >>" if items else "null")


class PagesMixin:
    """(Mixed into MainWindow: it uses its attributes.)"""

    # ----------------------------------------------------------------- construction

    def _build_pages(self) -> Mode:
        from .window import icon

        self._pages_cache: tuple | None = None  # ((file, its time and size), PagesState)
        self._building_table = False
        self.labels_rule_actions: dict[str, QAction] = {}

        # Every page action works on the pages chosen in the list (or the page shown) and does nothing
        # while no document is open.
        def act(text, icon_name, keys, triggered, tip=""):
            a = QAction(icon(icon_name), tr(text), self)
            if keys:
                a.setShortcuts([QKeySequence(k) for k in keys])
            a.setToolTip(tr(tip) if tip else tr(text))
            a.triggered.connect(lambda *_: triggered(self.selected_pages()) if self.path and self.count else None)
            return a

        self.a_rotate_left = act(N_("Rotate 90° counterclockwise"), "object-rotate-left", ["Ctrl+Shift+L"],
                                 lambda pages: self.arrange_pages(arrange.Rotate(tuple(pages), 270)))
        self.a_rotate_right = act(N_("Rotate 90° clockwise"), "object-rotate-right", ["Ctrl+L"],
                                  lambda pages: self.arrange_pages(arrange.Rotate(tuple(pages), 90)))
        # Las condiciones con "and" hacen que la acción no haga nada en los bordes: no se sube la página 1
        # ni se baja la última. move_pages recibe la posición "antes de", por eso el + 2.
        self.a_earlier = act(N_("Move page earlier"), "go-up", ["Alt+Up"],
                             lambda pages: pages[0] > 1 and self.move_pages(pages, pages[0] - 1))
        self.a_later = act(N_("Move page later"), "go-down", ["Alt+Down"],
                           lambda pages: pages[-1] < self.count and self.move_pages(pages, pages[-1] + 2))
        self.a_page_duplicate = act(N_("Duplicate"), "edit-copy", [],
                                    lambda pages: self.arrange_pages(arrange.Duplicate(tuple(pages))),
                                    N_("Duplicate the pages chosen"))
        # A PDF must keep at least one page, so deleting all of them is refused here.
        self.a_page_delete = act(N_("Delete"), "edit-delete", [],
                                 lambda pages: len(pages) < self.count
                                 and self.arrange_pages(arrange.Delete(tuple(pages))), N_("Delete the pages chosen"))
        self.a_blank = act(N_("Insert blank page after"), "document-new", [],
                           lambda pages: self.arrange_pages(arrange.InsertBlank(pages[-1] + 1)))
        self.a_insert = act(N_("Insert pages from file…"), "document-import", [],
                            lambda pages: self.arrange_dialog("insert", pages))
        self.page_actions = [self.a_rotate_left, self.a_rotate_right, self.a_earlier, self.a_later,
                             self.a_page_duplicate, self.a_page_delete, self.a_blank, self.a_insert]
        self.a_headfoot = QAction(icon("draw-text"), tr("Header and footer…"), self)
        self.a_headfoot.triggered.connect(lambda: self.stamp_dialog(stamps.HEADER_FOOTER))
        self.a_watermark = QAction(icon("watermark"), tr("Watermark…"), self)
        self.a_watermark.triggered.connect(lambda: self.stamp_dialog(stamps.WATERMARK))

        m = QMenu(tr("&Pages"), self)
        m.setToolTipsVisible(True)
        self.m_pages = m
        sub = m.addMenu(tr("Labels"))
        sub.setToolTipsVisible(True)
        self._action(sub, tr("Add a range"), self.add_range, tip=tr("Start a new range at the page shown"))
        self._action(sub, tr("Copy the labels of another PDF…"), self.copy_labels_dialog,
                     tip=tr("For instance, of an earlier export of the same book"))
        self._action(sub, tr("Labels from a list…"), self.import_labels_dialog,
                     tip=tr("A text file with the label of each page, one on each line"))
        self._action(sub, tr("Save the labels as a list…"), self.export_labels_dialog,
                     tip=tr("A text file with the label of each page, one on each line, to edit and read back"))
        sub.addSeparator()
        self._action(sub, tr("No labels"), self.clear_labels,
                     tip=tr("Remove all the page labels: viewers number the pages 1, 2, 3 ..."))
        # La regla para las etiquetas cuando se mueven páginas se guarda en la configuración; las tres opciones
        # forman un grupo exclusivo, como botones de radio.
        rule = sub.addMenu(tr("Labels of moved pages"))
        group = QActionGroup(rule)
        for value, text in (("ask", N_("Ask each time")), (arrange.FOLLOW, N_("Their labels")),
                            (arrange.POSITION, N_("The labels of their new places"))):
            a = rule.addAction(tr(text), lambda *_, v=value: self.set_labels_rule(v))
            a.setCheckable(True)
            a.setData(value)
            group.addAction(a)
            self.labels_rule_actions[value] = a
        self.set_labels_rule(str(self.settings.value("labels_when_moving", "ask")))
        # Estos submenús se rellenan al abrirse (aboutToShow), porque dependen del documento y de sus capas actuales.
        self.m_headfoot = m.addMenu(tr("Header and footer"))
        self.m_headfoot.aboutToShow.connect(lambda: self._fill_stamp_menu(self.m_headfoot, stamps.HEADER_FOOTER))
        self.m_watermark = m.addMenu(tr("Watermark"))
        self.m_watermark.aboutToShow.connect(lambda: self._fill_stamp_menu(self.m_watermark, stamps.WATERMARK))
        self.m_arrange = m.addMenu(tr("Arrange pages"))
        self.m_arrange.aboutToShow.connect(lambda: self._fill_arrange(self.m_arrange))
        self.m_opening = m.addMenu(tr("Initial view"))
        self.m_opening.aboutToShow.connect(lambda: (self.m_opening.clear(),
                                                    self.add_view_menus(self.m_opening, self.page + 1)))
        m.addSeparator()
        self._action(m, tr("On several files…"), self.batch_dialog,
                     tip=tr("Add or remove headers and footers, Bates numbers or watermarks on several PDFs at "
                            "once, the Bates numbers going on from one file to the next"))
        self.menuBar().insertMenu(self.m_layers.menuAction(), m)

        bars = [self.toolbar_of("arrange-pages", tr("Arrange pages"), self.page_actions),
                self.toolbar_of("layers", tr("Headers and watermarks"), [self.a_headfoot, self.a_watermark])]

        # El panel lateral reúne la tabla de intervalos de etiquetas y la lista de páginas.
        dock = QDockWidget(tr("Page labels"), self)
        dock.setObjectName("labels")
        dock.setWidget(self._pages_panel())
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.hints[KIND] = tr("Select pages in the list (Shift, Ctrl) and right-click them for more; drag them to "
                              "move them (with Ctrl, to copy them), or drop PDFs to insert their pages. Double-click "
                              "a page to start a range of labels at it; change a range in the table above.")
        # (the page actions: always in the toolbar, and only while the mode is on)
        return Mode(KIND, lambda a: False, bars=bars, docks=[dock], menus=[m.menuAction()],
                    actions=[*self.page_actions, self.a_headfoot, self.a_watermark], entered=self._pages_entered)

    def _pages_panel(self) -> QWidget:
        # The six columns: the first five are editable widgets (see widgets.range_row); the last shows
        # the labels the range gives, and takes up the spare width.
        self.ranges_table = table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels([tr("From page"), tr("Style"), tr("Starts at"), tr("Prefix"), tr("Suffix"),
                                         tr("Labels")])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(LABELS, QHeaderView.ResizeMode.Stretch)
        table.currentCellChanged.connect(lambda row, *_: self._range_chosen(row))
        buttons = QHBoxLayout()
        for text, tip, slot in ((N_("Add a range"), N_("Start a new range at the page shown"), self.add_range),
                                (N_("Remove the range"), N_("The range before goes on over its pages"),
                                 self.remove_range),
                                (N_("No labels"), N_("Remove all the page labels: viewers number the pages 1, 2, "
                                                     "3 ..."), self.clear_labels)):
            b = QPushButton(tr(text))
            b.setToolTip(tr(tip))
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch(1)
        # PageList admite arrastrar páginas dentro de la lista y soltar archivos PDF desde fuera.
        self.page_list = pl = PageList()
        pl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        pl.moved.connect(self.move_pages)
        pl.files_dropped.connect(self.files_dropped)
        # Guarda contra el bucle: show_page vuelve a mover la fila actual, así que solo se llama si cambió de verdad.
        pl.currentRowChanged.connect(lambda row: self.show_page(row) if row >= 0 and row != self.page else None)
        pl.itemDoubleClicked.connect(lambda item: self.start_range_at(pl.row(item) + 1))
        pl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        pl.customContextMenuRequested.connect(self.pages_menu)
        pl.itemSelectionChanged.connect(self._page_list_selection_changed)
        self.go_to_field = QLineEdit()
        self.go_to_field.setPlaceholderText(tr("Go to the page labelled…"))
        self.go_to_field.setToolTip(tr("Type a label (xii, 12v, A-3) and press Enter; Enter again goes to the "
                                       "next page with that label"))
        self.go_to_field.returnPressed.connect(lambda: self.go_to_label(self.go_to_field.text()))
        # Read-only field with the equivalent command for the command-line tool, to copy and run on other files.
        self.cmd_line = QLineEdit()
        self.cmd_line.setReadOnly(True)
        self.cmd_line.setToolTip(tr("The command that gives these labels to a file"))
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(QLabel("<b>" + tr("Ranges of page labels") + "</b>"))
        lay.addWidget(table, 2)
        lay.addLayout(buttons)
        lay.addWidget(QLabel("<b>" + tr("Page labels") + "</b>"))
        lay.addWidget(pl, 3)
        lay.addWidget(self.go_to_field)
        lay.addWidget(QLabel(tr("Command line:")))
        lay.addWidget(self.cmd_line)
        panel.setMinimumWidth(340)
        return panel

    def _pages_entered(self):
        self.set_tool("select")
        self.fill_pages_panel()

    # ----------------------------------------------------------------- what the document has

    def pages_state(self) -> PagesState:
        """The labels, the view on opening and the additions of the document as it is now (read
        from its file, or its working copy, once for each)."""
        if self.file is None:
            return PagesState()
        # La clave de la caché incluye la fecha y el tamaño del archivo: cada edición escribe una copia nueva,
        # así que basta con eso para saber si hay que volver a leerlo.
        try:
            st = self.file.stat()
            key = (str(self.file), st.st_mtime_ns, st.st_size)
        except OSError:
            return PagesState()
        if self._pages_cache is not None and self._pages_cache[0] == key:
            return self._pages_cache[1]
        try:
            with pikepdf.open(self.file, password=self.password) as pdf:
                state = PagesState(tuple(labels.read_labels(pdf)), view.read_view(pdf),
                                   tuple(stamps.additions(pdf)))
        # Un archivo dañado no impide trabajar: se muestra el error y el modo sigue con un estado vacío.
        except (pikepdf.PdfError, LabelError, OSError) as e:
            self.status(str(e), error=True)
            state = PagesState()
        self._pages_cache = (key, state)
        return state

    @property
    def ranges(self) -> list[Range]:
        return list(self.pages_state().ranges)

    def page_labels(self) -> list[str]:
        return labels.page_labels(self.ranges, self.count)

    def current_page(self) -> int:
        return self.page + 1

    def selected_pages(self) -> list[int]:
        """The pages chosen (1-based, in order): in the thumbnails, or in Foliate's list (the two are kept
        the same); or else the page shown."""
        rows = sorted({i.row() for i in self.pages.selectedIndexes()}) \
            or sorted(self.page_list.row(item) for item in self.page_list.selectedItems())
        if rows:
            return [r + 1 for r in rows]
        return [self.current_page()] if self.count else []

    def _page_list_selection_changed(self):
        """The pages chosen in Foliate's list are those of the thumbnails too."""
        if getattr(self, "_syncing_selection", False):
            return
        self._syncing_selection = True
        try:
            rows = {self.page_list.row(item) for item in self.page_list.selectedItems()}
            self.pages.blockSignals(True)
            for n in range(self.pages.count()):
                self.pages.item(n).setSelected(n in rows)
            self.pages.blockSignals(False)
            self._update_page_actions()
        finally:
            self._syncing_selection = False

    # ----------------------------------------------------------------- the labels

    def set_ranges(self, ranges: list[Range], select: int | None = None) -> bool:
        """Give the document these page labels (a step of the history)."""
        ranges = labels.normalize(ranges)
        if ranges == self.ranges:
            self.fill_pages_panel(select)
            # (antes, nada lo decía: parecía que la orden no había hecho nada)
            self.status(tr("The pages have those labels already"))
            return False
        before = self.page_labels()
        done = self.edit_document(lambda doc: write_page_labels(doc, ranges), message=tr("Labels changed"))
        self.fill_pages_panel(select)
        if done:
            self.refresh_captions()
            self.status(self._labels_said(before, self.page_labels()))
        return done

    def _labels_said(self, before: list[str], after: list[str]) -> str:
        """What changed in the labels, in a few words: 'Labels changed: page 5 is now i' (the first pages that
        changed, and how many)."""
        changed = [n for n in range(min(len(before), len(after))) if before[n] != after[n]]
        if not changed:
            return tr("Labels changed")
        shown = ", ".join(tr("page {page} is now {label}", page=n + 1, label=after[n] or tr("(no label)"))
                          for n in changed[:3])
        more = len(changed) - 3
        return tr("Labels changed: {what}", what=shown) + (
            " " + ntr("and {count} more page", "and {count} more pages", more) if more > 0 else "")

    def _edit(self, row: int, **changes):
        """Change one field of the range in ROW (later, out of the signal of the widget)."""
        # The ranges are read again here, not passed in: the table may have been rebuilt since the signal was connected.
        ranges = self.ranges
        if self._building_table or not 0 <= row < len(ranges):
            return
        old = ranges[row]
        new = dataclasses.replace(old, **changes)
        # Si cambió la página inicial del intervalo, hay que quitar también el intervalo viejo;
        # normalize ordena después.
        rest = [r for r in ranges if r.page not in (old.page, new.page)] + [new]
        # Diferido con singleShot: set_ranges reconstruye la tabla, y destruir el widget que emitió la señal
        # dentro de su propio manejador hace fallar a Qt.
        QTimer.singleShot(0, lambda: self.set_ranges(rest, select=new.page))

    def start_range_at(self, page: int):
        """Select the range that starts at PAGE, or start one there."""
        ranges = self.ranges
        if self.path is None:
            return
        # Page 1 always starts a range, even when the document has no labels: there is nothing new to add.
        if page in {r.page for r in ranges} or (page == 1 and not ranges):
            self.fill_pages_panel(page)
            return
        self.set_ranges(ranges + [Range(page)], select=page)

    def add_range(self):
        if self.path is None:
            return
        ranges = self.ranges
        # Se busca la primera página después de la mostrada que todavía no empiece un intervalo.
        starts = {r.page for r in ranges} or {1}
        page = self.current_page()
        while page in starts and page < self.count:
            page += 1
        if page in starts:
            self.status(tr("Every page already starts a range"), error=True)
            return
        self.set_ranges(ranges + [Range(page)], select=page)

    def remove_range(self):
        ranges = self.ranges
        row = self.ranges_table.currentRow()
        # El primer intervalo no se puede quitar: es el que empieza en la página 1.
        if not 0 < row < len(ranges):
            self.status(tr("Choose a range after the first one"), error=True)
            return
        # labels.apply with these pages removed lets the range before cover them, as the button's tip says.
        self.set_ranges(labels.apply(ranges, [], self.count, [ranges[row].page]), select=ranges[row - 1].page)

    def clear_labels(self):
        if self.path is not None:
            self.set_ranges([])

    def number_selected(self) -> bool:
        pages = self.selected_pages()
        dlg = NumberDialog(self, len(pages))
        if not pages or dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        style, prefix, start, suffix = dlg.values()
        ranges = labels.number_pages(self.ranges, self.count, pages, style, prefix, start, suffix)
        # Numerar como ya están (desde 1 un documento sin etiquetas) no cambia lo que se ve: se dice, y nada más.
        if labels.page_labels(labels.normalize(ranges), self.count) == self.page_labels():
            self.status(tr("The pages have those labels already"))
            return False
        return self.set_ranges(ranges)

    def continue_selected(self) -> bool:
        try:
            ranges = labels.continue_numbering(self.ranges, self.count, self.selected_pages())
        except LabelError as e:
            self.status(str(e), error=True)
            return False
        return self.set_ranges(ranges)

    def label_selected(self) -> bool:
        pages = self.selected_pages()
        text, ok = QInputDialog.getText(self, tr("One label"), tr("The label of the pages chosen:"),
                                        QLineEdit.EchoMode.Normal, self.page_labels()[pages[0] - 1])
        if not ok:
            return False
        return self.set_ranges(labels.relabel(self.ranges, self.count, {p: text for p in pages}))

    def edit_selected(self) -> bool:
        pages = self.selected_pages()
        current = self.page_labels()
        text, ok = QInputDialog.getMultiLineText(self, tr("Their labels"),
                                                 tr("The label of each page chosen, one on each line:"),
                                                 "\n".join(current[p - 1] for p in pages))
        if not ok:
            return False
        # Las líneas vacías que sobran al final (un salto de línea de más al pegar, por ejemplo) se descartan
        # antes de comparar con el número de páginas.
        lines = text.split("\n")
        while len(lines) > len(pages) and not lines[-1].strip():
            lines.pop()
        if len(lines) != len(pages):
            self.status(tr("There are {lines} lines for {count} pages", lines=len(lines), count=len(pages)),
                        error=True)
            return False
        return self.set_ranges(labels.relabel(self.ranges, self.count, dict(zip(pages, lines, strict=True))))

    def copy_labels(self):
        current = self.page_labels()
        QApplication.clipboard().setText("\n".join(current[p - 1] for p in self.selected_pages()))
        self.status(tr("Labels copied"))

    def copy_labels_dialog(self) -> bool:
        if self.path is None:
            return False
        name, _ = QFileDialog.getOpenFileName(self, tr("Copy the labels of another PDF"), self.last_dir(),
                                              tr("PDF files (*.pdf)"))
        return bool(name) and self.copy_labels_from(Path(name))

    def copy_labels_from(self, source: Path) -> bool:
        try:
            with pikepdf.open(source) as pdf:
                ranges = labels.read_labels(pdf)
        except (pikepdf.PdfError, LabelError, OSError) as e:
            self.status(tr("{path} cannot be read: {error}", path=source, error=e), error=True)
            return False
        # Only the ranges that start inside this document are kept: the other PDF may have more pages.
        done = self.set_ranges([r for r in ranges if r.page <= self.count])
        if done:
            self.status(tr("Labels copied from {path}", path=source))
        return done

    def import_labels_dialog(self) -> bool:
        if self.path is None:
            return False
        name, _ = QFileDialog.getOpenFileName(self, tr("Labels from a list"), self.last_dir(),
                                              tr("Text files (*.txt);;All files (*)"))
        return bool(name) and self.import_labels(Path(name))

    def import_labels(self, source: Path) -> bool:
        try:
            ranges = labels.from_list(files.read_list(str(source)), self.count)
        except (LabelError, OSError) as e:
            self.status(str(e), error=True)
            return False
        done = self.set_ranges(ranges)
        if done:
            self.status(tr("Labels read from {path}", path=source))
        return done

    def export_labels_dialog(self) -> bool:
        if self.path is None:
            return False
        # The default name sits in the last folder used, after the document's own name.
        default = Path(self.last_dir()) / f"{self.path.stem}-labels.txt"
        name, _ = QFileDialog.getSaveFileName(self, tr("Save the labels as a list"), str(default),
                                              tr("Text files (*.txt);;All files (*)"))
        if not name:
            return False
        try:
            Path(name).write_text("\n".join(self.page_labels()) + "\n", encoding="utf-8")
        except OSError as e:
            self.status(tr("{path} cannot be written: {error}", path=name, error=e), error=True)
            return False
        self.status(tr("Saved {path}", path=name))
        return True

    def go_to_label(self, label: str):
        """The next page labelled LABEL (or so, but for capitals), after the one shown."""
        label = label.strip()
        if not label or self.path is None:
            return
        found = labels.find_label(self.ranges, self.count, label)
        if not found:
            self.status(tr("No page is labelled {label}", label=label), error=True)
            return
        # Pressing Enter again finds the next page with the same label, and wraps around to the first one found.
        after = [p for p in found if p > self.current_page()]
        self.show_page((after or found)[0] - 1)

    def set_labels_rule(self, rule: str):
        """What the labels do when pages move: 'ask', arrange.FOLLOW or arrange.POSITION."""
        if rule not in self.labels_rule_actions:
            rule = "ask"
        self.settings.setValue("labels_when_moving", rule)
        for value, a in self.labels_rule_actions.items():
            a.setChecked(value == rule)

    def labels_choice(self) -> str | None:
        """What the labels do when pages move: as Pages ▸ Labels says, or as the user says now."""
        rule = self.settings.value("labels_when_moving", "ask")
        # "ask": se pregunta, y si el usuario marca la casilla su respuesta pasa a ser la regla permanente.
        if rule in (arrange.FOLLOW, arrange.POSITION):
            return rule
        answer = ask_labels(self)
        if answer is None:
            return None
        choice, keep = answer
        if keep:
            self.set_labels_rule(choice)
        return choice

    # ----------------------------------------------------------------- the view on opening

    def set_view_part(self, field: str, value) -> bool:
        """Change one part of the view when the document is opened: its layout, zoom (page view) or page."""
        old = self.pages_state().opening
        # view.without_lone_first_page adjusts the layout and the page together, so that a change of one
        # does not leave the other in a state viewers misread.
        new = view.without_lone_first_page(old, dataclasses.replace(old, **{field: value}), page_given=field == "page")
        if new == old:
            return False
        return self.transform(view.write_view, new, message=tr("The view when the document is opened changed"))

    def add_view_menus(self, menu: QMenu, page: int | None = None, heading: bool = True) -> None:
        """The submenus of MENU that choose the page layout and the page view of the document when it is
        opened, and with PAGE, the page it opens at (HEADING: under a heading that says so; not in a submenu
        whose title says it already)."""
        opening = self.pages_state().opening
        if heading:
            menu.addSection(tr("Initial view"))
        for title, field, current, titles, tips in (
                (tr("Page layout"), "layout", opening.layout, view.LAYOUT_TITLES, view.LAYOUT_TIPS),
                (tr("Page view"), "zoom", opening.zoom, view.PAGE_VIEW_TITLES, view.PAGE_VIEW_TIPS)):
            sub = menu.addMenu(title)
            sub.setEnabled(self.path is not None)
            sub.setToolTipsVisible(True)
            group = QActionGroup(sub)
            # La primera opción deja la decisión al visor (ninguna entrada en el catálogo). Si el documento trae
            # un valor que no está en la lista, se añade para que el menú lo muestre marcado.
            choices = [("", tr("The viewer's choice"), "")]
            choices += [(code, tr(text), tr(tips[code])) for code, text in titles.items()]
            if current and current not in titles:
                choices.append((current, view.page_view_title(current), ""))
            for code, text, tip in choices:
                a = sub.addAction(text, lambda *_, f=field, c=code: self.set_view_part(f, c))
                a.setCheckable(True)
                a.setChecked(code == current)
                a.setToolTip(tip)
                group.addAction(a)
        if page is not None:
            a = menu.addAction(tr("Open the document at page {page}", page=page),
                               lambda *_: self.set_view_part("page", page))
            a.setToolTip(tr("Viewers will show this page first when they open the file"))
            a.setCheckable(True)
            a.setChecked(opening.page == page)
        menu.setToolTipsVisible(True)

    # ----------------------------------------------------------------- headers, footers and watermarks

    def pages_with(self, kind: str, bates_only: bool = False) -> set[int]:
        # Bates numbers belong only to headers and footers; BATES_ONLY selects the additions that have them.
        return {p for a in self.pages_state().added if a.kind == kind and (a.bates or not bates_only)
                for p in a.pages}

    def last_added(self, kind: str):
        """(addition, settings) of the last layer of KIND the pages have (None if none)."""
        found = stamps.last_addition(list(self.pages_state().added), kind)
        # Las adiciones antiguas o hechas por otro programa pueden no tener ajustes guardados;
        # esas no se pueden actualizar.
        if found is None or not found.settings:
            return None
        cls = headfoot.HeaderFooter if kind == stamps.HEADER_FOOTER else watermark.Watermark
        # Los ajustes vienen del propio PDF: si están dañados o son de otra versión, se ignoran en vez de fallar.
        try:
            return found.id, cls.from_dict(found.settings)
        except (LabelError, TypeError, ValueError):
            return None

    def stamp_dialog(self, kind: str = stamps.HEADER_FOOTER, pages: list[int] | None = None,
                     update: bool = False) -> bool:
        """Ask for a header and footer, or a watermark (on PAGES, if given), and add it; with UPDATE,
        replace the last one added."""
        if self.path is None:
            return False
        replaces = None
        last = self.last_added(kind)
        # Con UPDATE se parte de los ajustes de la última capa y se la reemplaza; si no, esos ajustes sirven
        # solo como valores iniciales de una capa nueva.
        if update:
            if last is None:
                self.status(tr("There is nothing to update"), error=True)
                return False
            replaces, settings = last
        else:
            settings = last[1] if last is not None else (
                headfoot.HeaderFooter() if kind == stamps.HEADER_FOOTER else watermark.Watermark())
        # Called from the right-click menu: the layer goes only on the pages chosen, whatever their parity.
        if pages is not None:
            settings = dataclasses.replace(settings, pages=stamps.compact_pages(pages), parity="all")
        answer = self.ask_layer(kind, settings, pages[0] if pages else self.current_page(),
                                existing=bool(self.pages_with(kind)) and not update)
        if answer is None:
            return False
        settings, keep = answer
        return self.add_stamp(settings, keep, replaces)

    def ask_layer(self, kind: str, settings, page: int, existing: bool = False):
        """(settings, keep) from the dialog of KIND (None if cancelled)."""
        ask = ask_header_footer if kind == stamps.HEADER_FOOTER else ask_watermark
        return ask(self, settings, self.file, self.password, self.page_labels(), page, existing)

    def _change_layers(self, change: Change, message: str) -> bool:
        # The labels are read before the change: a header may print them, and the change runs on another copy.
        current = self.page_labels()
        path = self.path

        def apply(pdf):
            change.apply(pdf, headfoot.document_of(pdf, path, current))

        return self.transform(apply, message=message)

    def add_stamp(self, settings, keep: bool = False, replaces: int | None = None) -> bool:
        """Add SETTINGS (a header and footer, or a watermark) to the pages (a step of the history)."""
        if self.path is None:
            return False
        module = headfoot if settings.KIND == stamps.HEADER_FOOTER else watermark
        try:
            # Se validan antes de tocar el documento, para que un error no deje un paso vacío en el historial.
            settings = module.check(settings)
            stamps.chosen_pages(settings, self.count)
        except LabelError as e:
            self.status(str(e), error=True)
            return False
        return self._change_layers(Change(settings, keep=keep, replaces=replaces),
                                   tr("Header and footer added") if settings.KIND == stamps.HEADER_FOOTER
                                   else tr("Watermark added"))

    def remove_stamps(self, kind: str = stamps.HEADER_FOOTER, pages: list[int] | None = None,
                      bates_only: bool = False) -> bool:
        """Take away the layers of KIND added to the pages (on PAGES, or all; only those with Bates numbers,
        if BATES_ONLY)."""
        if self.path is None or not self.pages_with(kind, bates_only):
            return False
        spec = stamps.compact_pages(pages) if pages else ""
        return self._change_layers(Change(None, kind=kind, pages=spec, bates_only=bates_only), tr("Taken away"))

    def apply_profile(self, name: str, kind: str = stamps.HEADER_FOOTER) -> bool:
        module = headfoot if kind == stamps.HEADER_FOOTER else watermark
        profile = module.read_profiles().get(name)
        return profile is not None and self.add_stamp(profile)

    def _fill_stamp_menu(self, m: QMenu, kind: str):
        m.clear()
        has = self.path is not None
        module = headfoot if kind == stamps.HEADER_FOOTER else watermark
        m.addAction(tr("Add…"), lambda *_: self.stamp_dialog(kind)).setEnabled(has)
        a = m.addAction(tr("Update…"), lambda *_: self.stamp_dialog(kind, update=True))
        a.setToolTip(tr("Change the settings of the last one added"))
        a.setEnabled(has and self.last_added(kind) is not None)
        a = m.addAction(tr("Remove all"), lambda *_: self.remove_stamps(kind))
        a.setToolTip(tr("Take away all those py-pdftools added to this file"))
        a.setEnabled(has and bool(self.pages_with(kind)))
        if kind == stamps.HEADER_FOOTER:
            a = m.addAction(tr("Remove the Bates numbers"), lambda *_: self.remove_stamps(kind, bates_only=True))
            a.setToolTip(tr("Take away only the headers and footers with Bates numbers"))
            a.setEnabled(has and bool(self.pages_with(kind, bates_only=True)))
        # Only the profiles marked to be shown on the menu appear here; the rest are reached from the dialog.
        shown = [p for p in module.read_profiles().values() if p.show_on_menu]
        if shown:
            m.addSection(tr("Profiles"))
            for p in shown:
                m.addAction(p.name, lambda *_, n=p.name: self.apply_profile(n, kind)).setEnabled(has)
        m.setToolTipsVisible(True)

    def batch_dialog(self):
        """Headers and footers, Bates numbers or watermarks on several files at once."""
        # Imported here: the batch dialog is seldom used and pulls in the batch engine.
        from .pages.batch_dialog import BatchDialog

        BatchDialog(self, [self.path] if self.path else [], Path(self.last_dir())).exec()

    # ----------------------------------------------------------------- arranging the pages

    def arrange_pages(self, op: arrange.Operation, ask: bool = True) -> bool:
        """Make OP on the pages (a step of the history); with ASK, ask (if the pages move and have
        labels) what their labels do."""
        if self.path is None:
            return False
        state = self.pages_state()
        ranges = list(state.ranges)
        try:
            # items() raises LabelError for a move that is not possible, before the user is asked about labels.
            if op.moves_pages():
                op.items(self.count)
            if ask and op.moves_pages() and ranges:
                choice = self.labels_choice()
                if choice is None:
                    return False
                op = dataclasses.replace(op, labels=choice)
            # Las etiquetas, la página de apertura y la página mostrada se recalculan antes de cambiar nada,
            # y luego se escriben junto con la operación en un solo paso del historial.
            after = arrange.ranges_after(op, ranges, self.count)
            opening = state.opening
            if opening.page is not None:
                opening = dataclasses.replace(opening, page=arrange.position_after(op, opening.page, self.count))
            page = arrange.position_after(op, self.current_page(), self.count)
        except LabelError as e:
            self.status(str(e), error=True)
            return False

        def apply(pdf):
            op.apply(pdf)
            labels.write_labels(pdf, after)
            view.write_view(pdf, opening)

        return self.transform(apply, page=(page or 1) - 1, message=op.describe())

    def move_pages(self, pages: list[int], before: int, copied: bool = False) -> bool:
        """Move PAGES before page BEFORE (count + 1: to the end); COPIED: copy them there."""
        if not pages:
            return False
        op = arrange.Duplicate(tuple(pages), before) if copied else arrange.Move(tuple(pages), before)
        # Un movimiento que deja todas las páginas en su lugar no es un cambio: no se agrega al historial.
        if not copied and op.items(self.count) == list(range(1, self.count + 1)):
            return False  # (dropped where they were)
        # The count before the move is needed to compute the new order again, after it has changed.
        n = self.count
        if not self.arrange_pages(op):
            return False
        items = op.items(n)
        # Tras mover, se vuelven a seleccionar las páginas en sus nuevos lugares. En una copia, las originales
        # siguen en su sitio y solo se seleccionan las copias (i + 1 != item).
        moved = set(pages)
        self.page_list.clearSelection()
        for i, item in enumerate(items):
            if isinstance(item, int) and item in moved and (not copied or i + 1 != item):
                self.page_list.item(i).setSelected(True)
        first = next(i for i, item in enumerate(items) if item == pages[0] and (not copied or i + 1 != pages[0]))
        self.show_page(first)
        return True

    def files_dropped(self, paths: list[Path], before: int) -> bool:
        """PDFs dropped on the list of pages: their pages inserted there."""
        # Soltar un PDF sin documento abierto lo abre en vez de insertarlo.
        if self.path is None:
            return self.open_path(paths[0])
        choice = arrange.FOLLOW
        if self.ranges:
            choice = self.labels_choice()
            if choice is None:
                return False
        # The labels question is asked once for all the files dropped; each insertion then moves the
        # insertion point past the pages of the previous file.
        done = False
        for path in paths:
            try:
                count = arrange.source_count(str(path))
            except LabelError as e:
                self.status(str(e), error=True)
                continue
            done = self.arrange_pages(arrange.Insert(str(path), (), before, labels=choice), ask=False) or done
            before += count
        return done

    def arrange_dialog(self, mode: str, pages: list[int] | None = None) -> bool:
        """The dialog of an operation on the pages (see pages/arrange_dialog.MODES), and the operation."""
        if self.path is None:
            return False
        value = ask_arrange(self, mode, self.count, pages, self.current_page(), Path(self.last_dir()))
        if value is None:
            return False
        # Extracting and splitting do not change the document: they write new files from it.
        if mode == "extract":
            default = Path(self.last_dir()) / f"{self.path.stem}-{stamps.compact_pages(value)}.pdf"
            name, _ = QFileDialog.getSaveFileName(self, tr("Extract pages"), str(default),
                                                  tr("PDF files (*.pdf)"))
            target = Path(name).with_suffix(".pdf") if name else None
            if target is None or not self.write_parts([(target, value)]):
                return False
            # El PDF nuevo se abre enseguida, en una pestaña junto a este documento
            from .tabs import open_in_tab

            open_in_tab(target, near=self)
            return True
        if mode == "split":
            spec, folder = value
            return self.split_document(spec, folder)
        return self.arrange_pages(value, ask=False)

    def split_document(self, spec: dict, folder: Path) -> bool:
        """The document, as it is now (with its annotations), split into several files in FOLDER as SPEC says
        (see pages/split.py: every so many pages, at pages, at its bookmarks, by size)."""
        from ..pages import split

        whole = self._new_work("-split")
        try:
            annots.write(self.file, self.annotations, whole, self.password, shown=self.layers)
            parts = split.plan(spec, whole, self.password)
        except (AnnotateError, OSError, pikepdf.PdfError, LabelError) as e:
            whole.unlink(missing_ok=True)
            self.status(str(e), error=True)
            return False
        whole.unlink(missing_ok=True)
        names = split.file_names(self.path.stem, parts)
        return self.write_parts([(folder / name, list(range(first, last + 1)))
                                 for name, (first, last, _) in zip(names, parts, strict=True)])

    def write_parts(self, parts: list[tuple[Path, list[int]]]) -> bool:
        """Save some pages, as they are now (with their annotations), as new files: [(target, pages)]."""
        # Las anotaciones viven aparte del PDF de trabajo; se escriben primero en una copia completa
        # y de ella se sacan las partes, para que lleven también las anotaciones.
        whole = self._new_work("-parts")
        try:
            annots.write(self.file, self.annotations, whole, self.password, shown=self.layers)
            state = self.pages_state()
            files.write_parts(whole, list(state.ranges), parts, self.password, state.opening, ())
        except (AnnotateError, OSError, pikepdf.PdfError, LabelError) as e:
            self.status(tr("{path} cannot be written: {error}", path=parts[0][0], error=e), error=True)
            return False
        finally:
            whole.unlink(missing_ok=True)
        self.status(ntr("Saved {count} file: {path}", "Saved {count} files: {path}", len(parts), path=parts[0][0]))
        return True

    def _fill_arrange(self, menu: QMenu):
        """MENU: all the operations on the pages chosen, with their dialogs."""
        menu.clear()
        pages = self.selected_pages() if self.path is not None else []
        for mode, text in ARRANGE_MENU:
            if mode is None:
                menu.addSeparator()
            else:
                menu.addAction(tr(text), lambda *_, md=mode: self.arrange_dialog(md, pages)).setEnabled(
                    self.path is not None)

    def _update_page_actions(self):
        """Which of the actions on the pages chosen can be done now."""
        # Fuera de este modo las acciones están ocultas; no hace falta recalcularlas.
        if self.mode != KIND:
            return
        pages = self.selected_pages() if self.path is not None else []
        for a in self.page_actions:
            a.setEnabled(bool(pages))
        if pages:
            self.a_earlier.setEnabled(pages[0] > 1)
            self.a_later.setEnabled(pages[-1] < self.count)
            self.a_page_delete.setEnabled(len(pages) < self.count)
        for a in (self.a_headfoot, self.a_watermark):
            a.setEnabled(self.path is not None)

    # ----------------------------------------------------------------- the right-click menu of pages

    def pages_menu(self, pos):
        if self.path is None:
            return
        item = self.page_list.itemAt(pos)
        # Al hacer clic derecho sobre una página no seleccionada, se la toma como la elección (como en un gestor
        # de archivos).
        if item is not None and not item.isSelected():
            self.page_list.setCurrentItem(item)
        menu = self.build_pages_menu()
        if menu is not None:
            self.show_menu(menu, self.page_list.viewport().mapToGlobal(pos))

    def pages_title(self, pages: list[int]) -> str:
        """PAGES (1-based) for the heading of their menu: 'Page 3 (iv)', or 'Pages 3–7, 9 (6)'."""
        if len(pages) == 1:
            found = self.page_labels()
            label = found[pages[0] - 1] if pages[0] - 1 < len(found) else ""
            text = tr("Page {page}", page=pages[0])
            return f"{text} ({label})" if label and label != str(pages[0]) else text
        runs, start, last = [], pages[0], pages[0]
        for p in pages[1:] + [None]:
            if p is not None and p == last + 1:
                last = p
                continue
            runs.append(str(start) if start == last else f"{start}–{last}")
            if p is not None:
                start = last = p
        return tr("Pages {pages} ({count})", pages=", ".join(runs), count=len(pages))

    def build_pages_menu(self) -> QMenu | None:
        """The menu of actions on the pages chosen: those used most at its top, the others in submenus by
        kind (moving, inserting, labels, headers and watermarks, more arranging, the view on opening)."""
        pages = self.selected_pages()
        if not pages:
            return None
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        count = len(pages)
        menu.addSection(self.pages_title(pages))
        # Lo que más se hace con unas páginas, a la vista; el resto, agrupado en submenús.
        turn = menu.addMenu(tr("Rotate"))
        for angle, text in ((90, N_("90° clockwise")), (270, N_("90° counterclockwise")), (180, N_("180°"))):
            turn.addAction(tr(text), lambda *_, a=angle: self.arrange_pages(arrange.Rotate(tuple(pages), a)))
        menu.addAction(tr("Duplicate"), lambda *_: self.arrange_pages(arrange.Duplicate(tuple(pages))))
        menu.addAction(tr("Extract pages…"), lambda *_: self.arrange_dialog("extract", pages))
        # Delete is disabled when every page is chosen: the document must keep at least one.
        menu.addAction(tr("Delete"), lambda *_: self.arrange_pages(arrange.Delete(tuple(pages)))).setEnabled(
            count < self.count)
        menu.addSeparator()

        move = menu.addMenu(tr("Move"))
        move.addAction(tr("Move to the start"), lambda *_: self.move_pages(pages, 1)).setEnabled(pages[0] > 1)
        move.addAction(tr("Move to the end"), lambda *_: self.move_pages(pages, self.count + 1)).setEnabled(
            pages[-1] < self.count)
        move.addAction(tr("Move before page…"), lambda *_: self.arrange_dialog("move", pages))
        if count > 1:
            move.addAction(tr("Reverse their order"), lambda *_: self.arrange_pages(arrange.Reverse(tuple(pages))))

        insert = menu.addMenu(tr("Insert"))
        insert.addAction(tr("Insert a blank page before this one") if count == 1 else
                         tr("Insert a blank page before these"),
                         lambda *_: self.arrange_pages(arrange.InsertBlank(pages[0])))
        insert.addAction(tr("Insert a blank page after this one") if count == 1 else
                         tr("Insert blank page after"),
                         lambda *_: self.arrange_pages(arrange.InsertBlank(pages[-1] + 1)))
        insert.addSeparator()
        insert.addAction(tr("Insert pages of a PDF before this one…") if count == 1 else
                         tr("Insert pages from file…"), lambda *_: self.arrange_dialog("insert", pages))
        insert.addAction(tr("Replace pages…"), lambda *_: self.arrange_dialog("replace", pages))

        names = menu.addMenu(tr("Labels"))
        names.addAction(tr("Number these pages…") if count > 1 else tr("Number this page…"), self.number_selected)
        names.addAction(tr("Continue the numbering from before"), self.continue_selected).setEnabled(pages[0] > 1)
        names.addAction(tr("Give them one label…") if count > 1 else tr("Give it a label…"), self.label_selected)
        if count > 1:
            names.addAction(tr("Edit their labels one by one…"), self.edit_selected)
        names.addAction(tr("No label"), lambda: self.set_ranges(labels.relabel(self.ranges, self.count,
                                                                               {p: "" for p in pages})))
        names.addSeparator()
        names.addAction(tr("Start a range at page {page}", page=pages[0]), lambda: self.start_range_at(pages[0]))
        names.addAction(tr("Copy their labels") if count > 1 else tr("Copy its label"), self.copy_labels)

        marks = menu.addMenu(tr("Header, footer and watermark"))
        marks.addAction(tr("Header and footer on these pages…") if count > 1 else
                        tr("Header and footer on this page…"),
                        lambda *_: self.stamp_dialog(stamps.HEADER_FOOTER, pages))
        marks.addAction(tr("Watermark on these pages…") if count > 1 else tr("Watermark on this page…"),
                        lambda *_: self.stamp_dialog(stamps.WATERMARK, pages))
        marks.addSeparator()
        a = marks.addAction(tr("Remove their header and footer") if count > 1 else tr("Remove its header and footer"),
                            lambda *_: self.remove_stamps(stamps.HEADER_FOOTER, pages))
        # "Remove" is enabled only if some page chosen has a layer of that kind.
        a.setEnabled(bool(self.pages_with(stamps.HEADER_FOOTER) & set(pages)))
        a = marks.addAction(tr("Remove their watermark") if count > 1 else tr("Remove its watermark"),
                            lambda *_: self.remove_stamps(stamps.WATERMARK, pages))
        a.setEnabled(bool(self.pages_with(stamps.WATERMARK) & set(pages)))

        self._fill_arrange(menu.addMenu(tr("More page actions")))
        self.add_view_menus(menu.addMenu(tr("Initial view")), pages[0], heading=False)
        return menu

    # ----------------------------------------------------------------- the panel

    def fill_pages_panel(self, select: int | None = None):
        """The table of ranges (the range that starts at page SELECT chosen) and the list of pages
        with their labels, as the document has them now."""
        if self.mode != KIND:
            return
        ranges = self.ranges
        # _building_table silences the signals of the cell widgets while the table is rebuilt: setting their
        # values would otherwise call _edit and change the labels again.
        self._building_table = True
        table = self.ranges_table
        table.setRowCount(0)
        spans = labels.spans(ranges, self.count) if self.count else []
        table.setRowCount(len(spans))
        for row, (r, last) in enumerate(spans):
            # Cada celda editable conecta su señal con _edit; los valores por defecto de la lambda fijan fila,
            # widget y campo de esta iteración.
            for col, w in range_row(r, last, self.count, first_row=row == 0).items():
                if col in FIELDS:
                    field, value = FIELDS[col]
                    edited_signal(w).connect(
                        lambda *_, row=row, w=w, field=field, value=value: self._edit(row, **{field: value(w)}))
                table.setCellWidget(row, col, w)
        fit_columns(table)
        rows = [i for i, (r, _) in enumerate(spans) if r.page == select]
        if rows:
            table.setCurrentCell(rows[0], LABELS)
        self._building_table = False
        # La selección múltiple se conserva tras reconstruir la lista; una selección de una sola página no,
        # porque sigue a la página mostrada.
        chosen = set(self.selected_pages()) if self.page_list.selectedItems() else set()
        pl = self.page_list
        # Signals are blocked while the list is refilled, so that setCurrentRow does not move the page shown.
        pl.blockSignals(True)
        pl.clear()
        # TODO: the whole list is rebuilt on every change; with documents of thousands of pages it could
        # update only the labels that changed.
        for i, label in enumerate(labels.page_labels(ranges, self.count), 1):
            item = QListWidgetItem(f"{i:>5}   {label}")
            item.setToolTip(tr("page {page} of the file: {label}", page=i, label=label or tr("(no label)")))
            pl.addItem(item)
        if self.count:
            pl.setCurrentRow(self.page)
            for p in chosen:
                if p <= self.count and len(chosen) > 1:
                    pl.item(p - 1).setSelected(True)
        pl.blockSignals(False)
        if self.path is not None:
            self.cmd_line.setText(labels.set_command(Path(self.path.name), ranges))
        self._update_page_actions()

    def _range_chosen(self, row: int):
        ranges = self.ranges
        if not self._building_table and 0 <= row < len(ranges):
            self.show_page(ranges[row].page - 1)

    def pages_page_shown(self):
        """(The page shown changed: the list follows it.)"""
        # The list may be shorter than the document for a moment, while it is being rebuilt after a change.
        if self.mode == KIND and self.page_list.currentRow() != self.page and self.page < self.page_list.count():
            self.page_list.blockSignals(True)
            self.page_list.setCurrentRow(self.page)
            self.page_list.blockSignals(False)
            self._update_page_actions()
