"""A preview of a PDF, a page at a time, drawn with PyMuPDF (as the window draws its pages): the
result of an imposition. (py-imposition drew it with QtPdf, which py-pdftools does without.)"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from ...core.interface import ntr, tr


class PdfPane(QWidget):
    """A titled PDF viewer with page navigation and zoom controls."""

    output_selected = Signal(int)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.doc: pymupdf.Document | None = None
        self.path: Path | None = None
        self.fit = "page"  # 'page', 'width', or '' (the zoom given: ZOOM)
        self.zoom = 1.0

        self.title = QLabel(f"<b>{title}</b>")
        self.info = QLabel("")
        # may shrink (the full text is in the tooltip), so the window fits small screens
        self.info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.info.setMinimumWidth(40)
        self.outputs = QComboBox()
        self.outputs.setVisible(False)
        # Cuando un comando escribe varios archivos, este menú elige cuál se ve; el panel avisa y el espacio
        # de trabajo carga el archivo.
        self.outputs.currentIndexChanged.connect(self.output_selected.emit)
        self.page = QSpinBox()
        self.page.setAccessibleName(tr("Page"))
        self.page.setMinimum(1)
        self.page.setPrefix(tr("page "))
        self.page.setEnabled(False)
        self.page.valueChanged.connect(lambda _: self._draw())

        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.picture)
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea { background: palette(dark); }")
        # Al cambiar el tamaño del panel se redibuja con 50 ms de retraso, una vez y no por cada píxel.
        self._redraw = QTimer(self, singleShot=True, interval=50)
        self._redraw.timeout.connect(self._draw)

        zoom = QToolButton()
        zoom.setText(tr("Zoom"))
        zoom.setToolTip(tr("Fit the page or its width, or zoom in and out (also Ctrl+wheel)"))
        zoom.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(zoom)
        menu.addAction(tr("Fit page"), lambda: self.set_zoom("page"))
        menu.addAction(tr("Fit width"), lambda: self.set_zoom("width"))
        menu.addSeparator()
        menu.addAction(tr("Zoom in"), lambda: self.zoom_by(1.25))
        menu.addAction(tr("Zoom out"), lambda: self.zoom_by(1 / 1.25))
        zoom.setMenu(menu)

        top = QHBoxLayout()
        top.addWidget(self.title)
        top.addWidget(self.outputs)
        top.addWidget(self.info, 1)
        top.addWidget(self.page)
        top.addWidget(zoom)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(top)
        lay.addWidget(self.scroll, 1)
        self.clear("")

    # ----------------------------------------------------------------- loading

    def load(self, path: Path | None, note: str = ""):
        """Show PATH. A new version of what is shown (a result made again, which is always written
        to the same folder) stays on the page being looked at; another document starts at page 1."""
        # Todos los resultados se escriben en la carpeta temporal del espacio de trabajo: si el archivo nuevo
        # está en la misma carpeta que el anterior, se trata como otra versión del mismo resultado.
        keep = self.path is not None and path is not None and path.parent == self.path.parent
        before = self.page.value() if keep else 1
        self._close()
        self.path = path
        if path is None:
            self.clear(note)
            return
        try:
            self.doc = pymupdf.open(path)
        # pymupdf raises FileDataError for a damaged file and RuntimeError for other failures; either is shown
        # as the note.
        except (pymupdf.FileDataError, RuntimeError) as e:
            self.clear(str(e))
            return
        n = self.doc.page_count
        # Blocked so that setting the range and value does not draw the page before the document is ready.
        self.page.blockSignals(True)
        self.page.setMaximum(max(n, 1))
        self.page.setValue(min(before, max(n, 1)))
        self.page.setSuffix(f" / {n}")
        self.page.setEnabled(n > 1)
        self.page.blockSignals(False)
        r = self.doc[0].rect if n else None
        # El tamaño se da en centímetros, a partir de la primera página (72 puntos por pulgada, 2,54 cm por pulgada).
        dims = f"{r.width / 72 * 2.54:.1f} × {r.height / 72 * 2.54:.1f} cm" if r else ""
        self.info.setText(ntr("{name} — {count} page", "{name} — {count} pages", n, name=path.name)
                          + (", " + dims if dims else "") + (" — " + note if note else ""))
        self.info.setToolTip(self.info.text())
        self._draw()

    def _close(self):
        if self.doc is not None:
            self.doc.close()
            self.doc = None

    def clear(self, note: str):
        self._close()
        self.path = None
        self.page.setEnabled(False)
        self.page.setSuffix("")
        self.info.setText(note)
        self.picture.clear()

    def set_outputs(self, names: list[str]):
        # Sin señales mientras se rellena la lista, para no pedir otra salida en medio del cambio.
        self.outputs.blockSignals(True)
        self.outputs.clear()
        self.outputs.addItems(names)
        self.outputs.setVisible(len(names) > 1)
        self.outputs.blockSignals(False)

    # ----------------------------------------------------------------- drawing

    def _scale(self, page: pymupdf.Page) -> float:
        room = self.scroll.viewport().size()
        r = page.rect
        if self.fit == "page":
            # A margin of a few pixels keeps the scroll bars from appearing when the page fits exactly; 0.05 is
            # the smallest zoom, for very large sheets in a small pane.
            return max(min((room.width() - 16) / r.width, (room.height() - 16) / r.height), 0.05)
        if self.fit == "width":
            return max((room.width() - 24) / r.width, 0.05)
        return self.zoom

    def _draw(self):
        if self.doc is None or not self.doc.page_count:
            return
        # Se dibuja con la densidad real de la pantalla (devicePixelRatio), así la página se ve nítida
        # en pantallas HiDPI.
        page = self.doc[min(self.page.value(), self.doc.page_count) - 1]
        scale = self._scale(page)
        ratio = self.devicePixelRatioF() or 1.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale * ratio, scale * ratio), alpha=False)
        # copy() detaches the image from pymupdf's buffer, which is freed with the pixmap.
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
        picture = QPixmap.fromImage(image)
        picture.setDevicePixelRatio(ratio)
        self.picture.setPixmap(picture)
        # El zoom real queda guardado, así acercar o alejar desde un ajuste parte de lo que se ve.
        self.zoom = scale

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Only a fitted zoom depends on the size of the pane; a fixed zoom needs no redraw.
        if self.fit:
            self._redraw.start()

    def set_zoom(self, mode: str):
        self.fit = mode
        self._draw()

    def zoom_by(self, factor: float):
        self.fit = ""
        # Zoom limits: from 5 % to 2000 %.
        self.zoom = max(0.05, min(self.zoom * factor, 20))
        self._draw()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        # Las flechas y Re Pág / Av Pág pasan de página solo cuando el panel tiene el foco.
        if event.key() in (Qt.Key.Key_PageDown, Qt.Key.Key_Right):
            self.page.setValue(min(self.page.value() + 1, self.page.maximum()))
        elif event.key() in (Qt.Key.Key_PageUp, Qt.Key.Key_Left):
            self.page.setValue(max(self.page.value() - 1, 1))
        else:
            super().keyPressEvent(event)
