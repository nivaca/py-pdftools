"""Buscar mientras se escribe (Buscar, Alt+Mayús+F): un panel pequeño que baja deslizándose desde el borde de
arriba de las páginas, en su esquina derecha, sobre ellas, y vuelve a subir al cerrarse (su botón o Esc). Tiene
la casilla, «Aa» (distinguir mayúsculas), «á» (distinguir acentos), «Todos» (resaltar todos los lugares, o
solo el actual), dónde está el lugar mostrado («2 de 9»), Anterior y Siguiente, y un menú con «Mientras se
escribe» y las otras búsquedas con el mismo texto (el diálogo Buscar y resaltar, o Buscar y censurar, y el panel
Resultados de la búsqueda). Intro y Mayús+Intro van al lugar siguiente y al anterior. La casilla guarda los
últimos textos buscados y se vuelve rojiza cuando el texto no está en el documento. Las demás búsquedas
(Ctrl+F, la casilla de búsqueda rápida, «/») quedan como estaban.

Tiene que ser instantánea. Cada búsqueda va hacia adelante desde la página mostrada y se detiene en el primer
lugar que encuentra, que se muestra enseguida; Siguiente y Anterior buscan igual, desde el lugar actual. Contar
todos los lugares (para «3 de 41» y para resaltarlos) se hace después, por tramos de unos milisegundos cuando
el programa está desocupado, así que nunca demora lo que se escribe. Todo se busca en un índice del texto
(annotate/textindex.py), cuyas páginas se leen una vez, también por tramos, mientras el panel está abierto.
Solo se resaltan las páginas que se ven."""

from __future__ import annotations

import time

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QToolButton,
)

from ..annotate import annots
from ..annotate.textindex import Hit, TextIndex
from ..core.interface import tr

NAME = "findbar"
KEYS = ("Ctrl+F", "/")  # (Ctrl+Shift+F is the dialog Find and highlight)
PAUSE = 30  # (ms after a key before searching: only joins keys typed together)
HISTORY = 15  # (the texts kept in the box's list)
SLICE = 0.008  # (seconds of work at each turn of the event loop, counting or reading ahead: never felt)
SLIDE = 160  # (ms the panel takes to come down, or to go up)
MARGIN = 6  # (pixels between the panel and the top and right edges of the pages)
WIDTH = 520  # (pixels: the panel's width, if the pages leave room for it)


def _button(text: str, icon: str, tip: str, slot=None, checkable: bool = False) -> QToolButton:
    b = QToolButton()
    b.setText(text)
    if icon:
        b.setIcon(QIcon.fromTheme(icon))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setCheckable(checkable)
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if icon and not b.icon().isNull()
                         else Qt.ToolButtonStyle.ToolButtonTextOnly)
    if slot is not None:
        b.clicked.connect(slot)
    return b


