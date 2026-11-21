"""Búsqueda rápida: una casilla en la barra Buscar que busca un texto en el documento y va de un lugar
encontrado al siguiente (Intro) o al anterior (Mayús+Intro), sin abrir el diálogo ni anotar nada. No
distingue mayúsculas ni acentos. Como la casilla de la página, es una acción propia (QuickFindAction), que
puede ponerse en cualquier barra o quitarse en Personalizar las barras."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget, QWidgetAction

from ..annotate import annots
from ..annotate.search import Match, find_text
from ..core.interface import tr


class QuickFindAction(QWidgetAction):
    """The quick find box: Enter goes to the next place found, Shift+Enter to the previous, Esc back to
    the pages."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setText(tr("Quick find"))
        self.setToolTip(tr("Find a text in the document: Enter goes to the next place, Shift+Enter to the "
                           "previous one (Ctrl+Shift+F)"))
        self.matches: list[Match] = []
        self.current = -1  # (el lugar mostrado, en matches; -1 si ninguno)
        self.searched = None  # (the document and the text of the last search, to search again only if they change)
        self.cache: dict = {}
        self.cache_doc = None
        self.searching = False

    def createWidget(self, parent) -> QWidget:
        """A box for a toolbar PARENT (Qt asks for one for each toolbar the action is put on)."""
        widget = QWidget(parent)
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(4, 0, 4, 0)
        box = QLineEdit(widget)
        box.setObjectName("quickfind")
        box.setPlaceholderText(tr("Find in the text"))
        box.setClearButtonEnabled(True)
        box.setFixedWidth(180)
        box.setToolTip(self.toolTip())
        box.returnPressed.connect(lambda: self.step(box))
        box.textChanged.connect(lambda text: self._changed(text))
        box.installEventFilter(self)
        found = QLabel(widget)
        found.setObjectName("found")
        # (gris, como el número de páginas: un dato, no un control)
        found.setStyleSheet("color: palette(placeholder-text); padding-left: 4px;")
        lay.addWidget(box)
        lay.addWidget(found)
        return widget

    def eventFilter(self, obj, event) -> bool:
        # Esc devuelve el foco a las páginas, como Intro en la casilla de la página
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.key() == Qt.Key.Key_Escape:
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()  # (the key is the box's: no shortcut of the window takes it first)
                return False
            self.window.canvas.setFocus()
            return True
        return False

    def boxes(self) -> list[QLineEdit]:
        return [b for w in self.createdWidgets() if (b := w.findChild(QLineEdit, "quickfind")) is not None]

    def focus(self) -> bool:
        """Put the cursor in a box that can be seen (False if none can)."""
        for box in self.boxes():
            if box.isVisible() and box.isEnabled():
                box.setFocus()
                box.selectAll()
                return True
        return False

    def _changed(self, text: str):
        # Cada casilla muestra el mismo texto; una búsqueda nueva empieza de cero.
        for box in self.boxes():
            if box.text() != text:
                box.blockSignals(True)
                box.setText(text)
                box.blockSignals(False)
        self.matches, self.current, self.searched = [], -1, None
        self._say("")

    def _say(self, text: str):
        for w in self.createdWidgets():
            label = w.findChild(QLabel, "found")
            if label is not None:
                label.setText(text)

    def search(self, text: str) -> bool:
        """The places of TEXT in the document (again only if the document or the text changed)."""
        doc = self.window.doc
        if doc is None or not text.strip():
            self.matches, self.current = [], -1
            return False
        if self.searched == (id(doc), text):
            return True
        if self.cache_doc is not doc:  # (another document: its pages are read again)
            self.cache, self.cache_doc = {}, doc
        self.searching = True

        def progress(done, total):
            self._say(tr("Looking… page {page} of {count}", page=done, count=total))
            QApplication.processEvents()
            return True

        try:
            self.matches = find_text(doc, text, None, accents=True, progress=progress, cache=self.cache)
        finally:
            self.searching = False
        self.current, self.searched = -1, (id(doc), text)
        return True

    def step(self, box: QLineEdit | None = None, by: int | None = None):
        """Go to the next place found (BY 1) or the previous one (BY -1); Enter is 1, Shift+Enter -1."""
        if self.searching:
            return
        if by is None:
            shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
            by = -1 if shift else 1
        text = box.text() if box is not None else (self.boxes()[0].text() if self.boxes() else "")
        if not self.search(text):
            self._say("")
            return
        if not self.matches:
            self._say(tr("Not found"))
            return
        if self.current < 0:
            # La primera vez, el primer lugar desde la página mostrada (o el último antes de ella, hacia atrás)
            page = self.window.page
            after = [n for n, m in enumerate(self.matches) if m.page >= page]
            before = [n for n, m in enumerate(self.matches) if m.page < page]
            if by > 0:
                self.current = after[0] if after else 0
            else:
                self.current = before[-1] if before else len(self.matches) - 1
        else:
            self.current = (self.current + by) % len(self.matches)
        m = self.matches[self.current]
        self.window.remember_place()
        self.window.canvas.flash(m.page, annots.union(m.rects))
        self._say(f"{self.current + 1}/{len(self.matches)}")
