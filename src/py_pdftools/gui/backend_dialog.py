"""La pregunta, al abrir un documento, de qué motor dibuja sus páginas (véase core/backends.py), cuando la
configuración lo pide y hay más de uno. Es la idea del diálogo de elegir motor de Okular."""

from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout

from ..core import backends
from ..core.interface import tr


class BackendDialog(QDialog):
    def __init__(self, name: str, here: list[str], wanted: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Engine that draws the pages"))
        lay = QVBoxLayout(self)
        intro = QLabel(tr("Which engine should draw the pages of {name}? Only how they look changes: annotating, "
                          "finding and saving are the same with all of them.", name=name))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QRadioButton] = {}
        for key in here:
            b = QRadioButton(tr(backends.NAMES[key]))
            b.setChecked(key == wanted)
            self.group.addButton(b)
            self.buttons[key] = b
            note = QLabel(tr(backends.DESCRIPTIONS[key]))
            note.setWordWrap(True)
            note.setContentsMargins(24, 0, 0, 4)
            note.setEnabled(False)
            lay.addWidget(b)
            lay.addWidget(note)
        hint = QLabel(tr("Settings > Performance chooses the engine of every document, and whether to ask."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(placeholder-text);")
        lay.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def choice(self) -> str:
        return next((k for k, b in self.buttons.items() if b.isChecked()), backends.MUPDF)
