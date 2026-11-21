"""Digital signatures in the window (mixed into MainWindow): File > Digital signatures. They need pyHanko,
installed apart (pip install 'py-pdftools[signatures]'); without it, the menu says so. See signatures/."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
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


class SignDialog(QDialog):
    """How to sign: the digital ID and its password, the reason, place and contact, where the signature goes
    (an area drawn on the page, an empty field of the form, or nowhere: invisible), whether it certifies the
    document, locks its fields, and a timestamp server."""

    def __init__(self, parent=None, id_path: str = "", empty: list[str] | None = None, signed: bool = False,
                 remembered: dict | None = None):
        from ..signatures.sign import CERTIFY

        super().__init__(parent)
        self.setWindowTitle(tr("Sign the document"))
        r = remembered or {}
        self.id_path = QLineEdit(id_path)
        choose = QPushButton(tr("Choose…"))
        choose.clicked.connect(self._choose_id)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.id_path, 1)
        row.addWidget(choose)
        id_box = QWidget()
        id_box.setLayout(row)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.reason, self.location, self.contact = (QLineEdit(r.get(k, "")) for k in ("reason", "location",
                                                                                     "contact"))
        self.where = QComboBox()
        self.where.addItem(tr("Visible: drag where it goes on the page"), "draw")
        for name in empty or []:
            self.where.addItem(tr("In the empty field {name}", name=name), "field:" + name)
        self.where.addItem(tr("Invisible"), "none")
        if empty:
            self.where.setCurrentIndex(1)
        self.certify = QComboBox()
        for key, name in CERTIFY:
            self.certify.addItem(tr(name), key)
        self.certify.setEnabled(not signed)
        if signed:
            self.certify.setToolTip(tr("Only the first signature of a document can certify it"))
        self.lock = QCheckBox(tr("Lock the fields of the form once signed"))
        self.timestamp = QLineEdit(r.get("timestamp", ""))
        self.timestamp.setPlaceholderText(tr("(none) — e.g. http://timestamp.example.org"))
        self.timestamp.setToolTip(tr("A timestamp server (RFC 3161) vouches for the time of the signature; it "
                                     "needs the internet"))
        form = QFormLayout()
        form.addRow(tr("Digital ID:"), id_box)
        form.addRow(tr("Its password:"), self.password)
        form.addRow(tr("Reason:"), self.reason)
        form.addRow(tr("Place:"), self.location)
        form.addRow(tr("Contact:"), self.contact)
        form.addRow(tr("Signature:"), self.where)
        form.addRow(tr("Certify:"), self.certify)
        form.addRow(self.lock)
        form.addRow(tr("Timestamp server:"), self.timestamp)
        note = QLabel(tr("The signed document is saved as a new file; the signature covers it as it is saved "
                         "now."))
        note.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_ok = buttons.addButton(tr("Sign…"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        for w in (self.id_path, self.password):
            w.textChanged.connect(lambda _t: self._check())
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(note)
        lay.addWidget(buttons)
        self.setMinimumWidth(520)
        self._check()

    def _choose_id(self):
        name, _ = QFileDialog.getOpenFileName(self, tr("Digital ID"), self.id_path.text(),
                                              tr("Digital IDs (*.p12 *.pfx)"))
        if name:
            self.id_path.setText(name)

    def _check(self):
        self.b_ok.setEnabled(Path(self.id_path.text()).is_file() and bool(self.password.text()))

    def chosen(self):
        """(sign.Options without the page and area, what the place is: 'draw', 'none' or 'field:NAME')."""
        from ..signatures.sign import Options

        where = self.where.currentData()
        return Options(Path(self.id_path.text()), self.password.text(), self.reason.text().strip(),
                       self.location.text().strip(), self.contact.text().strip(),
                       field=where[6:] if where.startswith("field:") else "",
                       certify=self.certify.currentData(), lock=self.lock.isChecked(),
                       timestamp_url=self.timestamp.text().strip()), where


class SignaturesDialog(QDialog):
    """The signatures of the document, checked: a row for each (what to think of it, who signed, when), and
    what is known of the one chosen; its signer trusted, or the version it signed opened."""

    def __init__(self, reports, parent=None, on_trust=None, on_open=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Signatures"))
        self.reports, self.on_trust, self.on_open = list(reports), on_trust, on_open
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Signature"), tr("Signed by"), tr("When"), tr("Field")])
        self.tree.setRootIsDecorated(False)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.tree)
        split.addWidget(self.details)
        self.b_trust = QPushButton(tr("Trust this signer"))
        self.b_trust.setToolTip(tr("Keep the signer's certificate among those trusted: their signatures will be "
                                   "said to be trusted (do it only if you know the certificate is theirs)"))
        self.b_trust.clicked.connect(self._trust)
        self.b_open = QPushButton(tr("Open the signed version"))
        self.b_open.setToolTip(tr("The document as this signature signed it, in a window of its own"))
        self.b_open.clicked.connect(self._open)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(self.b_trust, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.b_open, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addWidget(buttons)
        self.resize(760, 520)
        self.tree.currentItemChanged.connect(lambda *_a: self._show())
        self.fill(self.reports)

    def fill(self, reports):
        self.reports = list(reports)
        self.tree.clear()
        for r in self.reports:
            when = r.timestamped or r.signed_at
            item = QTreeWidgetItem([("✔ " if r.good else "⚠ " if r.intact and r.valid else "✘ ") + r.verdict,
                                    r.signer, when.astimezone().strftime("%Y-%m-%d %H:%M") if when else "",
                                    r.field])
            self.tree.addTopLevelItem(item)
        for c in range(4):
            self.tree.resizeColumnToContents(c)
        if self.reports:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self._show()

    def current(self):
        i = self.tree.indexOfTopLevelItem(self.tree.currentItem()) if self.tree.currentItem() else -1
        return self.reports[i] if 0 <= i < len(self.reports) else None

    def _show(self):
        from ..signatures.verify import CHANGES

        r = self.current()
        self.b_trust.setEnabled(r is not None and r.valid and not r.trusted)
        self.b_open.setEnabled(r is not None and r.end > 0)
        if r is None:
            self.details.setPlainText("")
            return
        lines = [r.verdict, "", tr("Signed by: {who}", who=r.signer)]
        if r.signed_at:
            lines.append(tr("Signed on: {when}", when=r.signed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")))
        if r.timestamped:
            lines.append(tr("Time vouched for by a server: {when}",
                            when=r.timestamped.astimezone().strftime("%Y-%m-%d %H:%M:%S")))
        if r.reason:
            lines.append(tr("Reason: {reason}", reason=r.reason))
        if r.location:
            lines.append(tr("Place: {place}", place=r.location))
        if r.certified:
            lines.append(tr("It certifies the document"))
        lines.append(tr(CHANGES[r.changes]))
        lines += ["", r.details]
        self.details.setPlainText("\n".join(lines))

    def _trust(self):
        r = self.current()
        if r is not None and self.on_trust is not None:
            reports = self.on_trust(r)
            if reports is not None:
                row = self.tree.indexOfTopLevelItem(self.tree.currentItem())
                self.fill(reports)
                self.tree.setCurrentItem(self.tree.topLevelItem(row))

    def _open(self):
        r = self.current()
        if r is not None and self.on_open is not None:
            self.on_open(r)


class SignMixin:
    """(Mixed into MainWindow.)"""

    def _build_sign_menu(self, menu):
        """File > Digital signatures (disabled, saying why, without pyHanko)."""
        sub = menu.addMenu(tr("Digital signatures"))
        sub.setToolTipsVisible(True)
        self.m_signatures = sub
        self.a_make_id = self._action(sub, tr("Create a digital ID…"), lambda: self.make_id_dialog(),
                                      tip=tr("A self-signed digital ID (a .p12 file), to sign documents with"))
        self.a_sign = self._action(sub, tr("Sign the document…"), lambda: self.sign_dialog(),
                                   tip=tr("Sign it with a digital ID, visibly or not, and save the signed copy"))
        sub.insertAction(self.a_make_id, self.a_sign)
        self.a_check_signatures = self._action(sub, tr("Check the signatures…"), lambda: self.signatures_dialog(),
                                               tip=tr("Whether each signature is valid, who signed and whether "
                                                      "they are trusted, and what changed after it"))
        sub.insertAction(self.a_make_id, self.a_check_signatures)
        sub.insertSeparator(self.a_make_id)
        self._sign_actions = [self.a_sign, self.a_check_signatures, self.a_make_id]
        self._sign_pending = None  # (a signature waiting for its area to be drawn on the page)
        self.canvas.sign_drawn.connect(self._sign_area_drawn)
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

    # ----------------------------------------------------------------- signing

    def ask_sign(self, empty: list[str], signed: bool):
        """(sign.Options, place) chosen; None if cancelled."""
        r = {k: str(self.settings.value(f"sign_{k}", "")) for k in ("reason", "location", "contact", "timestamp")}
        dialog = SignDialog(self, str(self.settings.value("sign_id", "")), empty, signed, r)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        options, where = dialog.chosen()
        for key, value in (("id", str(options.id_path)), ("reason", options.reason), ("location",
                           options.location), ("contact", options.contact), ("timestamp", options.timestamp_url)):
            self.settings.setValue(f"sign_{key}", value)
        return options, where

    def sign_dialog(self) -> bool:
        """File > Digital signatures > Sign the document: saved first, if it has changes; then signed where the
        user says (a visible signature: an area dragged on the page, after this)."""
        import pymupdf

        from ..signatures import sign
        from .files import ask_save
        from PySide6.QtWidgets import QMessageBox

        if self.path is None:
            return False
        if self.is_modified():
            answer = ask_save(self, tr("Unsaved changes"),
                              tr("The signature covers the document as it is saved. Save the changes first?"))
            if answer == QMessageBox.StandardButton.Cancel or \
                    answer == QMessageBox.StandardButton.Save and not self.save():
                return False
        with pymupdf.open(self.path) as doc:
            if doc.needs_pass:
                doc.authenticate(self.password)
            empty = sign.empty_fields(doc)
            signed = any(w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE and
                         doc.xref_get_key(w.xref, "V")[0] != "null" for p in doc for w in p.widgets() or [])
        chosen = self.ask_sign(empty, signed)
        if chosen is None:
            return False
        options, where = chosen
        if where == "draw":
            self._sign_pending = (options, self.canvas.mode)
            self.canvas.set_mode("signarea")
            self.status(tr("Drag on the page where the signature goes (Escape: cancel)"))
            return True
        return self.sign_to_file(options)

    def _sign_area_drawn(self, page: int, rect):
        if self._sign_pending is None:
            return
        import dataclasses

        options, tool = self._sign_pending
        self._sign_pending = None
        self.set_tool(tool if tool in self.tool_actions else "select")
        if page < 0:
            self.status(tr("Not signed"))
            return
        self.sign_to_file(dataclasses.replace(options, page=page, rect=tuple(rect)))

    def sign_to_file(self, options) -> bool:
        """The document signed with OPTIONS, saved where the user says, and opened."""
        from ..signatures import sign
        from .redact import background

        target = self.ask_new_pdf(tr("Save the signed document"), f"{self.path.stem}-signed.pdf")
        if target is None or self._same_file(target):
            return False
        try:
            # En un hilo: un servidor de sellos de tiempo puede tardar, y la ventana no debe quedarse quieta.
            background.run(self, tr("Signing…"), sign.sign, self.path, target, options, self.password,
                           thread=True)
        except sign.SignError as e:
            self.status(str(e), error=True)
            return False
        password = self.password
        self.drop_work()
        if not self.open_path(target, password=password):
            return False
        self.status(tr("Signed: saved {path}", path=target))
        return True

    # ----------------------------------------------------------------- checking

    def signature_count(self) -> int:
        """How many signatures the document has (signed signature fields)."""
        import pymupdf

        if self.doc is None:
            return 0
        return sum(1 for page in self.doc for w in page.widgets() or []
                   if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE
                   and self.doc.xref_get_key(w.xref, "V")[0] != "null")

    def check_signatures(self):
        """The reports of the document's signatures (as its file is); None if they can't be checked."""
        from PySide6.QtWidgets import QApplication

        from ..signatures import verify

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return verify.check(self.path, self.password)
        except verify.VerifyError as e:
            self.status(str(e), error=True)
            return None
        finally:
            QApplication.restoreOverrideCursor()

    def signatures_dialog(self):
        """File > Digital signatures > Check the signatures."""
        if self.path is None:
            return None
        if not ids.available():
            self.status(tr("Needs pyHanko: {command}", command=NEEDS), error=True)
            return None
        reports = self.check_signatures()
        if reports is None:
            return None
        if not reports:
            self.status(tr("This document has no signatures"))
            return None
        dialog = SignaturesDialog(reports, self, self._trust_signer, self._open_signed)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.signatures_window = dialog
        dialog.show()
        good = sum(r.good for r in reports)
        self.status(tr("{good} of {count} signatures valid and trusted", good=good, count=len(reports)),
                    error=good < len(reports))
        return dialog

    def _trust_signer(self, report):
        from ..signatures import verify

        try:
            verify.trust(report)
        except (verify.VerifyError, OSError) as e:
            self.status(str(e), error=True)
            return None
        self.status(tr("{who} is now trusted", who=report.signer))
        return self.check_signatures()

    def _open_signed(self, report):
        """The version REPORT's signature signed, in a window of its own (from a copy, which stays apart)."""
        from ..signatures import verify
        from . import open_window
        from .working import work_root
        import tempfile

        folder = Path(tempfile.mkdtemp(prefix="signed-", dir=work_root()))
        target = folder / f"{self.path.stem} ({report.field}).pdf"
        try:
            verify.signed_version(self.path, report, target)
        except verify.VerifyError as e:
            self.status(str(e), error=True)
            return None
        return open_window(target)
