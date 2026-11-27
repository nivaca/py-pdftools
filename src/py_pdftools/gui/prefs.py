"""The Settings dialog: General (the author of new annotations, the recovery copies, running in the background
and starting with the session, tabs, OCR, the pen), Appearance (the colours and size of the interface, its
language, the hints, the toolbars), Documents (how they open, their places, links, the recent ones, the file
dialogs), the colours offered in the menus with what each means, the keyboard shortcuts, the categories, and
Performance."""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import config

from ..annotate import settings
from ..annotate.annots import NAMES
from ..core.interface import N_, tr
from .props import ColorButton

# the actions with a shortcut that aren't tools
ACTION_NAMES = {"select": N_("Select"), "selecttext": N_("Select text"), "hand": N_("Hand"), "zoomarea": N_("Zoom to area"), "magnifier": N_("Magnifier"), "link": N_("Link"), "eraser": N_("Eraser"),
                "comment": N_("Edit comment…"), "next": N_("Next annotation"),
                "previous": N_("Previous annotation"), "copy": N_("Copy"), "paste": N_("Paste"),
                "duplicate": N_("Duplicate"), "properties": N_("Properties"),
                "group": N_("Group"), "ungroup": N_("Ungroup"), "replace": N_("Replace text"),
                "typewriter": N_("Typewriter"), "mark": N_("Check mark"), "signature": N_("Signature")}


def action_name(action: str) -> str:
    # Las acciones que no son herramientas tienen nombre aquí; las herramientas usan el de su anotación.
    return tr(ACTION_NAMES[action]) if action in ACTION_NAMES else tr(NAMES[action])


