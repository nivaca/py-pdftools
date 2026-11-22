"""The toolbar Page navigation, as in other PDF viewers: First page, Previous page, the box of the page
("12 of 180") and Next page, Last page, at the bottom of the window. Its box is an action of its own
(PageNumberAction), so that, like the buttons, it can be put on any toolbar, or taken off, in Customize the
toolbars: each toolbar it is on gets a box of its own, and all of them show the page in view."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget, QWidgetAction

from ..core.interface import tr

NAME = "pagenav"  # (the object name of the toolbar, which keeps its place between sessions)


class PageNumberAction(QWidgetAction):
    """The box of the page shown, which takes a page number or a label (such as iv), and how many pages
    there are."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setText(tr("Page number"))
        self.setToolTip(tr("The page shown: type a page label (such as iv) or a number, and press Enter"))
        self.text_shown = ""
        self.count = 0
        self.details = ""  # (los detalles de la página mostrada: el consejo del número de páginas)

    def createWidget(self, parent) -> QWidget:
        """A box for a toolbar PARENT (Qt asks for one for each toolbar the action is put on)."""
        widget = QWidget(parent)
        # (de su tamaño justo: si no, empuja los botones que la siguen al otro extremo de la barra)
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(4, 0, 4, 0)
        box = QLineEdit(widget)
        box.setObjectName("page")
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setFixedWidth(64)
        box.setToolTip(self.toolTip())
        box.returnPressed.connect(lambda: self._typed(box))
        # Al salir sin pulsar Intro, la casilla vuelve a mostrar la página visible
        box.editingFinished.connect(lambda: box.setText(self.text_shown))
        of = QLabel(widget)
        of.setObjectName("count")
        # (gris: un dato, no un control)
        of.setStyleSheet("color: palette(placeholder-text);")
        lay.addWidget(box)
        lay.addWidget(of)
        self._fill(widget)
        return widget

    def _typed(self, box: QLineEdit):
        if self.window.doc is not None:
            self.window.go_to_typed(box.text())
        box.clearFocus()  # (de vuelta a las páginas, como al usar los botones)
        self.window.canvas.setFocus()

    def _fill(self, widget: QWidget):
        box = widget.findChild(QLineEdit, "page")
        if box is not None and not box.hasFocus():
            box.setText(self.text_shown)
        of = widget.findChild(QLabel, "count")
        if of is not None:
            of.setText(tr("of {count}", count=self.count) if self.count else "")
            of.setToolTip(self.details or tr("How many pages the document has"))

    def boxes(self) -> list[QLineEdit]:
        """The boxes of the page, one for each toolbar the action is on."""
        return [b for w in self.createdWidgets() if (b := w.findChild(QLineEdit, "page")) is not None]

    def show_page(self, text: str, count: int, details: str = ""):
        """The page in view is TEXT (its label, or its number) of COUNT pages, whose DETAILS (size,
        orientation) are the tip of the count: every box shows it."""
        self.text_shown, self.count, self.details = text, count, details
        for widget in self.createdWidgets():
            self._fill(widget)
