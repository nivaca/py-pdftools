"""Los iconos propios del programa (icons/actions/*.svg), para cuando el tema de iconos del escritorio no trae
uno con ese nombre: cada uno se dibuja desde su SVG en el momento de mostrarse, con los colores de la interfaz
de ese momento. Sobre un fondo oscuro, sus trazos oscuros (el gris de las líneas, el casi negro, el azul
marino de Firma) cambian por otros claros; así el icono se lee en los dos temas, y cambia con ellos sin
volver a cargarse."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QByteArray, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QIconEngine, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Colores oscuros de los SVG propios y los que los sustituyen sobre un fondo oscuro. El gris secundario
# (#9ca3af) se oscurece un poco: el principal se aclara más que él, y deben seguir distinguiéndose.
DARK = {"#6b7280": "#b4bac5", "#9ca3af": "#7d8593", "#1d1f24": "#eceff4", "#374151": "#dde1e8",
        "#4b5563": "#c9ced6", "#1a237e": "#a5b4fc", "#2e7d32": "#5cb860", "#c62828": "#ef5350"}
# (dark marks on a light fill of the icon itself stay as they are: the letters on Highlight's yellow)
ON_FILL = {"draw-highlight": {"#1d1f24"}, "highlight-area": {"#4b5563"}}
_COLOUR = re.compile("|".join(re.escape(c) for c in DARK), re.IGNORECASE)


def dark_interface() -> bool:
    """Whether the interface is dark now (its windows' colour, whatever made it so: the program's theme or
    the desktop's)."""
    return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128


def for_dark(svg: str, name: str = "") -> str:
    """SVG (the text of the icon NAME) with its dark colours made light, for a dark background."""
    keep = ON_FILL.get(name, set())
    return _COLOUR.sub(lambda m: m.group(0) if m.group(0).lower() in keep else DARK[m.group(0).lower()], svg)


class OwnIconEngine(QIconEngine):
    """An icon of icons/actions, drawn from its SVG each time, in the colours of the interface then."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = Path(path)
        self._renderers: dict[bool, QSvgRenderer] = {}

    def _renderer(self) -> QSvgRenderer:
        dark = dark_interface()
        if dark not in self._renderers:
            text = self.path.read_text(encoding="utf-8")
            if dark:
                text = for_dark(text, self.path.stem)
            self._renderers[dark] = QSvgRenderer(QByteArray(text.encode("utf-8")))
        return self._renderers[dark]

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State):
        painter.save()
        if mode == QIcon.Mode.Disabled:  # (a disabled button's icon, faint)
            painter.setOpacity(painter.opacity() * 0.4)
        self._renderer().render(painter, rect)
        painter.restore()

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State, scale: float) -> QPixmap:
        # (on a screen of a scale above 1, the pixels are more: the picture is drawn at that many, not enlarged)
        pixmap = QPixmap(QSize(max(1, round(size.width() * scale)), max(1, round(size.height() * scale))))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        return pixmap

    def actualSize(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QSize:
        return size

    def clone(self) -> QIconEngine:
        return OwnIconEngine(self.path)

    def key(self) -> str:
        return "py-pdftools-own"


def own_icon(path: Path) -> QIcon:
    """The icon of the SVG at PATH (one of icons/actions), in the colours of the interface when it shows."""
    return QIcon(OwnIconEngine(path))
