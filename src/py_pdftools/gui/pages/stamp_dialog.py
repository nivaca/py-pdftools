"""What the dialogs of headers and footers, and of watermarks, share: the profiles, the pages,
Bates numbering, the choice of adding to what the pages have or replacing it, and a preview of
a page."""

from __future__ import annotations

import dataclasses
import io
from datetime import datetime
from pathlib import Path

import pikepdf
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QSpinBox, QVBoxLayout,
)

from ...pages import stamps
from ...core.interface import tr
from ...pages.labels import LabelError

PREVIEW = QSize(300, 390)  # the largest preview of a page


class ColorButton(QPushButton):
    """A button that shows a color and lets the user choose another."""

    def __init__(self, color: str = "#000000"):
        super().__init__()
        self.setFixedWidth(56)
        self.clicked.connect(self._choose)
        self.color = ""
        self.set_color(color)

    def set_color(self, color: str):
        self.color = color or "#000000"
        swatch = QPixmap(28, 14)
        swatch.fill(QColor(self.color))
        self.setIcon(QIcon(swatch))
        self.setIconSize(swatch.size())
        self.setToolTip(self.color)

    def _choose(self):
        chosen = QColorDialog.getColor(QColor(self.color), self, tr("Color"))
        if chosen.isValid():
            self.set_color(chosen.name())
            self.colorChanged()

    def colorChanged(self):  # (replaced by the dialog)
        pass


class TextTarget(QLineEdit):
    """A text the dialog inserts variables into, when it was the last to have the focus."""

    def __init__(self, dialog: StampDialog, name: str = ""):
        super().__init__()
        self.dialog, self.slot = dialog, name

    def focusInEvent(self, event):
        self.dialog.target = self
        super().focusInEvent(event)


