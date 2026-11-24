"""La firma a mano: las firmas guardadas (la firma entera, las iniciales…), cada una dibujada una vez (con el
lápiz de una tableta o el ratón) o tomada de una imagen (una firma escaneada o fotografiada), y puestas en los
documentos con la herramienta Firma. La lista va en la configuración (KEPT): de cada una, su nombre, sus trazos
si es dibujada y su ancho en la página; la imagen, en la carpeta signatures/ de la configuración, con el fondo
blanco o del papel vuelto transparente y recortada a la firma misma. La herramienta pone la elegida (CHOSEN);
una firma digital visible puede mostrar cualquiera de ellas."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout, QWidget

from ..annotate.annots import smooth_segments
from ..core.interface import tr

Strokes = list[list[tuple[float, float]]]
KEPT = "signatures"  # (in what the window keeps, see state.py: the signatures, as a JSON list; see Kept)
CHOSEN = "signature_chosen"  # (the id of the one the Signature tool puts)
FOLDER = "signatures"  # (in the configuration folder: the pictures, <id>.png)
WIDTH = "signature_width"  # (in points: the usual width, for a signature that doesn't have its own)
# De las versiones que guardaban una sola firma: se pasan a la lista la primera vez (véase _from_before), y se
# dejan donde estaban
OLD_STROKES = "signature"  # (the strokes, as JSON, in a box of width 1)
OLD_SOURCE = "signature_source"  # ('drawn' or 'picture')
OLD_PICTURE = "signature.png"  # (in the configuration folder)
INK = Qt.GlobalColor.darkBlue  # (a drawn signature, made a picture: the colour of the pad)
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



def negative(pix) -> bool:
    """Whether PIX, a stored picture of a signature, is its negative: mostly dark and opaque, where the paper
    should be transparent or light. Pictures kept before on_white() existed came out so from a PNG already
    transparent; one of them is not used (the picture is asked for again)."""
    import pymupdf

    if not pix.alpha:
        return False
    # Ni el papel transparente (alfa 0) ni el papel opaco (claro) cuentan: solo lo opaco y oscuro
    gray = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.Pixmap(pix, 0)) if pix.n > 2 else pymupdf.Pixmap(pix, 0)
    alpha = pix.samples[pix.n - 1::pix.n]
    dark = sum(1 for g, a in zip(gray.samples, alpha) if a > 200 and g < 100)
    return dark > len(alpha) // 2


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



# ----------------------------------------------------------------- the signatures kept


@dataclass
class Kept:
    """A signature kept: its NAME; drawn (its STROKES, in a box of width 1) or a PICTURE (its PNG in the folder,
    or DATA while it isn't kept yet; FILE, the picture it was made from, to make it again, TRANSPARENT or not);
    and its WIDTH on the page, in points (0: the usual one)."""

    id: str
    name: str
    kind: str = "drawn"  # ('drawn' or 'picture')
    strokes: Strokes = field(default_factory=list)
    width: float = 0.0
    file: str = ""
    transparent: bool = True
    data: bytes | None = None

    def as_json(self) -> dict:
        d = {"id": self.id, "name": self.name, "kind": self.kind}
        if self.kind == "drawn":
            d["strokes"] = self.strokes
        else:
            d.update(file=self.file, transparent=self.transparent)
        if self.width:
            d["width"] = self.width
        return d


def folder() -> Path:
    from ..core import config

    return config.config_dir() / FOLDER


def picture_path(kid: str) -> Path:
    return folder() / f"{kid}.png"


def _strokes(value) -> Strokes:
    # Un valor dañado o editado a mano no da firma, en lugar de un error
    try:
        return [[(float(x), float(y)) for x, y in stroke] for stroke in value if stroke]
    except (TypeError, ValueError):
        return []


def kept(settings) -> list[Kept]:
    """The signatures kept, in their order (those of a version that kept only one, the first time)."""
    raw = settings.value(KEPT, None)
    if raw is None:
        return _from_before(settings)
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return []
    out = []
    for d in items if isinstance(items, list) else []:
        try:
            kind = "picture" if d.get("kind") == "picture" else "drawn"
            out.append(Kept(str(d["id"]), str(d.get("name") or ""), kind, _strokes(d.get("strokes") or []),
                            float(d.get("width") or 0), str(d.get("file") or ""), bool(d.get("transparent", True))))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return out


def _from_before(settings) -> list[Kept]:
    """The one signature of an earlier version, drawn or a picture (or both), as the first of the list. A
    picture kept as its negative (see negative) is left out: it is asked for again."""
    import pymupdf

    from ..core import config

    try:
        strokes = _strokes(json.loads(settings.value(OLD_STROKES, "") or "[]"))
    except (TypeError, ValueError):
        strokes = []
    entries = [Kept("1", tr("Signature"), "drawn", strokes)] if strokes else []
    try:
        data = (config.config_dir() / OLD_PICTURE).read_bytes()
        if not negative(pymupdf.Pixmap(data)):
            entries.append(Kept("2", tr("Signature (picture)"), "picture", data=data))
    except (OSError, RuntimeError, ValueError, pymupdf.mupdf.FzErrorBase):
        pass
    pictured = str(settings.value(OLD_SOURCE, "drawn")) == "picture" and entries[-1:] and entries[-1].kind == "picture"
    try:
        save(settings, entries, entries[-1].id if pictured else entries[0].id if entries else "")
    except OSError:
        pass
    return kept(settings) if settings.value(KEPT, None) is not None else entries


def save(settings, entries: list[Kept], chosen_id: str) -> None:
    """Keep ENTRIES (the pictures just chosen written in the folder; those of signatures no longer there,
    deleted), and CHOSEN_ID as the one the Signature tool puts."""
    pictures = {e.id for e in entries if e.kind == "picture"}
    for e in entries:
        if e.kind == "picture" and e.data is not None:
            path = picture_path(e.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(e.data)
            tmp.replace(path)
    if folder().is_dir():
        for path in folder().glob("*.png"):
            if path.stem not in pictures:
                path.unlink(missing_ok=True)
    settings.setValue(KEPT, json.dumps([e.as_json() for e in entries]))
    settings.setValue(CHOSEN, chosen_id)


def new_id(entries: list[Kept]) -> str:
    return str(max((int(e.id) for e in entries if e.id.isdigit()), default=0) + 1)


def picture_of(entry: Kept) -> tuple[bytes, float] | None:
    """ENTRY as a PNG, and its height for a width of 1: its picture, or its drawing made a picture; None if it
    has neither (or its picture is a negative kept by an earlier version)."""
    import pymupdf

    if entry.kind == "drawn":
        if not entry.strokes:
            return None
        data = drawn_picture(entry.strokes)
    else:
        try:
            data = entry.data if entry.data is not None else picture_path(entry.id).read_bytes()
        except OSError:
            return None
    try:
        pix = pymupdf.Pixmap(data)
    except (RuntimeError, ValueError, pymupdf.mupdf.FzErrorBase):
        return None
    if negative(pix):
        return None
    return data, pix.height / max(pix.width, 1)


def usable(entry: Kept) -> bool:
    return bool(entry.strokes) if entry.kind == "drawn" else picture_of(entry) is not None


def chosen(settings) -> Kept | None:
    """The signature the Signature tool puts: the one chosen, or else the first that has something."""
    entries = [e for e in kept(settings) if usable(e)]
    wanted = str(settings.value(CHOSEN, ""))
    return next((e for e in entries if e.id == wanted), entries[0] if entries else None)


def choose(settings, kid: str) -> None:
    settings.setValue(CHOSEN, kid)


def usual_width(settings, default: float) -> float:
    """The usual width of a signature on the page, in points."""
    try:
        value = float(settings.value(WIDTH, default))
    except (TypeError, ValueError):
        return default
    return value if 20 <= value <= 600 else default


def width(settings, entry: Kept | None, default: float) -> float:
    """How wide ENTRY goes on the page with a click, in points: its own width, or the usual one."""
    return entry.width if entry is not None and 20 <= entry.width <= 600 else usual_width(settings, default)


def stroke_path(stroke, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0) -> QPainterPath:
    """A stroke as the curves the annotation will have in the PDF (annots.smooth_segments), scaled and moved."""
    def at(p):
        return QPointF(dx + p[0] * scale, dy + p[1] * scale)

    path = QPainterPath(at(stroke[0]))
    if len(stroke) < 3:
        path.lineTo(at(stroke[-1]) + QPointF(0.01, 0))  # (one or two points: a dot, or a short line)
        return path
    for c1, c2, end in smooth_segments(stroke):
        path.cubicTo(at(c1), at(c2), at(end))
    return path


def drawn_picture(strokes: Strokes, size: int = 800) -> bytes:
    """STROKES (in a box of width 1) drawn on a transparent PNG SIZE pixels wide (or high), as on the page."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage

    points = [p for stroke in strokes for p in stroke]
    w = max(max(p[0] for p in points), 1e-3)
    h = max(max(p[1] for p in points), 1e-3)
    scale = size / max(w, h)
    pen_width = size * 0.012  # (as on the page: about 1.2 points for 100)
    margin = pen_width
    image = QImage(round(w * scale + 2 * margin), round(h * scale + 2 * margin), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(INK, pen_width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    for stroke in strokes:
        p.drawPath(stroke_path(stroke, scale, margin, margin))
    p.end()
    out = QByteArray()
    buffer = QBuffer(out)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(out.data())


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



def icon(entry: Kept, w: int = 96, h: int = 36):
    """A small picture of ENTRY, on white (as on a page, and seen in a dark theme too)."""
    from PySide6.QtGui import QIcon, QImage, QPixmap

    page = QPixmap(w, h)
    page.fill(Qt.GlobalColor.white)
    found = picture_of(entry)
    if found is not None:
        image = QImage.fromData(found[0]).scaled(w - 4, h - 4, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
        p = QPainter(page)
        p.drawImage((w - image.width()) // 2, (h - image.height()) // 2, image)
        p.end()
    return QIcon(page)


class SignatureDialog(QDialog):
    """My signatures: the signatures kept (a whole signature, initials…), in a list; the one selected is shown,
    and can be renamed, drawn again here with the pen or the mouse, or taken from a picture (Use a picture…),
    with its width on the page. OK keeps them all, and the Signature tool puts the one selected."""

    def __init__(self, parent=None, entries: list[Kept] | None = None, chosen_id: str = "",
                 width_points: float = 120.0):
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QHBoxLayout, QLineEdit, QListWidget, QSizePolicy,
                                       QStackedWidget)

        super().__init__(parent)
        self.setWindowTitle(tr("My signatures"))
        self.usual = width_points  # (the width of a signature that has none of its own)
        self.entries = [dataclasses.replace(e) for e in entries or []]  # (copies: kept only with OK)
        self.current = -1
        self.kind = "drawn"  # (what the one selected is: 'drawn' or 'picture')
        self.picture_data: bytes | None = None
        self.picture_file = ""
        self._loading = False
        outer = QHBoxLayout(self)

        # A la izquierda, la lista de firmas, con lo que se hace con ella
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setIconSize(QSize(96, 36))
        self.list.setMinimumWidth(220)
        # (all connected to methods, never to a lambda that holds the dialog: freed when the program ends, such a
        # lambda freed the dialog a second time, and it crashed on exit)
        self.list.currentRowChanged.connect(self._row_changed)
        left.addWidget(self.list, 1)
        self.b_new = QPushButton(tr("New signature"))
        self.b_new.setToolTip(tr("A new signature, drawn here (initials, for example)"))
        self.b_new.clicked.connect(self._new)
        self.b_new_picture = QPushButton(tr("New from a picture…"))
        self.b_new_picture.setToolTip(tr("A new signature, from a scan or a photo of it (PNG, JPEG…)"))
        self.b_new_picture.clicked.connect(self.add_picture)
        self.b_delete = QPushButton(tr("Delete"))
        self.b_delete.setToolTip(tr("Delete the signature selected"))
        self.b_delete.clicked.connect(self.delete)
        for b in (self.b_new, self.b_new_picture, self.b_delete):
            left.addWidget(b)
        outer.addLayout(left)

        # A la derecha, la firma elegida: su nombre, el panel para dibujarla o su imagen, y su ancho
        lay = QVBoxLayout()
        outer.addLayout(lay, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("Name:")))
        self.name = QLineEdit()
        self.name.setToolTip(tr("What this signature is called in the list (Signature, Initials…)"))
        self.name.textEdited.connect(self._renamed)
        name_row.addWidget(self.name, 1)
        lay.addLayout(name_row)
        self.pages = QStackedWidget()
        self.pad = Pad(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(420, 160)
        # (no crece con la imagen: si creciera, la imagen se escalaría a un espacio más grande que el diálogo)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview.installEventFilter(self)  # (la imagen se ajusta cada vez que el espacio cambia)
        # (sobre blanco, como una página: la firma se ve como quedará en un documento)
        self.preview.setStyleSheet("background: #ffffff; border: 1px solid palette(mid);")
        self.pages.addWidget(self.pad)
        self.pages.addWidget(self.preview)
        lay.addWidget(self.pages, 1)
        self.transparent = QCheckBox(tr("Make the paper transparent"))
        self.transparent.setChecked(True)
        self.transparent.setToolTip(tr("The white (or the colour of the paper) around the signature is taken "
                                       "away, so that it sits on the page like ink"))
        self.transparent.toggled.connect(self._transparency_changed)
        lay.addWidget(self.transparent)
        # El ancho en la página, en centímetros (se guarda en puntos: 72 por pulgada)
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
        edit_row = QHBoxLayout()
        self.b_picture = QPushButton(tr("Use a picture…"))
        self.b_picture.setToolTip(tr("Replace this signature by a scan or a photo of it (PNG, JPEG…)"))
        self.b_picture.clicked.connect(self.choose_picture)
        self.b_draw = QPushButton(tr("Draw it"))
        self.b_draw.setToolTip(tr("Draw this signature here, with the pen or the mouse"))
        self.b_draw.clicked.connect(self._draw)
        self.b_clear = QPushButton(tr("Clear"))
        self.b_clear.clicked.connect(self.pad.clear)
        for b in (self.b_picture, self.b_draw, self.b_clear):
            edit_row.addWidget(b)
        edit_row.addStretch(1)
        lay.addLayout(edit_row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        if not self.entries:
            self.entries.append(Kept("1", tr("Signature")))
        for e in self.entries:
            self.list.addItem(e.name)
        self._refresh_icons()
        self.list.setCurrentRow(next((i for i, e in enumerate(self.entries) if e.id == chosen_id), 0))

    # ----------------------------------------------------------------- the list

    def _row_changed(self, row: int):
        # Sin fila (-1): la lista se vacía (al borrar, o cuando el diálogo se destruye)
        if self._loading or row < 0:
            return
        self._commit()
        self.current = row
        if 0 <= row < len(self.entries):
            self._show_entry(self.entries[row])
        self.b_delete.setEnabled(len(self.entries) > 1)

    def _commit(self):
        """What is shown, kept in the signature selected (still in this dialog only)."""
        if not 0 <= self.current < len(self.entries):
            return
        e = self.entries[self.current]
        e.name = self.name.text().strip() or e.name
        e.width = self.width_points()
        e.kind = self.kind
        if self.kind == "drawn":
            e.strokes = normalized(self.strokes())
        else:
            if self.picture_data is not None:
                e.data = self.picture_data
            e.file = self.picture_file or e.file
            e.transparent = self.transparent.isChecked()
        item = self.list.item(self.current)
        item.setText(e.name)
        item.setIcon(icon(e))

    def _refresh_icons(self):
        for i, e in enumerate(self.entries):
            self.list.item(i).setIcon(icon(e))

    def _renamed(self, text: str):
        if 0 <= self.current < len(self.entries) and text.strip():
            self.list.item(self.current).setText(text.strip())

    def _new(self, *_):
        self.add()

    def _draw(self, *_):
        self.show_kind("drawn")

    def add(self) -> Kept:
        """A new signature at the end of the list, selected (drawn, its pad empty)."""
        self._commit()
        e = Kept(new_id(self.entries), tr("Signature {n}", n=len(self.entries) + 1))
        self.entries.append(e)
        self.list.addItem(e.name)
        self.list.setCurrentRow(len(self.entries) - 1)
        return e

    def add_picture(self, *_) -> bool:
        from PySide6.QtWidgets import QFileDialog

        name, _ = QFileDialog.getOpenFileName(self, tr("A picture of your signature"), str(Path.home()),
                                              tr("Pictures (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)"))
        if not name:
            return False
        self.add()
        if self.use_picture(name):
            return True
        self.delete()  # (unreadable: the new one goes)
        return False

    def delete(self, *_):
        """The signature selected, out of the list (there is always one left)."""
        if len(self.entries) < 2 or not 0 <= self.current < len(self.entries):
            return
        row = self.current
        self._loading = True
        del self.entries[row]
        self.list.takeItem(row)
        self._loading = False
        self.current = -1  # (nothing to keep from the one deleted)
        self.list.setCurrentRow(min(row, len(self.entries) - 1))
        if self.current < 0:  # (the same row as before: no signal)
            self._row_changed(self.list.currentRow())

    def chosen_id(self) -> str:
        return self.entries[self.current].id if 0 <= self.current < len(self.entries) else ""

    def kept_entries(self) -> list[Kept]:
        """The signatures as they are now; those with nothing drawn and no picture, left out."""
        self._commit()
        return [e for e in self.entries if (e.strokes if e.kind == "drawn" else
                                            e.data is not None or picture_path(e.id).is_file())]

    # ----------------------------------------------------------------- the signature selected

    def _show_entry(self, e: Kept):
        self._loading = True
        self.name.setText(e.name)
        self.width_cm.setValue(round((e.width or self.usual) / 72 * 2.54, 1))
        self.problem.setText("")
        if e.kind == "picture":
            self.picture_file = e.file if e.file and Path(e.file).is_file() else ""
            self.transparent.setChecked(e.transparent)
            found = picture_of(e)
            self.picture_data = None  # (only a picture chosen again is written again)
            self._shown_data(found[0] if found else None)
            if found is None:
                self.problem.setText(tr("The picture of this signature is missing or damaged: use a picture again."))
            self.pad.strokes = []
            self.show_kind("picture")
        else:
            self.picture_file, self.picture_data = "", None
            self._shown_data(None)
            self.pad.strokes = self._on_pad(e.strokes)
            self.pad.update()
            self.show_kind("drawn")
        self._loading = False

    def _on_pad(self, strokes: Strokes) -> Strokes:
        """STROKES (in a box of width 1) as large as the pad lets them, to be seen and drawn on."""
        if not strokes:
            return []
        margin = 20
        w = max(self.pad.width(), self.pad.minimumWidth()) - 2 * margin
        h = (max(self.pad.height(), self.pad.minimumHeight()) - 2 * margin)
        points = [p for s in strokes for p in s]
        scale = min(w / max(max(p[0] for p in points), 1e-3), h / max(max(p[1] for p in points), 1e-3))
        return [[(margin + x * scale, margin + y * scale) for x, y in s] for s in strokes]

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
        # (sin la imagen de la que se hizo, la transparencia no se puede rehacer)
        self.transparent.setEnabled(bool(self.picture_file))
        if not self._loading:
            self.problem.setText("")
        kept_where = tr("It is kept on this computer only, in the settings of py-pdftools, and put on documents "
                        "with the Signature tool.")
        if drawn:
            self.note.setText(tr("Sign above the line, with the pen or the mouse, or use a picture of your "
                                 "signature.") + " " + kept_where)
        elif self.picture_file:
            self.note.setText(tr("Your signature, from {file}.", file=Path(self.picture_file).name) + " " + kept_where)
        else:
            self.note.setText(tr("Your signature, from a picture.") + " " + kept_where)

    def choose_picture(self, *_) -> bool:
        from PySide6.QtWidgets import QFileDialog

        name, _ = QFileDialog.getOpenFileName(self, tr("A picture of your signature"), str(Path.home()),
                                              tr("Pictures (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)"))
        return bool(name) and self.use_picture(name)

    def use_picture(self, path) -> bool:
        """The picture at PATH, as the signature selected (kept with OK)."""
        previous = self.picture_file
        self.picture_file = str(path)
        if not self._load_picture():
            self.picture_file = previous
            return False
        self.show_kind("picture")
        self._commit()
        return True

    def _transparency_changed(self, _on: bool):
        if not self._loading and self.picture_file:
            self._load_picture()
            self._commit()

    def _load_picture(self) -> bool:
        if not self.picture_file:
            return False
        try:
            self.picture_data = prepared(self.picture_file, self.transparent.isChecked())
        except SignatureError as e:
            self.problem.setText(str(e))
            return False
        self._shown_data(self.picture_data)
        self.problem.setText("")
        return True

    def _shown_data(self, data: bytes | None):
        from PySide6.QtGui import QPixmap

        self._shown = QPixmap()
        if data:
            self._shown.loadFromData(data)
        self.preview.clear()
        self._fit_preview()

    def _fit_preview(self):
        """The picture made to fit the space it has now (when it is loaded, the dialog may not have its size yet:
        scaled then, it showed larger than the space, and cut)."""
        shown = getattr(self, "_shown", None)
        if shown is None or shown.isNull():
            return
        room = self.preview.contentsRect().size() * 0.92
        self.preview.setPixmap(shown.scaled(room, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent

        if obj is getattr(self, "preview", None) and event.type() == QEvent.Type.Resize:
            self._fit_preview()
        return False

    def strokes(self) -> Strokes:
        # Los trazos vacíos no deberían existir, pero se filtran por si acaso antes de guardar.
        return [s for s in self.pad.strokes if s]
