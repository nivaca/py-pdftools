"""Digital signatures in the window (mixed into MainWindow): File > Digital signatures. They need pyHanko,
installed apart (pip install 'py-pdftools[signatures]'); without it, the menu says so. See signatures/."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout,
)

from ..core.interface import tr
from ..signatures import ids

NEEDS = "pip install 'py-pdftools[signatures]'"


class IdDialog(QDialog):
    """A new self-signed digital ID: who it names, how long it lasts, its password."""

    def __init__(self, parent=None, author: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("Create a digital ID"))
        self.name = QLineEdit(author)
        self.email = QLineEdit()
        self.organization = QLineEdit()
        self.country = QLineEdit()
        self.country.setMaxLength(2)
        self.country.setPlaceholderText("CO, ES, US…")
        self.years = QSpinBox(minimum=1, maximum=20, value=3, suffix=" " + tr("years"))
        self.password, self.again = QLineEdit(), QLineEdit()
        for w in (self.password, self.again):
            w.setEchoMode(QLineEdit.EchoMode.Password)
            w.textChanged.connect(lambda _t: self._check())
        self.name.textChanged.connect(lambda _t: self._check())
        form = QFormLayout()
        form.addRow(tr("Name:"), self.name)
        form.addRow(tr("E-mail:"), self.email)
        form.addRow(tr("Organisation:"), self.organization)
        form.addRow(tr("Country:"), self.country)
        form.addRow(tr("Valid for:"), self.years)
        form.addRow(tr("Password:"), self.password)
        form.addRow(tr("Again:"), self.again)
        note = QLabel(tr("A self-signed ID: enough to sign your documents, and for others to check that nothing "
                         "changed after you signed. They trust it when you give them its certificate (the .cer "
                         "file saved beside it). Keep the ID file and its password to yourself."))
        note.setWordWrap(True)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_ok = buttons.addButton(tr("Save the ID…"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(note)
        lay.addWidget(self.problem)
        lay.addWidget(buttons)
        self.setMinimumWidth(460)
        self._check()

    def problem_text(self) -> str:
        if not self.name.text().strip():
            return tr("A digital ID needs a name")
        if len(self.password.text()) < 6:
            return tr("The password must have six characters or more")
        if self.password.text() != self.again.text():
            return tr("The two passwords are not the same")
        return ""

    def _check(self):
        text = self.problem_text()
        self.problem.setText(text)
        self.b_ok.setEnabled(not text)

    def identity(self) -> ids.Identity:
        return ids.Identity(self.name.text().strip(), self.email.text().strip(), self.organization.text().strip(),
                            self.country.text().strip().upper())


class SignMixin:
    """(Mixed into MainWindow.)"""

    def _build_sign_menu(self, menu):
        """File > Digital signatures (disabled, saying why, without pyHanko)."""
        sub = menu.addMenu(tr("Digital signatures"))
        sub.setToolTipsVisible(True)
        self.m_signatures = sub
        self.a_make_id = self._action(sub, tr("Create a digital ID…"), lambda: self.make_id_dialog(),
                                      tip=tr("A self-signed digital ID (a .p12 file), to sign documents with"))
        self._sign_actions = [self.a_make_id]
        if not ids.available():
            for act in self._sign_actions:
                act.setEnabled(False)
                act.setToolTip(tr("Needs pyHanko: {command}", command=NEEDS))

    def ask_id(self):
        """(identity, years, password, where to save it) for a new digital ID; None if cancelled."""
        dialog = IdDialog(self, self.prefs.author)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        name, _ = QFileDialog.getSaveFileName(self, tr("Save the digital ID"),
                                              str(Path(self.last_dir()) / f"{dialog.identity().name}.p12"),
                                              tr("Digital IDs (*.p12 *.pfx)"))
        if not name:
            return None
        target = Path(name)
        if target.suffix.lower() not in (".p12", ".pfx"):
            target = target.with_suffix(".p12")
        return dialog.identity(), dialog.years.value(), dialog.password.text(), target

    def make_id_dialog(self) -> Path | None:
        chosen = self.ask_id()
        if chosen is None:
            return None
        who, years, password, target = chosen
        try:
            cer = ids.make_id(who, password, target, years)
        except ids.IdError as e:
            self.status(str(e), error=True)
            return None
        self.settings.setValue("sign_id", str(target))
        self.status(tr("Saved {path}, and its certificate {cer}, to give to those who check your signatures",
                       path=target, cer=cer.name))
        return target
