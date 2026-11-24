"""La barra Buscar mientras se escribe (Editar, Alt+Mayús+F): una barra de herramientas siempre abajo, encima de
la barra de estado, que se cierra con su botón o con Esc. Con «Mientras se escribe» marcado, cada letra escrita o
borrada busca otra vez, y la vista va al primer lugar desde la página mostrada; Intro y Siguiente van al
siguiente, Mayús+Intro y Anterior al anterior. «Todos» resalta todos los lugares encontrados (si no, solo el
actual). «Mayúsculas» y «Acentos» deciden si cuentan las mayúsculas y los acentos. La casilla guarda los
últimos textos buscados y se vuelve rojiza cuando el texto no está en el documento. Dos botones llevan a las
otras búsquedas con el mismo texto: el diálogo Buscar y resaltar (o Buscar y censurar) y el panel Resultados
de la búsqueda. Las demás búsquedas (Ctrl+F, la casilla de búsqueda rápida, «/») quedan como estaban.

Tiene que ser muy rápida: busca en un índice del texto (annotate/textindex.py), que se lee por adelantado,
unas páginas cada vez, mientras la barra está abierta; una búsqueda en mil páginas ya leídas tarda unos
milisegundos. Si una página aún no se leyó, la búsqueda atiende los eventos entre una y otra, y si el texto
cambia entretanto se detiene y empieza otra. Solo se resaltan las páginas que se ven."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel, QSizePolicy, QToolBar, QToolButton, QWidget,
)

from ..annotate import annots
from ..annotate.textindex import Hit, TextIndex
from ..core.interface import tr

NAME = "findbar"  # (the toolbar's object name: the customizer of the toolbars leaves it alone)
KEY = "Alt+Shift+F"
PAUSE = 60  # (ms after a key before searching: a search takes a few ms, this only joins fast keys)
HISTORY = 15  # (the texts kept in the box's list)
AHEAD_PAGES = 12  # (pages read ahead at each turn of the event loop while the bar is open)


def _button(text: str, icon: str, tip: str, slot) -> QToolButton:
    b = QToolButton()
    b.setText(text)
    if icon:
        b.setIcon(QIcon.fromTheme(icon))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if icon
                         else Qt.ToolButtonStyle.ToolButtonTextOnly)
    b.clicked.connect(slot)
    return b


class FindBar(QToolBar):
    """The toolbar Find as you type: its box, Next, Previous, All, As you type, Match case, Match accents, the
    buttons to the other searches, how many places were found, and Close."""

    def __init__(self, window):
        super().__init__(tr("Find as you type"), window)
        self.window = window
        self.setObjectName(NAME)
        # Siempre abajo: ni se arrastra a otro borde ni se saca de la ventana
        self.setAllowedAreas(Qt.ToolBarArea.BottomToolBarArea)
        self.setFloatable(False)
        self.setMovable(False)
        self.hits: list[Hit] = []
        self.by_page: dict[int, list[Hit]] = {}
        self.current = -1  # (the place shown, in hits; -1: none)
        self.index: TextIndex | None = None
        self.searching = False
        self.again = False  # (the text changed while a search ran: that one stops, and another starts)
        self.searched = None  # (the document, text and options of the last search)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay = QHBoxLayout(inner)
        lay.setContentsMargins(2, 0, 2, 0)
        close = _button("", "window-close", tr("Close this toolbar (Esc)"), self.close_bar)
        close.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        if close.icon().isNull():
            close.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_TitleBarCloseButton))
        lay.addWidget(close)
        lay.addWidget(QLabel(tr("Find:")))
        # Una casilla con lista: los últimos textos buscados, el más reciente primero
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setMinimumContentsLength(24)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.setAccessibleName(tr("Find as you type"))
        self.box = self.combo.lineEdit()
        self.box.setObjectName("findbar_box")
        self.box.setPlaceholderText(tr("Find in the text"))
        self.box.setClearButtonEnabled(True)
        self.box.textEdited.connect(self._edited)
        self.combo.textActivated.connect(lambda _: self.run())  # (un texto elegido de la lista)
        self.box.returnPressed.connect(self._enter)
        self.box.installEventFilter(self)
        lay.addWidget(self.combo, 1)
        self.b_next = _button(tr("Next"), "go-down", tr("The next place found (Enter)"), lambda: self.step(1))
        self.b_previous = _button(tr("Previous"), "go-up", tr("The previous place found (Shift+Enter)"),
                                  lambda: self.step(-1))
        self.b_all = _button(tr("All"), "", tr("Highlight every place found on the pages, not only the one shown"),
                             self._all_toggled)
        self.b_all.setCheckable(True)
        for b in (self.b_next, self.b_previous, self.b_all):
            lay.addWidget(b)
        self.o_typing = QCheckBox(tr("As you type"))
        self.o_typing.setToolTip(tr("Search again at every letter typed or deleted (otherwise, with Enter)"))
        self.o_case = QCheckBox(tr("Match case"))
        self.o_case.setToolTip(tr("Find only what has the same capitals"))
        self.o_accents = QCheckBox(tr("Match accents"))
        self.o_accents.setToolTip(tr("Find only what has the same accents (otherwise «cancion» finds «canción»)"))
        for box in (self.o_typing, self.o_case, self.o_accents):
            lay.addWidget(box)
        self.b_dialog = _button(tr("Find and highlight…"), "edit-find",
                                tr("The dialog with every option, with this text (Ctrl+F)"), self.open_dialog)
        self.b_all_places = _button(tr("Find all…"), "edit-find-replace",
                                    tr("Every place of this text, listed in the panel Search results"),
                                    self.open_results)
        lay.addWidget(self.b_dialog)
        lay.addWidget(self.b_all_places)
        self.said = QLabel()
        self.said.setMinimumWidth(90)
        # (gris, como el número de páginas: un dato, no un control)
        self.said.setStyleSheet("color: palette(placeholder-text); padding-left: 4px;")
        lay.addWidget(self.said)
        self.addWidget(inner)

        settings = window.settings
        self.o_typing.setChecked(bool(settings.value("findbar_typing", True, type=bool)))
        self.o_case.setChecked(bool(settings.value("findbar_case", False, type=bool)))
        self.o_accents.setChecked(bool(settings.value("findbar_accents", False, type=bool)))
        self.b_all.setChecked(bool(settings.value("findbar_all", True, type=bool)))
        self.o_typing.toggled.connect(lambda on: settings.setValue("findbar_typing", on))
        self.o_case.toggled.connect(lambda on: (settings.setValue("findbar_case", on), self.run()))
        self.o_accents.toggled.connect(lambda on: (settings.setValue("findbar_accents", on), self.run()))
        history = settings.value("findbar_history", [])
        if isinstance(history, list):
            self.combo.addItems([t for t in history if isinstance(t, str) and t.strip()][:HISTORY])
        self.combo.setCurrentIndex(-1)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(PAUSE)
        self.timer.timeout.connect(self.run)
        # La lectura por adelantado: unas páginas en cada vuelta, mientras la barra está abierta
        self.reader = QTimer(self)
        self.reader.setInterval(0)
        self.reader.timeout.connect(self._read_ahead)
        self.visibilityChanged.connect(self._visibility)
        self.hide()

    def text(self) -> str:
        return self.box.text()

    def options(self) -> tuple[bool, bool]:
        return self.o_case.isChecked(), self.o_accents.isChecked()

    # ----------------------------------------------------------------- opening and closing

    def open_bar(self):
        """Show the bar with the cursor in its box (with the words selected on the page, if there are)."""
        canvas = self.window.canvas
        chosen = canvas.selected_text().strip() if getattr(canvas, "text_sel", None) else ""
        self.show()
        if chosen and "\n" not in chosen:
            self.box.setText(chosen)
        self.box.setFocus()
        self.box.selectAll()
        if self.text().strip():
            self.run()  # (the highlights again, if it was closed with a text in it)

    def close_bar(self):
        self.hide()
        self.window.canvas.setFocus()

    def _visibility(self, shown: bool):
        if shown:
            self._index()
            self.reader.start()
            return
        # (cerrada por su botón, por Esc o desde el menú de las barras: ningún resaltado queda en las páginas)
        self.timer.stop()
        self.reader.stop()
        self.again = self.searching
        self.keep_text()
        self.window.canvas.set_found(None, (), None)

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.key() == Qt.Key.Key_Escape:
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()  # (the key is the box's: no shortcut of the window takes it first)
                return False
            self.close_bar()
            return True
        return False

    def keep_text(self):
        """The text of the box first in its list (and in the settings), if it isn't empty."""
        text = self.text().strip()
        if not text:
            return
        items = [text] + [self.combo.itemText(i) for i in range(self.combo.count()) if self.combo.itemText(i) != text]
        items = items[:HISTORY]
        typed = self.text()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(items)
        self.combo.setCurrentIndex(0)
        self.box.setText(typed)  # (lo escrito queda como estaba, con sus espacios)
        self.combo.blockSignals(False)
        self.window.settings.setValue("findbar_history", items)

    # ----------------------------------------------------------------- searching

    def _index(self) -> TextIndex | None:
        """The index of the document shown (a new one if the document is another)."""
        doc = self.window.doc
        if doc is None:
            self.index = None
        elif self.index is None or self.index.doc is not doc:
            self.index = TextIndex(doc)
        return self.index

    def _read_ahead(self):
        index = self._index()
        if self.searching or index is None or not index.read_some(AHEAD_PAGES):
            self.reader.stop()

    def _edited(self, _text: str):
        if self.o_typing.isChecked():
            self.timer.start()
        else:  # (sin buscar mientras se escribe: lo hallado ya no es de este texto)
            self.searched = None
            self._show([], -1, quiet=True)

    def run(self):
        """Search the text of the box in the whole document, and show the first place from the page shown."""
        if self.searching:
            self.again = True  # (the running search stops at its next page; then this one runs)
            return
        self.timer.stop()
        index = self._index()
        text = self.text()
        if index is None or not text.strip() or not self.isVisible():
            self.searched = None
            self._show([], -1)
            return
        case, accents = self.options()
        page = self.window.page
        self.searching, self.again = True, False
        shown = [False]

        def progress(done, total, found):
            # (solo con páginas aún no leídas: se dice cuánto falta, y el primer lugar se muestra en cuanto aparece)
            if found and not shown[0]:
                shown[0] = True
                self._show(sorted(found), self._first(sorted(found), page), count=False)
            if total > 50 and done % 20 == 0:
                self.said.setText(tr("Looking… page {page} of {count}", page=done, count=total))
            QApplication.processEvents()
            return not self.again

        try:
            hits = index.search(text, case, page, progress, accents=accents)
        finally:
            self.searching = False
        if self.again:
            # (el texto cambió, o la barra se cerró, mientras buscaba: lo hallado no vale)
            self.again = False
            if self.isVisible():
                self.timer.start(0)
            return
        self.searched = (id(index.doc), text, case, accents)
        # (si el primer lugar ya se mostró mientras buscaba, la vista no se mueve otra vez)
        first = self._first(hits, page)
        if shown[0] and 0 <= self.current < len(self.hits):
            first = hits.index(self.hits[self.current]) if self.hits[self.current] in hits else first
        self._show(hits, first, move=not shown[0])
        if not index.complete():
            self.reader.start()

    @staticmethod
    def _first(hits: list[Hit], page: int) -> int:
        """The first place on PAGE or after it (or the very first), in HITS; -1 if there are none."""
        if not hits:
            return -1
        return next((n for n, h in enumerate(hits) if h.page >= page), 0)

    def _enter(self):
        shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        self.step(-1 if shift else 1)

    def step(self, by: int):
        """The next place found (BY 1) or the previous one (BY -1); the text is searched first if it wasn't."""
        if self.searching:
            return
        self.keep_text()
        doc = self.window.doc
        if self.timer.isActive() or self.searched != (id(doc), self.text(), *self.options()):
            self.run()
            return
        if self.hits:
            self._show(self.hits, (self.current + by) % len(self.hits))

    def _all_toggled(self):
        self.window.settings.setValue("findbar_all", self.b_all.isChecked())
        self._show(self.hits, self.current, move=False)

    def _rects_of(self, page: int) -> list:
        index = self.index
        if index is None:
            return []
        return [r for h in self.by_page.get(page, ()) for r in index.rects(h)]

    def _show(self, hits: list[Hit], current: int, move: bool = True, quiet: bool = False, count: bool = True):
        self.hits, self.current = hits, current
        by_page: dict[int, list[Hit]] = {}
        for h in hits:
            by_page.setdefault(h.page, []).append(h)
        self.by_page = by_page
        here = hits[current] if 0 <= current < len(hits) and self.index is not None else None
        canvas = self.window.canvas
        rects = list(self.index.rects(here)) if here is not None else []
        canvas.set_found(self._rects_of, by_page.keys() if self.b_all.isChecked() else (),
                         (here.page, rects) if here is not None else None)
        if here is not None and move and rects:
            self.window.remember_place()
            canvas.go_to(here.page, annots.union(rects))
        self.b_next.setEnabled(bool(hits))
        self.b_previous.setEnabled(bool(hits))
        text = self.text().strip()
        if not text or quiet:
            self.said.setText("")
        elif not hits:
            self.said.setText(tr("Not found"))
        elif count:
            self.said.setText(tr("{n} of {count}", n=current + 1, count=len(hits)))
        self._mark_box(bool(text) and not hits and not quiet)

    def _mark_box(self, missing: bool):
        """The box reddish when the text isn't in the document."""
        palette = QPalette(self.palette())  # (the bar's own, never changed: the box's usual colours)
        if missing:
            base = palette.color(QPalette.ColorRole.Base)
            red = QColor(220, 50, 50)
            # (mezclado con el fondo de la casilla: sirve con el tema claro y con el oscuro)
            palette.setColor(QPalette.ColorRole.Base, QColor((base.red() * 2 + red.red()) // 3,
                                                             (base.green() * 2 + red.green()) // 3,
                                                             (base.blue() * 2 + red.blue()) // 3))
        self.box.setPalette(palette)
        self.box.setProperty("missing", missing)

    # ----------------------------------------------------------------- the other searches

    def open_dialog(self):
        """The dialog Find and highlight (or Find and redact, in the mode Redact), with this text."""
        self.keep_text()
        if self.window.mode == "redact":
            self.window.redact_find_dialog()
        else:
            self.window.find_dialog(self.text().strip())

    def open_results(self):
        """The panel Search results, with every place of this text."""
        self.keep_text()
        w = self.window
        w.results_dock.show()
        w.results_dock.raise_()
        if self.text().strip():
            w.results_box.setText(self.text().strip())
            w.list_results()

    def mode_changed(self):
        """The button to the dialog says what the dialog of the mode does (highlight, or redact)."""
        self.b_dialog.setText(self.window.a_find.text())

    def document_changed(self):
        """The document changed (another one, or its pages): what was found is no longer where it was."""
        self.index, self.searched = None, None
        self.hits, self.by_page, self.current = [], {}, -1
        if self.isVisible():
            self._index()
            self.reader.start()
            if self.text().strip():
                self.timer.start()


def key() -> QKeySequence:
    return QKeySequence(KEY)
