"""The main window: the pages of a PDF (thumbnails on the left; the pages, one
under the other, in the middle) with their annotations, and the panel of the
annotations on the right: the list of them (searched and filtered) and the
one selected, with its comment, tags, replies and review status."""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections import Counter
from pathlib import Path

import pymupdf
from PySide6.QtCore import QByteArray, QItemSelection, QItemSelectionModel, QPoint, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QColorDialog, QComboBox, QDialog, QDockWidget, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QSlider, QSplitter, QStackedWidget, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__

from ..core import config, conform, interface

from ..annotate import annots, exchange, recovery, search, settings
from ..annotate.annots import (
    ANNOTATING, FILLED, KINDS, MARKUP, NAMES, STAMPS, STATES, TEXTUAL, AnnotateError, Annotation, PasswordError, Rect, Reply,
    date_text,
)
from ..core.interface import N_, ntr, tr
from . import colors
from .canvas import GAP, PageCanvas, page_image
from .colors import color_name, colors_menu, swatch, swatches
from .files import FilesMixin, ask_save
from .hint import HintOverlay
from . import reading
from .textselect import TEXT_SELECT
from .ocring import OcrMixin
from .navigation import NavigationMixin, SelectAllPages
from .forming import FormMixin
from . import appearance
from .linking import LinkEditMixin
from .signing import SignMixin
from .toolbars import ToolbarsMixin
from .watching import WatchMixin
from .outline import OutlineMixin
from .imposing import ImposeMixin
from .paging import PagesMixin
from .redacting import RedactMixin
from .working import DocState, WorkingMixin
from .finder import FindDialog
from .listing import AnnotationModel, Panel
from .paint import paint
from .prefs import SettingsDialog
from .props import PropertiesDialog
from .renderer import renderer
from .modes import TIPS, TITLES, Mode
from .stamps import text_stamp

RECENT_KEPT = 30  # (documents kept in the list, whatever File ▸ Open recent shows: see recent_count)


def recent_count() -> int:
    """How many documents File ▸ Open recent shows (Settings > Documents)."""
    try:
        return max(0, min(int(appearance.value("recent")), RECENT_KEPT))
    except (TypeError, ValueError):
        return 10
AUTHOR = '<a href="https://nicolasvaughan.org">Nicolas Vaughan</a>'
THUMB_SIZES = (60, 300, 112)  # the height of the thumbnails: smallest, largest, usual
# thumbnails kept at most (those farthest from the ones in view are forgotten, and made again if the list
# comes back to them): about 40 MB, whatever the length of the document
MAX_THUMBS = 400
ALL_THUMBS = False  # (the memory profile 'all': every thumbnail is made, not only those near view)
# the tools: (name, freedesktop icon, tooltip), in groups; besides select, hand and eraser, they are the
# kinds of annotations they make (annots.KINDS)
TOOLS = [
    [("select", "edit-select", N_("Select, move and resize annotations; drag around them to select several")),
     ("selecttext", "edit-select-text", N_("Select text: drag over it (Alt+drag: a column; across pages too), "
                                           "double-click a word, triple-click a line, Shift+click to extend; "
                                           "Ctrl+C copies it, right-click for more")),
     ("hand", "transform-browse", N_("Dragging moves the pages in the window")),
     ("zoomarea", "zoom-select", N_("Zoom to area: drag a frame on a page to zoom to it; a click zooms in there")),
     ("eraser", "draw-eraser", N_("Drag over annotations to erase them (over a drawing, only what is touched)"))],
    [("highlight", "draw-highlight", N_("Drag over text to highlight it")),
     ("area", "highlight-area", N_("Drag on the page to highlight a region (a picture, a table, a scanned page)")),
     ("underline", "format-text-underline", N_("Drag over text to underline it")),
     ("strikeout", "format-text-strikethrough", N_("Drag over text to strike it out")),
     ("squiggly", "format-text-underline-squiggle", N_("Drag over text to underline it with a wavy line")),
     ("caret", "insert-text", N_("Click where text should be inserted, and write it")),
     ("replace", "replace-text", N_("Drag over text to replace it: it is struck out, and the new text written at "
                                    "its end"))],
    [("note", "note", N_("Click on the page to add a note")),
     ("freetext", "draw-text", N_("Drag a box on the page (or click) to write a text in it")),
     ("callout", "draw-callout", N_("Press on the place to point at, and drag to where its text goes")),
     ("typewriter", "typewriter", N_("Click on the page and write there, as with a typewriter: no box, no "
                                     "border")),
     ("signature", "signature", N_("Click where your signature goes (drawn once, by hand: right-click the tool "
                                   "to draw it again)")),
     ("attachment", "mail-attachment", N_("Click where a file is to be attached, and choose it")),
     ("mark", "check-mark", N_("Click to put a check mark, a cross, a dot or a dash, as on a form (right-click "
                               "the tool to choose it)")),
     ("stamp", "stamp", N_("Click on the page to put a stamp (right-click the tool to choose it)"))],
    [("rect", "draw-rectangle", N_("Drag on the page to draw a rectangle")),
     ("ellipse", "draw-ellipse", N_("Drag on the page to draw an ellipse")),
     ("polygon", "draw-polygon", N_("Click each corner; double-click, or press Enter, to end")),
     ("cloud", "draw-cloud", N_("Drag on the page to draw a cloud")),
     ("line", "draw-line", N_("Drag on the page to draw a line")),
     ("arrow", "draw-arrow", N_("Drag on the page to draw an arrow")),
     ("polyline", "draw-polyline", N_("Click each point; double-click, or press Enter, to end"))],
    [("ink", "draw-freehand", N_("Draw on the page by hand (with a tablet's pen, pressing harder draws wider)")),
     ("marker", "draw-marker", N_("Highlight by hand, where there is no text to drag over"))],
]
ZOOMS = (25, 50, 75, 100, 125, 150, 200, 300, 400, 800, 1600)  # (the percentages offered in the box of the zoom)
DEFAULT_MODE = "read"  # (the mode of the window the first time; then, the one it was left in)
# the toolbar of each group of TOOLS (object name, title)
TOOL_BARS = [("selection", N_("Selection")), ("markup", N_("Text markup")), ("notes", N_("Notes and text")),
             ("shapes", N_("Shapes")), ("drawing", N_("Drawing"))]
TOOL_NAMES = {"select": N_("Select"), "selecttext": N_("Select text"), "hand": N_("Hand"),
              "zoomarea": N_("Zoom to area"), "link": N_("Link"), "eraser": N_("Eraser"), "replace": N_("Replace text"),
              "typewriter": N_("Typewriter"), "mark": N_("Check mark"), "signature": N_("Signature")}
# the marks of the Check mark tool, drawn in a square of side 1: strokes (a drawing), or None (a dot: a disc)
MARKS = {"check": (N_("Check mark ✓"), (((0.1, 0.55), (0.4, 0.85), (0.9, 0.15)),)),
         "cross": (N_("Cross ✕"), (((0.15, 0.15), (0.85, 0.85)), ((0.85, 0.15), (0.15, 0.85)))),
         "dot": (N_("Dot ●"), None),
         "dash": (N_("Dash ─"), (((0.1, 0.5), (0.9, 0.5)),))}
SORTS = {"page": N_("By page"), "changed": N_("Last changed first"), "kind": N_("By kind"),
         "author": N_("By author"), "status": N_("By status")}
# Portapapeles propio, del módulo: lo comparten todas las ventanas del proceso; al del sistema solo va
# el texto (ver copy_selected).
_CLIPBOARD: list[Annotation] = []  # (annotations copied, for all the windows)

_WINDOWS: list = []  # (windows built again in another language must stay referenced)


def install_qt_translations():
    """Qt's own texts (file dialogs, standard buttons) in the language in use."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    app = QApplication.instance()
    # Se quitan los traductores instalados antes: esta función vuelve a llamarse en cada cambio de idioma.
    for old in getattr(app, "_py_pdftools_translators", []):
        app.removeTranslator(old)
    app._py_pdftools_translators = []
    code = interface.code()
    QLocale.setDefault(QLocale(code))
    # El inglés no necesita catálogo: los textos de Qt ya están en inglés.
    if code == "en":
        return
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    # qtbase_XX holds the texts of the dialogs; qt_XX, an older catalogue that loads the others, is the
    # fallback. The first one found is enough.
    for name in ("qtbase", "qt"):
        t = QTranslator(app)
        if t.load(f"{name}_{code}", folder):
            app.installTranslator(t)
            app._py_pdftools_translators.append(t)
            break


ACTIONS = Path(__file__).resolve().parent.parent / "icons" / "actions"


PAGE_ZOOM = "pagezoom"  # (the object name of the toolbar Page and zoom: see MainWindow.page_zoom_bar)

def icon(name: str) -> QIcon:
    """The icon NAME (a freedesktop name: document-open...) of the desktop's icon
    theme, so that it looks like the rest of the desktop; or else the program's own."""
    # Primero el tema del escritorio; el SVG propio de icons/actions solo cuenta si el tema no trae ese icono.
    own = ACTIONS / f"{name}.svg"
    return QIcon.fromTheme(name, QIcon(str(own)) if own.is_file() else QIcon())


# los iconos de los modos (icons/actions; 'pages' es Foliar), con nombres que ningún tema tiene
MODE_ICONS = {"read": "pdftools-mode-read", "ocr": "pdftools-mode-ocr", "annotate": "pdftools-mode-annotate",
              "redact": "pdftools-mode-redact", "pages": "pdftools-mode-foliate", "impose": "pdftools-mode-impose"}


def tool_name(tool: str) -> str:
    # annots.OTHER is not a tool: it names the annotations the program only shows (links, form fields...).
    if tool == annots.OTHER:
        return tr("Other kinds (read only)")
    return tr(TOOL_NAMES[tool]) if tool in TOOL_NAMES else tr(NAMES[tool])


