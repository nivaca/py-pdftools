"""File > Protect with passwords: a password to open the document, and one for what may be done with it
(printing, copying...), with those permissions; or its protection removed. See core/protection.py."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QVBoxLayout,
)

from ..core.interface import tr
from ..core.protection import PERMISSIONS, Protection


def _password() -> QLineEdit:
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    return edit


class ProtectDialog(QDialog):
    def __init__(self, current: Protection, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Protect with passwords"))
        self.removing = False
        if not current.encrypted:
            state = tr("This document is not protected.")
        else:
            state = tr("This document is protected ({method}).", method=current.method) + " " + (
                tr("A password is asked for to open it.") if current.open_password
                else tr("It opens without a password, but what may be done with it is restricted."))
        head = QLabel(state)
        head.setWordWrap(True)

        self.ask_open = QGroupBox(tr("Ask for a password to open it"))
        self.ask_open.setCheckable(True)
        self.ask_open.setChecked(current.open_password or not current.encrypted)
        self.open_pw, self.open_again = _password(), _password()
        form = QFormLayout(self.ask_open)
        form.addRow(tr("Password:"), self.open_pw)
        form.addRow(tr("Again:"), self.open_again)

        self.restrict = QGroupBox(tr("Restrict what may be done with it"))
        self.restrict.setCheckable(True)
        self.restrict.setChecked(current.encrypted and current.allowed != frozenset(k for k, _ in PERMISSIONS))
        self.owner_pw, self.owner_again = _password(), _password()
        form = QFormLayout(self.restrict)
        form.addRow(tr("Permissions password:"), self.owner_pw)
        form.addRow(tr("Again:"), self.owner_again)
        self.allow: dict[str, QCheckBox] = {}
        for key, name in PERMISSIONS:
            box = QCheckBox(tr(name))
            box.setChecked(key in current.allowed)
            self.allow[key] = box
            form.addRow(box)
        note = QLabel(tr("The permissions are kept by PDF programs, but they are not a lock: a program that ignores "
                         "them can copy what can be read. The password to open it is the lock. The document is "
                         "encrypted with AES-256."))
        note.setWordWrap(True)

        self.problem = QLabel()
        self.problem.setStyleSheet("color: palette(link)")
        self.problem.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_protect = buttons.addButton(tr("Protect"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_remove = buttons.addButton(tr("Remove the protection"), QDialogButtonBox.ButtonRole.DestructiveRole)
        self.b_remove.setVisible(current.encrypted)
        self.b_remove.clicked.connect(self._remove)
        buttons.accepted.connect(self._protect)
        buttons.rejected.connect(self.reject)
        for w in (self.open_pw, self.open_again, self.owner_pw, self.owner_again):
            w.textChanged.connect(lambda _t: self._check())
        self.ask_open.toggled.connect(lambda _on: self._check())
        self.restrict.toggled.connect(lambda _on: self._check())
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(self.ask_open)
        lay.addWidget(self.restrict)
        lay.addWidget(note)
        lay.addWidget(self.problem)
        lay.addWidget(buttons)
        self.setMinimumWidth(460)
        self._check()

    def problem_text(self) -> str:
        """What is wrong with what is typed ('' if nothing)."""
        opening, restricting = self.ask_open.isChecked(), self.restrict.isChecked()
        if not opening and not restricting:
            return tr("Choose a password to open it, or restrictions, or both")
        if opening and not self.open_pw.text():
            return tr("Type the password to open it")
        if opening and self.open_pw.text() != self.open_again.text():
            return tr("The two passwords to open it are not the same")
        if restricting and not self.owner_pw.text():
            return tr("Type the permissions password")
        if restricting and self.owner_pw.text() != self.owner_again.text():
            return tr("The two permissions passwords are not the same")
        if opening and restricting and self.owner_pw.text() == self.open_pw.text():
            return tr("The permissions password must not be that to open it: with it, the restrictions are lifted")
        return ""

    def _check(self):
        text = self.problem_text()
        self.problem.setText(text)
        self.b_protect.setEnabled(not text)

    def _protect(self):
        if not self.problem_text():
            self.accept()

    def _remove(self):
        self.removing = True
        self.accept()

    def result_values(self) -> dict:
        """What was chosen: {'remove': True}, or the arguments of protection.protect."""
        if self.removing:
            return {"remove": True}
        restricting = self.restrict.isChecked()
        return {"open_password": self.open_pw.text() if self.ask_open.isChecked() else "",
                "owner_password": self.owner_pw.text() if restricting else "",
                "allowed": {k for k, box in self.allow.items() if box.isChecked()} if restricting else None}
