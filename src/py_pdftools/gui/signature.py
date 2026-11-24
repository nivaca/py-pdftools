"""La firma a mano: dibujada una vez (con el lápiz de una tableta o el ratón) o tomada de una imagen (una firma
escaneada o fotografiada), guardada, y puesta en los documentos con la herramienta Firma. La dibujada va como un
dibujo (sus trazos, en la configuración); la imagen, como un sello de imagen, en signature.png de la carpeta de
configuración, con el fondo blanco o del papel vuelto transparente y recortada a la firma misma. Se usa la que
se eligió la última vez (SOURCE)."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout, QWidget

from ..annotate.annots import smooth_segments
from ..core.interface import tr

Strokes = list[list[tuple[float, float]]]
# Se guarda normalizada: así no depende del tamaño que tenía el panel de dibujo al firmar.
KEY = "signature"  # (in what the window keeps, see state.py: the strokes, as JSON, in a box of width 1)
SOURCE = "signature_source"  # ('drawn' or 'picture': which of the two the Signature tool puts)
PICTURE = "signature.png"  # (in the configuration folder)
LARGEST = 1600  # (pixels: a larger picture is made smaller, keeping its proportions)
# El papel de una foto rara vez es blanco: bajo la luz de una lámpara sale gris, a veces azulado, y más oscuro en
# un rincón. Por eso el umbral no es fijo: se mide en cada imagen (véase paper_level)
PAPER_MARGIN = 28  # (greys down to this much darker than the paper's own are paper too: shadows, unevenness)
INK_SPAN = 80  # (from there, this much darker again is ink, fully opaque; between the two, partly)


def paper_level(gray) -> int:
    """How light the paper of the picture GRAY (a grey pixmap) is: the median grey, since most of a picture of
    a signature is paper. Measured on a small copy, quickly."""
    import pymupdf

    small = pymupdf.Pixmap(gray, 0) if gray.alpha else pymupdf.Pixmap(gray)
    while small.width * small.height > 40000:
        small.shrink(1)
    data = bytes(small.samples)
    counts = [data.count(bytes([v])) for v in range(256)]
    half, seen = len(data) / 2, 0
    for v, n in enumerate(counts):
        seen += n
        if seen >= half:
            return v
    return 255


class SignatureError(Exception):
    """A file that can't be read as a picture of a signature."""


def picture_path():
    from ..core import config

    return config.config_dir() / PICTURE


def source(settings) -> str:
    """Which signature the tool puts: 'picture' if one was chosen last and is there, else 'drawn'."""
    if str(settings.value(SOURCE, "drawn")) == "picture" and picture_path().is_file():
        return "picture"
    return "drawn"


WIDTH = "signature_width"  # (in points: how wide the Signature tool puts it with a click)


def width(settings, default: float) -> float:
    """The usual width of the signature on the page, in points."""
    try:
        value = float(settings.value(WIDTH, default))
    except (TypeError, ValueError):
        return default
    return value if 20 <= value <= 600 else default


def picture() -> tuple[bytes, float] | None:
    """The PNG of the signature's picture, and its height for a width of 1; None if there is none."""
    import pymupdf

    try:
        data = picture_path().read_bytes()
        pix = pymupdf.Pixmap(data)
    except (OSError, RuntimeError, ValueError, pymupdf.mupdf.FzErrorBase):
        return None
    return data, pix.height / max(pix.width, 1)


def on_white(pix):
    """PIX (with its own transparency) as it looks on a white page: a PNG of a signature already made
    transparent keeps, under its transparent pixels, colours that aren't seen, often black; taking the
    transparency away without this turns the picture into its negative."""
    import pymupdf
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage, QPainter

    source = QImage.fromData(pix.tobytes("png"))
    page = QImage(source.size(), QImage.Format.Format_RGB32)
    page.fill(Qt.GlobalColor.white)
    painter = QPainter(page)
    painter.drawImage(0, 0, source)
    painter.end()
    out = QByteArray()
    buffer = QBuffer(out)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    page.save(buffer, "PNG")
    flat = pymupdf.Pixmap(bytes(out.data()))
    return pymupdf.Pixmap(flat, 0) if flat.alpha else flat