class MainWindow(ImposeMixin, PagesMixin, RedactMixin, OcrMixin, OutlineMixin, NavigationMixin, WatchMixin,
                 WorkingMixin, FilesMixin, LinkEditMixin, FormMixin, SignMixin, ToolbarsMixin,
                 QMainWindow):
    def __init__(self, state: dict | None = None):
        """STATE (from export_state) carries the document over when the window is
        built again, for instance in another language."""
        super().__init__()
        self.setAcceptDrops(True)
        self.settings = QSettings("py-pdftools", "py-pdftools")
        self.path: Path | None = None
        self.host = None  # (the window of tabs this one is a tab of: see tabs.py)
        self._init_watch()  # (the file, changed by another program: see watching.py)
        self.password = ""
        self.doc: pymupdf.Document | None = None  # (its pages without the annotations of the list: those are drawn)
        self.count = 0
        self.page = 0  # (0-based) the page in view
        self.annotations: list[Annotation] = []
        self.layers: dict[str, bool] = {}  # the layers of the annotations: {name: whether they are shown}
        self.saved_layers: dict[str, bool] = {}  # (as the document has them)
        self.layer = ""  # the layer of the annotations made (see layers_menu)
        self.mark = "check"  # the mark of the Check mark tool (see MARKS)
        self.saved: list[Annotation] = []  # the annotations as they are in the file
        # Las pilas guardan listas de anotaciones; un cambio del documento mismo (modos Páginas e Imponer) entra
        # como un DocState (ver working.py). undo y redo distinguen los dos casos.
        self.undo_stack: list[list[Annotation]] = []
        self.redo_stack: list[list[Annotation]] = []
        self.selected: list[int] = []  # indices in self.annotations
        self.prefs = settings.load()
        colors.set_palette(self.prefs.palette)
        # (pdf2iso, for PDF/A and PDF/X: looked for when the menu Save as first opens, see _standards_menu;
        # finding Ghostscript runs it, which would slow every start)
        self._have_conform: bool | None = None
        self._thumbs: dict[int, QImage] = {}  # page -> its picture, without the annotations
        self._thumb_shown: dict[int, tuple] = {}  # page -> the annotations its thumbnail shows
        self._thumb_asked: set[int] = set()  # pages whose thumbnail is being made in the other processes
        self._by_page: list[list[Annotation]] = []
        self._marked: dict[tuple, str] = {}  # (page, quads) -> the text marked there
        self._words: dict[int, list] = {}  # page -> its words (see annots.page_text)
        self._rows: list[int] = []  # row of the list -> index of its annotation (those the filters let through)
        self._quiet_table = False  # (the list's selection is being set by the program)
        # Un valor de una versión anterior, o editado a mano, puede no ser un número: entonces, la altura usual.
        try:
            height = int(self.settings.value("thumb_height", THUMB_SIZES[2]))
        except (TypeError, ValueError):
            height = THUMB_SIZES[2]
        height = min(max(height, THUMB_SIZES[0]), THUMB_SIZES[1])
        self.thumb = QSize(round(height * 0.75), height)
        self.finder: FindDialog | None = None
        self.mode = ""
        # El orden importa: los modos se arman con las barras y menús ya creados, y _restore necesita todas las
        # barras (con su objectName) antes de que set_mode oculte las de los otros modos.
        self._build()
        self._build_outline()
        self._build_form()
        self._build_menus()
        self._build_modes()
        self._init_toolbars()  # (antes de _restore: las barras añadidas por el usuario también se colocan)
        self._restore()
        self.set_mode(str(self.settings.value("mode", DEFAULT_MODE)))
        # Recovery copies of the annotations every few minutes (Settings); the document itself is never written.
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.keep_recovery)
        self._start_autosave()
        self.refresh()
        # Ventana construida de nuevo (cambio de idioma): hereda el documento, las anotaciones y el historial.
        if state:
            self.adopt_state(state)

    # ----------------------------------------------------------------- construction

    def _build(self):
        self.pages = QListWidget()
        from .navigation import PageTips

        self.pages.viewport().installEventFilter(PageTips(self))
        from .navigation import CenterThumbnails

        # Al cambiar el ancho del panel, las celdas se ensanchan con él: las miniaturas quedan en el centro.
        self._center_thumbs = CenterThumbnails(self)
        self.pages.setItemDelegate(self._center_thumbs)
        self.pages.viewport().installEventFilter(self._center_thumbs)
        self._select_all_pages = SelectAllPages(self)
        self.pages.installEventFilter(self._select_all_pages)  # (each page's details, as its tip)
        self.pages.setViewMode(QListView.ViewMode.IconMode)
        self.pages.setFlow(QListView.Flow.TopToBottom)
        self.pages.setWrapping(False)
        self.pages.setMovement(QListView.Movement.Static)
        self.pages.setUniformItemSizes(True)
        self.pages.setToolTip(tr("The pages, with their labels when they are not their numbers; the number after ● "
                                 "is how many annotations a page has. Ctrl+click or Shift+click chooses several, "
                                 "Ctrl+A all; right-click for what can be done with them"))
        # Varias a la vez: Ctrl y Mayúsculas eligen páginas sin moverse a ellas; un clic solo va a la página.
        self.pages.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # La fila -1 llega cuando se vacía la lista (se abre otro documento): no hay nada que mostrar.
        self.pages.currentRowChanged.connect(self._thumb_row_changed)
        self.pages.itemSelectionChanged.connect(self._thumbs_selection_changed)
        self.pages.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pages.customContextMenuRequested.connect(self.thumbs_menu)
        # Intervalo 0: una miniatura por vuelta del bucle de eventos, para que la ventana siga respondiendo.
        self.thumb_timer = QTimer(self, interval=0)
        self.thumb_timer.timeout.connect(self._draw_thumbnails)
        # Solo se hacen las miniaturas cerca de las que se ven: al recorrer la lista se piden las nuevas.
        self.pages.verticalScrollBar().valueChanged.connect(lambda _: self.thumb_timer.start(0))
        self.thumb_slider = QSlider(Qt.Orientation.Horizontal)
        self.thumb_slider.setRange(*THUMB_SIZES[:2])
        self.thumb_slider.setValue(self.thumb.height())
        self.thumb_slider.setToolTip(tr("The size of the thumbnails"))
        self.thumb_slider.valueChanged.connect(self.set_thumb_size)
        self.thumbs_box = left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.pages, 1)
        lay.addWidget(self.thumb_slider)
        self._size_thumbnails()

        self.canvas = PageCanvas()
        self.canvas.pen_pressure, self.canvas.pen_curve, self.canvas.pen_button = (
            self.prefs.pen_pressure, self.prefs.pen_curve, self.prefs.pen_button)
        self.canvas.continuous = self.settings.value("continuous", "true") != "false"
        self.canvas.spread = self.settings.value("spread", "false") == "true"
        self.canvas.cover = self.settings.value("cover", "false") == "true"
        self.canvas.gap = GAP if self.settings.value("gaps", "true") != "false" else 0
        self.canvas.factory = self.new_annotation
        # Mientras una página se renderiza, el lienzo muestra en su lugar la miniatura que ya esté hecha.
        self.canvas.placeholder_for = lambda n: self._thumbs.get(n)
        self.canvas.drawn.connect(self.add_drawn)
        # A pen stroke whose pressure changed comes as several drawings: one change of the list, so one step
        # of the undo history.
        self.canvas.drawn_many.connect(
            lambda new: self.change(self.annotations + new,
                                    list(range(len(self.annotations), len(self.annotations) + len(new)))))
        # Las señales del lienzo traen índices de self.annotations; la lista se cambia aquí, nunca en el lienzo,
        # para que todo pase por change() y entre en el historial.
        self.canvas.edited.connect(self.replace)
        self.canvas.erased.connect(self.erase)
        self.canvas.nudged.connect(self.nudge)
        self.canvas.picked.connect(self.pick)
        self.canvas.text_chosen.connect(self.add_markup)
        self.canvas.text_menu.connect(self.text_menu)
        self.canvas.link_clicked.connect(self.follow_link)
        self.canvas.text_selected.connect(self._text_selection_changed)
        self.canvas.double_clicked.connect(self.double_clicked)
        self.canvas.menu_asked.connect(self.annotation_menu)
        self.canvas.page_changed.connect(self._page_shown)
        self.canvas.text_done.connect(self.text_done)
        self.canvas.zoom_changed.connect(self._show_zoom)
        # La casilla del zoom: un porcentaje escrito, o uno de la lista, o un ajuste (página, ancho, alto...).
        self.zoom_label = QComboBox()
        self.zoom_label.setEditable(True)
        self.zoom_label.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.zoom_label.setMinimumContentsLength(7)
        self.zoom_label.setToolTip(tr("The zoom: type a percentage and press Enter, or choose"))
        for text, data in ((tr("Fit the page"), "page"), (tr("Fit the width"), "width"),
                           (tr("Fit the height"), "height"), (tr("Fit the inked area"), "visible"),
                           (tr("Actual size"), "actual"), *[(f"{p} %", p / 100) for p in ZOOMS]):
            self.zoom_label.addItem(text, data)
        self.zoom_label.activated.connect(lambda i: self._choose_zoom(self.zoom_label.itemData(i)))
        self.zoom_label.lineEdit().returnPressed.connect(lambda: self._choose_zoom(self.zoom_label.currentText()))
        # (the page box and the zoom go on a toolbar of their own, which can be moved: see page_zoom_bar)
        center = QWidget()
        lay = QVBoxLayout(center)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.canvas, 1)
        # El consejo de cada modo flota un rato sobre las páginas al elegirlo (y con F1): ya no ocupa una franja
        # fija debajo de ellas.
        self.hint = HintOverlay(self.canvas)
        self.hints = {"annotate": tr(  # (each mode's; see set_mode)
            "Choose a tool in the toolbar: drag over text to mark it, drag on the page to draw, or "
            "click to add a note. Drag an annotation to move it or resize it; double-click it for its "
            "properties (a text box, or a note: to write its text), right-click it for more. "
            "Right-click a tool to set it up.")}

        # The model reads the current list through a lambda: self.annotations is replaced, not mutated, on each
        # change.
        self.model = AnnotationModel(lambda: self.annotations, self.marked_text)
        self.listing = Panel(self.model)
        p = self.listing
        # (the widgets of the panel, by the names the rest of the window uses)
        self.search, self.f_kind, self.f_author, self.f_color = p.search, p.f_kind, p.f_author, p.f_color
        self.f_status, self.f_tag, self.f_category, self.sort = p.f_status, p.f_tag, p.f_category, p.sort
        self.table, self.comment, self.color_button = p.table, p.comment, p.color_button
        self.b_props, self.b_delete = p.b_props, p.b_delete
        # (the list is searched when the typing stops for a moment, not at each key)
        self.search_timer = QTimer(self, singleShot=True, interval=250)
        self.search_timer.timeout.connect(self._filter_changed)
        self.search.textChanged.connect(lambda _: self.search_timer.start())
        # Los filtros desplegables se aplican al elegir, sin la espera de la búsqueda.
        for box in (self.f_kind, self.f_author, self.f_color, self.f_status, self.f_tag, self.f_category):
            box.activated.connect(lambda _: self._filter_changed())
        for key, name in SORTS.items():
            self.sort.addItem(tr(name), key)
        self.sort.activated.connect(lambda _: self._fill_table())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._table_selected())
        self.table.doubleClicked.connect(lambda _: self.properties_dialog())
        self.color_button.menu().aboutToShow.connect(self._color_menu)
        self.comment.finished.connect(self.keep_comment)
        p.tags.editingFinished.connect(self.keep_tags)
        p.reply_button.clicked.connect(lambda: self.add_reply())
        p.reply_edit.returnPressed.connect(lambda: self.add_reply())
        p.replies.itemDoubleClicked.connect(lambda item: self.edit_reply(p.replies.row(item)))
        p.replies.deleted.connect(lambda: self.delete_reply(p.replies.currentRow()))
        p.status.activated.connect(lambda _: self.set_status(p.status.currentData()))
        self.b_props.clicked.connect(self.properties_dialog)
        self.b_delete.clicked.connect(self.delete_selected)

        self.splitter = QSplitter()
        self.splitter.addWidget(left)
        self.splitter.addWidget(center)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([150, 800])
        self.central = QStackedWidget()  # (the pages; or, in the mode Impose, its workspace)
        self.central.addWidget(self.splitter)
        self.setCentralWidget(self.central)
        # the list of the annotations, with their authors, and the one selected: a panel on the right that
        # can be hidden (View, or its close button), moved to the left, or taken out of the window
        self.panel = QDockWidget(tr("Annotations"), self)
        self.panel.setObjectName("annotations")
        self.panel.setWidget(self.listing)
        self.panel.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.listing.setMinimumWidth(300)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.panel)
        self.resizeDocks([self.panel], [500], Qt.Orientation.Horizontal)

    def _action(self, menu: QMenu | None, text: str, triggered, shortcut=None, tip: str = "") -> QAction:
        act = QAction(text, self, triggered=triggered)
        if shortcut is not None:
            act.setShortcuts(shortcut if isinstance(shortcut, list) else [QKeySequence(shortcut)])
        if tip:
            act.setToolTip(tip)
            act.setStatusTip(tip)
        if menu is not None:
            menu.addAction(act)
        return act

    def _build_menus(self):
        m = self.m_file = self.menuBar().addMenu(tr("&File"))
        m.setToolTipsVisible(True)
        self.a_open = self._action(m, tr("Open…"), self.open_dialog, QKeySequence.StandardKey.Open)
        self.m_recent = m.addMenu(tr("Open recent"))
        self._recent_menu()
        self.a_images = self._action(m, tr("New PDF from pictures…"), lambda: self.images_dialog(),
                                     tip=tr("A PDF of photographs or scans, a page for each, and then, if wished, "
                                            "their text read (OCR)"))
        self.a_combine = self._action(m, tr("Combine files…"), lambda: self.combine_dialog(),
                                      tip=tr("Make one PDF of several, or of some of their pages, one file after "
                                             "another"))
        self.a_save = self._action(m, tr("Save"), self.save, QKeySequence.StandardKey.Save,
                                   tr("Write the annotations in the document (its signatures stay valid for what "
                                      "they signed)"))
        self.a_save_as = self._action(m, tr("Save as…"), self.save_as_dialog, QKeySequence.StandardKey.SaveAs,
                                      tr("Write a copy of the document with the annotations, and go on with it"))
        sub = self.m_save_copy = m.addMenu(tr("Save a copy"))
        sub.setToolTipsVisible(True)
        self.a_flat = self._action(sub, tr("Flattened…"), self.save_flattened_dialog,
                                   tip=tr("The annotations become part of the pages: they are seen and printed "
                                          "everywhere, but can no longer be edited or removed"))
        self.a_flat_form = self._action(sub, tr("With the form flattened…"), lambda: self.save_flat_form_dialog(),
                                        tip=tr("What the fields of the form show becomes part of the pages: it "
                                               "can no longer be changed"))
        self.a_version = self._action(sub, tr("With another PDF version…"), lambda: self.save_version_dialog(),
                                      tip=tr("The same document, saying it is another version of PDF (1.3 to "
                                             "2.0), for programs that ask for one"))
        self.a_bare = self._action(sub, tr("Without annotations…"), self.save_without_dialog,
                                   tip=tr("The document as it is without any annotation (links and form fields "
                                          "stay)"))
        self.a_smaller = self._action(sub, tr("Smaller…"), lambda: self.save_smaller_dialog(),
                                      tip=tr("A copy that takes less space: its pictures at a lower resolution, "
                                             "its fonts reduced, what nothing uses taken out"))
        self.a_ocr = self._action(sub, tr("Searchable (OCR)…"), self.save_searchable_dialog,
                                  tip=tr("The text of the scanned pages is read (with Tesseract) and written under "
                                         "their images, invisible: it can be found, copied and marked"))
        sub.addSeparator()
        self.standard_actions: dict[str, QAction] = {}
        # Una entrada por norma (PDF/A, PDF/X); _enable las desactiva si falta la orden externa (ver conform).
        for value, name in conform.STANDARDS:
            act = self._action(sub, tr(name) + "…", lambda _=False, v=value: self.save_standard_dialog(v))
            self.standard_actions[value] = act
        sub.aboutToShow.connect(self._standards_menu)
        self.a_protect = self._action(m, tr("Protect with passwords…"), self.protection_dialog,
                                      tip=tr("A password to open the document, and one for what may be done with "
                                             "it (printing, copying, changing it); or its protection removed"))
        self._build_sign_menu(m)
        self.a_print = self._action(m, tr("Print…"), self.print_dialog, QKeySequence.StandardKey.Print,
                                    tr("Print the pages with their annotations"))
        self.a_doc_props = self._action(m, tr("PDF properties…"), self.document_properties,
                                        tip=tr("What the document is: its title, author and dates, its PDF version, "
                                               "pages and size, its security, and the fonts it uses"))
        self.a_doc_props.setIcon(icon("document-properties"))
        # (en Editar: véase menus.py)
        self.a_word_index = self._action(None, tr("Word index…"), self.word_index,
                                         tip=tr("On which pages each word, phrase or pattern of a list appears, by "
                                                "the labels of the pages: lines ready for an index"))
        # (un icono propio, con un nombre que ningún tema tiene: va en la barra Buscar)
        self.a_word_index.setIcon(icon("pdftools-word-index"))
        m.addSeparator()
        self.a_export_pages = self._action(None, tr("Pages as pictures…"), lambda: self.export_pages_dialog(),
                                           tip=tr("The pages drawn as PNG, JPEG or TIFF pictures, at a resolution"))
        self.a_export_images = self._action(None, tr("The pictures of the document…"),
                                            lambda: self.export_images_dialog(),
                                            tip=tr("The pictures the pages show, each in a file, as they are "
                                                   "stored"))
        self.a_export_text = self._action(None, tr("The text…"), lambda: self.export_text_dialog(),
                                          tip=tr("The text of the pages as Markdown (headings and lists "
                                                 "guessed), HTML or plain text"))
        sub = self.m_export_annots = m.addMenu(tr("Export the annotations"))
        sub.setToolTipsVisible(True)
        self.a_export_md = self._action(sub, tr("As a report (Markdown)…"), lambda: self.export_dialog("md"))
        self.a_export_csv = self._action(sub, tr("As a table (CSV)…"), lambda: self.export_dialog("csv"))
        self.a_export_apparatus = self._action(
            sub, tr("The critical apparatus (Markdown)…"), lambda: self.export_dialog("apparatus"),
            tip=tr("The entries of textual criticism, in the order of the text"))
        self.a_export_json = self._action(sub, tr("As data, to import them again (JSON)…"),
                                          lambda: self.export_dialog("json"))
        self.a_export_xfdf = self._action(sub, tr("For other PDF programs (XFDF)…"), lambda: self.export_dialog("xfdf"),
                                          tip=tr("XFDF, the format in which PDF programs exchange annotations (tags and "
                                                 "categories are py-pdftools's own, and are left out)"))
        self.a_summary = self._action(sub, tr("A summary of the comments (PDF)…"), lambda: self.export_dialog("pdf"),
                                      tip=tr("Each page with annotations, beside a numbered list of them, with the "
                                             "text they mark, their comments and their replies"))
        sub = self.m_import_annots = m.addMenu(tr("Import annotations"))
        sub.setToolTipsVisible(True)
        self.a_import_json = self._action(sub, tr("From a file of annotations (JSON)…"),
                                          lambda: self.import_dialog("json"))
        self.a_import_xfdf = self._action(sub, tr("From another PDF program (XFDF)…"),
                                          lambda: self.import_dialog("xfdf"))
        self.a_import_pdf = self._action(sub, tr("From another copy of the PDF…"), lambda: self.import_dialog("pdf"),
                                         tip=tr("Bring in the annotations of another copy of this document, such as "
                                                "one annotated by someone else; those already here are left out"))
        self.a_compare = self._action(m, tr("Compare with another version…"), self.compare_dialog,
                                      tip=tr("Mark here what differs from another version of this text (another "
                                             "edition, a draft): its words, in reading order"))
        m.addSeparator()
        self.a_close = self._action(m, tr("Close window"), self.close, QKeySequence.StandardKey.Close)
        self.a_open_tab = self._action(
            None, tr("Open in a new tab…"), self.open_tab_dialog, "Ctrl+T",
            tip=tr("Another document in a tab of this window (Settings: open every document so)"))
        m.insertAction(self.m_recent.menuAction(), self.a_open_tab)
        # Quit ends the program, also when it keeps running in the background (see instance.py).
        self.a_quit = self._action(m, tr("Quit"), self.quit_program, QKeySequence.StandardKey.Quit)

        m = self.menuBar().addMenu(tr("&Edit"))
        self.a_undo = self._action(m, tr("Undo"), self.undo, QKeySequence.StandardKey.Undo)
        self.a_redo = self._action(m, tr("Redo"), self.redo, QKeySequence.StandardKey.Redo)
        m.addSeparator()
        self.a_copy = self._action(m, tr("Copy"), self.copy_selected)
        self.a_paste = self._action(m, tr("Paste"), self.paste)
        self.a_duplicate = self._action(m, tr("Duplicate"), self.duplicate)
        self.m_edit = m
        m.addSeparator()
        self.a_group = self._action(m, tr("Group"), self.group_selected,
                                    tip=tr("Make the selected annotations one group: selected, moved and deleted "
                                           "together"))
        self.a_ungroup = self._action(m, tr("Ungroup"), self.ungroup_selected)
        m.addSeparator()
        self.a_props = self._action(m, tr("Properties…"), self.properties_dialog)
        self.a_comment = self._action(m, tr("Comment on the annotation selected"), self.comment_action,
                                      tip=tr("Write the comment of the annotation selected; with none, add a note"))
        self.a_lock = self._action(m, tr("Lock"), self.toggle_lock)
        # Backspace as well as Delete: some keyboards (laptops, Macs) have no separate Delete key.
        self.a_delete = self._action(m, tr("Delete the selected annotations"), self.delete_selected,
                                     [QKeySequence(QKeySequence.StandardKey.Delete), QKeySequence("Backspace")])
        m.addSeparator()
        self.a_select_all = self._action(m, tr("Select the annotations of this page"), self.select_page,
                                         QKeySequence.StandardKey.SelectAll)

        self.a_select_kind = self._action(m, tr("Select those of the same kind on this page"), self.select_kind)
        self.a_select_none = self._action(m, tr("Select none"), lambda: self.pick([], False), "Escape")
        self.m_align = m.addMenu(tr("Align"))
        # Un par vacío marca un separador del menú.
        for key, name in (("left", N_("Left sides")), ("hcenter", N_("Centres, across")),
                          ("right", N_("Right sides")), ("top", N_("Tops")), ("vcenter", N_("Middles, up and down")),
                          ("bottom", N_("Bottoms")), ("", ""), ("across", N_("Spread evenly across")),
                          ("down", N_("Spread evenly up and down")), ("size", N_("Make them the same size"))):
            if key:
                self._action(self.m_align, tr(name), lambda _=False, k=key: self.align(k))
            else:
                self.m_align.addSeparator()
        m.addSeparator()
        self.a_clear_page = self._action(m, tr("Delete the annotations of this page"), self.delete_page)
        self.a_clear_all = self._action(m, tr("Delete all the annotations"), self.delete_all)
        # Sus textos, y qué acciones están habilitadas, se fijan cada vez que se abre (ver _edit_menu).
        m.aboutToShow.connect(self._edit_menu)

        m = self.menuBar().addMenu(tr("&Tools"))
        self.m_tools = m
        m.setToolTipsVisible(True)
        # Grupo exclusivo: marcar una herramienta desmarca la anterior, en el menú y en las barras.
        group = QActionGroup(self)
        self.tool_actions: dict[str, QAction] = {}
        for tools in TOOLS:
            for tool, icon_name, tip in tools:
                act = self._action(m, tool_name(tool), lambda _=False, t=tool: self.set_tool(t), tip=tr(tip))
                act.setCheckable(True)
                act.setIcon(icon(icon_name))
                group.addAction(act)
                self.tool_actions[tool] = act
            m.addSeparator()
        self.tool_actions["select"].setChecked(True)
        self._build_link_tool(self.m_edit, m)  # (la herramienta Enlace, también en este menú)
        m.addSeparator()
        self._action(m, tr("Properties of the tool…"), lambda: self.tool_dialog(self.canvas.mode))
        m.addSeparator()
        self.a_find = self._action(m, tr("Find and highlight…"), lambda: self.find_in_mode(),
                                   QKeySequence.StandardKey.Find,
                                   tr("Find a word, a phrase or a pattern on the pages, and highlight (or underline, "
                                      "strike out…) the places found"))
        from .quickfind import QuickFindAction

        # La búsqueda rápida: una casilla en la barra Buscar; Ctrl+Mayús+F pone el cursor en ella.
        self.a_quick_find = QuickFindAction(self)
        self.quick_find_key = self._action(m, tr("Quick find"), self.quick_find, "Ctrl+Shift+F",
                                           tr("Put the cursor in the quick find box, on the toolbar Find"))

        self.m_layers = self.menuBar().addMenu(tr("&Layers"))
        self.m_layers.setToolTipsVisible(True)
        self.m_layers.aboutToShow.connect(self.layers_menu)
        m = self.m_view = self.menuBar().addMenu(tr("&View"))
        m.setToolTipsVisible(True)
        self.a_show = QAction(tr("Show the annotations"), self, checkable=True, checked=True)
        self.a_show.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.a_show.setToolTip(tr("Hide them to see the document as it is without them"))
        # Hiding the annotations leaves the list as it is: only the pages are drawn again.
        self.a_show.toggled.connect(lambda _: self.refresh(table=False))
        m.addAction(self.a_show)
        self.a_only_listed = QAction(tr("Only those the list shows"), self, checkable=True)
        self.a_only_listed.setToolTip(tr("On the page, only the annotations that the search and filters of the list "
                                         "let through"))
        self.a_only_listed.toggled.connect(lambda _: self.refresh(table=False))
        m.addAction(self.a_only_listed)
        # La acción que muestra u oculta el panel la da el propio QDockWidget; así sigue también a su botón de cerrar.
        self.a_panel = self.panel.toggleViewAction()
        self.a_panel.setText(tr("The panel of the annotations"))
        self.a_panel.setShortcut(QKeySequence("F4"))
        self.a_panel.setToolTip(tr("The list of the annotations, with their authors, on the right of the window"))
        m.addAction(self.a_panel)
        m.addAction(self.a_outline)
        m.addAction(self.a_form)
        self.a_thumbs = QAction(tr("The thumbnails of the pages"), self, checkable=True, checked=True)
        self.a_thumbs.setShortcut(QKeySequence("F3"))
        self.a_thumbs.setToolTip(tr("The pages, small, on the left of the window"))
        self.a_thumbs.toggled.connect(self.show_thumbnails)
        m.addAction(self.a_thumbs)
        self.a_continuous = QAction(tr("Continuous scrolling"), self, checkable=True,
                                    checked=self.canvas.continuous)
        self.a_continuous.setToolTip(tr("The pages one under the other; otherwise, one page at a time"))
        self.a_continuous.toggled.connect(self.set_continuous)
        m.addAction(self.a_continuous)
        self.a_spread = QAction(tr("Two pages side by side"), self, checkable=True, checked=self.canvas.spread)
        self.a_spread.setShortcut(QKeySequence("Ctrl+Shift+2"))
        self.a_spread.setToolTip(tr("The pages in pairs, as an open book; next and previous move a pair at a time"))
        self.a_spread.toggled.connect(lambda on: self.set_spread(on))
        m.addAction(self.a_spread)
        self.a_cover = QAction(tr("The first page alone, as a cover"), self, checkable=True, checked=self.canvas.cover)
        self.a_cover.setToolTip(tr("With two pages side by side: the first page by itself, so that the even pages "
                                   "are on the left"))
        self.a_cover.toggled.connect(lambda on: self.set_spread(self.a_spread.isChecked(), on))
        self.a_cover.setEnabled(self.canvas.spread)
        m.addAction(self.a_cover)
        self.a_gaps = QAction(tr("Gaps between the pages"), self, checkable=True, checked=bool(self.canvas.gap))
        self.a_gaps.setToolTip(tr("Unticked, the pages follow one another without a gap, as one long sheet"))
        self.a_gaps.toggled.connect(self.set_gaps)
        m.addAction(self.a_gaps)
        self.a_split = self._action(m, tr("Split the view"), self.split_tab, "Ctrl+\\",
                                    tip=tr("This tab beside the others, on the other side of the window, to read two "
                                           "documents side by side; again, to bring it back"))
        self.a_detach = self._action(m, tr("Move the tab to a window of its own"), self.detach_tab)
        self.a_present = self._action(m, tr("Full screen"), self.present, "F11",
                                      tip=tr("The pages one at a time, full screen, as a presentation: arrows or a "
                                             "click turn them, Escape ends it"))
        # Colores de lectura: solo cambia la vista de las páginas, no el archivo ni las miniaturas.
        colours = self.m_reading = m.addMenu(tr("Reading colours"))
        colours.setToolTipsVisible(True)
        group = QActionGroup(self)
        self.reading_actions: dict[str, QAction] = {}
        for name, title, _, _ in [*reading.SCHEMES, ("custom", N_("Colours of my own…"), None, None)]:
            act = colours.addAction(tr(title), lambda n=name: self.set_reading(n, ask=n == "custom"))
            act.setCheckable(True)
            act.setToolTip(tr("Only the pages in view change, not the file; the colours of pictures change "
                              "with them"))
            group.addAction(act)
            self.reading_actions[name] = act
        m.addSeparator()
        self.a_next_annot = self._action(m, tr("Next annotation"), lambda: self.go_annotation(1))
        self.a_prev_annot = self._action(m, tr("Previous annotation"), lambda: self.go_annotation(-1))
        m.addSeparator()
        # (with two pages side by side, a pair at a time)
        self.a_prev = self._action(m, tr("Previous page"), lambda: self.show_page(self.canvas.neighbour(self.page, -1)),
                                   [QKeySequence("PgUp")])
        self.a_next = self._action(m, tr("Next page"), lambda: self.show_page(self.canvas.neighbour(self.page, 1)),
                                   [QKeySequence("PgDown")])
        self.a_first = self._action(m, tr("First page"), lambda: self.show_page(0), "Ctrl+Home")
        self.a_last = self._action(m, tr("Last page"), lambda: self.show_page(self.count - 1), "Ctrl+End")
        # La historia de los saltos (enlaces, marcadores, la casilla de la página, Buscar), como en un navegador.
        self.a_back = self._action(m, tr("Previous view"), lambda: self.history_step(True),
                                   [QKeySequence("Alt+Left"), QKeySequence(QKeySequence.StandardKey.Back)],
                                   tip=tr("Back to the place before the last jump (a link, a bookmark, a page "
                                          "typed, a search)"))
        self.a_forward = self._action(m, tr("Next view"), lambda: self.history_step(False),
                                      [QKeySequence("Alt+Right"), QKeySequence(QKeySequence.StandardKey.Forward)],
                                      tip=tr("Forward again, to the place left with Previous view"))
        self.a_back.setIcon(icon("go-previous-view"))
        self.a_forward.setIcon(icon("go-next-view"))
        self.a_first.setIcon(icon("go-first"))
        self.a_last.setIcon(icon("go-last"))
        from .pagebar import PageNumberAction

        # (la casilla de la página como acción, para la barra Navegación de páginas y cualquier otra)
        self.a_page_number = PageNumberAction(self)
        self._update_history()
        m.addSeparator()
        self.a_fit = self._action(m, tr("Fit the page"), lambda: self._fit("page"), "Ctrl+0")
        self.a_fit_width = self._action(m, tr("Fit the width"), lambda: self._fit("width"), "Ctrl+9")
        self.a_fit_height = self._action(m, tr("Fit the height"), lambda: self._fit("height"), "Ctrl+8")
        self.a_fit_visible = self._action(m, tr("Fit the inked area"), lambda: self._fit("visible"), "Ctrl+7",
                                          tip=tr("The part of the page that has ink (its margins left out), as wide "
                                                 "as the window"))
        self.a_actual = self._action(m, tr("Actual size"), self.canvas.actual_size, "Ctrl+Shift+0",
                                     tip=tr("The page at its printed size on this screen"))
        m.addSeparator()
        # Girar la vista, no el archivo: las páginas se ven giradas hasta abrir otro documento.
        self.a_turn_right = self._action(m, tr("Rotate the view clockwise"), lambda: self.turn_view(90), "Ctrl+]",
                                         tip=tr("Every page is shown turned; the file stays as it is (to turn pages "
                                                "for good: Foliate, Rotate)"))
        self.a_turn_left = self._action(m, tr("Rotate the view counterclockwise"), lambda: self.turn_view(-90),
                                        "Ctrl+[")
        self.a_zoom_in = self._action(m, tr("Zoom in"), lambda: self.canvas.zoom_by(1.25),
                                      [QKeySequence(QKeySequence.StandardKey.ZoomIn), QKeySequence("Ctrl+=")])
        self.a_zoom_out = self._action(m, tr("Zoom out"), lambda: self.canvas.zoom_by(1 / 1.25),
                                       QKeySequence.StandardKey.ZoomOut)

        m = self.menuBar().addMenu(tr("&Settings"))
        self.a_settings = self._action(m, tr("Settings…"), self.settings_dialog, [QKeySequence("Ctrl+,")])
        self.a_customize_bars = self._action(None, tr("Customize the toolbars…"), lambda: self.customize_toolbars(),
                                             tip=tr("Choose the buttons of each toolbar and their order, or add "
                                                    "toolbars of your own"))
        # Barras: cómo se ven todas (el texto, el tamaño de los iconos), bloquearlas y personalizarlas; el menú se
        # hace al abrirse, con lo que está elegido entonces.
        self.m_toolbars = m.addMenu(tr("Toolbars"))
        self.m_toolbars.aboutToShow.connect(lambda: (self.m_toolbars.clear(), self.looks_menu(self.m_toolbars)))
        lang = self.m_language = m.addMenu(tr("Language"))
        group = QActionGroup(self)
        for code, name in interface.names().items():
            act = QAction(name, self, checkable=True)
            act.setChecked(code == interface.code())
            act.triggered.connect(lambda _=False, c=code: self.change_language(c))
            group.addAction(act)
            lang.addAction(act)
        m = self.menuBar().addMenu(tr("&Help"))
        self.a_tips = self._action(m, tr("Tips for this mode"), self.show_tips, "F1",
                                   tip=tr("What can be done in this mode, and how, shown over the pages"))
        # (también en Configuración, en la fila de los botones)
        self.a_check = self._action(m, tr("Check the configuration…"), self.check_configuration,
                                    tip=tr("Whether py-pdftools has what it needs (Python, its libraries, "
                                           "tesseract, Ghostscript), and whether its settings are right"))
        self.a_updates = self._action(m, tr("Check for a new version…"), self.check_for_updates,
                                      tip=tr("Ask GitHub for the latest version of py-pdftools (only now, never "
                                             "by itself), and say how to install it"))
        self._action(m, tr("About"), self.about)

        for act, name in ((self.a_open, "document-open"), (self.a_save, "document-save"),
                          (self.a_save_as, "document-save-as"), (self.a_undo, "edit-undo"),
                          (self.a_redo, "edit-redo"), (self.a_delete, "edit-delete"), (self.a_prev, "go-previous"),
                          (self.a_next, "go-next"), (self.a_fit, "zoom-fit-best"),
                          (self.a_fit_width, "zoom-fit-width"), (self.a_zoom_out, "zoom-out"),
                          (self.a_zoom_in, "zoom-in"), (self.a_copy, "edit-copy"), (self.a_paste, "edit-paste"),
                          (self.a_find, "edit-find"), (self.a_print, "document-print")):
            act.setIcon(icon(name))
        # the toolbars of every mode, one for each kind of work: the file, editing, finding, moving through
        # the pages, and zooming (each mode adds its own, on the row below)
        self.common_bars = [
            self.toolbar_of("file", tr("File"), [self.a_open, self.a_save, self.a_print]),
            self.toolbar_of("edit", tr("Edit"), [self.a_undo, self.a_redo, self.a_delete]),
            self.toolbar_of("find", tr("Find"), [self.a_find, self.a_quick_find, self.a_word_index]),
            # (Select text and Hand: in every mode, Read too; the previous and next page are in Page navigation)
            self.toolbar_of("navigation", tr("Navigation"), [self.a_back, self.a_forward,
                                                             self.tool_actions["selecttext"],
                                                             self.tool_actions["hand"], self.tool_actions["zoomarea"]]),
            self.toolbar_of("zoom", tr("Zoom"), [self.a_fit, self.a_fit_width, self.a_zoom_out, self.a_zoom_in]),
            self.page_zoom_bar(),
            self.page_bar(),
        ]
        self.addToolBarBreak()
        # those of the mode Annotate: a toolbar for each group of tools (Hand and Select text are in Navigation)
        self.tool_bars = []
        for (name, title), group_ in zip(TOOL_BARS, TOOLS, strict=True):
            tools = [tool for tool, _, _ in group_ if tool not in ("hand", "selecttext", "zoomarea")]
            bar = self.toolbar_of(name, tr(title), [self.tool_actions[tool] for tool in tools])
            self._tool_button_menus(bar)
            self.tool_bars.append(bar)
            if name == "notes":  # (la herramienta Enlace, que no hace anotaciones, va con las notas)
                bar.addAction(self.tool_actions["link"])
        self.apply_shortcuts()

        from .menus import regroup

        regroup(self)  # (Archivo, Editar y Ver, en grupos: véase menus.py)

    def _tool_button_menus(self, bar: QToolBar):
        """The buttons of the tools on BAR, each with its menu (a right click: colour, stamp, properties...)."""
        # Clic derecho sobre el botón de una herramienta: su menú de color, sello y propiedades (ver tool_menu).
        own = {tool for group_ in TOOLS for tool, _, _ in group_} - {"hand", "selecttext", "zoomarea"}
        for tool, act in self.tool_actions.items():
            button = bar.widgetForAction(act)
            if button is None or tool not in own:
                continue
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, t=tool, b=button: self.tool_menu(t, b.mapToGlobal(pos)))

    def check_for_updates(self):
        """Help > Check for a new version (see updating.py)."""
        from .updating import check_for_updates

        return check_for_updates(self)

    def check_configuration(self):
        """Help > Check the configuration (see health_dialog.py), with the shortcuts of this window."""
        from .health_dialog import HealthDialog

        HealthDialog(self, self).exec()

    def word_index(self):
        """Edit > Word index: the pages of each term of a list (see wordindex_dialog.py)."""
        if self.doc is None:
            return
        from .wordindex_dialog import WordIndexDialog

        WordIndexDialog(self).exec()

    def document_properties(self):
        """File > PDF properties: what the document is, and its fonts (see docprops_dialog.py)."""
        if self.doc is None:
            return
        from .docprops_dialog import DocumentPropertiesDialog

        DocumentPropertiesDialog(self.doc, self.path, self).exec()

    def page_zoom_bar(self) -> QToolBar:
        """The toolbar Zoom box: the box of the zoom, once fixed above the pages; as a toolbar, it can be moved
        anywhere or hidden. Its widget is always this one, so it is not one of those changed in Customize the
        toolbars. (The box of the page is in Page navigation only: it was here too, which showed it twice.)"""
        # (el nombre de objeto sigue siendo "pagezoom", para que la barra conserve su lugar guardado)
        bar = self.toolbar_of(PAGE_ZOOM, tr("Zoom box"), [])
        bar.addWidget(self.zoom_label)
        return bar

    def page_bar(self) -> QToolBar:
        """The toolbar Page navigation (see pagebar.py), at the bottom of the window."""
        from .pagebar import NAME

        bar = self.toolbar_of(NAME, tr("Page navigation"), [self.a_first, self.a_prev, self.a_page_number,
                                                             self.a_next, self.a_last])
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bar)
        return bar

    def toolbar_of(self, name: str, title: str, actions: list) -> QToolBar:
        """A new toolbar NAME (its object name, which keeps its place between sessions), with ACTIONS."""
        bar = QToolBar(title, self)
        bar.setObjectName(name)
        bar.setIconSize(QSize(22, 22))
        for act in actions:
            bar.addAction(act)
        self.addToolBar(bar)
        return bar

    def toolbars(self) -> list[QToolBar]:
        """The toolbars of the window (not those of the workspace of Impose, inside it)."""
        # findChildren searches the whole tree: the workspace of Impose has toolbars of its own, left out here by
        # their parent.
        return [bar for bar in self.findChildren(QToolBar) if bar.parent() is self]

    def createPopupMenu(self) -> QMenu:
        """The menu of the toolbars and panels (a right click on them): only those of the mode on, and of all."""
        menu = QMenu(self)
        mode = self.modes.get(self.mode) if hasattr(self, "modes") else None
        # Fuera del menú, las barras y paneles de los otros modos: mostrarlos aquí dejaría a la vista herramientas
        # desactivadas.
        others = {id(b) for m in getattr(self, "modes", {}).values() if m is not mode for b in m.bars + m.docks}
        for bar in self.toolbars():
            if id(bar) not in others and bar is not getattr(self, "modes_bar", None):
                menu.addAction(bar.toggleViewAction())
        if mode is not None and mode.docks:
            menu.addSeparator()
            for dock in mode.docks:
                menu.addAction(dock.toggleViewAction())
        if hasattr(self, "a_customize_bars"):
            # La posición del texto y el tamaño de los iconos, de todas las barras (como en Configuración >
            # Barras de herramientas); cada una por separado, en el diálogo de personalizarlas.
            menu.addSeparator()
            self.looks_menu(menu)
        return menu

    def apply_shortcuts(self):
        """The keys of the settings, given to the actions."""
        # Only these actions have keys the user can change in Settings; the others keep Qt's standard shortcuts.
        actions = dict(self.tool_actions)
        actions.update({"comment": self.a_comment, "next": self.a_next_annot, "previous": self.a_prev_annot,
                        "copy": self.a_copy, "paste": self.a_paste, "duplicate": self.a_duplicate,
                        "properties": self.a_props, "group": self.a_group, "ungroup": self.a_ungroup})
        for name, act in actions.items():
            act.setShortcut(QKeySequence(self.prefs.shortcut(name)))
        self._toolbar_tips()

    # ----------------------------------------------------------------- the modes

    def _build_modes(self):
        """The modes (see modes/), and the bar that chooses one (Ctrl+1, Ctrl+2 ...)."""
        # Anotar es dueño de todo salvo las cajas de censura, que pertenecen al modo Censurar.
        annotate = Mode("annotate", lambda a: a.kind != "redact", bars=list(self.tool_bars), docks=[self.panel],
                        menus=[self.m_tools.menuAction(), self.m_layers.menuAction()],
                        # Seleccionar y Mano valen en todos los modos; las otras herramientas, solo en Anotar.
                        actions=[act for tool, act in self.tool_actions.items()
                                 if tool not in ("select", "hand", "selecttext", "zoomarea")])
        # Leer: solo las páginas y sus miniaturas; nada es suyo, y el ratón mueve las páginas (la mano).
        read = Mode("read", lambda a: False, without=("edit",), entered=lambda: self.set_tool("hand"))
        self.hints["read"] = tr("Scroll through the pages, or drag them with the mouse; Ctrl and the mouse wheel "
                                "zoom. Choose another mode, above, to annotate, redact, foliate or impose the "
                                "document.")
        redact, pages, impose = self._build_redact(), self._build_pages(), self._build_impose()
        ocr_mode = self._build_ocr()
        # (in this order on the bar, and for Ctrl+1 ... Ctrl+6; 'pages' is the mode Foliate; OCR comes before
        # the modes that mark text, since it gives scanned pages their text)
        self.modes: dict[str, Mode] = {"read": read, "ocr": ocr_mode, "redact": redact, "annotate": annotate,
                                       "pages": pages, "impose": impose}
        bar = QToolBar(tr("Modes"))
        self.modes_bar = bar
        bar.setObjectName("modes")
        # Icono y nombre: los modos se reconocen por su nombre, y el icono los distingue de un vistazo.
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        bar.setIconSize(QSize(20, 20))
        group = QActionGroup(self)
        self.mode_actions: dict[str, QAction] = {}
        # Ctrl+1 a Ctrl+6 siguen el orden del diccionario: leer, OCR, censurar, anotar, foliar, imponer.
        for n, key in enumerate(self.modes, 1):
            act = QAction(icon(MODE_ICONS[key]), tr(TITLES[key]), self, checkable=True)
            act.setToolTip(tr(TIPS[key]))
            act.setShortcut(QKeySequence(f"Ctrl+{n}"))
            act.triggered.connect(lambda _=False, k=key: self.set_mode(k))
            group.addAction(act)
            bar.addAction(act)
            self.mode_actions[key] = act
        # La barra de los modos va primero en la fila de arriba, antes de la de Archivo.
        self.insertToolBar(self.common_bars[0], bar)

    def unmarked(self) -> list[Annotation]:
        """The annotations without the redaction boxes: for copies that make the annotations part of the
        pages, or print them (a box flattened there would hide what is under it, which would still be in
        the file: only a redacted copy, made in the mode Redact, takes it out)."""
        return [a for a in self.annotations if a.kind != "redact"]

    def _mode_enable(self):
        """The actions of the modes that are not on, disabled (their tools, and their shortcuts)."""
        for other in self.modes.values():
            if other.key != self.mode:
                for act in other.actions:
                    act.setEnabled(False)

    def quick_find(self):
        """The cursor in the quick find box; if no toolbar shows one (it was taken off, or the mode has no
        Find), the dialog Find."""
        bar = self.findChild(QToolBar, "find")
        if not self.a_quick_find.focus():
            mode = self.modes.get(self.mode)
            if bar is not None and bar.parent() is self and not bar.isVisible() and \
                    "find" not in getattr(mode, "without", ()) and self.a_quick_find in bar.actions():
                bar.show()
                if self.a_quick_find.focus():
                    return
            self.find_in_mode()

    def find_in_mode(self):
        """Find: and highlight (Annotate), or redact (Redact)."""
        if self.mode == "redact":
            self.redact_find_dialog()
        else:
            self.find_dialog()

    def owns(self, a: Annotation) -> bool:
        """Whether A is an annotation of the mode on (one the mouse, the list and the Edit menu work on)."""
        mode = self.modes.get(self.mode)
        return mode is None or mode.owns(a)

    def set_mode(self, key: str):
        """Turn on the mode KEY (see modes/): its toolbars, panels and menus are shown, those of the others hidden."""
        if key not in self.modes:
            key = DEFAULT_MODE
        if key == self.mode:
            return
        old = self.modes.get(self.mode)
        # El texto que se esté escribiendo en el lienzo, o un polígono a medias, se cierra antes de salir del modo.
        if old is not None:
            self.canvas.commit_text()
            self.canvas.cancel_polygon()
            # The arrangement of the window it leaves is kept, to come back with it (see arrangement).
            self.keep_arrangement()
            old.left()
        self.mode = key
        mode = self.modes[key]
        # Las barras comunes solo se tocan si cambia lo que el modo excluye (Imponer no usa buscar, navegar ni zoom).
        if old is None or old.without != mode.without:
            for bar in self.common_bars:
                bar.setVisible(bar.objectName() not in mode.without)
        for other in self.modes.values():
            on = other is mode
            for bar in other.bars:
                bar.setVisible(on)
            for act in other.menus:
                act.setVisible(on)
            for act in other.actions:
                act.setEnabled(on)
            for dock in other.docks:
                dock.setVisible(on)
        # La disposición propia del modo, si ya tiene una: dónde están sus barras y paneles, cuáles se ven.
        self.arrange(key)
        self.mode_actions[key].setChecked(True)
        if appearance.value("hints"):  # (Settings > Appearance; F1 shows it all the same)
            self.hint.show_text(self.hints.get(key, ""))
        self._mode_enable()
        # El lienzo solo deja seleccionar o mover las anotaciones del modo; las demás se ven, pero no se tocan.
        self.canvas.touchable = mode.owns
        # A selection kept across modes must not include annotations the new mode doesn't own.
        self.selected = [i for i in self.selected if mode.owns(self.annotations[i])]
        # Se vuelve a Seleccionar: la herramienta anterior podía ser de otro modo, cuyas acciones quedan desactivadas.
        self.set_tool("select")
        mode.entered()
        self.settings.setValue("mode", key)
        self.refresh()

    def show_tips(self):
        """Help > Tips for this mode (F1): the hint of the mode on, over the pages, again."""
        self.hint.show_text(self.hints.get(self.mode, ""))

    def quit_program(self) -> bool:
        from . import quit_all

        return quit_all()

    def keep_arrangement(self):
        """Keep the arrangement of the window in the mode on (its toolbars and panels, where they are and which
        are shown; the thumbnails, and the width of the pages beside them), to give it back when the mode is
        chosen again, in this session or another (see arrange)."""
        if not self.mode:
            return
        self.settings.setValue(f"arrangement/{self.mode}/state", self.saveState())
        self.settings.setValue(f"arrangement/{self.mode}/splitter", self.splitter.saveState())
        self.settings.setValue(f"arrangement/{self.mode}/thumbnails", self.a_thumbs.isChecked())

    def arrange(self, key: str):
        """The arrangement of the window kept for the mode KEY, if it has one: then, whatever it says, only
        the toolbars, panels and menus of that mode are shown (and of every mode, but those it has no use for)."""
        state = self.settings.value(f"arrangement/{key}/state")
        if isinstance(state, QByteArray):
            # The bookmarks stay as the user left them: their panel isn't part of a mode's arrangement
            bookmarks = self.outline_dock.isVisibleTo(self)
            self.restoreState(state)
            self.outline_dock.setVisible(bookmarks)
            mode = self.modes[key]
            for other in self.modes.values():
                if other is not mode:
                    for item in other.bars + other.docks:
                        item.setVisible(False)
            for bar in self.common_bars:
                if bar.objectName() in mode.without:
                    bar.setVisible(False)
            self.modes_bar.setVisible(True)
        split = self.settings.value(f"arrangement/{key}/splitter")
        if isinstance(split, QByteArray):
            self.splitter.restoreState(split)
        thumbs = self.settings.value(f"arrangement/{key}/thumbnails")
        if thumbs is not None:
            on = thumbs in (True, "true")
            self.a_thumbs.setChecked(on)
            self.show_thumbnails(on)

    # ----------------------------------------------------------------- the window's state (kept by Qt between sessions)

    def _restore_reading(self):
        """The reading colours of the last time."""
        name = str(self.settings.value("reading", ""))
        custom = str(self.settings.value("reading_custom", ""))
        try:
            pair = tuple(int(v) for v in custom.split(",")) if custom else None
        except ValueError:
            pair = None
        reading.TINT = reading.tint_of(name, pair)
        self._check_reading()

    def _restore(self):
        self._restore_reading()
        geo = self.settings.value("geometry")
        if isinstance(geo, QByteArray):
            self.restoreGeometry(geo)
        else:
            self.resize(1360, 900)
        split = self.settings.value("splitter2")
        if isinstance(split, QByteArray):
            self.splitter.restoreState(split)
        self.a_thumbs.setChecked(self.settings.value("thumbnails", True, type=bool))
        self.show_thumbnails(self.a_thumbs.isChecked())
        mark = self.settings.value("mark", "check")
        self.mark = mark if mark in MARKS else "check"
        # restoreState goes last: it needs every toolbar and dock of every mode to exist, with its object name.
        bars = self.settings.value("toolbars")
        if isinstance(bars, QByteArray):
            self.restoreState(bars)
        # Los marcadores empiezan ocultos en cada sesión; F5 los abre
        self.outline_dock.hide()

    def save_settings(self):
        if self.host is None:  # (a tab's size is its window's)
            self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter2", self.splitter.saveState())
        self.settings.setValue("thumbnails", self.a_thumbs.isChecked())
        self.settings.setValue("toolbars", self.saveState())
        self.keep_arrangement()  # (that of the mode on, to come back with it)
        self.settings.sync()

    def closeEvent(self, event):
        self.canvas.commit_text()
        self.keep_comment()
        if not self.maybe_discard():
            event.ignore()
            return
        # El usuario ya aceptó cerrar (guardó o descartó): la copia de recuperación sobra.
        if self.path is not None:
            recovery.discard(self.path)
        if self.finder is not None:
            self.finder.close()
        self.remember_file_place()  # (where it was left, to open it there again)
        from . import _QUITTING, save_session

        # The last window closed (not by Quit, which saved them all): its document is the session to reopen.
        if not _QUITTING and not any(w is not self and w.is_open() for w in _WINDOWS):
            save_session([self.path])
        # Removes the temporary folder of the working copies; unsaved changes of the document itself go with it.
        self.drop_work()
        if self._workspace is not None:  # (made only if the mode Impose was entered)
            self._workspace.close_down()
        self.save_settings()
        super().closeEvent(event)
        if self.host is not None:  # (its tab goes: see tabs.py)
            self.host.window_closed(self)

    def is_open(self) -> bool:
        """Shown, by itself or as a tab (a tab behind another is not visible, but open)."""
        if self.host is not None:
            return self.host.isVisible() and self in self.host.windows()
        return self.isVisible()

    def open_tab_dialog(self):
        name, _ = QFileDialog.getOpenFileName(self, tr("Open PDF"), self.last_dir(), tr("PDF files (*.pdf)"))
        if name:
            from .tabs import open_in_tab

            open_in_tab(Path(name), near=self)

    def split_tab(self):
        """This tab to the other side of its window (the split view), or back."""
        if self.host is None or not self.host.move_to_other_side(self):
            self.status(tr("Open another document in a tab first (File > Open in a new tab)"), error=True)

    def detach_tab(self):
        if self.host is not None:
            self.host.detach(self)

    def export_state(self) -> dict:
        """What a new window needs to carry on with the same document."""
        self.canvas.commit_text()
        self.keep_comment()
        # La copia de trabajo y su carpeta pasan a la ventana nueva (los DocState del historial están en ella);
        # la vieja la suelta, para no borrarla al irse.
        state = {"path": self.path, "password": self.password, "annotations": self.annotations,
                 "saved": self.saved, "undo": self.undo_stack, "redo": self.redo_stack, "page": self.page,
                 "tool": self.canvas.mode, "work": self.work, "work_dir": self._work_dir, "works": self._works}
        self.work, self._work_dir = None, None
        return state

    def adopt_state(self, state: dict):
        self.set_tool(state["tool"])
        if state["path"] is None or self._load(state["path"], state["password"]) is None:
            self.refresh()
            return
        if state.get("work") is not None:  # (shown from the working copy, as the old window showed it)
            self._work_dir, self._works = state["work_dir"], state["works"]
            if self._load_work(state["work"], state["page"]) is None:
                self.drop_work()
        # The annotations of the old window replace those just read: they include the changes not yet saved.
        self.annotations, self.saved = list(state["annotations"]), list(state["saved"])
        self.undo_stack, self.redo_stack = list(state["undo"]), list(state["redo"])
        self.refresh()
        self.show_page(state["page"])

    def last_dir(self) -> str:
        """Where the file dialogs start: the last folder used, or the document's (Settings > Documents)."""
        if appearance.value("dialogs") == "document" and self.path is not None:
            return str(self.path.parent)
        return self.settings.value("last_dir", str(Path.home()))

    # ----------------------------------------------------------------- language

    def change_language(self, code: str):
        """Use CODE for the interface, keep it in the configuration file, and
        build the window again in that language."""
        if code == interface.code():
            return
        if not interface.use(code):
            self.warn(tr("Language"), tr("The language of the interface could not be changed: {error}",
                                         error=interface.error()))
            interface.use(config.get("interface"))
            return
        try:
            config.set("interface", code)
        except OSError as e:
            self.status(tr("Could not keep the setting: {error}", error=e), error=True)
        install_qt_translations()
        self.save_settings()
        host = self.host
        if host is not None:  # (the new window takes this one's tab; the window of tabs stays meanwhile)
            host.closing = True
            host.take(self)
            host.closing = False
        new = MainWindow(self.export_state())
        if host is not None:
            host.add(new)
        else:
            new.restoreGeometry(self.saveGeometry())
            new.show()
        _WINDOWS.append(new)
        self.annotations = self.saved = []  # (nothing to ask about: the new window has it)
        self.path = None  # (nor a recovery copy to remove: it is the new window's)
        # hide() and deleteLater(), not close(): closeEvent would ask about unsaved changes and remove the
        # working copies.
        self.hide()
        self.deleteLater()
        if self in _WINDOWS:
            _WINDOWS.remove(self)

    # ----------------------------------------------------------------- documents

    def open_dialog(self):
        name, _ = QFileDialog.getOpenFileName(self, tr("Open PDF"), self.last_dir(), tr("PDF files (*.pdf)"))
        if name:
            self.open_path(Path(name))

    def open_path(self, path: Path, place: dict | None = None, password: str = "") -> bool:
        """Open the document at PATH (shown at PLACE, if given: see navigation.open_at_start), with PASSWORD if
        it is protected (else it is asked for)."""
        self.canvas.commit_text()
        self.keep_comment()
        self.reset_history()  # (the places of another document)
        if not path.is_file():
            self.status(tr("{path} not found", path=path), error=True)
            return False
        if not self.maybe_discard():
            return False
        if self.path is not None:
            recovery.discard(self.path)
        # Se pide la contraseña hasta que el archivo abra o el usuario cancele; open_pdf solo prueba, y se cierra
        # enseguida.
        tried = bool(password)
        while True:
            try:
                annots.open_pdf(path, password).close()
                break
            except PasswordError:
                password = self.ask_password(path, again=tried)
                tried = True
                if password is None:
                    self.status(tr("{path} is protected by a password", path=path), error=True)
                    return False
            except AnnotateError as e:
                self.status(str(e), error=True)
                return False
        # From here on the old document is gone: its working copies are removed (the history is cleared below).
        self.remember_file_place()  # (where it was left, to open it there again)
        self.canvas.turn = 0  # (a view turned is of the document left)
        self.drop_work()
        found = self._load(path, password)
        if found is None:
            return False
        self.settings.setValue("last_dir", str(path.parent))
        self.add_recent(path)
        self.annotations, self.saved = list(found), list(found)
        used = {a.layer for a in found}  # (the layers of the annotations; not those of the pages' contents)
        self.layers = {name: on for name, on in annots.layers(self.doc).items() if name in used}
        self.saved_layers = dict(self.layers)
        self.layer = ""
        self.undo_stack, self.redo_stack, self.selected = [], [], []
        self.search.clear()
        self.refresh()
        self.open_at_start(place)
        signed = self.signature_count()
        self.status(tr("Opened {path}", path=path) + " (" + ntr("{count} page", "{count} pages", self.count) + ", "
                    + ntr("{count} annotation", "{count} annotations", len(found)) + ")"
                    + (" — " + ntr("signed once: File > Digital signatures > Check the signatures",
                                   "signed {count} times: File > Digital signatures > Check the signatures", signed)
                       if signed else ""))
        # Una copia de recuperación igual a lo que tiene el archivo no se ofrece: se guardó después.
        kept = recovery.find(path)
        if kept is not None and kept[1] != found:
            when, annotations = kept
            if self.ask_recover(when.replace("T", " ")[:16]):
                # The recovered annotations come in as one change, so Undo goes back to those of the file; those on
                # pages the document no longer has are dropped.
                self.change([a for a in annotations if 0 <= a.page < self.count], [])
                self.status(tr("The annotations not saved before were brought back"))
            else:
                recovery.discard(path)
        return True

    def ask_recover(self, when: str) -> bool:
        return QMessageBox.question(
            self, tr("Annotations not saved"),
            tr("This document has annotations that were not saved, kept at {when} (the program stopped before they "
               "were saved). Bring them back?", when=when)) == QMessageBox.StandardButton.Yes

    def ask_password(self, path: Path, again: bool = False) -> str | None:
        text = tr("That password is not right. The password of {name}:", name=path.name) if again \
            else tr("{name} is protected. Its password:", name=path.name)
        password, ok = QInputDialog.getText(self, tr("Password"), text, QLineEdit.EchoMode.Password)
        return password if ok and password else None

    def _load(self, path: Path, password: str, page: int = 0,
              known: list[Annotation] | None = None) -> list[Annotation] | None:
        """Open PATH: its pages are shown without the annotations that can be
        edited, which are returned (None if it can't be opened). KNOWN: those annotations, if
        they are known already (just written): they are not read again."""
        try:
            doc = annots.open_pdf(path, password)
            # Las anotaciones editables se quitan del documento en memoria: la ventana las dibuja por su cuenta, encima.
            found = annots.read(doc) if known is None else list(known)
            annots.remove_editable(doc)
        except (AnnotateError, RuntimeError, ValueError) as e:
            self.status(str(e), error=True)
            return None
        # The old document is closed only once the new one has opened: on an error, the window keeps showing it.
        self._close_doc()
        self.doc, self.path, self.password, self.count = doc, path, password, doc.page_count
        self.file_annotations = list(found)  # (as the file has them: see working.py)
        self.page = min(page, self.count - 1)
        # Las cachés (miniaturas, texto marcado, palabras) eran de las páginas del archivo anterior.
        self._thumbs, self._thumb_shown, self._marked, self._words = {}, {}, {}, {}
        self._thumb_asked = set()
        self.redact_texts, self.redact_meta = {}, None
        self._by_page = [[] for _ in range(self.count)]
        # Bare only if there are annotations to take out: else the renderers can use the file as it is.
        self.canvas.source = self._source(path, password, bool(found))
        self.canvas.set_document(doc, self.page)
        self._fill_pages()
        self.outline_refresh()
        self.form_refresh()
        self.watch_file()
        return found

    @staticmethod
    def _source(path: Path, password: str, bare: bool):
        """What the other processes render the pages from (see renderer.py): the file itself
        (BARE: they take out the annotations the window draws, in their own copy)."""
        try:
            st = path.stat()
        except OSError:
            return None
        # El tercer elemento (fecha y tamaño) es la marca con que working.py sabe si otro programa cambió el archivo.
        return str(path.resolve()), password, (st.st_mtime_ns, st.st_size), bare

    def _close_doc(self):
        """Close the document shown (its pages are no longer shown)."""
        self.thumb_timer.stop()
        self.canvas.set_document(None)
        if self.doc is not None:
            self.doc.close()
            self.doc = None

    def _ask_target(self, title: str, suffix: str, ext: str = "pdf") -> Path | None:
        default = Path(self.last_dir()) / f"{self.path.stem}{suffix}.{ext}"
        filters = {"pdf": tr("PDF files (*.pdf)"), "json": tr("Annotations (*.json)"),
                   "md": tr("Markdown (*.md)"), "csv": tr("Tables (*.csv)"), "xfdf": tr("XFDF files (*.xfdf)")}
        name, _ = QFileDialog.getSaveFileName(self, title, str(default), filters[ext])
        if not name:
            return None
        target = Path(name)
        # El diálogo puede devolver un nombre sin extensión: se le añade, sin duplicarla.
        return target if target.suffix.lower() == f".{ext}" else target.with_suffix(f".{ext}")

    def save(self) -> bool:
        if self.path is None:
            return False
        return self.save_to(self.path)

    def save_as_dialog(self) -> bool:
        if self.path is None:
            return False
        target = self._ask_target(tr("Save as"), "-annotated")
        return self.save_to(target) if target is not None else False

    def save_to(self, target: Path) -> bool:
        """Write the document with the annotations as TARGET (which may be the
        document itself), and go on with TARGET. What was done can still be undone."""
        self.canvas.commit_text()
        self.keep_comment()
        # source es la copia de trabajo, si la hay: lo guardado incluye los cambios del documento mismo.
        source, page = self.file, self.page
        replacing = target.resolve() == self.path.resolve()
        # (what the file has is what was read when it was shown, unless it changed since: then it is read again)
        known = self.known_in_file()
        if replacing:  # (the file is about to change under the open document)
            self._close_doc()
        kept: set[int] = set()
        try:
            result: list[Annotation] = []
            written = annots.write(source, self.annotations, target, self.password, kept=kept, result=result,
                                   original=known, shown=self.layers)
        except AnnotateError as e:
            # The document was closed above: show it again from SOURCE before reporting the error.
            if replacing:
                self._load_work(source, page)
                self.refresh()
            self.status(str(e), error=True)
            return False
        recovery.discard(self.path)
        # (with a working copy, or with a change of the document itself still to redo after undoing back to
        # the file: those steps are of other files, and are dropped, as drop_work does)
        working = self.work is not None or any(isinstance(s, DocState) for s in self.undo_stack + self.redo_stack)
        # Las anotaciones escritas vienen en result: el archivo recién guardado no se vuelve a leer.
        found = self._load(target, self.password, page, known=result)
        if found is None:
            return False
        if working:  # (it is in the file now; and the history's steps are of files that are gone)
            self.drop_work()
            kept = set()
        if not replacing:
            kept = set()  # (another file: its xrefs are its own)
        # (the history keeps the xrefs of the annotations still there; the others are new to it)
        replies = {r.xref for a in found if a.xref in kept for r in a.replies}
        self.undo_stack = [self._remapped(s, kept, replies) for s in self.undo_stack]
        self.redo_stack = [self._remapped(s, kept, replies) for s in self.redo_stack]
        self.annotations, self.saved = list(found), list(found)
        self.saved_layers = dict(self.layers)
        self.selected = []
        self.settings.setValue("last_dir", str(target.parent))
        self.add_recent(target)
        self.refresh()
        self.show_page(page)
        self.status(tr("Saved {path}", path=target) + " — "
                    + ntr("{count} annotation written", "{count} annotations written", written))
        return True

    @staticmethod
    def _remapped(snapshot: list[Annotation], kept: set[int], replies: set[int]) -> list[Annotation]:
        """SNAPSHOT (of the history) with the xrefs no longer in the file taken out (those annotations are new)."""
        # xref 0 marca una anotación nueva: el próximo guardado la escribe como objeto nuevo en lugar de actualizar
        # uno que ya no está.
        out = []
        for a in snapshot:
            if a.xref in kept:
                thread = tuple(r if r.xref in replies else dataclasses.replace(r, xref=0) for r in a.replies)
                out.append(dataclasses.replace(a, replies=thread))
            else:
                out.append(dataclasses.replace(a, xref=0, replies=tuple(dataclasses.replace(r, xref=0)
                                                                        for r in a.replies)))
        return out

    # ----------------------------------------------------------------- recovery copies

    def _start_autosave(self):
        minutes = self.prefs.autosave
        # 0 minutos en los ajustes desactiva las copias de recuperación.
        if minutes:
            self.autosave_timer.start(minutes * 60_000)
        else:
            self.autosave_timer.stop()

    def keep_recovery(self):
        """Keep a recovery copy of the annotations, if they have changed since the document was saved."""
        if self.path is None or not self.is_modified() or self.work is not None:
            return  # (with changes of the document itself, the annotations are those of its working copy)
        try:
            recovery.keep(self.path, self.annotations)
        except OSError as e:
            self.status(tr("The recovery copy could not be kept: {error}", error=e), error=True)

    # ----------------------------------------------------------------- the toolbar

    def _toolbar_tips(self):
        """The tooltip of each button of the toolbars: what it does, and its shortcut."""
        for bar in self.toolbars():
            for act in bar.actions():
                if act.isSeparator():
                    continue
                # En los textos de las acciones, & marca la tecla de acceso y && es un & literal;
                # aquí se quiere el texto limpio.
                text = act.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
                keys = act.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
                tip = f"<b>{text}</b>" + (f" &nbsp;<span style='color:gray'>{keys}</span>" if keys else "")
                if act.statusTip():
                    tip += f"<br>{act.statusTip()}"
                for button in bar.findChildren(QToolButton):
                    if button.defaultAction() is act:
                        button.setToolTip(tip)

    def tool_menu(self, tool: str, where):
        """The menu of a tool (right-click on its button): its colour, its stamp, its properties."""
        menu = QMenu(self)
        menu.addSection(tool_name(tool))
        if tool in ANNOTATING:
            style = self.prefs.style(tool)
            for value, name in swatches():
                act = menu.addAction(swatch(value), name, lambda v=value: self.set_tool_color(tool, v))
                act.setCheckable(True)
                act.setChecked(value == style.color)
            menu.addAction(tr("Other colour…"), lambda: self.choose_tool_color(tool))
            if tool == "stamp":
                menu.addSeparator()
                stamps = menu.addMenu(tr("Stamp"))
                for key, name in STAMPS.items():
                    act = stamps.addAction(tr(name), lambda k=key: self.set_stamp(k))
                    act.setCheckable(True)
                    act.setChecked(style.stamp == key)
                # Un sello propio se guarda como 'text:' seguido de su texto; los estándar, por su clave en STAMPS.
                custom = style.stamp[5:] if style.stamp.startswith("text:") else ""
                act = menu.addAction(tr("A stamp of my own ({text})…", text=custom) if custom
                                     else tr("A stamp of my own…"), self.ask_stamp)
                act.setCheckable(True)
                act.setChecked(bool(custom))
            menu.addSeparator()
            menu.addAction(tr("Properties of the tool…"), lambda: self.tool_dialog(tool))
        if tool == "signature":
            menu.addAction(tr("Draw my signature again…"), self.draw_signature)
        if tool == "mark":
            for key, (name, _) in MARKS.items():
                act = menu.addAction(tr(name), lambda k=key: self.set_mark(k))
                act.setCheckable(True)
                act.setChecked(self.mark == key)
        # Opening the menu of a tool also chooses it, so that what is picked there applies at once.
        self.set_tool(tool)
        self.show_menu(menu, where)

    def set_tool_color(self, tool: str, color: str):
        self.set_prefs(self.prefs.with_style(tool, dataclasses.replace(self.prefs.style(tool), color=color)))
        self.status(tr("New annotations ({kind}) will be {color}", kind=tool_name(tool).lower(),
                       color=color_name(color)))

    def choose_tool_color(self, tool: str):
        chosen = QColorDialog.getColor(QColor(self.prefs.style(tool).color), self, tr("Colour"))
        if chosen.isValid():
            self.set_tool_color(tool, chosen.name())

    def set_stamp(self, stamp: str):
        self.set_prefs(self.prefs.with_style("stamp", dataclasses.replace(self.prefs.style("stamp"), stamp=stamp)))
        self.set_tool("stamp")

    def ask_stamp(self):
        current = self.prefs.style("stamp").stamp
        text, ok = QInputDialog.getText(self, tr("A stamp of my own"), tr("What the stamp says:"),
                                        QLineEdit.EchoMode.Normal, current[5:] if current.startswith("text:") else "")
        # Espacios normalizados y a lo sumo 60 caracteres: un texto largo no cabría en el sello.
        text = " ".join(text.split())[:60]
        if ok and text:
            self.set_stamp("text:" + text)

    def tool_dialog(self, tool: str):
        """The properties of TOOL: how the annotations it makes look, and how it behaves."""
        if tool not in ANNOTATING:
            return
        style = self.prefs.style(tool)
        # The dialog needs an annotation to show: a sample one, new, on the first page.
        dialog = PropertiesDialog([self.new_annotation(tool, 0, (0, 0, 10, 10))], self, tool=style)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_prefs(self.prefs.with_style(tool, dialog.style()))

    # ----------------------------------------------------------------- recent files

    def recent_files(self) -> list[Path]:
        try:
            # La lista se guarda como JSON en QSettings; si está dañada, se empieza de cero.
            names = json.loads(self.settings.value("recent", "[]"))
        except (TypeError, ValueError):
            names = []
        return [Path(n) for n in names if isinstance(n, str)][:recent_count()]

    def _set_recent(self, paths: list[Path]):
        self.settings.setValue("recent", json.dumps([str(p) for p in paths[:max(recent_count(), RECENT_KEPT)]]))
        self._recent_menu()

    def add_recent(self, path: Path):
        path = path.resolve()
        self._set_recent([path] + [p for p in self.recent_files() if p != path])

    def clear_recent(self):
        self._set_recent([])

    def _recent_menu(self):
        m = self.m_recent
        m.clear()
        paths = self.recent_files()
        for i, path in enumerate(paths, 1):
            # Teclas de acceso &1 a &9, y 1&0 para la décima.
            key = f"&{i}" if i < 10 else "1&0"
            act = m.addAction(f"{key} " + path.name.replace("&", "&&"), lambda p=path: self.open_path(p))
            act.setToolTip(str(path))
            act.setStatusTip(str(path))
        if paths:
            m.addSeparator()
        m.addAction(tr("Clear the list"), self.clear_recent).setEnabled(bool(paths))
        m.setToolTipsVisible(True)

    # ----------------------------------------------------------------- changing the annotations

    def change(self, annotations: list[Annotation], selected: list[int] | None = None):
        """Make ANNOTATIONS the annotations (so that it can be undone), selecting SELECTED."""
        if annotations == self.annotations:
            return
        # (those of other kinds, a link, an attached file..., are shown as they are in the document: whatever
        # was done to them is undone, and copies of them are left out)
        others = {a.xref: a for a in self.annotations if a.kind == annots.OTHER}
        if others or any(a.kind == annots.OTHER for a in annotations):
            annotations = [others.get(a.xref, a) if a.kind == annots.OTHER else a for a in annotations
                           if a.kind != annots.OTHER or a.xref in others]
            if annotations == self.annotations:
                return
        # El historial guarda la lista anterior tal cual: las listas se reemplazan, nunca se modifican, así que
        # cada instantánea sigue valiendo.
        self.undo_stack.append(self.annotations)
        self.redo_stack.clear()
        self.annotations = annotations
        # Indices past the end may come from callers that counted on the list before the filter above.
        self.selected = [i for i in (selected or []) if i < len(annotations)]
        self.refresh()

    def new_annotation(self, kind: str, page: int, rect: Rect, paths: tuple = (), quads: tuple = ()) -> Annotation:
        """An annotation with the style of new ones of its KIND (Settings, or Properties); a
        stamp, of its usual size where RECT has none."""
        # Las cajas de censura las hace el modo Censurar (ver redacting.py).
        if kind == "redact":
            return self.new_box(page, rect)
        if kind == "typewriter":  # (a text box with no border nor fill, written at once)
            a = self.new_annotation("freetext", page, rect)
            return dataclasses.replace(a, width=0, fill="", intent=annots.TYPEWRITER)
        if kind == "mark":
            return self._mark(page, rect)
        if kind == "signature":
            return self._signature(page, rect)
        style = self.prefs.style(kind)
        a = Annotation(kind, page, rect, style.color, fill=style.fill if kind in FILLED else "",
                       opacity=style.opacity, width=style.width, author=self.prefs.author,
                       font_size=style.font_size, font=style.font, align=style.align, icon=style.icon,
                       ends=(style.start, style.end), dashed=style.dashed, quads=quads, paths=paths,
                       layer=self.layer)
        if kind == "stamp":
            a = self._stamp(a, style)
        return a

    SIGNATURE_WIDTH = 120.0  # points

    def _signature(self, page: int, rect: Rect) -> Annotation:
        """The signature kept (see gui/signature.py), as a drawing SIGNATURE_WIDTH wide, its top left
        corner at RECT's (or an empty drawing, if there is none yet)."""
        from . import signature

        style = self.prefs.style("ink")
        x0, y0 = rect[0], rect[1]
        s = self.SIGNATURE_WIDTH
        # The signature is kept in a unit square: it is scaled to SIGNATURE_WIDTH and placed at the click.
        paths = tuple(tuple((round(x0 + u * s, 2), round(y0 + v * s, 2)) for u, v in stroke)
                      for stroke in signature.load(self.settings))
        # Un ancho mínimo, para que la firma no salga demasiado fina con el estilo de la herramienta a mano alzada.
        width = max(style.width, 1.2)
        return Annotation("ink", page, annots.frame("ink", paths, width) if paths else rect, style.color, width=width,
                          paths=paths, author=self.prefs.author, contents=tr("Signature"), layer=self.layer)

    def draw_signature(self) -> bool:
        """Draw the signature again (Signature tool, right-click)."""
        from . import signature

        dialog = signature.SignatureDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.strokes():
            return False
        signature.store(self.settings, dialog.strokes())
        self.status(tr("Signature kept: click with the Signature tool where it goes"))
        return True

    def ask_attachment(self) -> Path | None:
        name, _ = QFileDialog.getOpenFileName(self, tr("Attach a file"), self.last_dir())
        return Path(name) if name else None

    def save_attachment(self, a: Annotation, target: Path | None = None) -> Path | None:
        """Save the file attached in A (as TARGET, or where the user says)."""
        if target is None:
            name, _ = QFileDialog.getSaveFileName(self, tr("Save the attached file"),
                                                  str(Path(self.last_dir()) / (a.filename or "file")))
            if not name:
                return None
            target = Path(name)
        try:
            target.write_bytes(a.data)
        except OSError as e:
            self.status(tr("{path} cannot be written: {error}", path=target, error=e), error=True)
            return None
        self.status(tr("Saved {path}", path=target))
        return target

    def open_attachment(self, a: Annotation):
        """Open the file attached in A with the program the desktop opens such files with (a copy of it,
        in a folder of its own)."""
        import tempfile

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        # TODO: estas carpetas de mkdtemp no se borran nunca; podrían borrarse al cerrar la ventana (el programa
        # externo puede seguir leyendo el archivo mientras tanto).
        folder = Path(tempfile.mkdtemp(prefix="py-pdftools-"))
        path = self.save_attachment(a, folder / Path(a.filename or "file").name)
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _mark(self, page: int, rect: Rect) -> Annotation:
        """The mark chosen for the Check mark tool (see MARKS) in RECT: a drawing, or a disc for a dot,
        in the colour and width of the freehand tool's style."""
        style = self.prefs.style("ink")
        x0, y0, x1, y1 = rect
        _, strokes = MARKS.get(self.mark, MARKS["check"])
        # Un punto es una elipse rellena, de la mitad del tamaño del recuadro y centrada en él.
        if strokes is None:
            r = (x0 + (x1 - x0) * 0.25, y0 + (y1 - y0) * 0.25, x1 - (x1 - x0) * 0.25, y1 - (y1 - y0) * 0.25)
            return Annotation("ellipse", page, r, style.color, fill=style.color, width=0, author=self.prefs.author,
                              layer=self.layer)
        paths = tuple(tuple((round(x0 + u * (x1 - x0), 2), round(y0 + v * (y1 - y0), 2)) for u, v in stroke)
                      for stroke in strokes)
        width = max(style.width, 1.5)
        return Annotation("ink", page, annots.frame("ink", paths, width), style.color, width=width, paths=paths,
                          author=self.prefs.author, layer=self.layer)

    def set_mark(self, mark: str):
        self.mark = mark
        self.settings.setValue("mark", mark)
        self.set_tool("mark")

    def _stamp(self, a: Annotation, style: settings.Style) -> Annotation:
        if style.stamp.startswith("text:"):
            text = style.stamp[5:]
            image, (w, h) = text_stamp(text, style.color, self.prefs.author if style.stamp_date else "",
                                       style.stamp_date)
            a = dataclasses.replace(a, stamp="", image=image, contents=text)
        else:
            name = style.stamp if style.stamp in STAMPS else "Approved"
            image, (w, h) = annots.standard_stamp(name)
            a = dataclasses.replace(a, stamp=name, image=image, contents=tr(STAMPS[name]))
        x0, y0, x1, _ = a.rect
        if x1 - x0 > 5:  # (dragged: as wide as that, with its proportions)
            h, w = h * (x1 - x0) / w, x1 - x0
        else:  # (clicked: centred there)
            x0, y0 = x0 - w / 2, y0 - h / 2
        # El sello no puede salirse de la página: se empuja hacia dentro.
        if self.doc is not None and 0 <= a.page < self.count:
            r = self.doc[a.page].rect
            x0, y0 = max(min(x0, r.width - w), 0), max(min(y0, r.height - h), 0)
        return dataclasses.replace(a, rect=(round(x0, 2), round(y0, 2), round(x0 + w, 2), round(y0 + h, 2)))

    def add(self, annotation: Annotation):
        self.change(self.annotations + [annotation], [len(self.annotations)])
        self._after_making(annotation.kind)

    def _after_making(self, kind: str):
        """What the tool does once it has made an annotation: open something, and go back to Select."""
        style = self.prefs.style(kind)
        # style.show: "properties" opens the dialog; "comment" (or "text", for kinds with no text of their own)
        # goes to the comment box.
        if style.show == "properties":
            self.properties_dialog()
        elif style.show == "comment" or (style.show == "text" and kind not in TEXTUAL + ("note", "caret")):
            self.comment.setFocus()
        # Una herramienta fija (sticky) sigue elegida; si no, se vuelve a Seleccionar tras cada anotación.
        if not style.sticky and self.canvas.mode == kind:
            self.set_tool("select")

    def add_drawn(self, annotation: Annotation):
        """An annotation drawn on a page; a text box, a callout, a note or a caret has its text written
        first, on the page (if its tool says so: see text_done); an attached file, its file chosen."""
        # With no signature kept yet, the tool makes an empty drawing: the signature is drawn first, then placed.
        if annotation.kind == "ink" and annotation.contents == tr("Signature") and not annotation.paths:
            if not self.draw_signature():  # (none yet: drawn first)
                return
            annotation = self._signature(annotation.page, annotation.rect)
        if annotation.kind == "attachment":
            path = self.ask_attachment()
            if path is None:
                return
            try:
                data = path.read_bytes()
            except OSError as e:
                self.status(tr("{path} cannot be read: {error}", path=path, error=e), error=True)
                return
            annotation = dataclasses.replace(annotation, data=data, filename=path.name, icon="Paperclip",
                                             contents=annotation.contents or path.name)
        # Con show == "text", el texto se escribe sobre la página y la anotación entra después, en text_done.
        if annotation.kind in TEXTUAL + ("note", "caret") and self.prefs.style(annotation.kind).show == "text":
            self.canvas.edit_text(annotation, -1)
            return
        self.add(annotation)

    def text_done(self, index: int, annotation: Annotation):
        """The text of ANNOTATION, written on the page: a new one (INDEX -1), or the one at INDEX."""
        if index < 0:
            # _replacing is the strikeout of a replacement in progress (see replace_text): used once, then cleared.
            struck, self._replacing = getattr(self, "_replacing", None), None
            if struck is not None and annotation.group == struck.group:  # (a replacement: the mark and its strikeout)
                # La marca y su tachado entran juntos, en un solo paso del historial; sin texto, no entra ninguno.
                if annotation.contents.strip():
                    n = len(self.annotations)
                    self.change(self.annotations + [annotation, struck], [n, n + 1])
                return
            if annotation.contents.strip():
                self.add(annotation)
            return
        if 0 <= index < len(self.annotations):
            old = self.annotations[index]
            if (annotation.contents, annotation.rich) != (old.contents, old.rich):  # (its text, or its formatting)
                self.replace(index, dataclasses.replace(old, contents=annotation.contents, rich=annotation.rich))

    def add_markup(self, page: int, rects: list[Rect], kind: str | None = None):
        """A highlight (or the kind of markup of the tool) over the lines of text RECTS of PAGE."""
        if self.canvas.mode == "redact":  # (boxes over them)
            self.add_redact_text(page, rects)
            return
        # No kind given: the tool's own, or a highlight when the tool chosen is not a markup tool.
        kind = kind or (self.canvas.mode if self.canvas.mode in MARKUP + ("replace",) else "highlight")
        if kind == "replace":
            self.replace_text(page, rects)
            return
        self.add(self.new_annotation(kind, page, annots.union(rects), quads=tuple(rects)))

    def replace_text(self, page: int, rects: list[Rect], text: str | None = None):
        """Propose a replacement for the text under RECTS of PAGE: it is struck out, and an insert-text
        mark at its end holds TEXT (or what is written there), the two one group, as PDF programs
        write it (the mark answers nothing: the strikeout is in its group, /IT /StrikeOutTextEdit, and
        the mark has /IT /Replace)."""
        group = uuid.uuid4().hex[:12]
        struck = dataclasses.replace(self.new_annotation("strikeout", page, annots.union(rects), quads=tuple(rects)),
                                     intent="StrikeOutTextEdit", group=group)
        # La marca de inserción va al final de la última línea tachada, centrada en su borde inferior.
        x, bottom = rects[-1][2], rects[-1][3]
        w, h = annots.CARET_SIZE
        caret = dataclasses.replace(self.new_annotation("caret", page, (x - w / 2, bottom - h / 2, x + w / 2,
                                                                         bottom + h / 2)),
                                    intent="Replace", group=group, contents=text or "")
        self._replacing = struck
        if text is None:
            self.canvas.edit_text(caret, -1)
        else:
            self.text_done(-1, caret)

    def double_clicked(self, index: int, page: int, point: tuple):
        """An annotation: its text, written on the page (a text box, a note...), or its properties.
        A word, with a markup tool: that word marked."""
        if self.mode == "redact":
            self.redact_double_clicked(index, page, point)
            return
        if index >= 0:
            a = self.annotations[index]
            if a.kind in TEXTUAL + ("note", "caret") and not a.locked:
                self.canvas.edit_text(a, index)
            else:
                self.properties_dialog()
            return
        # With a markup tool, a double click marks the word under the pointer (with 2 points of slack around it).
        if self.canvas.mode not in MARKUP or self.doc is None:
            return
        found = annots.words(self.doc[page])
        i = annots.nearest_word(found, *point)
        if i is not None:
            x0, y0, x1, y1 = found[i][0]
            if x0 - 2 <= point[0] <= x1 + 2 and y0 - 2 <= point[1] <= y1 + 2:
                self.add_markup(page, annots.text_rects(found, i, i))

    def set_tool(self, tool: str):
        # Cambiar de herramienta cierra el texto que se esté escribiendo en el lienzo.
        self.canvas.commit_text()
        self.canvas.set_mode(tool)
        self.tool_actions[tool].setChecked(True)
        self._show_panel()
        if tool in ("polygon", "polyline"):
            self.status(tr("Click each point; double-click, press Enter or click the first point to end; Escape "
                           "gives it up"))

    def replace(self, index: int, annotation: Annotation):
        """ANNOTATION in the place of the one at INDEX (moved, resized...)."""
        if annotation.kind == "redact":  # (moved on another of its pages: it stays a box of its own page)
            annotation = dataclasses.replace(annotation, page=self.annotations[index].page)
        annotations = list(self.annotations)
        annotations[index] = annotation
        # If the annotation was part of the selection, the whole selection is kept; else it alone is selected.
        self.change(annotations, self.selected if index in self.selected else [index])

    def erase(self, changes: dict):
        """What the eraser did: {index: the annotation as it is left, or None if it is gone}."""
        annotations = []
        for i, a in enumerate(self.annotations):
            if i not in changes:
                annotations.append(a)
            elif changes[i] is not None:
                annotations.append(changes[i])
        self.change(annotations, [])

    def _movable(self) -> list[int]:
        # Las marcas sobre texto no se mueven: van atadas a las letras que marcan.
        return [i for i in self.selected if self.annotations[i].kind not in MARKUP and not self.annotations[i].locked]

    def nudge(self, dx: float, dy: float):
        """The selected annotations moved by (DX, DY) points, kept on their pages."""
        chosen = self._movable()
        if not chosen or self.doc is None:
            return
        annotations = list(self.annotations)
        for i in chosen:
            a = annotations[i]
            page = self.doc[a.page].rect
            x0, y0, x1, y1 = a.rect
            # El desplazamiento se acota para que cada anotación quede dentro de su página.
            mx = max(-x0, min(dx, page.width - x1))
            my = max(-y0, min(dy, page.height - y1))
            annotations[i] = annots.moved(a, mx, my)
        self.change(annotations, self.selected)

    def align(self, how: str):
        """Line up the selected annotations (that can be moved): see the Align menu."""
        chosen = self._movable()
        if len(chosen) < 2 or (how in ("across", "down") and len(chosen) < 3):
            self.status(tr("Select at least two annotations that can be moved (three, to spread them)"), error=True)
            return
        rects = {i: self.annotations[i].rect for i in chosen}
        annotations = list(self.annotations)
        if how in ("across", "down"):
            # Repartir: los extremos quedan donde están y el espacio libre se divide por igual entre los huecos.
            axis = 0 if how == "across" else 1
            order = sorted(chosen, key=lambda i: rects[i][axis])
            first, last = rects[order[0]], rects[order[-1]]
            sizes = sum(rects[i][axis + 2] - rects[i][axis] for i in order)
            gap = (last[axis + 2] - first[axis] - sizes) / (len(order) - 1)
            at = first[axis]
            for i in order:
                r = rects[i]
                shift = at - r[axis]
                annotations[i] = annots.moved(annotations[i], shift if axis == 0 else 0, shift if axis == 1 else 0)
                at += r[axis + 2] - r[axis] + gap
        else:
            # The reference is the first annotation selected, if it can be moved.
            ref = rects[self.selected[0]] if self.selected[0] in rects else rects[chosen[0]]
            for i in chosen:
                x0, y0, x1, y1 = rects[i]
                w, h = x1 - x0, y1 - y0
                if how == "size":
                    if self.annotations[i].kind in annots.RESIZABLE:
                        annotations[i] = annots.fitted(annotations[i], (x0, y0, x0 + ref[2] - ref[0],
                                                                         y0 + ref[3] - ref[1]))
                    continue
                dx = {"left": ref[0] - x0, "right": ref[2] - x1,
                      "hcenter": (ref[0] + ref[2]) / 2 - (x0 + w / 2)}.get(how, 0)
                dy = {"top": ref[1] - y0, "bottom": ref[3] - y1,
                      "vcenter": (ref[1] + ref[3]) / 2 - (y0 + h / 2)}.get(how, 0)
                annotations[i] = annots.moved(annotations[i], dx, dy)
        self.change(annotations, self.selected)

    def _change_selected(self, **changes):
        annotations = list(self.annotations)
        for i in self.selected:
            # El relleno solo se aplica a los tipos que lo admiten (FILLED); en los demás queda como estaba.
            fields = {k: v for k, v in changes.items() if k != "fill" or annotations[i].kind in FILLED}
            annotations[i] = dataclasses.replace(annotations[i], **fields)
        self.change(annotations, self.selected)

    def _remove(self, keep) -> None:
        """Remove the annotations of the mode for which KEEP(annotation) is false (locked ones are always
        kept, and so are those of the other modes)."""
        annotations = [a for a in self.annotations if keep(a) or a.locked or not self.owns(a)]
        if len(annotations) != len(self.annotations):
            self.change(annotations, [])

    def delete_selected(self):
        chosen = {i for i in self.selected if not self.annotations[i].locked}
        locked = len(self.selected) - len(chosen)
        if chosen:
            self.change([a for i, a in enumerate(self.annotations) if i not in chosen], [])
        if locked:
            self.status(ntr("{count} annotation is locked, and was kept", "{count} annotations are locked, and "
                            "were kept", locked), error=not chosen)

    def toggle_lock(self):
        if self.selected:
            self._change_selected(locked=not all(self.annotations[i].locked for i in self.selected))

    def delete_page(self):
        self._remove(lambda a: a.page != self.page)

    def delete_all(self):
        mine = sum(map(self.owns, self.annotations))
        if mine and QMessageBox.question(
                self, tr("Delete all the annotations"),
                ntr("Delete the {count} annotation of the document?", "Delete the {count} annotations of the "
                    "document?", mine)) == QMessageBox.StandardButton.Yes:
            self._remove(lambda a: False)

    def copy_selected(self):
        # (with the tool Select text, the text selected, to the clipboard)
        if self.canvas.mode == TEXT_SELECT and self.canvas.text_sel:
            self.copy_selected_text()
            return
        if not self.selected:
            return
        self.keep_comment()
        # Annotations of other kinds are not copied: the program can show them, not make them.
        _CLIPBOARD[:] = [self.annotations[i] for i in sorted(self.selected) if self.annotations[i].kind != annots.OTHER]
        # Al portapapeles del sistema va el texto marcado o el comentario, para pegarlo en otro programa.
        texts = [self.marked_text(a) or a.contents for a in _CLIPBOARD]
        QApplication.clipboard().setText("\n".join(t for t in texts if t))
        self.status(ntr("{count} annotation copied", "{count} annotations copied", len(_CLIPBOARD)))

    def paste(self, offset: float | None = None):
        """The annotations copied, on the page in view: a little apart from where they were if
        that is this page (marks over text, in the same place)."""
        if not _CLIPBOARD or self.doc is None:
            return
        page = self.doc[self.page].rect
        new, renamed = [], {}
        for a in _CLIPBOARD:
            # On the same page, copies go 10 points apart so as not to hide the originals; marks on text stay put.
            shift = (10.0 if a.page == self.page else 0.0) if offset is None else offset
            if a.kind in MARKUP:
                shift = 0.0
            # (copies of a group make a group of their own)
            group = renamed.setdefault(a.group, uuid.uuid4().hex[:12]) if a.group else ""
            # Una copia es una anotación nueva: sin xref, fechas, respuestas ni bloqueo.
            b = dataclasses.replace(a, page=self.page, xref=0, created="", modified="", locked=False,
                                    replies=(), group=group)
            x0, y0, x1, y1 = b.rect
            dx = max(-x0, min(shift, page.width - x1))
            dy = max(-y0, min(shift, page.height - y1))
            new.append(annots.moved(b, dx, dy) if dx or dy else b)
        self.change(self.annotations + new, list(range(len(self.annotations), len(self.annotations) + len(new))))

    def duplicate(self):
        if self.selected:
            self.copy_selected()
            self.paste()

    def comment_action(self):
        """The comment of the annotation selected, to write; with none, the note tool."""
        if len(self.selected) == 1:
            self.comment.setFocus()
        else:
            self.set_tool("note")

    def properties_dialog(self):
        if self.mode == "redact":
            self.redact_properties_dialog()
            return
        self.canvas.commit_text()
        self.keep_comment()
        if not self.selected:
            return
        chosen = [self.annotations[i] for i in self.selected]
        dialog = PropertiesDialog(chosen, self, categories=self.prefs.category_list())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        annotations = list(self.annotations)
        for i in self.selected:
            annotations[i] = dialog.apply(annotations[i])
        self.change(annotations, self.selected)
        # 'Use as default' makes sense only when the annotations edited are all of one kind.
        if dialog.as_default.isChecked() and len({a.kind for a in chosen}) == 1:
            self.use_style(annotations[self.selected[0]])

    def use_style(self, a: Annotation):
        """Make new annotations of A's kind look like A."""
        old = self.prefs.style(a.kind)
        style = dataclasses.replace(old, color=a.color, fill=a.fill, opacity=a.opacity, width=a.width,
                                    font_size=a.font_size, font=a.font, align=a.align, icon=a.icon,
                                    start=a.ends[0], end=a.ends[1], dashed=a.dashed)
        self.set_prefs(self.prefs.with_style(a.kind, style))
        self.status(tr("New annotations of this kind will look like this one"))

    def set_color(self, color: str):
        """The colour of the selected annotations; with none selected, that of new
        annotations of the tool chosen."""
        if self.selected:
            self._change_selected(color=color)
        elif self.canvas.mode in ANNOTATING:
            self.set_tool_color(self.canvas.mode, color)

    def choose_color(self):
        if self.selected:
            current = self.annotations[self.selected[0]].color
        elif self.canvas.mode in ANNOTATING:
            current = self.prefs.style(self.canvas.mode).color
        else:
            return
        chosen = QColorDialog.getColor(QColor(current), self, tr("Colour"))
        if chosen.isValid():
            self.set_color(chosen.name())

    def _color_menu(self):
        menu = self.color_button.menu()
        menu.clear()
        for value, name in swatches():
            menu.addAction(swatch(value), name, lambda v=value: self.set_color(v))
        menu.addSeparator()
        menu.addAction(tr("Other colour…"), self.choose_color)

    def _one(self) -> int | None:
        """The index of the annotation selected, if only one is."""
        if len(self.selected) == 1 and self.selected[0] < len(self.annotations):
            return self.selected[0]
        return None

    def keep_comment(self):
        """The comment typed in the panel, given to the annotation selected."""
        i = self._one()
        # El cuadro del comentario está desactivado si no hay exactamente una seleccionada: nada que guardar.
        if i is None or not self.comment.isEnabled():
            return
        # Only the newlines at the ends are trimmed; spaces the user typed are kept.
        text = self.comment.toPlainText().strip("\n")
        if text != self.annotations[i].contents:
            self.replace(i, dataclasses.replace(self.annotations[i], contents=text))

    def keep_tags(self):
        """The tags typed in the panel, given to the annotation selected."""
        i = self._one()
        if i is None:
            return
        # Etiquetas separadas por comas, con los espacios internos normalizados; las vacías se descartan.
        tags = tuple(t for t in (" ".join(x.split()) for x in self.listing.tags.text().split(",")) if t)
        if tags != self.annotations[i].tags:
            self.replace(i, dataclasses.replace(self.annotations[i], tags=tags))

    # ----------------------------------------------------------------- replies and status

    def add_reply(self, text: str | None = None, state: str = ""):
        """A reply (TEXT, or what is written in the panel) to the annotation selected, by the author
        of the settings; with STATE, a review status given to it."""
        i = self._one()
        if i is None:
            return
        text = self.listing.reply_edit.text().strip() if text is None else text
        if not text and not state:
            return
        a = self.annotations[i]
        reply = Reply(author=self.prefs.author, contents=text, state=state, created=annots.now())
        self.listing.reply_edit.clear()
        self.replace(i, dataclasses.replace(a, replies=a.replies + (reply,)))

    def set_status(self, state: str | None):
        """Give the annotation selected the review status STATE (a reply that says it)."""
        if not state:
            return
        # A review status is a reply that carries it, as PDF review states are written.
        self.add_reply(tr("Status: {status}", status=tr(STATES[state])), state=state)

    def edit_reply(self, row: int):
        i = self._one()
        if i is None or not 0 <= row < len(self.annotations[i].replies):
            return
        a = self.annotations[i]
        old = a.replies[row]
        text, ok = QInputDialog.getMultiLineText(self, tr("Reply"), tr("The reply:"), old.contents)
        if ok and text.strip() != old.contents:
            thread = list(a.replies)
            thread[row] = dataclasses.replace(old, contents=text.strip(), modified=annots.now())
            self.replace(i, dataclasses.replace(a, replies=tuple(thread)))

    def delete_reply(self, row: int):
        i = self._one()
        if i is None or not 0 <= row < len(self.annotations[i].replies):
            return
        a = self.annotations[i]
        self.replace(i, dataclasses.replace(a, replies=a.replies[:row] + a.replies[row + 1:]))

    # ----------------------------------------------------------------- preferences and the view

    def set_prefs(self, prefs: settings.Settings):
        """Use PREFS, and keep them in the configuration file."""
        self.prefs = prefs
        try:
            settings.save(prefs)
        except (OSError, ValueError) as e:
            self.status(tr("Could not keep the setting: {error}", error=e), error=True)
        colors.set_palette(prefs.palette)
        self.canvas.pen_pressure, self.canvas.pen_curve, self.canvas.pen_button = (
            prefs.pen_pressure, prefs.pen_curve, prefs.pen_button)
        # La ruta de pdf2iso puede haber cambiado en los ajustes: se comprueba de nuevo.
        self._have_conform = conform.available(prefs.pdfconform)
        self.apply_shortcuts()
        self._enable()
        self._start_autosave()
        self._show_panel()

    def settings_dialog(self):
        dialog = SettingsDialog(self.prefs, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_prefs(dialog.settings())
            if getattr(dialog, "language_changed", False):  # (after the dialog: the windows are built again)
                QTimer.singleShot(0, lambda code=dialog.language.currentData(): self.change_language(code))
            if getattr(dialog, "performance_changed", False):
                # (drawn anew: with the antialiasing chosen, and caches of the new size)
                self.canvas.clear_cache()
                self._thumbs, self._thumb_shown, self._thumb_asked = {}, {}, set()
                self.canvas.render_timer.start()
                self.thumb_timer.start()
            self.refresh()

    def set_reading(self, name: str, ask: bool = False) -> bool:
        """The reading colours NAME (see reading.py; 'custom': asked for, if ASK, else those kept); kept for the
        next time, and the pages drawn again in them."""
        custom = self.settings.value("reading_custom", "")
        try:
            custom = tuple(int(v) for v in str(custom).split(",")) if custom else None
        except ValueError:
            custom = None
        if name == "custom" and ask:
            before = custom or (0xFFFFFF, 0x000000)
            text = QColorDialog.getColor(QColor(f"#{before[0]:06x}"), self, tr("The colour of the text"))
            if not text.isValid():
                self._check_reading()
                return False
            page = QColorDialog.getColor(QColor(f"#{before[1]:06x}"), self, tr("The colour of the page"))
            if not page.isValid():
                self._check_reading()
                return False
            custom = (text.rgb() & 0xFFFFFF, page.rgb() & 0xFFFFFF)
            self.settings.setValue("reading_custom", f"{custom[0]},{custom[1]}")
        reading.TINT = reading.tint_of(name, custom)
        if name == "custom" and reading.TINT is None:
            name = ""
        self.settings.setValue("reading", name)
        self._check_reading()
        if self.doc is not None:
            page = self.page
            self.canvas.clear_cache()
            self.canvas.layout()  # (the pages not yet drawn show the page colour)
            self.canvas.set_annotations(self.canvas_items(self.shown()), self.selected)
            self.show_page(page)
        return True

    def redraw_pages(self):
        """The pages drawn again (the reading colours or the sharpness of the text changed)."""
        if self.doc is None:
            return
        page = self.page
        self.canvas.clear_cache()
        self._thumbs, self._thumb_shown, self._thumb_asked = {}, {}, set()
        self.canvas.layout()
        self.canvas.set_annotations(self.canvas_items(self.shown()), self.selected)
        self.show_page(page)
        self.thumb_timer.start()

    def _check_reading(self):
        name = str(self.settings.value("reading", ""))
        for key, act in self.reading_actions.items():
            act.setChecked(key == name)

    def present(self, page: int | None = None):
        """Full screen, as a presentation, from PAGE (else the page shown): see presentation.py."""
        from .presentation import Presentation

        if self.doc is None:
            return None
        self.presentation = Presentation(self, self.page if page is None else page, self.canvas.spread)
        # Al salir, la ventana muestra la página a la que se llegó.
        self.presentation.ended.connect(lambda n: self.show_page(n))
        self.presentation.start()
        return self.presentation

    def set_gaps(self, on: bool):
        """The gaps between the pages shown or hidden: kept for the next time."""
        self.settings.setValue("gaps", "true" if on else "false")
        page = self.page
        self.canvas.set_gaps(on)
        self.canvas.set_annotations(self.canvas_items(self.shown()), self.selected)
        self.show_page(page)

    def turn_view(self, degrees: int):
        """Turn the view DEGREES more (the file stays as it is); the page shown stays in view."""
        page = self.page
        self.canvas.set_turn(self.canvas.turn + degrees)
        self.canvas.set_annotations(self.canvas_items(self.shown()), self.selected)
        self.show_page(page)
        self.status(tr("The view is turned {degrees}°", degrees=self.canvas.turn) if self.canvas.turn
                    else tr("The view is upright again"))

    def set_spread(self, on: bool, cover: bool | None = None, keep: bool = True):
        """Two pages side by side (ON), the first alone if COVER: kept for the next time (KEEP; not when a
        document asks for it, on opening)."""
        cover = self.a_cover.isChecked() if cover is None else cover
        if keep:
            self.settings.setValue("spread", "true" if on else "false")
            self.settings.setValue("cover", "true" if cover else "false")
        for act, value in ((self.a_spread, on), (self.a_cover, cover)):
            act.blockSignals(True)
            act.setChecked(value)
            act.blockSignals(False)
        self.a_cover.setEnabled(on)
        page = self.page
        self.canvas.set_spread(on, cover)
        self.canvas.set_annotations(self.canvas_items(self.shown()), self.selected)
        self.show_page(page)

    def set_continuous(self, on: bool):
        self.settings.setValue("continuous", "true" if on else "false")
        # The page in view is kept across the switch: set_continuous lays the pages out anew.
        page = self.page
        self.canvas.set_continuous(on)
        self.canvas.set_annotations(self.canvas_items(self.shown()), self.selected)
        self.canvas.apply_fit()
        self.show_page(page)

    def set_thumb_size(self, height: int):
        self.thumb = QSize(round(height * 0.75), height)
        self.settings.setValue("thumb_height", height)
        self._size_thumbnails()
        # Las miniaturas hechas tienen el tamaño anterior: se descartan y se dibujan otra vez.
        self._thumbs, self._thumb_shown, self._thumb_asked = {}, {}, set()
        if self.doc is not None:
            self._fill_pages()
            self._label_pages()

    def _size_thumbnails(self):
        self.pages.setIconSize(self.thumb)
        # Cells as wide as the panel (at least as the thumbnail and its margin): each thumbnail in the middle
        width = max(self.thumb.width() + 28, self.pages.viewport().width())
        size = QSize(width, self.thumb.height() + 30)
        if self.pages.gridSize() != size:
            self.pages.setGridSize(size)
        self.pages.setMinimumWidth(min(self.thumb.width() + 50, 140))

    # ----------------------------------------------------------------- the menu of an annotation

    def _colors_menu(self, menu: QMenu, title: str, current: str | None, choose) -> QMenu:
        """A menu of the colours of the palette (CURRENT ticked), each given to CHOOSE."""
        return colors_menu(menu, title, current, choose, swatches(), self.choose_color)

    def _categories_menu(self, menu: QMenu, chosen: list[Annotation]):
        """The categories (ticked those all CHOSEN are in), each put in or taken out of them."""
        sub = menu.addMenu(tr("Categories"))
        names = self.prefs.category_list()
        # También las categorías que tienen las anotaciones y no están en los ajustes (traídas de otro archivo).
        for a in chosen:
            names += [c for c in a.categories if c not in names]
        for name in names:
            act = sub.addAction(name, lambda n=name: self.toggle_category(n))
            act.setCheckable(True)
            act.setChecked(all(name in a.categories for a in chosen))

    def toggle_category(self, name: str):
        """Put the selected annotations in category NAME, or take them out if they all are in it."""
        # If all of them have it already, it is taken out of all; else it is put in those that lack it.
        have = all(name in self.annotations[i].categories for i in self.selected)
        annotations = list(self.annotations)
        for i in self.selected:
            cats = [c for c in annotations[i].categories if c != name] + ([] if have else [name])
            annotations[i] = dataclasses.replace(annotations[i], categories=tuple(cats))
        self.change(annotations, self.selected)

    def annotation_menu(self, index: int, where, page: int = -1, point=None):
        """The right-click menu: of the annotations selected (INDEX: the one clicked),
        or of the page (INDEX -1)."""
        if self.mode == "redact":
            self.box_menu(index, where, page, point)
            return
        self.canvas.commit_text()
        self.keep_comment()
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        if index >= 0 and self.selected:
            chosen = [self.annotations[i] for i in self.selected]
            if len(chosen) == 1:
                menu.addSection(chosen[0].name())
            else:
                menu.addSection(ntr("{count} annotation", "{count} annotations", len(chosen)))
            colors_ = {a.color for a in chosen}
            self._colors_menu(menu, tr("Colour"), colors_.pop() if len(colors_) == 1 else None,
                              lambda v: self._change_selected(color=v))
            # Cambiar el tipo solo tiene sentido entre marcas sobre texto: comparten la forma (quads).
            if all(a.kind in MARKUP for a in chosen):
                change = menu.addMenu(tr("Change to"))
                for kind in MARKUP:
                    act = change.addAction(tool_name(kind), lambda k=kind: self._change_selected(kind=k))
                    act.setEnabled(any(a.kind != kind for a in chosen))
            if len(chosen) == 1 and chosen[0].kind in MARKUP:
                text = self.marked_text(chosen[0])
                if text:
                    menu.addAction(tr("Copy the text marked"), lambda: QApplication.clipboard().setText(text))
                    act = menu.addAction(tr("Copy it as a quotation"), lambda: QApplication.clipboard().setText(
                        exchange.quotation(self.doc, chosen[0], self.path.name if self.path else "")))
                    act.setToolTip(tr("The text marked, in quotation marks, with the document and its page"))
            if len(chosen) == 1 and chosen[0].kind == "attachment" and chosen[0].data:
                menu.addAction(tr("Open the attached file"), lambda: self.open_attachment(chosen[0]))
                menu.addAction(tr("Save the attached file…"), lambda: self.save_attachment(chosen[0]))
            if len(chosen) == 1 and chosen[0].kind in TEXTUAL + ("note", "caret") and not chosen[0].locked:
                menu.addAction(tr("Write its text…"), lambda: self.canvas.edit_text(chosen[0], self.selected[0]))
            status = menu.addMenu(tr("Status"))
            for key, name in STATES.items():
                status.addAction(tr(name), lambda k=key: self._status_for_selected(k))
            self._categories_menu(menu, chosen)
            critical = menu.addMenu(tr("Textual criticism"))
            for key, name in annots.CRITICAL.items():
                act = critical.addAction(tr(name), lambda k=key: self._critical_for_selected(k))
                act.setCheckable(True)
                act.setChecked(all(a.critical and a.critical.type == key for a in chosen))
            critical.addSeparator()
            critical.addAction(tr("None"), lambda: self._critical_for_selected(""))
            # Agrupar si no son ya todas un mismo grupo; si lo son, Desagrupar.
            if len(chosen) > 1 or any(a.group for a in chosen):
                menu.addAction(self.a_group if not all(a.group == chosen[0].group != "" for a in chosen)
                               else self.a_ungroup)
            menu.addSeparator()
            menu.addAction(self.a_copy)
            menu.addAction(self.a_duplicate)
            if len({a.kind for a in chosen}) == 1:
                menu.addAction(tr("Use its style for new annotations"), lambda: self.use_style(chosen[0]))
            if len(self._movable()) > 1:
                menu.addMenu(self.m_align)
            menu.addSeparator()
            menu.addAction(tr("Properties…"), self.properties_dialog)
            all_locked = all(a.locked for a in chosen)
            menu.addAction(tr("Unlock") if all_locked else tr("Lock"), self.toggle_lock)
            act = menu.addAction(icon("edit-delete"), ntr("Delete the annotation", "Delete the {count} annotations",
                                                          len(chosen)), self.delete_selected)
            act.setEnabled(not all_locked)
        else:
            # Clic derecho en un hueco de la página: añadir una nota ahí, pegar o buscar la palabra señalada.
            if point is not None and self.doc is not None and 0 <= page < self.count:
                size = self.doc[page].rect
                # The note is kept inside the page, near its right and bottom edges.
                x = min(point.x(), size.width - annots.NOTE_SIZE)
                y = min(point.y(), size.height - annots.NOTE_SIZE)
                rect = (round(x, 2), round(y, 2), round(x + annots.NOTE_SIZE, 2), round(y + annots.NOTE_SIZE, 2))
                menu.addAction(icon("note"), tr("Add a note here…"),
                               lambda: self.add_drawn(self.new_annotation("note", page, rect)))
                if _CLIPBOARD:
                    menu.addAction(self.a_paste)
                word = self.canvas.word_at(page, point)
                if word:
                    menu.addAction(icon("edit-find"), tr("Find “{word}” and highlight it…", word=word),
                                   lambda: self.find_dialog(word))
                menu.addSeparator()
            for tool in ("select", "highlight", "note", "freetext", "rect", "ink", "eraser"):
                menu.addAction(self.tool_actions[tool])
            # TODO: aquí se usa self.page (la página a la vista) y no PAGE, la del clic; en la vista continua pueden
            # no coincidir (select_page y a_clear_page también trabajan sobre self.page).
            here = [i for i, a in enumerate(self.annotations) if a.page == self.page]
            if here:
                menu.addSeparator()
                menu.addAction(ntr("Select the annotation of this page", "Select the {count} annotations of this "
                                   "page", len(here)), self.select_page)
                menu.addAction(self.a_clear_page)
        self.show_menu(menu, where)

    def _status_for_selected(self, state: str):
        """Give each selected annotation the review status STATE."""
        name = tr(STATES[state])
        annotations = list(self.annotations)
        for i in self.selected:
            a = annotations[i]
            reply = Reply(self.prefs.author, tr("Status: {status}", status=name), state, annots.now())
            annotations[i] = dataclasses.replace(a, replies=a.replies + (reply,))
        self.change(annotations, self.selected)

    def show_menu(self, menu: QMenu, where):
        # A method of its own so that the tests can replace it: exec() would block them.
        menu.exec(where)

    def _edit_menu(self):
        """The Edit menu, as things are when it opens."""
        n = len(self.selected)
        self.a_delete.setText(ntr("Delete the selected annotation", "Delete the {count} selected annotations", n)
                              if n else tr("Delete the selected annotations"))
        here = self.doc is not None and any(a.page == self.page for a in self.annotations)
        self.a_select_all.setEnabled(here)
        self.a_select_kind.setEnabled(bool(self.selected))
        self.a_clear_page.setEnabled(here)
        self.a_lock.setText(tr("Unlock") if self.selected and all(self.annotations[i].locked for i in self.selected)
                            else tr("Lock"))
        self.m_align.setEnabled(len(self._movable()) > 1)
        # Group needs at least two annotations that are not all in one group already.
        self.a_group.setEnabled(n > 1 and len({self.annotations[i].group or i for i in self.selected}) > 1)
        self.a_ungroup.setEnabled(any(self.annotations[i].group for i in self.selected))
        self.a_undo.setText(tr("Undo") if not self.undo_stack else tr("Undo ({count})", count=len(self.undo_stack)))

    def undo(self):
        self.canvas.commit_text()
        self.keep_comment()
        if self.undo_stack and isinstance(self.undo_stack[-1], DocState):  # (a change of the document itself)
            state = self.undo_stack.pop()
            # Antes de volver atrás, el estado actual (archivo, anotaciones y página) se guarda para poder rehacer.
            self.redo_stack.append(self._state())
            self.restore(state)
        elif self.undo_stack:
            # A plain change of the annotations: the lists are swapped between the two stacks.
            self.redo_stack.append(self.annotations)
            self.annotations = self.undo_stack.pop()
            self.selected = []
            self.refresh()

    # TODO: unlike undo, redo doesn't commit the text being written on the canvas, nor keep the comment typed
    # in the panel, before it changes the state: they may be lost.
    def redo(self):
        if self.redo_stack and isinstance(self.redo_stack[-1], DocState):
            state = self.redo_stack.pop()
            self.undo_stack.append(self._state())
            self.restore(state)
        elif self.redo_stack:
            self.undo_stack.append(self.annotations)
            self.annotations = self.redo_stack.pop()
            self.selected = []
            self.refresh()

    # ----------------------------------------------------------------- find and highlight

    def find_dialog(self, text: str = ""):
        if self.doc is None:
            return
        if self.finder is None:
            self.finder = FindDialog(self)
            # El diálogo se crea una vez y se reutiliza: show_match hace destellar un resultado en el lienzo, y mark
            # marca los elegidos.
            self.finder.show_match.connect(lambda m: (self.remember_place(), self.canvas.flash(m.page, annots.union(m.rects))))
            self.finder.mark.connect(self.mark_matches)
        self.finder.start(text)

    def mark_matches(self, matches: list, kind: str):
        """A mark of KIND over each place of MATCHES (not twice over the same place)."""
        # Places already marked with this kind are skipped, so that running the same search twice adds nothing.
        have = {(a.page, a.quads) for a in self.annotations if a.kind == kind}
        new = []
        for m in matches:
            if (m.page, m.rects) not in have:
                have.add((m.page, m.rects))
                new.append(self.new_annotation(kind, m.page, annots.union(m.rects), quads=m.rects))
        if not new:
            self.status(tr("Those places are marked already"))
            return
        self.change(self.annotations + new, list(range(len(self.annotations), len(self.annotations) + len(new))))
        self.status(ntr("{count} place marked", "{count} places marked", len(new)))

    # ----------------------------------------------------------------- selection and the list

    def pick(self, indices: list[int], add: bool):
        self.keep_comment()
        # Solo se pueden elegir las anotaciones del modo activo.
        indices = [i for i in indices if self.owns(self.annotations[i])]
        # With ADD, each index is toggled in or out of the selection.
        if add:
            chosen = list(self.selected)
            for i in indices:
                if i in chosen:
                    chosen.remove(i)
                else:
                    chosen.append(i)
        else:
            chosen = list(indices)
        # Un miembro de un grupo arrastra a los demás; al quitarlo de la selección, sale el grupo entero.
        chosen = self._with_groups(chosen, indices if add else None)
        if chosen != self.selected:
            self.selected = chosen
            # Only the selection changed: the list and the page labels need not be built again.
            self.refresh(pages=False, table=False)
            self._select_rows()

    # ----------------------------------------------------------------- layers

    def layers_menu(self):
        """The Layers menu, as things are when it opens: each layer, to show or hide; the layer of the
        annotations made; moving the selected ones to a layer; a new layer."""
        m = self.m_layers
        m.clear()
        names = sorted(self.layers, key=str.lower)
        for name in names:
            act = m.addAction(name, lambda _=False, n=name: self.show_layer(n, not self.layers[n]))
            act.setCheckable(True)
            act.setChecked(self.layers[name])
            act.setToolTip(tr("Show or hide the annotations of this layer (saved in the document)"))
        if not names:
            m.addAction(tr("(no layers yet)")).setEnabled(False)
        m.addSeparator()
        made = m.addMenu(tr("Make new annotations in"))
        # El nombre vacío es «sin capa».
        for name in ["", *names]:
            act = made.addAction(name or tr("No layer"), lambda _=False, n=name: setattr(self, "layer", n))
            act.setCheckable(True)
            act.setChecked(self.layer == name)
        move = m.addMenu(tr("Move the selected annotations to"))
        move.setEnabled(bool(self.selected) and self.doc is not None)
        for name in ["", *names]:
            move.addAction(name or tr("No layer"), lambda _=False, n=name: self.move_to_layer(n))
        m.addSeparator()
        m.addAction(tr("New layer…"), self.new_layer).setEnabled(self.doc is not None)

    def show_layer(self, name: str, on: bool):
        self.layers[name] = on
        # Las anotaciones ocultas no pueden seguir seleccionadas.
        if not on:
            self.selected = [i for i in self.selected if self.annotations[i].layer != name]
        self.refresh()
        self._update_title()

    def move_to_layer(self, name: str):
        chosen = set(self.selected)
        # Una capa nueva entra visible; si se mueve a una capa oculta, lo movido sale de la selección.
        if name:
            self.layers.setdefault(name, True)
        self.change([dataclasses.replace(a, layer=name) if i in chosen else a for i, a in enumerate(self.annotations)],
                    sorted(i for i in chosen if self.layers.get(name, True)))

    def new_layer(self, name: str | None = None) -> str:
        """A new layer (NAME, or asked), made the layer of new annotations, and of those selected."""
        if name is None:
            name, ok = QInputDialog.getText(self, tr("New layer"), tr("Name of the layer:"))
            if not ok:
                return ""
        name = " ".join(name.split())
        if not name:
            return ""
        self.layers.setdefault(name, True)
        self.layer = name
        if self.selected:
            self.move_to_layer(name)
        return name

    def _critical_for_selected(self, kind: str):
        """Give the annotations selected an entry of textual criticism of KIND (keeping what else
        their entries had); '': none."""
        def entry(a: Annotation):
            if not kind:
                return None
            # Changing the type keeps the rest of the entry (lemma, reading, witness...).
            return dataclasses.replace(a.critical, type=kind) if a.critical else annots.Critical(kind)

        chosen = set(self.selected)
        self.change([dataclasses.replace(a, critical=entry(a)) if i in chosen else a
                     for i, a in enumerate(self.annotations)], sorted(chosen))

    def _with_groups(self, chosen: list[int], toggled: list[int] | None = None) -> list[int]:
        """CHOSEN, with the others of their groups (those of TOGGLED that were taken out, without theirs)."""
        # Grupos de las anotaciones quitadas de la selección: sus compañeras también salen.
        dropped = {self.annotations[i].group for i in toggled or [] if i not in chosen and i < len(self.annotations)}
        groups = {self.annotations[i].group for i in chosen if i < len(self.annotations)} - {""} - dropped
        out = [i for i in chosen if i < len(self.annotations) and self.annotations[i].group not in dropped - {""}]
        return out + [i for i, a in enumerate(self.annotations) if a.group in groups and i not in out]

    def group_selected(self):
        """The annotations selected (and the others of their groups), made one group."""
        if len(self.selected) < 2:
            return
        name = uuid.uuid4().hex[:12]
        chosen = set(self.selected)
        self.change([dataclasses.replace(a, group=name) if i in chosen else a for i, a in enumerate(self.annotations)],
                    sorted(chosen))
        self.status(ntr("{count} annotation grouped", "{count} annotations grouped", len(chosen)))

    def ungroup_selected(self):
        groups = {self.annotations[i].group for i in self.selected} - {""}
        if not groups:
            return
        self.change([dataclasses.replace(a, group="") if a.group in groups else a for a in self.annotations],
                    list(self.selected))

    def select_page(self):
        if self.canvas.mode == TEXT_SELECT:  # (Ctrl+A with the tool Select text: the text of the page)
            self.canvas.select_all_text(self.page)
            return
        self.pick([i for i, a in enumerate(self.annotations) if a.page == self.page], False)

    # ----------------------------------------------------------------- the text selected (tool Select text)

    def _text_selection_changed(self):
        self.a_copy.setEnabled(bool(self.canvas.text_sel) or bool(self.selected))

    def copy_selected_text(self) -> str:
        text = self.canvas.selected_text()
        if text:
            QApplication.clipboard().setText(text)
            self.status(ntr("{count} character copied", "{count} characters copied", len(text)))
        return text

    def text_menu(self, where):
        """The menu of the text selected: copy it, mark it (highlight, underline, strike out, squiggle),
        mark it for redaction, or find it."""
        menu = QMenu(self)
        menu.addAction(icon("edit-copy"), tr("Copy"), self.copy_selected_text)
        menu.addSeparator()
        for kind, name in (("highlight", "draw-highlight"), ("underline", "format-text-underline"),
                           ("strikeout", "format-text-strikethrough"), ("squiggly", "format-text-underline-squiggle")):
            menu.addAction(icon(name), tool_name(kind), lambda k=kind: self.mark_selected_text(k))
        menu.addAction(tr("Mark for redaction"), self.redact_selected_text)
        menu.addSeparator()
        text = self.canvas.selected_text()
        short = text if len(text) <= 30 else text[:29] + "…"
        menu.addAction(icon("edit-find"), tr("Find “{text}”", text=" ".join(short.split())),
                       lambda: self.find_dialog(" ".join(text.split())))
        self.show_menu(menu, where)

    def mark_selected_text(self, kind: str) -> bool:
        """The text selected, marked (KIND: highlight...), one mark for each page it is on."""
        if not self.canvas.editable:
            return False
        for page, rects in self.canvas.selection_rects().items():
            self.add_markup(page, rects, kind)
        self.canvas.clear_text_selection()
        return True

    def redact_selected_text(self) -> bool:
        """Boxes of redaction over the text selected."""
        if not self.canvas.editable:
            return False
        for page, rects in self.canvas.selection_rects().items():
            self.add_redact_text(page, rects)
        self.canvas.clear_text_selection()
        return True

    def select_kind(self):
        kinds = {self.annotations[i].kind for i in self.selected}
        self.pick([i for i, a in enumerate(self.annotations) if a.page == self.page and a.kind in kinds], False)

    def _table_selected(self):
        # La selección la está poniendo el programa (ver _select_rows): no hay que reaccionar.
        if self._quiet_table:
            return
        # The rows of the list map to indices of self.annotations through _rows (sorted and filtered).
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        chosen = [self._rows[r] for r in rows if r < len(self._rows)]
        if chosen == self.selected:
            return
        self.keep_comment()
        self.selected = chosen
        self.refresh(pages=False, table=False)
        # Una sola elegida en la lista: el lienzo va a ella y la hace destellar.
        if len(chosen) == 1:
            a = self.annotations[chosen[0]]
            self.canvas.flash(a.page, a.rect)

    def go_annotation(self, step: int):
        """The next (STEP 1) or previous (-1) annotation of the list, as it is sorted and filtered."""
        if not self._rows:
            return
        current = self._rows.index(self.selected[0]) if self.selected and self.selected[0] in self._rows else None
        if current is None:  # (from the page in view)
            # Without a selection, start from the page in view: forward, the first at or after it; back, the one
            # before.
            after = [r for r, i in enumerate(self._rows) if self.annotations[i].page >= self.page]
            row = (after[0] if after else 0) if step > 0 else (max(after[0] - 1, 0) if after else len(self._rows) - 1)
        else:
            # Pasada la última, se vuelve a la primera (y al revés).
            row = (current + step) % len(self._rows)
        i = self._rows[row]
        self.keep_comment()
        self.selected = [i]
        self.refresh(pages=False, table=False)
        self._select_rows()
        self.canvas.flash(self.annotations[i].page, self.annotations[i].rect)

    def _filter_changed(self):
        self._fill_table()
        self._enable()
        # With 'Only those the list shows', the pages depend on the filters too.
        if self.a_only_listed.isChecked():
            self.refresh(table=False)

    def _passes(self, a: Annotation) -> bool:
        """Whether A is let through by the search and filters of the list (and its layer is shown)."""
        # Las de otros modos y las de capas ocultas nunca aparecen en la lista.
        if not self.owns(a) or a.layer and not self.layers.get(a.layer, True):
            return False
        kind, author, color = self.f_kind.currentData(), self.f_author.currentData(), self.f_color.currentData()
        status, tag, category = self.f_status.currentData(), self.f_tag.currentData(), self.f_category.currentData()
        if kind and a.kind != kind or author is not None and a.author != author or color and a.color != color:
            return False
        # Status filter: '-' means no status yet; any other value, that status.
        if status == "-" and a.status() or status and status != "-" and a.status() != status:
            return False
        if tag and tag not in a.tags or category and category not in a.categories:
            return False
        # TODO: el texto de cada anotación se arma y se normaliza otra vez en cada búsqueda y cada refresco; con
        # miles de anotaciones convendría guardarlo por anotación.
        words = search.fold(self.search.text().lower())[0].split()  # (accents not minded)
        if words:
            c = a.critical
            # Se busca en todo lo que el usuario ve de una anotación: comentario, autor, texto marcado, etiquetas,
            # aparato crítico, categorías y respuestas.
            text = " ".join((a.contents, a.author, a.name(), a.layer, self.marked_text(a), " ".join(a.tags),
                             " ".join((c.name(), c.lemma, c.reading, c.witness, c.location, c.source, c.rationale))
                             if c else "",
                             " ".join(a.categories), " ".join(f"{r.author} {r.contents}" for r in a.replies))).lower()
            text = search.fold(text)[0]
            return all(w in text for w in words)
        return True

    def _fill_filters(self):
        """The choices of the filters: the kinds, authors (with how many annotations each has),
        colours, statuses, tags and categories there are."""
        by_author = Counter(a.author for a in self.annotations)
        statuses = {a.status() for a in self.annotations if a.status()}
        for box, everything, values in (
                (self.f_kind, tr("All kinds"), sorted({a.kind for a in self.annotations},
                                                      key=lambda k: (KINDS + (annots.OTHER,)).index(k))),
                (self.f_author, tr("All authors"), sorted(by_author)),
                (self.f_color, tr("All colours"), sorted({a.color for a in self.annotations})),
                (self.f_status, tr("Any status"), ["-"] + [s for s in STATES if s in statuses]),
                (self.f_tag, tr("All tags"), sorted({t for a in self.annotations for t in a.tags}, key=str.lower)),
                (self.f_category, tr("All categories"), sorted({c for a in self.annotations for c in a.categories},
                                                               key=str.lower))):
            # The choice in each box is kept across the refill if it still exists; signals are blocked meanwhile.
            current = box.currentData()
            box.blockSignals(True)
            box.clear()
            # El filtro de autor usa None para «todos», porque "" es un autor válido (anotaciones sin autor).
            box.addItem(everything, None if box is self.f_author else "")
            for value in values:
                if box is self.f_kind:
                    box.addItem(tool_name(value), value)
                elif box is self.f_author:
                    box.addItem(f"{value or tr('(no author)')} ({by_author[value]})", value)
                elif box is self.f_color:
                    box.addItem(swatch(value), color_name(value), value)
                elif box is self.f_status:
                    box.addItem(tr("No status yet") if value == "-" else tr(STATES[value]), value)
                else:
                    box.addItem(value, value)
            index = box.findData(current) if current is not None else 0
            box.setCurrentIndex(max(index, 0))
            box.blockSignals(False)

    # ----------------------------------------------------------------- showing

    def refresh(self, pages: bool = True, table: bool = True):
        """Show the annotations again, after a change."""
        if table:
            self._fill_filters()
            self._fill_table()
        if pages:
            self._label_pages()
        # With the annotations hidden (View menu), the canvas doesn't let them be edited.
        self.canvas.editable = self.a_show.isChecked()
        self.canvas.set_annotations(self.canvas_items(self.shown()), self.selected)
        # Los paneles de Páginas y Censurar se rellenan cuando cambia la lista; con table=False, el de Censurar
        # solo actualiza la selección.
        if self.mode == "pages" and table:
            self.fill_pages_panel()
        if self.mode == "redact":
            if table:
                self.fill_redact_panel()
            else:
                self._select_redact_rows()
                self._show_redact_panel()
        self._show_panel()
        self._enable()
        self._update_title()

    def shown(self) -> list[int]:
        """The annotations to show on the pages: all, none, or those the list lets through."""
        if not self.a_show.isChecked():
            return []
        if self.a_only_listed.isChecked():
            # _rows holds the annotations the list shows, in its order: sorted again for drawing.
            return sorted(self._rows)
        return [i for i, a in enumerate(self.annotations) if self.layers.get(a.layer, True)]

    def show_page(self, page: int):
        """Bring PAGE into view."""
        if self.doc is None:
            return
        # Se acota al rango: quien llama pasa page ± 1, o números guardados sin comprobar.
        page = max(0, min(page, self.count - 1))
        self.canvas.go_to(page)
        self._page_shown(page)

    def _thumb_row_changed(self, row: int):
        """A thumbnail made the current one: go to its page, unless it was chosen with Ctrl or Shift (then it
        joins the pages chosen, and the page shown stays)."""
        held = QApplication.keyboardModifiers() & (Qt.KeyboardModifier.ControlModifier
                                                   | Qt.KeyboardModifier.ShiftModifier)
        if row >= 0 and not held:
            self.show_page(row)

    def _thumbs_selection_changed(self):
        """The pages chosen in the thumbnails are those of Foliate's list too (see selected_pages)."""
        if getattr(self, "_syncing_selection", False):
            return
        self._syncing_selection = True
        try:
            rows = {i.row() for i in self.pages.selectedIndexes()}
            pl = self.page_list
            pl.blockSignals(True)
            for n in range(pl.count()):
                pl.item(n).setSelected(n in rows)
            pl.blockSignals(False)
            self._update_page_actions()
            self.ocr_refresh()
        finally:
            self._syncing_selection = False

    def thumbs_menu(self, pos):
        """The menu of the pages chosen in the thumbnails (in any mode): a page right-clicked outside them
        becomes the one chosen."""
        item = self.pages.itemAt(pos)
        if item is None or self.doc is None:
            return
        if not item.isSelected():
            self.pages.blockSignals(True)
            self.pages.clearSelection()
            item.setSelected(True)
            self.pages.blockSignals(False)
            self._thumbs_selection_changed()
        menu = self.build_pages_menu()
        if menu is None:
            return
        pages = self.selected_pages()
        menu.addSeparator()
        every = menu.addAction(tr("Select all the pages"), self.select_all_pages)
        every.setShortcut(QKeySequence.StandardKey.SelectAll)  # (que se vea: la tecla la toma la lista)
        every.setEnabled(len(pages) < self.count)
        a = menu.addAction(tr("Recognise the text of these pages (OCR)…") if len(pages) > 1
                           else tr("Recognise the text of this page (OCR)…"),
                           lambda: self.recognise_dialog(chosen=True))
        # (en cualquier modo: no se mira la acción del modo OCR, que se desactiva mientras otro modo está activo)
        from ..annotate import ocr

        a.setEnabled(self.path is not None and ocr.available())
        self.show_menu(menu, self.pages.viewport().mapToGlobal(pos))

    def select_all_pages(self):
        """Every page chosen in the thumbnails (and in Foliate's list, which follows them)."""
        self.pages.selectAll()

    def go_to_typed(self, typed: str) -> bool:
        """Go to the page TYPED names: the page shown, if it is its label; else a page with that label (any
        case; Enter again goes to the next one with it); else '(3)', the third page; else a page number."""
        text = typed.strip()
        if self.doc is None or not text:
            return False
        found = self.page_labels()
        if self.page < len(found) and (found[self.page] or str(self.page + 1)) == text:
            return True
        same = [n for n, label in enumerate(found) if label and label.casefold() == text.casefold()]
        if same:
            after = [n for n in same if n > self.page]
            self.go_place((after or same)[0])
            return True
        digits = text[1:-1] if text.startswith("(") and text.endswith(")") else text
        if digits.isdigit() and 1 <= int(digits) <= self.count:
            self.go_place(int(digits) - 1)
            return True
        self.status(tr("No page is labelled {label}", label=text), error=True)
        self._page_shown(self.page)
        return False

    def _page_shown(self, page: int):
        """PAGE is the one in view now (turned to, or scrolled to)."""
        self.page = page
        found = self.page_labels() if self.doc is not None else []
        label = found[page] if page < len(found) else ""
        # La casilla muestra la etiqueta (o el número, sin etiqueta); junto a ella, cuántas páginas hay, con los
        # detalles de la página (tamaño, orientación) como consejo.
        self.a_page_number.show_page(label or str(page + 1), self.count,
                                     self.page_details(page) if self.doc is not None else "")
        self.pages.blockSignals(True)
        if len(self.pages.selectedIndexes()) > 1:
            # (several pages chosen: they stay chosen, and only the current one follows the page shown)
            self.pages.selectionModel().setCurrentIndex(self.pages.model().index(page, 0),
                                                        QItemSelectionModel.SelectionFlag.NoUpdate)
        else:
            self.pages.setCurrentRow(page)
        self.pages.blockSignals(False)
        self._show_panel()
        self.ocr_refresh()
        self._outline_mark(page)
        self._enable()
        # _page_shown may run while the window is being built, before the modes (and the mode Pages) exist.
        if hasattr(self, "modes"):
            self.pages_page_shown()

    def _show_zoom(self, z: float):
        """The zoom in its box (not while it is being typed)."""
        if not self.zoom_label.lineEdit().hasFocus():
            self.zoom_label.setEditText(f"{z * 100:.0f} %")

    def _choose_zoom(self, value):
        """A fit ('page', 'width'...), 'actual', a factor, or a percentage typed ('150', '150 %')."""
        if value in ("page", "width", "height", "visible"):
            self._fit(value)
        elif value == "actual":
            self.canvas.actual_size()
        elif isinstance(value, float):
            self.canvas.set_zoom(value)
        else:
            text = str(value).replace("%", "").replace(",", ".").strip()
            try:
                self.canvas.set_zoom(float(text) / 100)
            except ValueError:
                self.status(tr("{text} is not a zoom: type a percentage, such as 150", text=value), error=True)
        self.zoom_label.lineEdit().clearFocus()
        self.canvas.setFocus()
        self._show_zoom(self.canvas.zoom())

    def _fit(self, how: str):
        self.canvas.fit = how
        self.canvas.apply_fit()

    def _fill_pages(self):
        self.pages.clear()
        # Iconos transparentes del tamaño final, para que la lista no cambie de alto cuando lleguen las miniaturas.
        blank = QPixmap(self.thumb)
        blank.fill(QColor(0, 0, 0, 0))
        self._blank_icon = QIcon(blank)  # (also for a thumbnail forgotten: see _forget_far_thumbnails)
        for n in range(self.count):
            item = QListWidgetItem(self._blank_icon, str(n + 1))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.pages.addItem(item)
        self.thumb_timer.start()

    def refresh_captions(self):
        """The captions of the thumbnails as the labels are now (see _label_pages)."""
        self._label_pages()

    def show_thumbnails(self, on: bool):
        """Show or hide the thumbnails of the pages (View menu)."""
        self.thumbs_box.setVisible(on)
        if self.a_thumbs.isChecked() != on:
            self.a_thumbs.setChecked(on)
        if on and self.doc is not None:
            self.thumb_timer.start()

    def _thumb_rows(self) -> list[int]:
        """The pages whose thumbnails are wanted now: those in view, then a screenful below and above."""
        if not self.count:
            return []
        top = max(self.pages.indexAt(QPoint(10, 10)).row(), 0)
        bottom = self.pages.indexAt(QPoint(10, self.pages.viewport().height() - 10)).row()
        if bottom < top:  # (the list is taller than its rows, or not laid out yet)
            bottom = min(self.count - 1, top + 20)
        if ALL_THUMBS:  # (those in view first, then all the others, nearest first)
            rest = sorted(set(range(self.count)) - set(range(top, bottom + 1)), key=lambda n: abs(n - top))
            return [*range(top, bottom + 1), *rest]
        span = bottom - top + 1
        return [*range(top, bottom + 1), *range(bottom + 1, min(self.count, bottom + 1 + span)),
                *range(top - 1, max(-1, top - 1 - span), -1)]

    def _forget_far_thumbnails(self, rows: list[int]):
        """Keep at most MAX_THUMBS thumbnails: those farthest from ROWS (the ones wanted) are forgotten."""
        if len(self._thumbs) <= MAX_THUMBS:
            return
        middle, wanted = rows[0] if rows else 0, set(rows)
        far = sorted((n for n in self._thumbs if n not in wanted), key=lambda n: -abs(n - middle))
        for n in far[:len(self._thumbs) - MAX_THUMBS]:
            del self._thumbs[n]
            self._thumb_shown.pop(n, None)
            if n < self.pages.count():
                self.pages.item(n).setIcon(self._blank_icon)

    def _draw_thumbnails(self):
        """Make the thumbnails near those in view (see _thumb_rows), the visible ones first: in the other
        processes, all at once, once the pages in view are drawn; or here, one at each turn of the event
        loop, so that the window answers between them."""
        if self.doc is None or self.thumbs_box.isHidden():  # (hidden: drawn when they are shown again)
            self.thumb_timer.stop()
            return
        remote = renderer()
        remote = remote if self.canvas.source is not None and remote.available() else None
        # Primero las páginas: mientras se dibujan las que se ven, las miniaturas esperan.
        if (remote is not None and remote.busy("view")) or self.canvas._here:
            self.thumb_timer.start(50)
            return
        rows = self._thumb_rows()
        self._forget_far_thumbnails(rows)
        missing = [n for n in rows if n not in self._thumbs]
        if remote is not None:
            wanted = set(rows)
            # Las que ya no se ven dejan la cola; las que se están haciendo llegan igual.
            remote.drop("thumbs", keep=lambda path, number: number in wanted)
            self._thumb_asked &= wanted
            source = self.canvas.source
            for n in missing:
                if n in self._thumb_asked:
                    continue
                self._thumb_asked.add(n)
                page = self.doc[n]
                scale = min(self.thumb.width() / page.rect.width, self.thumb.height() / page.rect.height)
                remote.request("thumbs", source, n, round(scale, 4),
                               lambda image, n=n, scale=scale: self._thumb_arrived(source, n, scale, image))
            # (each one that arrives starts the timer again, for those still missing)
            self.thumb_timer.stop()
            return
        if not missing:
            self.thumb_timer.stop()
            return
        n = missing[0]
        page = self.doc[n]
        scale = min(self.thumb.width() / page.rect.width, self.thumb.height() / page.rect.height)
        self.thumb_timer.setInterval(0)
        self._thumbs[n] = page_image(page, scale)
        self._thumb(n)

    def _thumb_arrived(self, source, n: int, scale: float, image):
        from .renderer import Skipped, skipped_image

        self._thumb_asked.discard(n)
        if self.doc is None or source != self.canvas.source:
            return  # (of a document no longer open)
        if isinstance(image, Skipped):  # (a page skipped: grey, without words, at the thumbnail's size)
            r = self.doc[n].rect
            image = skipped_image(round(r.width * scale), round(r.height * scale), image, words=False)
        # Si el otro proceso no pudo, la miniatura se hace aquí.
        self._thumbs[n] = image if image is not None else page_image(self.doc[n], scale)
        self._thumb(n)
        self.thumb_timer.start()

    def _thumb(self, n: int):
        """The thumbnail of page N, with its annotations (drawn again only if they changed)."""
        image = self._thumbs.get(n)
        if image is None or n >= self.pages.count():
            return
        shown = tuple(self._by_page[n]) if n < len(self._by_page) else ()
        # The annotations shown on it are those of last time: no need to paint it again.
        if self._thumb_shown.get(n) == shown:
            return
        self._thumb_shown[n] = shown
        pixmap = QPixmap(self.thumb)
        pixmap.fill(QColor(0, 0, 0, 0))
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # La imagen va centrada a lo ancho y apoyada en el borde inferior del icono.
        x, y = (self.thumb.width() - image.width()) // 2, self.thumb.height() - image.height()
        p.drawImage(x, y, image)
        p.save()
        p.translate(x, y)
        # The annotations are in PDF points: scaled to the size of the picture.
        scale = image.width() / self.doc[n].rect.width
        p.scale(scale, scale)
        for a in shown:
            paint(p, a, thumbnail=True)
        p.restore()
        p.setPen(QPen(QColor(128, 128, 128)))
        p.drawRect(x, y, image.width() - 1, image.height() - 1)
        p.end()
        self.pages.item(n).setIcon(QIcon(pixmap))

    def _label_pages(self):
        if self.doc is None:
            return
        self._by_page = [[] for _ in range(self.count)]
        shown = set(self.shown())
        # Solo las anotaciones visibles y del modo cuentan para el número junto a la miniatura.
        for i, a in enumerate(self.annotations):
            if 0 <= a.page < self.count and i in shown and self.owns(a):
                self._by_page[a.page].append(a)
        # En todos los modos, cada página con su etiqueta, o con su número si no la tiene (nunca las dos cosas);
        # y cuántas anotaciones tiene.
        try:
            shown_labels = self.page_labels()
        except Exception:  # (unas etiquetas que no se pueden leer no impiden mostrar las páginas)
            shown_labels = []
        for n in range(min(self.count, self.pages.count())):
            item = self.pages.item(n)
            count = len(self._by_page[n])
            label = shown_labels[n] if n < len(shown_labels) else ""
            text = label or str(n + 1)
            if count:
                text += f"  ● {count}"
            # setText solo si cambia: cada llamada vuelve a pintar el elemento.
            if item.text() != text:
                item.setText(text)
            self._thumb(n)

    def marked_text(self, a: Annotation) -> str:
        """The text under a highlight (or another markup), kept once found."""
        if a.kind not in MARKUP:
            return ""
        key = (a.page, a.quads)
        if key not in self._marked and self.doc is not None and 0 <= a.page < self.count:
            if a.page not in self._words:  # (the words of a page, read once)
                self._words[a.page] = annots.page_text(self.doc[a.page])
            self._marked[key] = annots.text_in(self._words[a.page], a.quads)
        return self._marked.get(key, "")

    def _fill_table(self):
        sort = self.sort.currentData()
        # Las claves de orden; casi todas desempatan por la página.
        keys = {
            "page": lambda i: (self.annotations[i].page, self.annotations[i].rect[1], self.annotations[i].rect[0]),
            "changed": lambda i: (self._age(self.annotations[i]), self.annotations[i].page),
            "kind": lambda i: ((KINDS + (annots.OTHER,)).index(self.annotations[i].kind), self.annotations[i].page),
            "author": lambda i: (self.annotations[i].author.lower(), self.annotations[i].page),
            "status": lambda i: (list(STATES).index(self.annotations[i].status()) if self.annotations[i].status()
                                 else -1, self.annotations[i].page),
        }
        order = sorted((i for i, a in enumerate(self.annotations) if self._passes(a)), key=keys.get(sort, keys["page"]))
        self._rows = order
        # Resetting the model clears its selection, which must not reach _table_selected.
        self._quiet_table = True
        self.model.set_rows(order)
        self._quiet_table = False
        self.listing.listed.setText(tr("{shown} of {count}", shown=len(order), count=len(self.annotations))
                                    if len(order) != len(self.annotations) else
                                    ntr("{count} annotation", "{count} annotations", len(order)))
        self._select_rows()

    @staticmethod
    def _age(a: Annotation) -> float:
        """For sorting the last changed first (those never saved, before all)."""
        when = annots.date_value(a.modified or a.created)
        # Las nunca guardadas (sin fecha) van primero: -inf.
        return -when.timestamp() if when else float("-inf")

    def _select_rows(self):
        """Select in the list the rows of the annotations selected, all at once."""
        chosen = set(self.selected)
        model = self.model
        last = model.columnCount() - 1
        selection = QItemSelection()
        start = None
        rows = []
        # Un None al final cierra la última racha de filas seleccionadas.
        for row, i in enumerate(self._rows + [None]):
            if i is not None and i in chosen:
                rows.append(row)
                if start is None:
                    start = row
            elif start is not None:  # (a run of selected rows ends: one range for all of it)
                selection.select(model.index(start, 0), model.index(row - 1, last))
                start = None
        self._quiet_table = True
        self.table.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self._quiet_table = False
        # Con una sola fila elegida, la lista se desplaza hasta ella.
        if len(rows) == 1:
            self.table.scrollTo(model.index(rows[0], 0))

    def _show_panel(self):
        """The colour, comment, tags, replies and status of the annotation selected (or the colour of new
        ones of the tool)."""
        chosen = [self.annotations[i] for i in self.selected if i < len(self.annotations)]
        p = self.listing
        if chosen:
            if len(chosen) == 1:
                title = tr("{kind}, on page {page}", kind=chosen[0].name(), page=chosen[0].page + 1)
                if chosen[0].author:
                    title += " — " + chosen[0].author
                p.title.setText("<b>" + title + "</b>")
            else:
                p.title.setText("<b>" + ntr("{count} annotation selected", "{count} annotations selected",
                                            len(chosen)) + "</b>")
            colors_ = {a.color for a in chosen}
        # No selection: the panel shows the colour of the tool, and the colour button sets it for new annotations.
        elif self.canvas.mode in ANNOTATING:
            p.title.setText("<b>" + tr("New annotations: {kind}", kind=tool_name(self.canvas.mode).lower()) + "</b>")
            colors_ = {self.prefs.style(self.canvas.mode).color}
        else:
            p.title.setText("<b>" + tr("No annotation selected") + "</b>")
            colors_ = set()
        color = colors_.pop() if len(colors_) == 1 else None
        self.color_button.setIcon(swatch(color) if color else QIcon())
        self.color_button.setText(color_name(color) if color else (tr("(several)") if chosen else "—"))
        self.color_button.setEnabled(self.doc is not None and (bool(chosen) or self.canvas.mode in ANNOTATING))
        one = chosen[0] if len(chosen) == 1 else None
        # Señales bloqueadas: rellenar el comentario no debe contar como un cambio del usuario.
        self.comment.blockSignals(True)
        self.comment.setEnabled(one is not None)
        text = one.contents if one is not None else ""
        if self.comment.toPlainText() != text:
            self.comment.setPlainText(text)
        self.comment.setPlaceholderText(tr("A comment on this annotation") if one is not None
                                        else tr("Select an annotation to see its comment here"))
        self.comment.blockSignals(False)
        p.comment_label.setText(tr("Text:") if one is not None and one.kind in TEXTUAL + ("note", "caret")
                                else tr("Comment:"))
        tags = ", ".join(one.tags) if one is not None else ""
        # The tags field is not overwritten while the user is typing in it.
        if p.tags.text() != tags and not p.tags.hasFocus():
            p.tags.setText(tags)
        # Las respuestas se rehacen siempre; son pocas por anotación.
        p.replies.clear()
        if one is not None:
            for r in one.replies:
                head = f"{r.author or tr('(no author)')}"
                when = date_text(r.modified or r.created)
                if when:
                    head += f", {when}"
                if r.state:
                    head += f" [{tr(STATES[r.state])}]"
                p.replies.addItem(f"{head}: {r.contents}" if r.contents else head)
        p.replies_label.setText(tr("Replies:") if one is None or not one.status()
                                else tr("Replies (status: {status}):", status=tr(STATES[one.status()])))
        # The status box works as a menu of actions: it always goes back to 'Set the status…'.
        p.status.blockSignals(True)
        p.status.clear()
        p.status.addItem(tr("Set the status…"), "")
        for key, name in STATES.items():
            p.status.addItem(tr(name), key)
        p.status.setCurrentIndex(0)
        p.status.blockSignals(False)
        for w in (p.tags, p.replies, p.reply_edit, p.reply_button, p.status):
            w.setEnabled(one is not None)

    def _standards_menu(self):
        """(The menu Save as opens.) Whether PDF/A and PDF/X can be made, looked for the first time now."""
        if self._have_conform is None:
            self._have_conform = conform.available(self.prefs.pdfconform)
        self._enable_standards()

    def _enable_standards(self):
        for act in self.standard_actions.values():
            act.setEnabled(self.doc is not None and bool(self._have_conform))
            act.setToolTip("" if self._have_conform else tr("Needs {command}: install it, or say where it is in "
                                                            "Settings", command=conform.COMMAND))

    def _enable(self):
        has = self.doc is not None
        for w in (self.a_save_as, self.a_first, self.a_last, self.a_fit, self.a_fit_width, self.a_zoom_in,
                  self.a_zoom_out, self.a_page_number, self.a_flat, self.a_bare, self.a_import_json, self.a_import_pdf,
                  self.a_import_xfdf, self.a_print, self.a_doc_props, self.a_word_index, self.a_find, self.a_quick_find, self.quick_find_key, self.a_compare,
                  *self.tool_actions.values()):
            w.setEnabled(has)
        if not has:
            self.a_page_number.show_page("", 0)
        # ocr.available() se calcula una sola vez (functools.cache): si se instala Tesseract con la ventana
        # abierta, no se nota hasta reiniciar.
        from ..annotate import ocr

        self.a_ocr.setEnabled(has and ocr.available())
        self.a_recognise.setEnabled(has and ocr.available())
        self.a_ocr.setToolTip(self.a_ocr.toolTip() if ocr.available() else tr("Needs Tesseract: install it"))
        if self._have_conform is not None:
            self._enable_standards()
        for w in (self.a_export_md, self.a_export_csv, self.a_export_apparatus, self.a_export_json, self.a_export_xfdf, self.a_summary,
                  self.a_next_annot, self.a_prev_annot):
            w.setEnabled(has and bool(self._rows))
        # Save is enabled only with something to save; Save as, with any document.
        self.a_save.setEnabled(has and self.is_modified())
        self.a_clear_all.setEnabled(bool(self.annotations))
        self.a_paste.setEnabled(has and bool(_CLIPBOARD))
        self.a_prev.setEnabled(has and self.page > 0)
        self.a_next.setEnabled(has and self.page < self.count - 1)
        self.a_undo.setEnabled(bool(self.undo_stack))
        self.a_redo.setEnabled(bool(self.redo_stack))
        for w in (self.a_delete, self.b_delete, self.a_props, self.b_props, self.a_copy, self.a_duplicate,
                  self.a_lock):
            w.setEnabled(bool(self.selected))
        # Al final, las acciones de los modos inactivos vuelven a desactivarse: el bucle de arriba las habilitó.
        if hasattr(self, "modes"):
            self._mode_enable()

    # ----------------------------------------------------------------- unsaved changes

    def is_modified(self) -> bool:
        # A working copy means changes to the document itself (Pages, Impose) not yet saved.
        return self.annotations != self.saved or self.layers != self.saved_layers or self.work is not None

    def _update_title(self):
        # [*] es el marcador de Qt: muestra un asterisco cuando setWindowModified(True).
        name = f"{self.path.name}[*] — py-pdftools" if self.path else "py-pdftools"
        self.setWindowTitle(name)
        self.setWindowModified(self.is_modified())

    def ask_unsaved(self) -> QMessageBox.StandardButton:
        return ask_save(self, tr("Unsaved annotations"),
                        tr("The annotations have changed since the document was last saved. Save them before "
                           "going on?"))

    def maybe_discard(self) -> bool:
        """True if it is all right to go on (nothing unsaved, saved now, or discarded)."""
        if not self.is_modified():
            return True
        answer = self.ask_unsaved()
        # If saving fails, the caller stops: the window stays open, or the other document is not opened.
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        if answer == QMessageBox.StandardButton.Discard:
            # Descartar también borra la copia de recuperación: no se ofrecerá la próxima vez.
            if self.path is not None:
                recovery.discard(self.path)
            return True
        return False

    # ----------------------------------------------------------------- drag and drop

    def dragEnterEvent(self, event):
        if any(u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        # Solo se abre el primer PDF soltado: la ventana muestra un documento.
        for u in event.mimeData().urls():
            if u.toLocalFile().lower().endswith(".pdf"):
                self.open_path(Path(u.toLocalFile()))
                break

    # ----------------------------------------------------------------- messages

    def warn(self, title: str, text: str):
        """A warning the user must see (a modal message box)."""
        QMessageBox.warning(self, title, text)

    def status(self, text: str, error: bool = False):
        # Los errores quedan en la barra de estado hasta el próximo mensaje; los demás, 8 segundos.
        self.statusBar().setStyleSheet("color: #c0392b;" if error else "")
        self.statusBar().showMessage(text, 0 if error else 8000)

    def about(self):
        QMessageBox.about(self, tr("About py-pdftools"),
                          tr("<b>py-pdftools {version}</b><p>Edits PDF documents: annotates them, redacts them, "
                             "changes their page labels, headers, footers, watermarks and the order of their "
                             "pages, and imposes them for printing.</p><p>It brings together py-annotate, "
                             "py-redact, py-foliation and py-imposition.</p><p>By {author}.</p><p>Licensed under "
                             "the GNU General Public License, version 3 or later.</p>",
                             version=__version__, author=AUTHOR))
