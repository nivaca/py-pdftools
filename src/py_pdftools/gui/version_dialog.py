"""File > Save a copy > With another PDF version: the version the document has, the one chosen, and what the
document uses that is newer than it (see pages/version.py)."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from ..core.interface import tr
from ..pages.version import VERSIONS


class VersionDialog(QDialog):
    def __init__(self, current: str, newer_than, parent=None):
        """CURRENT: the document's version; NEWER_THAN(version): what it uses newer than that, said."""
        super().__init__(parent)
        self.setWindowTitle(tr("Save a copy with another PDF version"))
        self.newer_than = newer_than
        self.version = QComboBox()
        for v in VERSIONS:
            self.version.addItem(f"PDF {v}", v)
        index = self.version.findData(current)
        self.version.setCurrentIndex(index if index >= 0 else len(VERSIONS) - 2)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("It is now:"), QLabel(f"PDF {current}"))
        form.addRow(tr("Save it as:"), self.version)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_ok = buttons.addButton(tr("Save the copy…"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.version.currentIndexChanged.connect(lambda _i: self._check())
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.warning)
        lay.addWidget(buttons)
        self.setMinimumWidth(440)
        self._check()

    def _check(self):
        found = self.newer_than(self.chosen())
        self.warning.setText(tr("The document uses what this version doesn't have, and a program that keeps to "
                                "it may not show it right:") + "\n• " + "\n• ".join(found) if found else "")
        self.b_ok.setEnabled(not any("AES-256" in f for f in found))

    def chosen(self) -> str:
        return self.version.currentData()