def _scrolled(page: QWidget) -> QScrollArea:
    """PAGE (a tab of forms) in a scroll area: in a dialog too small for it, it scrolls, instead of its rows
    being squeezed until the texts under a field (wrapped labels) are covered by the next one."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(page)
    # Solo se desplaza de arriba abajo: el diálogo no se estrecha más que lo que piden sus casillas
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setMinimumWidth(page.minimumSizeHint().width() + area.verticalScrollBar().sizeHint().width())
    return area


class SettingsDialog(QDialog):
    def __init__(self, prefs: settings.Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.prefs = prefs
        # Siete pestañas (véase el texto del módulo). Nada se guarda hasta pulsar Aceptar.
        tabs = QTabWidget()

        general = QWidget()
        form = QFormLayout(general)
        self.author = QLineEdit(prefs.author)
        self.author.setPlaceholderText(tr("Your name"))
        self.author.setToolTip(tr("Written in each new annotation, as its author"))
        form.addRow(tr("Author:"), self.author)
        self.autosave = QSpinBox()
        # 0 minutes shows as 'Never' (the special value text) and turns the recovery copies off.
        self.autosave.setRange(0, 120)
        self.autosave.setSuffix(" " + tr("min"))
        self.autosave.setSpecialValueText(tr("Never"))
        self.autosave.setValue(prefs.autosave)
        self.autosave.setToolTip(tr("A copy of the annotations not yet saved is kept this often, and offered "
                                    "if the program stops before they are saved"))
        form.addRow(tr("Recovery copy every:"), self.autosave)
        from . import instance

        self.background = QCheckBox(tr("Keep running in the background, to open documents faster"))
        self.background.setChecked(instance.enabled())
        self.background.setToolTip(tr("When the last window is closed, py-pdftools goes on running (with an "
                                      "icon in the tray, where there is one), and opens the next document at "
                                      "once. File > Quit ends it."))
        form.addRow("", self.background)
        from . import autostart

        self.login = QCheckBox(tr("Start at login, in the system tray: the first document opens at once too"))
        self.login.setChecked(autostart.enabled())
        self.login.setToolTip(tr("py-pdftools starts when you log in, without a window, and waits in the "
                                 "background (so this needs the setting above, which is turned on with it)"))
        # (empezar con la sesión es empezar en segundo plano: una casilla arrastra a la otra)
        self.login.toggled.connect(lambda on: self.background.setChecked(True) if on else None)
        self.background.toggled.connect(lambda on: self.login.setChecked(False) if not on else None)
        form.addRow("", self.login)
        self.reopen = QCheckBox(tr("Reopen the files that were open when py-pdftools last closed"))
        try:
            self.reopen.setChecked(bool(config.get("reopen")))
        except config.ConfigError:
            pass
        form.addRow("", self.reopen)
        self.tabs = QCheckBox(tr("Open documents in tabs of one window"))
        self.tabs.setToolTip(tr("Each document opened goes into a tab of the window, not into a window of its own"))
        try:
            self.tabs.setChecked(bool(config.get("tabs")))
        except config.ConfigError:
            pass
        form.addRow("", self.tabs)
        self.lone_tab = QCheckBox(tr("Show the tabbar with only one document open"))
        try:
            self.lone_tab.setChecked(bool(config.get("lone_tab")))
        except config.ConfigError:
            pass
        form.addRow("", self.lone_tab)
        self.warn_many = QCheckBox(tr("Warn before closing several documents at once"))
        self.warn_many.setToolTip(tr("When py-pdftools is quit, or a window of tabs is closed, with more than "
                                     "one document open"))
        try:
            self.warn_many.setChecked(bool(config.get("warn_many")))
        except config.ConfigError:
            self.warn_many.setChecked(True)
        form.addRow("", self.warn_many)
        self.reload = QCheckBox(tr("Reload documents when their files change on disk"))
        self.reload.setToolTip(tr("At once if nothing is unsaved here; else py-pdftools asks first"))
        try:
            self.reload.setChecked(bool(config.get("reload")))
        except config.ConfigError:
            self.reload.setChecked(True)
        form.addRow("", self.reload)
        # Imported here, not at the top: finding the Tesseract languages runs a program, only worth it
        # when the dialog opens.
        from ..annotate import ocr

        self.ocr_language = QLineEdit(prefs.ocr_language)
        found = ocr.languages()
        self.ocr_language.setToolTip(tr("The languages of the text of scanned pages, as Tesseract names them; "
                                        "several with +: lat+eng") + "\n"
                                     + (tr("Installed: {languages}", languages=", ".join(found)) if found
                                        else tr("Tesseract is not installed: there is no OCR")))
        form.addRow(tr("OCR languages:"), self.ocr_language)
        # Qué hay instalado (y qué modelos mejores se han descargado), y el botón para descargar otros.
        self.ocr_found = QLabel()
        self.ocr_found.setWordWrap(True)
        self.ocr_found.setStyleSheet("color: palette(placeholder-text);")
        manage = QPushButton(tr("OCR languages…"))
        manage.setToolTip(tr("The languages tesseract can read here; download, update or remove its more "
                             "accurate models (and osd, to turn pages)"))
        manage.clicked.connect(self._manage_languages)
        form.addRow("", self.ocr_found)
        form.addRow("", manage)
        self._show_ocr()
        self.pen_pressure = QComboBox()
        for key, name in settings.PEN_PRESSURE.items():
            self.pen_pressure.addItem(tr(name), key)
        # Un valor guardado que ya no existe (de otra versión) cae en la primera opción.
        self.pen_pressure.setCurrentIndex(max(self.pen_pressure.findData(prefs.pen_pressure), 0))
        self.pen_pressure.setToolTip(tr("For drawing with the pen of a tablet; its eraser end always erases"))
        form.addRow(tr("Pen pressure:"), self.pen_pressure)
        self.pen_curve = QComboBox()
        for key, name in settings.PEN_CURVES.items():
            self.pen_curve.addItem(tr(name), key)
        self.pen_curve.setCurrentIndex(max(self.pen_curve.findData(prefs.pen_curve), 0))
        form.addRow(tr("Pen touch:"), self.pen_curve)
        self.pen_button = QComboBox()
        for key, name in settings.PEN_BUTTON.items():
            self.pen_button.addItem(tr(name), key)
        self.pen_button.setCurrentIndex(max(self.pen_button.findData(prefs.pen_button), 0))
        form.addRow(tr("Pen side button:"), self.pen_button)
        self.reset = QCheckBox(tr("Put the tools back as they were at first"))
        self.reset.setToolTip(tr("The colours, lines, fonts and opacity of the annotations each tool makes, and "
                                 "how it behaves"))
        form.addRow("", self.reset)
        where = QLabel(tr("The settings are kept in {path}", path=config.config_path()))
        where.setWordWrap(True)
        where.setStyleSheet("color: palette(placeholder-text);")
        form.addRow(where)
        tabs.addTab(_scrolled(general), tr("General"))
        tabs.addTab(_scrolled(self._appearance_tab(parent)), tr("Appearance"))
        tabs.addTab(_scrolled(self._documents_tab()), tr("Documents"))
        tabs.addTab(_scrolled(self._annotations_tab(parent)), tr("Annotations"))

        colours = QWidget()
        form = QFormLayout(colours)
        intro = QLabel(tr("The colours offered in the menus, and what each one means to you (shown with its name)"))
        intro.setWordWrap(True)
        form.addRow(intro)
        self.palette_rows = []
        # Un significado None es el de fábrica: se muestra traducido solo si el color sigue siendo el
        # de fábrica; si el usuario lo cambió, el campo queda vacío.
        for i, (color, meaning) in enumerate(prefs.palette):
            button = ColorButton(color, bare=True)  # (the colour itself: its meaning is in the field beside it)
            edit = QLineEdit(meaning if meaning is not None else (
                tr(settings.PALETTE[i][2]) if color == settings.PALETTE[i][0] and settings.PALETTE[i][2] else ""))
            edit.setPlaceholderText(tr("What it means"))
            self.palette_rows.append((button, edit))
            form.addRow(button, edit)
        usual = QPushButton(tr("The usual colours"))
        usual.clicked.connect(self._usual_colours)
        form.addRow("", usual)
        tabs.addTab(colours, tr("Colours"))

        keys = QWidget()
        lay = QVBoxLayout(keys)
        # Una fila por acción: la columna de la izquierda no se edita; la de la derecha es un editor de teclas.
        self.keys = QTableWidget(len(settings.SHORTCUTS), 2)
        self.keys.setHorizontalHeaderLabels([tr("Action"), tr("Shortcut")])
        self.keys.verticalHeader().setVisible(False)
        self.keys.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.key_edits: dict[str, QKeySequenceEdit] = {}
        for row, action in enumerate(settings.SHORTCUTS):
            item = QTableWidgetItem(action_name(action))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.keys.setItem(row, 0, item)
            edit = QKeySequenceEdit(QKeySequence(prefs.shortcut(action)))
            edit.setClearButtonEnabled(True)
            self.key_edits[action] = edit
            self.keys.setCellWidget(row, 1, edit)
        lay.addWidget(self.keys)
        usual = QPushButton(tr("The usual keys"))
        usual.clicked.connect(self._usual_keys)
        lay.addWidget(usual, 0, Qt.AlignmentFlag.AlignRight)
        tabs.addTab(keys, tr("Shortcuts"))

        cats = QWidget()
        lay = QVBoxLayout(cats)
        intro = QLabel(tr("The categories annotations can be put in (in their properties): one on each line"))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.categories = QPlainTextEdit("\n".join(prefs.category_list()))
        lay.addWidget(self.categories, 1)
        usual = QPushButton(tr("The usual categories"))
        # A fresh Settings() gives the usual categories, translated.
        usual.clicked.connect(lambda: self.categories.setPlainText(
            "\n".join(settings.Settings().category_list())))
        lay.addWidget(usual, 0, Qt.AlignmentFlag.AlignRight)
        tabs.addTab(cats, tr("Categories"))

        # Rendimiento: la memoria que puede usar la ventana, la transparencia de las selecciones, el suavizado.
        from . import performance

        current = performance.settings()
        perf = QWidget()
        form = QFormLayout(perf)
        self.memory = QComboBox()
        for name, title, tip in performance.PROFILES:
            self.memory.addItem(tr(title), name)
            self.memory.setItemData(self.memory.count() - 1, tr(tip), Qt.ItemDataRole.ToolTipRole)
        self.memory.setCurrentIndex(max(self.memory.findData(current["memory"]), 0))
        self.memory.setToolTip(tr("The more memory the window may use, the faster it goes: more pages kept "
                                  "drawn, drawn further ahead. The number of processes that draw them changes "
                                  "the next time py-pdftools starts."))
        form.addRow(tr("Memory:"), self.memory)
        self.transparency = QCheckBox(tr("Transparency effects"))
        self.transparency.setChecked(current["transparency"])
        self.transparency.setToolTip(tr("Selections drawn with transparency; without, as outlines, which is "
                                        "faster on a slow computer"))
        self.text_antialias = QCheckBox(tr("Smooth the text (antialiasing)"))
        self.text_antialias.setChecked(current["text_antialias"])
        self.graphics_antialias = QCheckBox(tr("Smooth the graphics (antialiasing)"))
        self.graphics_antialias.setChecked(current["graphics_antialias"])
        self.smooth = QCheckBox(tr("Animate zooming and scrolling with the wheel"))
        self.smooth.setChecked(current.get("smooth", True))
        self.smooth.setToolTip(tr("The zoom grows or shrinks in a few steps, and the wheel glides, instead of "
                                  "jumping; smoother still with the graphics card"))
        self.gpu = QCheckBox(tr("Draw the pages with the graphics card (OpenGL)"))
        self.gpu.setChecked(bool(config.get("gpu")))
        self.gpu.setToolTip(tr("Smoother scrolling and zooming: the pictures of the pages are moved and scaled "
                               "by the graphics card. It changes the next time py-pdftools starts. If the pages "
                               "then show black or flicker, turn it off again."))
        self.thumb_cache = QCheckBox(tr("Keep the thumbnails on disk"))
        self.thumb_cache.setChecked(current.get("thumb_cache", False))
        self.thumb_cache.setToolTip(tr("A scanned document opened again shows its thumbnails at once, instead of "
                                       "drawing them again. They are kept in the cache folder, at most 200 MB, and "
                                       "all removed when a redacted copy is written or this is turned off: they "
                                       "would still show what the redaction covers."))
        for box in (self.transparency, self.text_antialias, self.graphics_antialias, self.smooth, self.gpu,
                    self.thumb_cache):
            form.addRow("", box)
        # El motor que dibuja las páginas (core/backends.py): los que faltan aquí, desactivados, con lo que piden.
        from PySide6.QtGui import QStandardItemModel

        from ..core import backends

        self.backend = QComboBox()
        for key in backends.BACKENDS:
            self.backend.addItem(tr(backends.NAMES[key]), key)
            why = backends.why_not(key)
            index = self.backend.count() - 1
            self.backend.setItemData(index, why or tr(backends.DESCRIPTIONS[key]), Qt.ItemDataRole.ToolTipRole)
            if why:
                model = self.backend.model()
                if isinstance(model, QStandardItemModel):
                    model.item(index).setEnabled(False)
        wanted = config.get("backend")
        self.backend.setCurrentIndex(max(self.backend.findData(wanted if not backends.why_not(wanted)
                                                               else backends.MUPDF), 0))
        self.backend.setToolTip(tr("The engine that draws the pages on the screen, in the thumbnails and the "
                                   "presentation. Only how they look changes: annotating, finding, saving and "
                                   "printing are the same with all of them."))
        form.addRow(tr("Draw the pages with:"), self.backend)
        self.ask_backend = QCheckBox(tr("Ask which engine when opening a document"))
        self.ask_backend.setChecked(bool(config.get("ask_backend")))
        self.ask_backend.setToolTip(tr("When more than one can draw here; the one chosen above comes first"))
        form.addRow("", self.ask_backend)
        tabs.addTab(_scrolled(perf), tr("Performance"))

        # Aceptar, Aplicar y Cancelar, como en KDE Plasma: Aplicar deja la ventana abierta, y solo se puede pulsar
        # cuando algo cambió desde la última vez
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Apply
                                   | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setToolTip(tr("Put the changes in effect now, and keep the window open (a new language "
                                        "comes when it is closed)"))
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        self.applied = False  # (whether Apply was pressed: the window then takes the settings even on Cancel)
        self.on_apply = None  # (what the window does with the settings applied: see MainWindow.settings_dialog)
        self.language_changed = self.performance_changed = False
        # Revisar la configuración: en la fila de los botones, a la vista desde cualquier pestaña (al pie de
        # General, bajo una lista larga, no se veía)
        self.check = buttons.addButton(tr("System check…"), QDialogButtonBox.ButtonRole.HelpRole)
        self.check.setToolTip(tr("Whether py-pdftools has what it needs (Python, its libraries, tesseract, "
                                 "Ghostscript), and whether its settings are right"))
        self.check.clicked.connect(lambda: self.check_configuration(parent))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer = QVBoxLayout(self)
        outer.addWidget(tabs)
        outer.addWidget(buttons)
        self.resize(560, 620)
        self._watch(buttons)

    def _watch(self, buttons: QDialogButtonBox):
        """Any change in any page turns Apply on (the buttons of the row at the bottom are not changes)."""
        from PySide6.QtWidgets import QAbstractButton, QKeySequenceEdit

        own = set(buttons.buttons())
        changed = lambda *_: self.apply_button.setEnabled(True)  # noqa: E731
        for w in self.findChildren(QCheckBox):
            w.toggled.connect(changed)
        for w in self.findChildren(QComboBox):
            w.currentIndexChanged.connect(changed)
            if w.isEditable():
                w.editTextChanged.connect(changed)
        for w in self.findChildren(QLineEdit):
            w.textEdited.connect(changed)
        for w in self.findChildren(QSpinBox):
            w.valueChanged.connect(changed)
        for w in self.findChildren(QPlainTextEdit):
            w.textChanged.connect(changed)
        for w in self.findChildren(QKeySequenceEdit):
            w.keySequenceChanged.connect(changed)
        for w in self.findChildren(QTableWidget):
            w.itemChanged.connect(changed)
        for w in self.findChildren(QAbstractButton):
            if w not in own and not isinstance(w, QCheckBox) and w is not self.check:
                w.clicked.connect(changed)  # (los colores, Como era al principio...)

    def apply(self) -> bool:
        """Apply: the changes in effect, the window left open."""
        if not self.put_in_effect():
            return False
        self.applied = True
        self.apply_button.setEnabled(False)
        return True

    # ----------------------------------------------------------------- Appearance and Documents

    def _appearance_tab(self, window) -> QWidget:
        """The colours and the size of the interface, its language, the hints of the modes, and how the toolbars
        look (see appearance.py, toolbars.py)."""
        from ..core import interface
        from . import appearance
        from .toolbars import SIZES, STYLES

        page = QWidget()
        form = QFormLayout(page)
        self.theme = QComboBox()
        for key in appearance.THEMES:
            self.theme.addItem(tr(appearance.THEME_NAMES[key]), key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(appearance.value("theme"))))
        form.addRow(tr("Theme:"), self.theme)
        # (the icon themes installed, after the desktop's and the program's own; a theme no longer there: the desktop's)
        self.icons = QComboBox()
        for key, name in appearance.ICON_CHOICES.items():
            self.icons.addItem(tr(name), key)
        installed = appearance.installed_icon_themes()
        if installed:
            self.icons.insertSeparator(self.icons.count())
        for key, name in installed:
            self.icons.addItem(name, key)
        self.icons.setCurrentIndex(max(0, self.icons.findData(appearance.value("icons"))))
        self.icons.setToolTip(tr("The icons of the buttons and menus: the desktop's icon theme, the program's own "
                                 "everywhere, or another icon theme installed"))
        form.addRow(tr("Icons:"), self.icons)
        self.scale = QComboBox()
        for percent in appearance.SCALES:
            self.scale.addItem(f"{percent} %", percent)
        self.scale.setCurrentIndex(max(0, self.scale.findData(int(appearance.value("scale") or 100))))
        self.scale.setToolTip(tr("The size of the letters of the menus, panels and dialogs"))
        form.addRow(tr("Interface size:"), self.scale)
        self.sharpness = QComboBox()
        for key, name in (("drawn", N_("As drawn")), ("sharper", N_("Sharper")), ("sharpest", N_("Sharpest"))):
            self.sharpness.addItem(tr(name), key)
        self.sharpness.setCurrentIndex(max(0, self.sharpness.findData(appearance.value("sharpness"))))
        self.sharpness.setToolTip(tr("The edges of letters and lines are drawn soft (they are not snapped to the "
                                     "pixels of the screen, as the desktop's own fonts are); sharper darkens them "
                                     "and makes them steeper, and pictures a little too"))
        form.addRow(tr("Text on the pages:"), self.sharpness)
        self.language = QComboBox()
        for code, name in interface.names().items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(interface.code())))
        form.addRow(tr("Language:"), self.language)
        self.hints = QCheckBox(tr("Show a hint of what can be done when a mode is chosen"))
        self.hints.setChecked(bool(appearance.value("hints")))
        self.hints.setToolTip(tr("Over the pages, for a few seconds; Help > Tips for this mode (F1) shows it always"))
        form.addRow("", self.hints)
        self.annot_panel = QCheckBox(tr("Show the Annotations panel when the mode Annotate is chosen"))
        self.annot_panel.setChecked(bool(appearance.value("annot_panel")))
        self.annot_panel.setToolTip(tr("Off, the panel stays hidden until View > Panels > Annotations panel (F4) "
                                       "shows it"))
        form.addRow("", self.annot_panel)
        self.tooltips = QCheckBox(tr("Show tooltips: what a button, menu or field does, when the mouse rests on it"))
        self.tooltips.setChecked(bool(appearance.value("tooltips")))
        form.addRow("", self.tooltips)
        looks = window.looks() if window is not None and hasattr(window, "looks") else {}
        self.bar_style = QComboBox()
        for key, name, _ in STYLES:
            self.bar_style.addItem(tr(name), key)
        self.bar_style.setCurrentIndex(max(0, self.bar_style.findData(looks.get("style", "icons"))))
        self.bar_size = QComboBox()
        for px, name in SIZES:
            self.bar_size.addItem(tr(name), px)
        self.bar_size.setCurrentIndex(max(0, self.bar_size.findData(looks.get("size", 22))))
        self.bar_lock = QCheckBox(tr("Lock the toolbars"))
        self.bar_lock.setChecked(bool(looks.get("locked")))
        self._bars_before = (self.bar_style.currentData(), self.bar_size.currentData(), self.bar_lock.isChecked())
        form.addRow(tr("Toolbar button style:"), self.bar_style)
        form.addRow(tr("Toolbar icon size:"), self.bar_size)
        form.addRow("", self.bar_lock)
        return page

    def _documents_tab(self) -> QWidget:
        """How documents open, what is remembered of them, links, the recent files, the file dialogs."""
        from . import appearance

        page = QWidget()
        form = QFormLayout(page)
        self.opening = QComboBox()
        for key, name in (("document", N_("As the document asks")), ("page", N_("The whole page")),
                          ("width", N_("The width of the page")), ("actual", N_("Actual size (100 %)"))):
            self.opening.addItem(tr(name), key)
        self.opening.setCurrentIndex(max(0, self.opening.findData(appearance.value("opening"))))
        self.opening.setToolTip(tr("The zoom of a document opened for the first time (one opened before opens "
                                   "where it was left, if that is remembered)"))
        form.addRow(tr("Default zoom:"), self.opening)
        self.places = QCheckBox(tr("Restore the last page and zoom of each document"))
        self.places.setChecked(bool(appearance.value("places")))
        form.addRow("", self.places)
        self.ask_links = QCheckBox(tr("Ask before opening a web or mail address"))
        self.ask_links.setChecked(bool(appearance.value("ask_links")))
        form.addRow("", self.ask_links)
        self.recent = QSpinBox(minimum=0, maximum=30)
        self.recent.setValue(int(appearance.value("recent") or 0))
        self.recent.setSpecialValueText(tr("none"))
        form.addRow(tr("Recent files to keep:"), self.recent)
        clear = QPushButton(tr("Clear recent files"))
        clear.clicked.connect(self._clear_recent)
        form.addRow("", clear)
        self.dialogs = QComboBox()
        for key, name in (("last", N_("The last folder used")), ("document", N_("The folder of the document"))):
            self.dialogs.addItem(tr(name), key)
        self.dialogs.setCurrentIndex(max(0, self.dialogs.findData(appearance.value("dialogs"))))
        form.addRow(tr("Open and save dialogs start in:"), self.dialogs)
        return page

    def _annotations_tab(self, window) -> QWidget:
        """Where the annotations are saved: those of the document open (WINDOW's), those of the documents
        without a separate file yet, and whether those files are hidden (see gui/storing.py)."""
        from .storing import default_storage

        page = QWidget()
        form = QFormLayout(page)
        # (la del documento abierto: solo si la ventana tiene uno; se aplica al aceptar, y guarda enseguida)
        self._apart_window = window if getattr(window, "path", None) is not None and hasattr(window, "apart") \
            else None
        self.apart_here = QCheckBox(tr("Save the annotations of this document in a separate file"))
        self.apart_here.setChecked(self._apart_window is not None and self._apart_window.apart())
        self.apart_here.setEnabled(self._apart_window is not None)
        self.apart_here.setToolTip(tr("Unchecked, they are saved in the PDF itself. Changing it saves them at "
                                      "once, when the settings are applied"))
        form.addRow("", self.apart_here)
        self.apart_default = QCheckBox(tr("Save those of new documents in a separate file"))
        self.apart_default.setChecked(default_storage() == "file")
        self.apart_default.setToolTip(tr("For documents that have no separate file of annotations yet "
                                         "(NAME.pdf.pdfnotes); unchecked, their annotations are saved in the PDF "
                                         "itself. One that has the file is always saved there"))
        form.addRow("", self.apart_default)
        self.hide_notes = QCheckBox(tr("Hide the separate files of annotations"))
        self.hide_notes.setChecked(bool(config.get("hide_notes")))
        self.hide_notes.setToolTip(tr("Name them .NAME.pdf.pdfnotes, which Linux and macOS hide, and mark them "
                                      "hidden on Windows; a file already saved changes at its next save"))
        form.addRow("", self.hide_notes)
        return page

    def _keep_annotations(self):
        """The settings of the page Annotations kept; the document open switched, if asked (it may ask whether
        the PDF keeps its own annotations: cancelled, the box shows again how they are saved)."""
        from .storing import default_storage

        try:
            if self.apart_default.isChecked() != (default_storage() == "file"):
                config.set("annot_storage", "file" if self.apart_default.isChecked() else "pdf")
            if self.hide_notes.isChecked() != bool(config.get("hide_notes")):
                config.set("hide_notes", self.hide_notes.isChecked())
        except (OSError, config.ConfigError) as e:
            QMessageBox.warning(self, tr("Settings"), tr("Could not keep the setting: {error}", error=e))
        win = self._apart_window
        if win is not None and win.path is not None and self.apart_here.isChecked() != win.apart():
            win.set_apart(self.apart_here.isChecked())
            self.apart_here.blockSignals(True)
            self.apart_here.setChecked(win.apart())
            self.apart_here.blockSignals(False)

    def _clear_recent(self):
        from .window import _WINDOWS

        for win in _WINDOWS:
            win.clear_recent()

    def _keep_appearance(self) -> bool:
        """The settings of Appearance and Documents kept and applied (to every window). Whether the language
        changed (the windows are then built again, after the dialog)."""
        from ..core import interface
        from . import appearance
        from .window import _WINDOWS

        values = {"theme": self.theme.currentData(), "icons": self.icons.currentData(),
                  "scale": self.scale.currentData(),
                  "sharpness": self.sharpness.currentData(),
                  "hints": self.hints.isChecked(), "tooltips": self.tooltips.isChecked(),
                  "annot_panel": self.annot_panel.isChecked(),
                  "opening": self.opening.currentData(),
                  "places": self.places.isChecked(), "ask_links": self.ask_links.isChecked(),
                  "recent": self.recent.value(), "dialogs": self.dialogs.currentData()}
        changed = {k: v for k, v in values.items() if v != appearance.value(k)}
        if changed:
            try:
                config.set_many(changed)
            except OSError as e:
                QMessageBox.warning(self, tr("Settings"), tr("Could not keep the setting: {error}", error=e))
        if "theme" in changed:
            appearance.apply_theme()  # (and the icons: see apply_icons)
        elif "icons" in changed:
            appearance.apply_icons()
        if "scale" in changed:
            appearance.apply_scale()
        if "tooltips" in changed:
            appearance.apply_tooltips()
        if "sharpness" in changed and appearance.apply_sharpness():
            for win in _WINDOWS:  # (drawn again, with the text as sharp as chosen)
                win.redraw_pages()
        if "recent" in changed:
            for win in _WINDOWS:
                win._recent_menu()
        bars = (self.bar_style.currentData(), self.bar_size.currentData(), self.bar_lock.isChecked())
        if bars != self._bars_before:
            for win in [w for w in _WINDOWS if hasattr(w, "set_bar_look")] or [self.parent()]:
                if win is None:
                    continue
                win.set_bar_look(None, style=bars[0], size=bars[1])
                win.set_bars_locked(bars[2])
        return self.language.currentData() != interface.code()

    def _usual_colours(self):
        # zip relies on the palette rows being made from the same PALETTE, in the same order.
        for (button, edit), (color, _, meaning) in zip(self.palette_rows, settings.PALETTE):
            button.set_color(color)
            edit.setText(tr(meaning) if meaning else "")

    def _categories(self) -> tuple[str, ...] | None:
        """The categories written (None if they are the usual ones)."""
        names = []
        for line in self.categories.toPlainText().splitlines():
            # El punto y coma separa las categorías al guardarlas en la configuración: dentro de un nombre se
            # cambia por una coma.
            name = " ".join(line.replace(";", ",").split())
            if name and name not in names:
                names.append(name)
        # Si coinciden con las de fábrica se guarda None, para que sigan traduciéndose al cambiar de idioma.
        return None if names == settings.Settings().category_list() else tuple(names)

    def _usual_keys(self):
        for action, key in settings.SHORTCUTS.items():
            self.key_edits[action].setKeySequence(QKeySequence(key))

    def check_configuration(self, window=None):
        """The check of the configuration (gui/health_dialog.py), with the shortcuts of WINDOW."""
        from .health_dialog import HealthDialog

        HealthDialog(window, self).exec()

    def shortcuts(self) -> dict[str, str]:
        # PortableText: the same text on every system and language, as it is saved.
        return {action: edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                for action, edit in self.key_edits.items()}

    def conflicts(self) -> list[tuple[str, str, str]]:
        """(key, action, action) of each key given to two actions."""
        seen: dict[str, str] = {}
        out = []
        # Only the first clash is reported; the dialog stays open until it is solved.
        for action, key in self.shortcuts().items():
            if not key:
                continue
            if key in seen:
                out.append((key, seen[key], action))
            seen[key] = action
        return out

    def accept(self):
        if self.put_in_effect():
            super().accept()

    def put_in_effect(self) -> bool:
        """Keep the settings chosen and put them in effect (OK and Apply); False if they can't be (two actions
        with one shortcut), and then the window stays open."""
        clash = self.conflicts()
        if clash:
            key, a, b = clash[0]
            QMessageBox.warning(self, tr("Shortcuts"), tr("{key} is the shortcut of two actions: {first} and "
                                                          "{second}. Give another to one of them.", key=key,
                                                          first=action_name(a), second=action_name(b)))
            return False
        # (performance: kept in the configuration file, and in effect at once)
        from . import performance

        values = {"memory": self.memory.currentData(), "transparency": self.transparency.isChecked(),
                  "text_antialias": self.text_antialias.isChecked(),
                  "graphics_antialias": self.graphics_antialias.isChecked(), "smooth": self.smooth.isChecked(),
                  "thumb_cache": self.thumb_cache.isChecked()}
        before = performance.settings()
        # (de esta vez: lo que la ventana debe dibujar de nuevo; guardar las miniaturas en el disco no cambia nada
        # de lo dibujado)
        self.performance_changed = {k: v for k, v in values.items() if k != "thumb_cache"} != \
            {k: v for k, v in before.items() if k != "thumb_cache"}
        if values != before:
            try:
                config.set_many({k: v for k, v in values.items() if v != before[k]})
            except OSError as e:
                QMessageBox.warning(self, tr("Settings"), tr("Could not keep the setting: {error}", error=e))
            performance.apply(values)
        try:
            if self.reopen.isChecked() != bool(config.get("reopen")):
                config.set("reopen", self.reopen.isChecked())
            if self.tabs.isChecked() != bool(config.get("tabs")):
                config.set("tabs", self.tabs.isChecked())
            if self.reload.isChecked() != bool(config.get("reload")):
                config.set("reload", self.reload.isChecked())
            if self.gpu.isChecked() != bool(config.get("gpu")):
                config.set("gpu", self.gpu.isChecked())
            if self.ask_backend.isChecked() != bool(config.get("ask_backend")):
                config.set("ask_backend", self.ask_backend.isChecked())
            backend = self.backend.currentData()
            if backend != config.get("backend"):
                config.set("backend", backend)
                from .window import _WINDOWS

                for win in _WINDOWS:  # (every document open, drawn anew with it)
                    if hasattr(win, "set_backend"):
                        win.set_backend(backend)
            if self.warn_many.isChecked() != bool(config.get("warn_many")):
                config.set("warn_many", self.warn_many.isChecked())
            if self.lone_tab.isChecked() != bool(config.get("lone_tab")):
                config.set("lone_tab", self.lone_tab.isChecked())
                from .tabs import apply_tab_bars

                apply_tab_bars()  # (en efecto enseguida, en todas las ventanas de pestañas)
        except (OSError, config.ConfigError) as e:
            QMessageBox.warning(self, tr("Settings"), tr("Could not keep the setting: {error}", error=e))
        # (running in the background: kept in the configuration file, and in effect at once)
        from . import background, instance

        on = self.background.isChecked()
        if on != instance.enabled():
            try:
                config.set("background", on)
            except OSError as e:
                QMessageBox.warning(self, tr("Settings"), tr("Could not keep the setting: {error}", error=e))
            else:
                background(on)
        # (el idioma: si cambió alguna vez, aunque fuera con Aplicar, la ventana se rehace al cerrarse el diálogo)
        self.language_changed = self._keep_appearance() or self.language_changed
        from . import autostart

        if self.login.isChecked() != autostart.enabled():
            try:
                autostart.enable(self.login.isChecked())
            except OSError as e:
                QMessageBox.warning(self, tr("Settings"), tr("Could not keep the setting: {error}", error=e))
        self._keep_annotations()
        if self.on_apply is not None:
            self.on_apply(self)
        return True

    def settings(self) -> settings.Settings:
        # Se limitan a 200 caracteres el autor y los significados: van a cada anotación y al archivo de
        # configuración.
        author = " ".join(self.author.text().split())[:200]
        palette = []
        for i, (button, edit) in enumerate(self.palette_rows):
            color, text = button.color, " ".join(edit.text().split())[:200]
            usual_color, _, usual_meaning = settings.PALETTE[i]
            # Un color que sigue como el de fábrica guarda None como significado, de modo que se traduzca
            # en otro idioma.
            same = color == usual_color and text == (tr(usual_meaning) if usual_meaning else "")
            palette.append((color, None if same else text))
        prefs = dataclasses.replace(self.prefs, author=author, autosave=self.autosave.value(),
                                    ocr_language=self._ocr_language(),
                                    pen_pressure=self.pen_pressure.currentData(),
                                    pen_curve=self.pen_curve.currentData(),
                                    pen_button=self.pen_button.currentData(),
                                    categories=self._categories(),
                                    palette=tuple(palette), shortcuts=tuple(self.shortcuts().items()))
        if self.reset.isChecked():
            # Resetting the tools replaces only their styles; the rest of the settings stay as the dialog left them.
            prefs = dataclasses.replace(prefs, styles=settings.DEFAULTS.styles)
        return prefs

    def _show_ocr(self):
        """Tesseract's version, and its languages (the better models marked)."""
        from ..core import ocr

        if not ocr.available():
            self.ocr_found.setText(tr("Tesseract is not installed: there is no OCR"))
            return
        names = [f"{n}{' ★' if ocr.better(n) else ''}" for n in ocr.languages()]
        self.ocr_found.setText(tr("Tesseract {version}: {languages}", version=ocr.version(),
                                  languages=", ".join(names) or tr("no language")) + "  "
                               + (tr("(★ better model; pages can be turned)") if ocr.has_osd()
                                  else tr("(★ better model; osd, to turn pages, is not there)")))

    def _manage_languages(self):
        """The languages of OCR (see ocr_languages.py); then what is there now."""
        from .ocr_languages import LanguagesDialog

        LanguagesDialog(self).exec()
        self._show_ocr()

    def _ocr_language(self) -> str:
        # Commas and spaces are accepted as separators and turned into Tesseract's +; an invalid result
        # keeps the language set before.
        text = "+".join(self.ocr_language.text().replace(",", "+").split()).strip("+")
        return text if settings.valid("ocr_language", text) else self.prefs.ocr_language