def prepared(path, transparent: bool = True) -> bytes:
    """The picture at PATH as a signature, a PNG: made smaller if it is very large, the paper made transparent
    (if TRANSPARENT: the lighter a pixel, the more transparent, so the edges of the strokes stay soft), and cut
    to what is drawn. SignatureError if it can't be read, or nothing is drawn on it."""
    import pymupdf

    try:
        pix = pymupdf.Pixmap(str(path))
    except (RuntimeError, ValueError, pymupdf.mupdf.FzErrorBase) as e:
        raise SignatureError(tr("{path} can't be read as a picture: {error}", path=str(path), error=e)) from None
    if pix.alpha:
        pix = on_white(pix)
    if pix.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    while max(pix.width, pix.height) > LARGEST:
        pix.shrink(1)
    gray = pix if pix.n == 1 else pymupdf.Pixmap(pymupdf.csGRAY, pix)
    paper = max(paper_level(gray) - PAPER_MARGIN, 60)  # (lighter than this: paper)
    ink = max(paper - INK_SPAN, 0)  # (darker than this: ink)
    if transparent:
        # Cuanto más claro, más transparente: una tabla de 256 valores aplicada a todos los píxeles de una vez
        table = bytes(0 if v >= paper else 255 if v <= ink else round(255 * (paper - v) / (paper - ink))
                      for v in range(256))
    else:
        table = bytes([255]) * 256
    alpha = bytes(gray.samples).translate(table)
    color = pymupdf.Pixmap(pix, 1)  # (con un canal alfa)
    color.set_alpha(alpha)
    # Recortada a lo dibujado: las filas y columnas con algo que no es papel
    w, h = gray.width, gray.height
    # (para recortar cuenta solo lo claramente oscuro: unas motas débiles del papel, casi invisibles, no deben
    # agrandar el recorte; los bordes suaves de los trazos quedan, con su transparencia)
    middle = (paper + ink) // 2
    drawn = bytes(gray.samples).translate(bytes(0 if v >= middle else 1 for v in range(256)))
    rows = [y for y in range(h) if drawn[y * w:(y + 1) * w].strip(b"\0")]
    if not rows:
        raise SignatureError(tr("Nothing is drawn on {path}: is it a picture of a signature?", path=str(path)))
    left = min(len(drawn[y * w:(y + 1) * w]) - len(drawn[y * w:(y + 1) * w].lstrip(b"\0")) for y in rows)
    right = max(len(drawn[y * w:(y + 1) * w].rstrip(b"\0")) for y in rows)
    margin = max(2, w // 200)
    box = pymupdf.IRect(max(left - margin, 0), max(rows[0] - margin, 0), min(right + margin, w),
                        min(rows[-1] + 1 + margin, h))
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage

    image = QImage.fromData(color.tobytes("png")).copy(box.x0, box.y0, box.width, box.height)
    out = QByteArray()
    buffer = QBuffer(out)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(out.data())


def store_picture(settings, data: bytes) -> None:
    """Keep DATA (a PNG made by prepared) as the signature, and choose it for the Signature tool (if SETTINGS:
    without them, only kept, as when the picture is chosen to sign digitally)."""
    path = picture_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    if settings is not None:
        settings.setValue(SOURCE, "picture")


def load(settings) -> Strokes:
    # A damaged or hand-edited value gives no signature rather than an error.
    try:
        strokes = json.loads(settings.value(KEY, "") or "[]")
        return [[(float(x), float(y)) for x, y in stroke] for stroke in strokes if stroke]
    except (TypeError, ValueError):
        return []


def store(settings, strokes: Strokes) -> None:
    settings.setValue(KEY, json.dumps(normalized(strokes)))
    settings.setValue(SOURCE, "drawn")


def normalized(strokes: Strokes) -> Strokes:
    """STROKES moved to (0, 0) and scaled so that the larger of their width and height is 1 (the other
    in proportion)."""
    points = [p for stroke in strokes for p in stroke]
    if not points:
        return []
    x0, y0 = min(p[0] for p in points), min(p[1] for p in points)
    # Se divide por la mayor de las dos medidas, no solo por el ancho: una firma más alta que ancha
    # también cabe en 1. El 1e-6 evita dividir por cero con un solo punto.
    width = max(max(p[0] for p in points) - x0, max(p[1] for p in points) - y0, 1e-6)
    return [[(round((x - x0) / width, 5), round((y - y0) / width, 5)) for x, y in stroke] for stroke in strokes]


class Pad(QWidget):
    """Where the signature is drawn."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.strokes: Strokes = []
        self.setMinimumSize(480, 180)
        # WA_StaticContents: on resize only the new area is repainted.
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        # Cada pulsación empieza un trazo nuevo; con cualquier botón, no solo el izquierdo.
        p = event.position()
        self.strokes.append([(p.x(), p.y())])
        self.update()

    def mouseMoveEvent(self, event):
        if self.strokes and event.buttons() & Qt.MouseButton.LeftButton:
            p = event.position()
            last = self.strokes[-1][-1]
            # Distancia Manhattan de 1,5 px como mínimo: menos puntos, y la curva sale más suave.
            if abs(p.x() - last[0]) + abs(p.y() - last[1]) >= 1.5:
                self.strokes[-1].append((p.x(), p.y()))
                self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        p.setPen(QPen(Qt.GlobalColor.lightGray, 1, Qt.PenStyle.DashLine))
        # A dashed baseline at three quarters of the height, as on a form, to sign above it.
        base = self.height() * 0.75
        p.drawLine(QPointF(20, base), QPointF(self.width() - 20, base))
        pen = QPen(Qt.GlobalColor.darkBlue, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        for stroke in self.strokes:
            # A stroke of one or two points is drawn as a dot here, since smooth_segments needs three;
            # on the page (paint.py) a stroke of two points is a line.
            if len(stroke) < 3:
                p.drawPoint(QPointF(*stroke[0]))
                continue
            path = QPainterPath(QPointF(*stroke[0]))
            # Las mismas curvas que usará la anotación en el PDF (annots.smooth_segments): se ve como quedará.
            for c1, c2, end in smooth_segments(stroke):
                path.cubicTo(QPointF(*c1), QPointF(*c2), QPointF(*end))
            p.drawPath(path)

    def clear(self):
        self.strokes = []
        self.update()


class SignatureDialog(QDialog):
    """My signature: drawn here, with the pen or the mouse, or taken from a picture (Use a picture…). OK keeps
    the one shown, and the Signature tool puts that one."""

    def __init__(self, parent=None, width_points: float = 120.0):
        from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QHBoxLayout, QStackedWidget

        super().__init__(parent)
        self.setWindowTitle(tr("My signature"))
        self.kind = "drawn"  # (which one is shown, and kept with OK: 'drawn' or 'picture')
        self.picture_data: bytes | None = None
        self.picture_file = ""
        lay = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        # Dos páginas: el panel para dibujar, o la imagen elegida
        self.pages = QStackedWidget()
        self.pad = Pad(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(420, 160)
        # (sobre blanco, como una página: la firma se ve como quedará en un documento)
        self.preview.setStyleSheet("background: #ffffff; border: 1px solid palette(mid);")
        self.pages.addWidget(self.pad)
        self.pages.addWidget(self.preview)
        lay.addWidget(self.pages, 1)
        self.transparent = QCheckBox(tr("Make the paper transparent"))
        self.transparent.setChecked(True)
        self.transparent.setToolTip(tr("The white (or the colour of the paper) around the signature is taken "
                                       "away, so that it sits on the page like ink"))
        self.transparent.toggled.connect(lambda _on: self._load_picture())
        lay.addWidget(self.transparent)
        # El ancho de siempre en la página, en centímetros (se guarda en puntos: 72 por pulgada)
        self.width_cm = QDoubleSpinBox(minimum=1.0, maximum=20.0, singleStep=0.5, decimals=1, suffix=" cm")
        self.width_cm.setValue(round(width_points / 72 * 2.54, 1))
        self.width_cm.setToolTip(tr("How wide the Signature tool puts it with a click; drag a box with the tool to "
                                    "make it as wide as the box, or drag its corners afterwards"))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Width on the page:")))
        row.addWidget(self.width_cm)
        row.addStretch(1)
        lay.addLayout(row)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #c0392b;")
        lay.addWidget(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.b_picture = QPushButton(tr("Use a picture…"))
        self.b_picture.setToolTip(tr("A scan or a photo of your signature (PNG, JPEG…)"))
        self.b_picture.clicked.connect(self.choose_picture)
        self.b_draw = QPushButton(tr("Draw it"))
        self.b_draw.setToolTip(tr("Draw your signature here, with the pen or the mouse"))
        self.b_draw.clicked.connect(lambda: self.show_kind("drawn"))
        self.b_clear = QPushButton(tr("Clear"))
        self.b_clear.clicked.connect(self.pad.clear)
        for b in (self.b_picture, self.b_draw, self.b_clear):
            buttons.addButton(b, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.show_kind("drawn")

    def width_points(self) -> float:
        return round(self.width_cm.value() / 2.54 * 72, 1)

    def show_kind(self, kind: str):
        """Show the pad ('drawn') or the picture ('picture'), with what to do."""
        self.kind = kind
        drawn = kind == "drawn"
        self.pages.setCurrentWidget(self.pad if drawn else self.preview)
        self.b_draw.setVisible(not drawn)
        self.b_clear.setVisible(drawn)
        self.transparent.setVisible(not drawn)
        self.problem.setText("")
        self.note.setText(tr("Sign above the line, with the pen or the mouse, or use a picture of your signature. "
                             "It is kept on this computer only, in the settings of py-pdftools, and put on "
                             "documents with the Signature tool.") if drawn else
                          tr("Your signature, from {file}. It is kept on this computer only, in the settings of "
                             "py-pdftools, and put on documents with the Signature tool.",
                             file=Path(self.picture_file).name))

    def choose_picture(self) -> bool:
        from PySide6.QtWidgets import QFileDialog

        name, _ = QFileDialog.getOpenFileName(self, tr("A picture of your signature"), str(Path.home()),
                                              tr("Pictures (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)"))
        return bool(name) and self.use_picture(name)

    def use_picture(self, path) -> bool:
        """The picture at PATH, as the signature shown (and kept with OK)."""
        self.picture_file = str(path)
        if not self._load_picture():
            return False
        self.show_kind("picture")
        return True

    def _load_picture(self) -> bool:
        if not self.picture_file:
            return False
        from PySide6.QtGui import QPixmap

        try:
            self.picture_data = prepared(self.picture_file, self.transparent.isChecked())
        except SignatureError as e:
            self.picture_data = None
            self.problem.setText(str(e))
            return False
        shown = QPixmap()
        shown.loadFromData(self.picture_data)
        self.preview.setPixmap(shown.scaled(self.preview.size() * 0.9, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
        self.problem.setText("")
        return True

    def strokes(self) -> Strokes:
        # Los trazos vacíos no deberían existir, pero se filtran por si acaso antes de guardar.
        return [s for s in self.pad.strokes if s]
