"""La ventana de Comparar visualmente (Archivo > Comparar): dos PDF página a página, con lo que difiere a la vista
(pages/visual.py). Lado a lado, cada par de páginas con las zonas distintas enmarcadas en las dos; superpuestas,
este documento en rojo y el otro en azul, en negro lo que coincide. Se pasa de página en página, o a la
siguiente (o anterior) página con diferencias, que se buscan al pedirlas. Compara los archivos tal como están
guardados; ninguno se cambia."""

from __future__ import annotations

import html

import pymupdf
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
)

from ..core.interface import tr
from ..pages import visual

GAP = 16  # (between the two pages side by side, in pixels)
MARK = QColor(229, 57, 53)  # (the frames of what differs)


class VisualCompare(QDialog):
    """HERE and THERE (open documents, closed with the window) page by page; their names, HERE_NAME and
    THERE_NAME, say which is which."""

    def __init__(self, window, here, there, here_name: str, there_name: str):
        super().__init__(window)
        self.setWindowFlag(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("Compare visually: {here} and {there}", here=here_name, there=there_name))
        self.here, self.there = here, there
        self.names = (here_name, there_name)
        self.count = max(here.page_count, there.page_count)
        self.found: dict[int, list] = {}  # (page -> the rectangles that differ; computed when asked)
        self.page = 0
        self.how = QComboBox()
        self.how.addItem(tr("Side by side"), "side")
        self.how.addItem(tr("Overlay"), "overlay")
        self.how.setToolTip(tr("Side by side, with what differs framed; or one over the other, this document in "
                               "red and the other in blue, in black what they have in common"))
        self.how.currentIndexChanged.connect(lambda _: self.show_page(self.page))
        self.number = QSpinBox()
        self.number.setRange(1, self.count)
        self.number.setSuffix(" / {}".format(self.count))
        self.number.setAccessibleName(tr("Page"))
        self.number.valueChanged.connect(lambda n: self.show_page(n - 1))
        buttons = []
        for text, tip, slot in ((tr("Previous difference"), tr("The last page before this one that differs"),
                                 lambda: self.go_difference(-1)),
                                (tr("Next difference"), tr("The next page that differs"),
                                 lambda: self.go_difference(1))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            buttons.append(b)
        self.b_previous, self.b_next = buttons
        self.legend = QLabel(tr('<span style="color:#e53935">■</span> {here} &nbsp; '
                                '<span style="color:#1e88e5">■</span> {there}', here=html.escape(here_name),
                                there=html.escape(there_name)))
        self.said = QLabel()
        self.said.setAccessibleName(tr("What differs on this page"))
        top = QHBoxLayout()
        top.addWidget(self.how)
        top.addWidget(QLabel(tr("Page")))
        top.addWidget(self.number)
        top.addWidget(self.b_previous)
        top.addWidget(self.b_next)
        top.addStretch(1)
        top.addWidget(self.legend)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.picture.setAccessibleName(tr("The two pages"))
        self.area = QScrollArea()
        self.area.setWidget(self.picture)
        self.area.setWidgetResizable(True)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.said)
        lay.addWidget(self.area, 1)
        # (al cambiar el tamaño, la página se vuelve a dibujar a su medida, una vez quieta la ventana)
        self.redraw = QTimer(self, singleShot=True, interval=150)
        self.redraw.timeout.connect(lambda: self.show_page(self.page))
        self.resize(int(window.width() * 0.9), int(window.height() * 0.9))
        self.show_page(0)

    # ----------------------------------------------------------------- the pages

    def _pages(self, n: int):
        return (self.here[n] if n < self.here.page_count else None,
                self.there[n] if n < self.there.page_count else None)

    def differences(self, n: int) -> list:
        """What differs on page N (rectangles in points), computed once."""
        if n not in self.found:
            self.found[n] = visual.differences(*self._pages(n))
        return self.found[n]

    def show_page(self, n: int):
        n = max(0, min(n, self.count - 1))
        self.page = n
        if self.number.value() != n + 1:
            self.number.blockSignals(True)
            self.number.setValue(n + 1)
            self.number.blockSignals(False)
        rects = self.differences(n)
        here, there = self._pages(n)
        if here is None or there is None:
            self.said.setText(tr("Page {page} is only in {name}", page=n + 1,
                                 name=self.names[0] if here is not None else self.names[1]))
        elif rects:
            self.said.setText(tr("Page {page}: {count} places differ", page=n + 1, count=len(rects)))
        else:
            self.said.setText(tr("Page {page}: no difference", page=n + 1))
        image = self.overlay(here, there) if self.how.currentData() == "overlay" else self.side(here, there, rects)
        self.picture.setPixmap(QPixmap.fromImage(image))

    def _scale(self, width_points: float) -> float:
        """The scale (pixels per point) at which WIDTH_POINTS fill the width of the view."""
        room = max(self.area.viewport().width() - 8, 200)
        return max(0.2, min(room / max(width_points, 1.0), 4.0))

    def side(self, here, there, rects: list) -> QImage:
        """The two pages side by side, what differs framed on both."""
        pages = [here, there]
        width = sum(p.rect.width for p in pages if p is not None) or 1
        scale = self._scale(width + GAP)
        ratio = self.devicePixelRatioF()
        images = [_image(p, scale * ratio) if p is not None else None for p in pages]
        widths = [round(p.rect.width * scale) if p is not None else 0 for p in pages]
        height = max(round(p.rect.height * scale) for p in pages if p is not None)
        out = QImage(round((sum(widths) + GAP) * ratio), round(height * ratio), QImage.Format.Format_RGB32)
        out.setDevicePixelRatio(ratio)
        out.fill(self.palette().window().color())
        p = QPainter(out)
        x = 0
        for page, image, w in zip(pages, images, widths, strict=True):
            if image is not None:
                p.drawImage(QRectF(x, 0, w, page.rect.height * scale), image)
                pen = QPen(MARK, 2)
                p.setPen(pen)
                p.setBrush(QBrush(QColor(MARK.red(), MARK.green(), MARK.blue(), 40)))
                for x0, y0, x1, y1 in rects:
                    p.drawRect(QRectF(x + x0 * scale, y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale))
            x += w + GAP
        p.end()
        return out

    def overlay(self, here, there) -> QImage:
        """One page over the other: this document in red, the other in blue, black where both are."""
        pages = [p for p in (here, there) if p is not None]
        width = max(p.rect.width for p in pages)
        scale = self._scale(width)
        ratio = self.devicePixelRatioF()
        height = max(p.rect.height for p in pages)
        out = QImage(round(width * scale * ratio), round(height * scale * ratio), QImage.Format.Format_RGB32)
        out.fill(QColor("white"))
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        for page, colour in ((here, visual.RED), (there, visual.BLUE)):
            pix = visual.tinted(page, colour, scale * ratio)
            if pix is not None:
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                p.drawImage(0, 0, image)
        p.end()
        out.setDevicePixelRatio(ratio)
        return out

    # ----------------------------------------------------------------- moving

    def go_difference(self, step: int) -> bool:
        """To the next page that differs (STEP 1) or the previous one (STEP -1), looking for it page by page;
        False if there is none."""
        n = self.page + step
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            while 0 <= n < self.count:
                if n not in self.found and n % 10 == 0:  # (cada diez páginas, dónde va la búsqueda)
                    self.said.setText(tr("Looking… page {page} of {count}", page=n + 1, count=self.count))
                    QApplication.processEvents()
                if self.differences(n):
                    self.show_page(n)
                    return True
                n += step
        finally:
            QApplication.restoreOverrideCursor()
        self.said.setText(tr("No more pages differ") if step > 0 else tr("No page before this one differs"))
        return False

    def keyPressEvent(self, event):
        # Re Pág y Av Pág pasan las páginas, como en la ventana principal.
        if event.key() == Qt.Key.Key_PageDown:
            self.show_page(self.page + 1)
        elif event.key() == Qt.Key.Key_PageUp:
            self.show_page(self.page - 1)
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.redraw.start()

    def done(self, result: int):
        # (Esc, o la × de la ventana: los dos documentos se cierran con ella)
        for doc in (self.here, self.there):
            if not doc.is_closed:
                doc.close()
        super().done(result)

    def closeEvent(self, event):
        self.done(0)
        super().closeEvent(event)


def _image(page, scale: float) -> QImage:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
