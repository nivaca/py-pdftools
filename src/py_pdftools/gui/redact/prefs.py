"""The settings dialog: the default colour of new boxes, and how boxes are redacted."""

from __future__ import annotations

from PySide6.QtGui import QColor
import dataclasses

from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout,
)

from ...core.interface import N_, tr
from ...redact.settings import DEFAULTS, Settings

IMAGES = [("pixels", N_("Blank the part under the box")), ("whole", N_("Remove the whole image")),
          ("none", N_("Leave the images as they are"))]
DRAWINGS = [("covered", N_("Remove those wholly under a box")), ("touched", N_("Remove those a box touches")),
            ("none", N_("Leave the drawings as they are"))]


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, swatch, color_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self._swatch, self._color_name = swatch, color_name
        self.original = settings
        self.color = settings.color
        self.outline = settings.mark_outline
        self.outline_button = QPushButton()
        self.outline_button.clicked.connect(self._choose_outline)
        self.opacity = QSpinBox()
        # Los mismos límites que acepta settings.valid.
        self.opacity.setRange(10, 100)
        self.opacity.setSuffix(" %")
        self.opacity.setToolTip(tr("How much of what is under a box shows through it until it is applied"))
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self._choose)
        self.images = QComboBox()
        for value, name in IMAGES:
            self.images.addItem(tr(name), value)
        self.drawings = QComboBox()
        for value, name in DRAWINGS:
            self.drawings.addItem(tr(name), value)
        self.clean = QCheckBox(tr("Also remove metadata, hidden text, attachments and scripts"))
        form = QFormLayout()
        form.addRow(tr("Colour of new boxes:"), self.color_button)
        form.addRow(tr("Images under a box:"), self.images)
        form.addRow(tr("Drawings under a box:"), self.drawings)
        form.addRow("", self.clean)
        form.addRow(QLabel("<b>" + tr("Boxes not yet applied") + "</b>"))
        form.addRow(tr("Outline:"), self.outline_button)
        form.addRow(tr("Fill opacity:"), self.opacity)
        note = QLabel(tr("Text under a box is always removed."))
        note.setStyleSheet("color: palette(placeholder-text);")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        # Restore defaults only fills in the dialog; nothing is kept until OK.
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(lambda: self.show_settings(
            DEFAULTS))
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(note)
        bottom = QHBoxLayout()
        bottom.addWidget(buttons)
        lay.addLayout(bottom)
        self.show_settings(settings)

    def show_settings(self, settings: Settings):
        self.color = settings.color
        self._show_color()
        # settings.load ya garantiza que el valor es uno de la lista, así que index() no falla.
        self.images.setCurrentIndex([v for v, _ in IMAGES].index(settings.images))
        self.drawings.setCurrentIndex([v for v, _ in DRAWINGS].index(settings.drawings))
        self.clean.setChecked(settings.clean)
        self.outline = settings.mark_outline
        self.outline_button.setIcon(self._swatch(self.outline))
        self.outline_button.setText(self.outline)
        self.opacity.setValue(settings.mark_opacity)

    def _show_color(self):
        self.color_button.setIcon(self._swatch(self.color))
        self.color_button.setText(self._color_name(self.color))

    def _choose(self):
        chosen = QColorDialog.getColor(QColor(self.color), self, tr("The colour of the boxes"))
        if chosen.isValid():
            self.color = chosen.name()
            self._show_color()

    def _choose_outline(self):
        chosen = QColorDialog.getColor(QColor(self.outline), self, tr("Outline"))
        if chosen.isValid():
            self.outline = chosen.name()
            self.outline_button.setIcon(self._swatch(self.outline))
            self.outline_button.setText(self.outline)

    def settings(self) -> Settings:
        """The settings shown, with those the dialog doesn't show kept as they were."""
        # El aspecto del texto de los recuadros no está aquí (se cambia en Propiedades) y se
        # conserva como estaba.
        return dataclasses.replace(self.original, color=self.color, clean=self.clean.isChecked(),
                                   images=self.images.currentData(), drawings=self.drawings.currentData(),
                                   mark_outline=self.outline,
                                   mark_opacity=self.opacity.value())
