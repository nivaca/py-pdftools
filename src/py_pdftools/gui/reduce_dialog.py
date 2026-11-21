"""File > Save a copy > Smaller: how much smaller (the levels of pages/reduce.py), and where the bytes of
the document go now, to see what is worth reducing."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QLabel, QRadioButton, QVBoxLayout,
)

from ..core.interface import tr
from ..pages import reduce


class ReduceDialog(QDialog):
    def __init__(self, found: dict[str, int] | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Save a smaller copy"))
        lay = QVBoxLayout(self)
        if found:
            total = sum(found.values()) or 1
            rows = "".join(f"<tr><td>{tr(name)}</td><td align='right'>&nbsp;&nbsp;{reduce.size_text(found[k])}"
                           f"</td><td align='right'>&nbsp;&nbsp;{100 * found[k] / total:.0f} %</td></tr>"
                           for k, name in reduce.KINDS if found[k])
            where = QLabel(tr("Where its {size} go:", size=reduce.size_text(total)) + f"<table>{rows}</table>")
            lay.addWidget(where)
        box = QGroupBox(tr("How much smaller"))
        inner = QVBoxLayout(box)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QRadioButton] = {}
        for key, name, what, _ in reduce.LEVELS:
            b = QRadioButton(tr(name))
            b.setToolTip(tr(what))
            note = QLabel(tr(what))
            note.setWordWrap(True)
            note.setContentsMargins(24, 0, 0, 4)
            note.setEnabled(False)
            self.group.addButton(b)
            self.buttons[key] = b
            inner.addWidget(b)
            inner.addWidget(note)
        self.buttons["medium"].setChecked(True)
        self.gray = QCheckBox(tr("Pictures in grey"))
        self.gray.setToolTip(tr("For documents to be read or printed in black and white: much smaller"))
        lay.addWidget(box)
        lay.addWidget(self.gray)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(tr("Save the copy…"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def options(self) -> reduce.Options:
        key = next(k for k, b in self.buttons.items() if b.isChecked())
        base = reduce.options_of(key)
        return reduce.Options(base.dpi, base.quality, self.gray.isChecked(), base.fonts)