class FindBar(QFrame):
    """The panel Find as you type, over the top right of the pages: its box, Aa, á, All, where the place shown
    is, Previous, Next, its menu, and Close."""

    def __init__(self, window):
        super().__init__(window.canvas)
        self.window = window
        self.setObjectName(NAME)
        self.index: TextIndex | None = None
        self.q = None  # (the query being searched, prepared: see TextIndex.query)
        self.hit: Hit | None = None  # (the place shown)
        self.by_page: dict[int, list[Hit]] = {}  # (the places counted so far, by page)
        self.counted: set[int] = set()  # (the pages already counted)
        self.order: list[int] = []  # (the pages still to count, in order)
        self.complete = False  # (every page counted: hits is the whole list)
        self.hits: list[Hit] = []
        self.searching = False
        self.again = False  # (the text changed while a search ran: that one stops, and another starts)
        self.started = self.told = 0.0  # (when the search began, and when it last said how far it got)
        self.closing = False  # (going up: when it is out of sight, it is hidden)

        # Un panel con borde y sombra de la paleta, como las ventanas emergentes: sirve con el tema claro y el oscuro
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        self.setStyleSheet("#findbar { background: palette(window); border: 1px solid palette(mid); "
                           "border-top: none; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 4, 4)
        lay.setSpacing(2)
        # Una casilla con lista: los últimos textos buscados, el más reciente primero
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setMinimumContentsLength(14)
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
        self.o_case = _button("Aa", "", tr("Match case: find only what has the same capitals"), checkable=True)
        self.o_accents = _button("á", "", tr("Match accents: find only what has the same accents (otherwise "
                                            "«cancion» finds «canción»)"), checkable=True)
        self.b_all = _button(tr("All"), "", tr("Highlight every place found on the pages, not only the one shown"),
                             self._all_toggled, checkable=True)
        for b in (self.o_case, self.o_accents, self.b_all):
            lay.addWidget(b)
        self.said = QLabel()
        self.said.setMinimumWidth(70)
        self.said.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # (gris, como el número de páginas: un dato, no un control)
        self.said.setStyleSheet("color: palette(placeholder-text); padding: 0 4px;")
        lay.addWidget(self.said)
        self.b_previous = _button("↑", "go-up", tr("The previous place found (Shift+Enter)"), lambda: self.step(-1))
        self.b_next = _button("↓", "go-down", tr("The next place found (Enter)"), lambda: self.step(1))
        lay.addWidget(self.b_previous)
        lay.addWidget(self.b_next)
        # El menú del panel: buscar mientras se escribe, y las otras búsquedas con este texto
        more = _button("⋯", "", tr("More"))
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.setToolTipsVisible(True)
        self.o_typing = QAction(tr("As you type"), self, checkable=True)
        self.o_typing.setToolTip(tr("Search again at every letter typed or deleted (otherwise, with Enter)"))
        menu.addAction(self.o_typing)
        menu.addSeparator()
        self.b_dialog = menu.addAction(tr("Find and highlight…"), self.open_dialog)
        self.b_dialog.setToolTip(tr("The dialog with every option, with this text (Ctrl+F)"))
        self.b_all_places = menu.addAction(tr("Find all…"), self.open_results)
        self.b_all_places.setToolTip(tr("Every place of this text, listed in the panel Search results"))
        more.setMenu(menu)
        lay.addWidget(more)
        close = _button("✕", "window-close", tr("Close (Esc)"), self.close_bar)
        lay.addWidget(close)

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
        # Contar los lugares y leer por adelantado: un tramo en cada vuelta, mientras el programa está desocupado
        self.worker = QTimer(self)
        self.worker.setInterval(0)
        self.worker.timeout.connect(self._work)
        # Bajar y subir: la posición, animada
        self.slide = QPropertyAnimation(self, b"pos", self)
        self.slide.setDuration(SLIDE)
        self.slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.slide.finished.connect(self._slid)
        # (el panel sigue la esquina de las páginas cuando la ventana cambia de tamaño, o aparece o se va la barra
        # de desplazamiento, que cambia el ancho de lo que se ve)
        # (guardados: al cerrar la ventana, Qt borra las páginas antes que este panel, y no se les pregunta nada)
        self.watched = (window.canvas, window.canvas.viewport())
        for widget in self.watched:
            widget.installEventFilter(self)
        self.hide()

    def text(self) -> str:
        return self.box.text()

    def options(self) -> tuple[bool, bool]:
        return self.o_case.isChecked(), self.o_accents.isChecked()

    # ----------------------------------------------------------------- opening and closing

    def _place(self) -> tuple[QPoint, QPoint]:
        """Where the panel is, down (open) and up (out of sight): the top right of the pages, left of the
        scroll bar; and its size, as the pages allow."""
        canvas = self.window.canvas
        view = canvas.viewport().geometry()  # (in the canvas: without its scroll bars)
        width = max(min(WIDTH, view.width() - 2 * MARGIN), 200)
        self.setFixedSize(width, self.sizeHint().height())  # (fixed: showing it doesn't give it another size)
        x = view.right() - self.width() - MARGIN + 1
        return QPoint(x, view.top()), QPoint(x, view.top() - self.height() - 2)

    def open_bar(self):
        """The panel comes down, with the cursor in its box (with the words selected on the page, if there are)."""
        canvas = self.window.canvas
        chosen = canvas.selected_text().strip() if getattr(canvas, "text_sel", None) else ""
        down, up = self._place()
        if not self.isVisible() or self.closing:
            self.closing = False
            self.slide.stop()
            self.move(up if not self.isVisible() else self.pos())
            self.show()
            self.raise_()
            self.slide.setStartValue(self.pos())
            self.slide.setEndValue(down)
            self.slide.start()
            self._index()
            self.worker.start()
        if chosen and "\n" not in chosen:
            self.box.setText(chosen)
        self.box.setFocus()
        self.box.selectAll()
        if self.text().strip():
            self.run()  # (the highlights again, if it was closed with a text in it)

    def close_bar(self):
        """The panel goes up, and the highlights go with it."""
        if not self.isVisible() or self.closing:
            return
        self.closing = True
        self._closed()
        _down, up = self._place()
        self.slide.stop()
        self.slide.setStartValue(self.pos())
        self.slide.setEndValue(up)
        self.slide.start()
        self.window.canvas.setFocus()

    def _slid(self):
        if self.closing:
            self.closing = False
            self.hide()

    def _closed(self):
        # (ningún resaltado queda en las páginas, y nada sigue trabajando)
        self.timer.stop()
        self.worker.stop()
        self.again = self.searching
        self.keep_text()
        self.window.canvas.set_found(None, (), None)

    def eventFilter(self, obj, event) -> bool:
        if any(obj is w for w in getattr(self, "watched", ())):  # (la casilla ya filtra antes de que existan)
            if event.type() == QEvent.Type.Resize and self.isVisible() and not self.closing:
                self.slide.stop()
                self.move(self._place()[0])
            return False
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

    def _edited(self, _text: str):
        if self.o_typing.isChecked():
            self.timer.start()
        else:  # (sin buscar mientras se escribe: lo hallado ya no es de este texto)
            self._forget()
            self._show(None, quiet=True)

    def _forget(self):
        self.q, self.hit = None, None
        self.by_page, self.counted, self.order, self.hits, self.complete = {}, set(), [], [], False

    def _stop(self) -> bool:
        # (entre una página leída y la siguiente: lo que se escribió entretanto se atiende, y manda)
        now = time.perf_counter()
        if now - self.started > 0.15 and now - self.told > 0.1 and self.index is not None:
            # Una búsqueda larga (un texto que no está, en un documento aún sin leer) dice por dónde va
            self.told = now
            self.said.setText(tr("Looking… page {page} of {count}", page=len(self.index.pages),
                                 count=self.index.doc.page_count))
        QApplication.processEvents()
        return self.again

    def run(self):
        """Search the text of the box, forward from the page shown, and show the first place found at once;
        counting the others is left for later (see _work)."""
        if self.searching:
            self.again = True  # (the running search stops at its next page; then this one runs)
            return
        self.timer.stop()
        index = self._index()
        text = self.text()
        self._forget()
        if index is None or not text.strip() or not self.isVisible() or self.closing:
            self._show(None)
            return
        q = index.query(text, *self.options())
        self.q = q
        self.searching, self.again = True, False
        self.started = self.told = time.perf_counter()
        try:
            hit = index.next_hit(q, self.window.page, 0, 1, stop=self._stop)
        finally:
            self.searching = False
        if self.again:
            # (el texto cambió, o la barra se cerró, mientras buscaba: otra búsqueda, con lo de ahora)
            self.again = False
            if self.isVisible():
                self.timer.start(0)
            return
        # El conteo empieza por la página del lugar mostrado, que así se resalta primero
        only = index.candidates(q)
        n = index.doc.page_count
        start = hit.page if hit is not None else 0
        self.order = [p for p in (list(range(start, n)) + list(range(0, start))) if only is None or p in only]
        self._show(hit)
        self.worker.start()

    def _work(self):
        """A slice of work, while the program is idle: counting the places of the text, or else reading pages
        ahead for the next search."""
        index = self.index
        if index is None or self.searching:
            self.worker.stop()
            return
        end = time.perf_counter() + SLICE
        if self.q is not None and self.order:
            found = []
            while self.order and time.perf_counter() < end:
                number = self.order.pop(0)
                hits = index.page_hits(number, self.q)
                self.counted.add(number)
                if hits:
                    self.by_page[number] = hits
                    found.append(number)
            if found and self.b_all.isChecked():
                self.window.canvas.add_found(found)
            if not self.order:
                self._counted()
            return
        if not index.read_some_for(end):
            self.worker.stop()

    def _counted(self):
        """Every page counted: the whole list, and where the place shown is in it."""
        self.hits = [h for p in sorted(self.by_page) for h in self.by_page[p]]
        self.complete = True
        if self.index is not None and self.q is not None:
            self.index.finished(self.q, set(self.by_page))
        self._say()

    def _enter(self):
        shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        self.step(-1 if shift else 1)

    def step(self, by: int):
        """The next place found (BY 1) or the previous one (BY -1); the text is searched first if it wasn't."""
        if self.searching:
            return
        self.keep_text()
        index = self._index()
        if index is None:
            return
        if self.timer.isActive() or self.q != index.query(self.text(), *self.options()):
            self.run()
            return
        if self.hit is None:
            return
        if self.complete and self.hits:
            k = self.hits.index(self.hit) if self.hit in self.hits else 0
            self._show(self.hits[(k + by) % len(self.hits)])
            return
        # (aún contando: el siguiente se busca desde el actual, como el primero)
        h = self.hit
        hit = index.next_hit(self.q, h.page, h.start + 1 if by > 0 else h.start, by)
        self._show(hit or h)

    def _all_toggled(self):
        self.window.settings.setValue("findbar_all", self.b_all.isChecked())
        self._show(self.hit, move=False)

    def _rects_of(self, page: int) -> list:
        index = self.index
        if index is None:
            return []
        return [r for h in self.by_page.get(page, ()) for r in index.rects(h)]

    def _show(self, hit: Hit | None, move: bool = True, quiet: bool = False):
        self.hit = hit
        canvas = self.window.canvas
        rects = list(self.index.rects(hit)) if hit is not None and self.index is not None else []
        canvas.set_found(self._rects_of, self.by_page.keys() if self.b_all.isChecked() else (),
                         (hit.page, rects) if hit is not None else None)
        if hit is not None and move and rects:
            self.window.remember_place()
            canvas.go_to(hit.page, annots.union(rects))
        self.b_next.setEnabled(hit is not None)
        self.b_previous.setEnabled(hit is not None)
        self._say(quiet)

    def _say(self, quiet: bool = False):
        text = self.text().strip()
        hit = self.hit
        if not text or quiet:
            self.said.setText("")
        elif hit is None:
            self.said.setText(tr("Not found"))
        elif self.complete and hit in self.hits:
            self.said.setText(tr("{n} of {count}", n=self.hits.index(hit) + 1, count=len(self.hits)))
        else:  # (contando todavía)
            labels = self.window.page_labels()
            name = labels[hit.page] if hit.page < len(labels) and labels[hit.page] else str(hit.page + 1)
            self.said.setText(tr("Found on page {page}", page=name))
        self._mark_box(bool(text) and hit is None and not quiet)

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
        self.index = None
        self._forget()
        if self.isVisible():
            self._index()
            self.worker.start()
            if self.text().strip():
                self.timer.start()


def keys() -> list[QKeySequence]:
    return [QKeySequence(k) for k in KEYS]
