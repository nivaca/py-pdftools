"""The Settings dialog: the author written in new annotations and the
recovery copies; the colours offered in the menus, with what each means; and
the keyboard shortcuts."""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import config, conform

from ..annotate import settings
from ..annotate.annots import NAMES
from ..core.interface import N_, tr
from .props import ColorButton

# the actions with a shortcut that aren't tools
ACTION_NAMES = {"select": N_("Select"), "hand": N_("Hand"), "eraser": N_("Eraser"),
                "comment": N_("Comment on the annotation selected"), "next": N_("Next annotation"),
                "previous": N_("Previous annotation"), "copy": N_("Copy"), "paste": N_("Paste"),
                "duplicate": N_("Duplicate"), "properties": N_("Properties"),
                "group": N_("Group"), "ungroup": N_("Ungroup"), "replace": N_("Replace text"),
                "typewriter": N_("Typewriter"), "mark": N_("Check mark"), "signature": N_("Signature")}


def action_name(action: str) -> str:
    # Las acciones que no son herramientas tienen nombre aquí; las herramientas usan el de su anotación.
    return tr(ACTION_NAMES[action]) if action in ACTION_NAMES else tr(NAMES[action])


class SettingsDialog(QDialog):
    def __init__(self, prefs: settings.Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.prefs = prefs
        # Cuatro pestañas: General, Colores, Atajos y Categorías. Nada se guarda hasta pulsar Aceptar.
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
        self.pdfconform = QLineEdit(prefs.pdfconform)
        self.pdfconform.setPlaceholderText(tr("Look for it on the PATH, in ~/bin and in ~/.local/bin"))
        self.pdfconform.setToolTip(tr("Another pdf2iso to use instead of the one of py-pdftools (a script, with or without the .py "
                                      "extension); empty for its own"))
        # Al escribir la ruta se dice enseguida qué pdf2iso se usaría, o que no existe.
        self.pdfconform.textChanged.connect(self._show_pdfconform)
        choose = QPushButton(tr("Choose…"))
        choose.clicked.connect(self._choose_pdfconform)
        row = QHBoxLayout()
        row.addWidget(self.pdfconform, 1)
        row.addWidget(choose)
        form.addRow(tr("pdf2iso:"), row)
        self.pdfconform_found = QLabel()
        self.pdfconform_found.setWordWrap(True)
        self.pdfconform_found.setStyleSheet("color: palette(placeholder-text);")
        form.addRow("", self.pdfconform_found)
        self._show_pdfconform()
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
        tabs.addTab(general, tr("General"))

        colours = QWidget()
        form = QFormLayout(colours)
        intro = QLabel(tr("The colours offered in the menus, and what each one means to you (shown with its name)"))
        intro.setWordWrap(True)
        form.addRow(intro)
        self.palette_rows = []
        # Un significado None es el de fábrica: se muestra traducido solo si el color sigue siendo el
        # de fábrica; si el usuario lo cambió, el campo queda vacío.
        for i, (color, meaning) in enumerate(prefs.palette):
            button = ColorButton(color)
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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer = QVBoxLayout(self)
        outer.addWidget(tabs)
        outer.addWidget(buttons)
        self.resize(560, 620)

    def _show_pdfconform(self, *_):
        """Which pdf2iso will be used (File > Save a copy > PDF/A, PDF/X)."""
        path = self.pdfconform.text().strip()
        # With an empty path, conform.find looks on the PATH, in ~/bin and in ~/.local/bin.
        found = conform.find(path)
        if found is not None:
            self.pdfconform_found.setText(tr("It will be {path}", path=found))
        elif path:
            self.pdfconform_found.setText(tr("There is no such file"))
        else:
            self.pdfconform_found.setText(tr("Not found: PDF/A and PDF/X can't be made until it is given here"))

    def _choose_pdfconform(self):
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        # El diálogo de archivos empieza en la ruta escrita, o en ~/bin, donde suele estar el script.
        start = self.pdfconform.text().strip() or str(Path.home() / "bin")
        name, _ = QFileDialog.getOpenFileName(self, tr("Where is pdf2iso?"), start)
        if name:
            self.pdfconform.setText(name)

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
        clash = self.conflicts()
        if clash:
            key, a, b = clash[0]
            QMessageBox.warning(self, tr("Shortcuts"), tr("{key} is the shortcut of two actions: {first} and "
                                                          "{second}. Give another to one of them.", key=key,
                                                          first=action_name(a), second=action_name(b)))
            return
        super().accept()

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
                                    pdfconform=self.pdfconform.text().strip(),
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

    def _ocr_language(self) -> str:
        # Commas and spaces are accepted as separators and turned into Tesseract's +; an invalid result
        # keeps the language set before.
        text = "+".join(self.ocr_language.text().replace(",", "+").split()).strip("+")
        return text if settings.valid("ocr_language", text) else self.prefs.ocr_language