class StampDialog(QDialog):
    """The base of the dialogs: SETTINGS (of MODULE: headfoot or watermark) to show; the document at
    SOURCE (with its pages labelled LABELS) is the one checked and previewed, at page PAGE. EXISTING:
    whether its pages already have this kind of layer (then the dialog asks whether to keep it)."""

    module = None
    settings_class = None

    def __init__(self, parent, settings, source: Path, password: str, labels: list[str] | None, page: int = 1,
                 existing: bool = False):
        super().__init__(parent)
        self.setWindowTitle(self.title())
        self.pdf = pikepdf.open(source, password=password)
        self.doc = stamps.document_of(self.pdf, source, labels)
        self.now = datetime.now()
        self._loading = False
        self.timer = QTimer(self, singleShot=True, interval=150)
        self.timer.timeout.connect(self.update_preview)
        self.target: TextTarget | None = None

        # ------------------------------------------------- profile
        self.profile = QComboBox()
        self.profile.setMinimumWidth(180)
        self.show_on_menu = QCheckBox(tr("Show on menu"))
        self.show_on_menu.setToolTip(tr("List this profile in its menu, to apply it at once"))
        save = QPushButton(tr("Save…"))
        save.setToolTip(tr("Keep these settings as a profile"))
        save.clicked.connect(self.save_profile)
        self.delete = QPushButton(tr("Delete"))
        self.delete.clicked.connect(self.delete_profile)
        self.top = QHBoxLayout()
        self.top.addWidget(QLabel(tr("Profile:")))
        self.top.addWidget(self.profile, 1)
        self.top.addWidget(self.show_on_menu)
        self.top.addWidget(save)
        self.top.addWidget(self.delete)

        # ------------------------------------------------- pages
        self.all_pages = QRadioButton(tr("All pages"))
        self.some_pages = QRadioButton(tr("Pages:"))
        self.pages = QLineEdit()
        self.pages.setPlaceholderText(tr("e.g. 9-200 or 1,3,9-"))
        self.pages.setToolTip(tr("The pages of the file, from 1; LAST counts from the end"))
        self.parity = QComboBox()
        for code, title in stamps.PARITIES.items():
            self.parity.addItem(tr(title), code)
        for w in (self.all_pages, self.some_pages):
            w.toggled.connect(self.changed)
        self.pages.textChanged.connect(lambda *_: (self.some_pages.setChecked(True) if self.pages.text() and
                                                   not self._loading else None, self.changed()))
        self.parity.currentIndexChanged.connect(self.changed)
        self.keep = QCheckBox(self.keep_text())
        self.keep.setToolTip(tr("Else they are replaced, on the pages this one goes on"))
        self.keep.setVisible(existing)
        self.keep.toggled.connect(self.changed)
        grid = QGridLayout()
        grid.addWidget(self.all_pages, 0, 0)
        grid.addWidget(self.some_pages, 1, 0)
        grid.addWidget(self.pages, 1, 1)
        grid.addWidget(QLabel(tr("Of those:")), 2, 0)
        grid.addWidget(self.parity, 2, 1)
        grid.addWidget(self.keep, 3, 0, 1, 2)
        self.pages_box = QGroupBox(tr("Pages"))
        self.pages_box.setLayout(grid)

        # ------------------------------------------------- Bates numbering
        self.bates_prefix = QLineEdit()
        self.bates_suffix = QLineEdit()
        self.bates_start = QSpinBox()
        self.bates_start.setRange(0, 999_999_999)
        self.bates_digits = QSpinBox()
        self.bates_digits.setRange(1, 20)
        for w in (self.bates_prefix, self.bates_suffix):
            w.textChanged.connect(self.changed)
        for w in (self.bates_start, self.bates_digits):
            w.valueChanged.connect(self.changed)
        form = QFormLayout()
        form.addRow(tr("Prefix"), self.bates_prefix)
        form.addRow(tr("Starts at"), self.bates_start)
        form.addRow(tr("Digits"), self.bates_digits)
        form.addRow(tr("Suffix"), self.bates_suffix)
        self.bates_box = QGroupBox(tr("Bates numbering ($bates)"))
        self.bates_box.setLayout(form)

        # ------------------------------------------------- the date
        self.date_format = QComboBox()
        for code, title in stamps.DATE_FORMATS.items():
            self.date_format.addItem(tr(title), code)
        self.date_format.setToolTip(tr("How $date writes the date"))
        self.date_format.currentIndexChanged.connect(self.changed)

        # ------------------------------------------------- preview
        self.preview = QLabel()
        self.preview.setFixedSize(PREVIEW + QSize(8, 8))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background: palette(dark);")
        self.preview_page = QSpinBox()
        self.preview_page.setRange(1, max(self.doc.count, 1))
        self.preview_page.setValue(min(max(page, 1), self.doc.count))
        self.preview_page.setPrefix(tr("Page") + " ")
        self.preview_page.valueChanged.connect(self.changed)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #c0392b;")
        self.note = QLabel()
        self.note.setWordWrap(True)
        preview = QVBoxLayout()
        preview.addWidget(self.preview)
        preview.addWidget(self.preview_page)
        preview.addWidget(self.note)
        preview.addWidget(self.problem)
        preview.addStretch(1)
        self.preview_box = QGroupBox(tr("Preview"))
        self.preview_box.setLayout(preview)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Apply"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        body = QHBoxLayout()
        body.addLayout(self.build(), 1)
        body.addWidget(self.preview_box)
        lay = QVBoxLayout(self)
        lay.addLayout(self.top)
        lay.addLayout(body)
        lay.addWidget(self.buttons)
        self._fill_profiles(settings.name)
        self.profile.currentIndexChanged.connect(self._profile_chosen)
        self.load(settings)

    # ----------------------------------------------------------------- for the dialogs to say

    def title(self) -> str:
        return ""

    def keep_text(self) -> str:
        return ""

    def build(self):
        """The layout of the dialog's own settings (with self.pages_box and self.bates_box in it)."""
        raise NotImplementedError

    def load_own(self, settings):
        """Show the settings of the dialog's own kind."""
        raise NotImplementedError

    def own_values(self) -> dict:
        """The values of the dialog's own settings."""
        raise NotImplementedError

    def preview_note(self) -> str:
        """What the preview says when the page chosen is not one the settings go on."""
        return ""

    # ----------------------------------------------------------------- the settings

    def load(self, settings):
        self._loading = True
        self.load_own(settings)
        self.pages.setText(settings.pages)
        (self.some_pages if settings.pages.strip() else self.all_pages).setChecked(True)
        self.parity.setCurrentIndex(self.parity.findData(settings.parity))
        self.bates_prefix.setText(settings.bates_prefix)
        self.bates_start.setValue(settings.bates_start)
        self.bates_digits.setValue(settings.bates_digits)
        self.bates_suffix.setText(settings.bates_suffix)
        self.date_format.setCurrentIndex(max(self.date_format.findData(settings.date_format), 0))
        self.show_on_menu.setChecked(settings.show_on_menu)
        self._loading = False
        self.changed()

    def value(self):
        """The settings shown (not checked: see check)."""
        return self.settings_class(
            **self.own_values(),
            pages=self.pages.text().strip() if self.some_pages.isChecked() else "", parity=self.parity.currentData(),
            bates_prefix=self.bates_prefix.text(), bates_start=self.bates_start.value(),
            bates_digits=self.bates_digits.value(), bates_suffix=self.bates_suffix.text(),
            date_format=self.date_format.currentData(), name=self.profile.currentData() or "",
            show_on_menu=self.show_on_menu.isChecked())

    def check(self):
        """(the settings, what goes on each page, '') if they are right; else (None, [], what is wrong)."""
        try:
            settings = self.module.check(self.value())
            pages = self.module.page_texts(settings, self.doc, self.now)
            if not pages:
                raise LabelError(tr("no page is chosen"))
        except LabelError as e:
            return None, [], str(e)
        return settings, pages, ""

    def insert(self, text: str):
        """Put TEXT ($date, Page $page ...) where the cursor is, in the last text that had the focus."""
        if self.target is not None:
            self.target.insert(text)
            self.target.setFocus()

    def changed(self, *_):
        if not self._loading:
            self.timer.start()

    # ----------------------------------------------------------------- the preview

    def update_preview(self):
        """Draw the page chosen with these settings, and say what is wrong, if anything."""
        settings, pages, problem = self.check()
        self.problem.setText(problem)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(settings is not None)
        number = self.preview_page.value()
        found = dict(pages).get(number) if settings is not None else None
        if settings is not None:
            self.note.setText("" if found is not None else self.preview_note())
        one = pikepdf.new()
        try:
            one.pages.append(self.pdf.pages[number - 1])
            if found is not None:
                self.module.stamp_page(one, one.pages[0], settings, found, keep=self.keep.isChecked())
            data = io.BytesIO()
            one.save(data)
        except (pikepdf.PdfError, LabelError, ValueError) as e:
            self.problem.setText(str(e))
            return
        finally:
            one.close()
        import pymupdf  # (drawn with PyMuPDF, as the window draws the pages)

        with pymupdf.open(stream=data.getvalue(), filetype="pdf") as doc:
            r = doc[0].rect
            if r.is_empty:
                return
            scale = min(PREVIEW.width() / r.width, PREVIEW.height() / r.height)
            pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
        self.preview.setPixmap(QPixmap.fromImage(image))

    # ----------------------------------------------------------------- profiles

    def _fill_profiles(self, current: str = ""):
        self.profiles = self.module.read_profiles()
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItem(tr("(new profile)"), "")
        for name in self.profiles:
            self.profile.addItem(name, name)
        self.profile.setCurrentIndex(max(self.profile.findData(current), 0))
        self.profile.blockSignals(False)
        self.delete.setEnabled(bool(self.profile.currentData()))

    def _profile_chosen(self, *_):
        name = self.profile.currentData()
        self.delete.setEnabled(bool(name))
        if name in self.profiles:
            self.load(self.profiles[name])

    def ask_profile_name(self, current: str) -> str | None:
        name, ok = QInputDialog.getText(self, tr("Save the profile"), tr("The name of the profile:"),
                                        QLineEdit.EchoMode.Normal, current)
        return name.strip() if ok and name.strip() else None

    def save_profile(self) -> bool:
        settings, _, problem = self.check()
        if settings is None:
            QMessageBox.warning(self, self.title(), problem)
            return False
        name = self.ask_profile_name(self.profile.currentData() or "")
        if name is None:
            return False
        try:
            self.module.save_profile(dataclasses.replace(settings, name=name))
        except (OSError, LabelError) as e:
            QMessageBox.warning(self, self.title(), tr("Could not keep the setting: {error}", error=e))
            return False
        self._fill_profiles(name)
        return True

    def delete_profile(self) -> bool:
        name = self.profile.currentData()
        if not name:
            return False
        try:
            self.module.delete_profile(name)
        except OSError as e:
            QMessageBox.warning(self, self.title(), tr("Could not keep the setting: {error}", error=e))
            return False
        self._fill_profiles("")
        return True

    def done(self, result: int):
        self.pdf.close()
        super().done(result)


def ask(dialog_class, parent, settings, source: Path, password: str, labels: list[str], page: int = 1,
        existing: bool = False):
    """(settings, keep) the user applies in the dialog (None if cancelled)."""
    dlg = dialog_class(parent, settings, source, password, labels, page, existing)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    settings, _, _ = dlg.check()
    return settings, dlg.keep.isChecked()
