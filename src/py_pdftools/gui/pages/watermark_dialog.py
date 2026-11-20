"""The dialog of watermarks: a text or a page of another PDF, its appearance, its position, the
pages, with a preview of a page and the profiles kept."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QPushButton, QRadioButton, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from ...pages import stamps, watermark
from ...core.interface import tr
from ...pages.watermark import Watermark
from .stamp_dialog import ColorButton, StampDialog, TextTarget, ask


class WatermarkDialog(StampDialog):
    """Settings for a watermark, from WM; see StampDialog."""

    module = watermark
    settings_class = Watermark

    def title(self) -> str:
        return tr("Watermark")

    def keep_text(self) -> str:
        return tr("Keep the watermarks already on the pages (add another)")

    def preview_note(self) -> str:
        return tr("The watermark doesn't go on this page.")

    def build(self):
        # ------------------------------------------------- what
        self.is_text = QRadioButton(tr("Text:"))
        self.is_file = QRadioButton(tr("Page of a PDF:"))
        self.text = TextTarget(self, "text")
        self.text.setPlaceholderText(tr("e.g. DRAFT, or Copy for $author"))
        self.text.textChanged.connect(lambda *_: (self.is_text.setChecked(True) if not self._loading else None,
                                                  self.changed()))
        self.target = self.text
        insert = QToolButton()
        insert.setText(tr("Insert"))
        insert.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(insert)
        for variable, help_text in stamps.VARIABLES.items():
            menu.addAction(f"${variable}  —  {tr(help_text)}", lambda *_, v=variable: self.insert("$" + v))
        insert.setMenu(menu)
        self.source = QLineEdit()
        self.source.setPlaceholderText(tr("a PDF file"))
        self.source.textChanged.connect(lambda *_: (self.is_file.setChecked(True) if not self._loading else None,
                                                    self.changed()))
        browse = QPushButton(tr("Choose…"))
        browse.clicked.connect(self.choose_source)
        self.source_page = QSpinBox()
        self.source_page.setRange(1, 99999)
        self.source_page.setPrefix(tr("Page") + " ")
        self.source_page.valueChanged.connect(self.changed)
        for w in (self.is_text, self.is_file):
            w.toggled.connect(self.changed)
        grid = QGridLayout()
        grid.addWidget(self.is_text, 0, 0)
        grid.addWidget(self.text, 0, 1)
        grid.addWidget(insert, 0, 2)
        grid.addWidget(self.is_file, 1, 0)
        grid.addWidget(self.source, 1, 1)
        row = QHBoxLayout()
        row.addWidget(browse)
        row.addWidget(self.source_page)
        grid.addLayout(row, 1, 2)
        self.font_box = QComboBox()
        for code, title in stamps.FAMILY_TITLES.items():
            self.font_box.addItem(title, code)
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(1, 500)
        self.font_size.setDecimals(1)
        self.font_size.setSuffix(" pt")
        self.color = ColorButton()
        self.color.colorChanged = self.changed
        self.bold = QCheckBox(tr("Bold"))
        self.italic = QCheckBox(tr("Italic"))
        for w in (self.font_box, self.font_size):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged).connect(self.changed)
        for w in (self.bold, self.italic):
            w.toggled.connect(self.changed)
        font_row = QHBoxLayout()
        for w in (QLabel(tr("Font:")), self.font_box, self.font_size, self.color, self.bold, self.italic):
            font_row.addWidget(w)
        font_row.addWidget(QLabel(tr("Date:")))
        font_row.addWidget(self.date_format)
        font_row.addStretch(1)
        what_box = QGroupBox(tr("Watermark"))
        lay = QVBoxLayout(what_box)
        lay.addLayout(grid)
        lay.addLayout(font_row)

        # ------------------------------------------------- appearance
        self.rotation = QSpinBox()
        self.rotation.setRange(-360, 360)
        self.rotation.setSuffix("°")
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix(" %")
        self.relative = QCheckBox(tr("Relative to the page:"))
        self.scale = QSpinBox()
        self.scale.setRange(1, 1000)
        self.scale.setSuffix(" %")
        self.relative.toggled.connect(lambda on: (self.scale.setEnabled(on), self.changed()))
        self.behind = QComboBox()
        self.behind.addItem(tr("In front of the content"), False)
        self.behind.addItem(tr("Behind the content"), True)
        self.on_print = QCheckBox(tr("Show when printing"))
        self.on_screen = QCheckBox(tr("Show on the screen"))
        for w in (self.rotation, self.opacity, self.scale):
            w.valueChanged.connect(self.changed)
        self.behind.currentIndexChanged.connect(self.changed)
        for w in (self.on_print, self.on_screen):
            w.toggled.connect(self.changed)
        look = QFormLayout()
        look.addRow(tr("Rotation"), self.rotation)
        look.addRow(tr("Opacity"), self.opacity)
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.relative)
        scale_row.addWidget(self.scale)
        look.addRow(scale_row)
        look.addRow(self.behind)
        look.addRow(self.on_print)
        look.addRow(self.on_screen)
        look_box = QGroupBox(tr("Appearance"))
        look_box.setLayout(look)

        # ------------------------------------------------- position
        self.halign = QComboBox()
        for code, title in watermark.HALIGNS.items():
            self.halign.addItem(tr(title), code)
        self.valign = QComboBox()
        for code, title in watermark.VALIGNS.items():
            self.valign.addItem(tr(title), code)
        self.units = QComboBox()
        for code, title in stamps.UNIT_TITLES.items():
            self.units.addItem(tr(title), code)
        self.hoffset = QDoubleSpinBox()
        self.voffset = QDoubleSpinBox()
        for spin in (self.hoffset, self.voffset):
            spin.setRange(-1000, 1000)
            spin.setDecimals(2)
            spin.valueChanged.connect(self.changed)
        for w in (self.halign, self.valign, self.units):
            w.currentIndexChanged.connect(self.changed)
        position = QFormLayout()
        row = QHBoxLayout()
        row.addWidget(self.halign)
        row.addWidget(QLabel(tr("moved")))
        row.addWidget(self.hoffset)
        position.addRow(tr("Across"), row)
        row = QHBoxLayout()
        row.addWidget(self.valign)
        row.addWidget(QLabel(tr("moved")))
        row.addWidget(self.voffset)
        position.addRow(tr("Up and down"), row)
        position.addRow(tr("Units"), self.units)
        position_box = QGroupBox(tr("Position"))
        position_box.setLayout(position)

        left = QVBoxLayout()
        left.addWidget(what_box)
        row = QHBoxLayout()
        row.addWidget(look_box)
        row.addWidget(position_box, 1)
        left.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.pages_box, 1)
        row.addWidget(self.bates_box)
        left.addLayout(row)
        return left

    def choose_source(self):
        name, _ = QFileDialog.getOpenFileName(self, tr("The PDF of the watermark"), str(Path.home()),
                                              tr("PDF files (*.pdf)"))
        if name:
            self.source.setText(name)

    def load_own(self, wm: Watermark):
        self.text.setText(wm.text)
        self.source.setText(wm.source)
        self.source_page.setValue(wm.source_page)
        (self.is_file if wm.source else self.is_text).setChecked(True)
        self.font_box.setCurrentIndex(self.font_box.findData(wm.font))
        self.font_size.setValue(wm.size)
        self.color.set_color(wm.color)
        self.bold.setChecked(wm.bold)
        self.italic.setChecked(wm.italic)
        self.rotation.setValue(round(wm.rotation))
        self.opacity.setValue(round(wm.opacity * 100))
        self.relative.setChecked(wm.scale > 0)
        self.scale.setValue(round(wm.scale) or 50)
        self.scale.setEnabled(wm.scale > 0)
        self.behind.setCurrentIndex(1 if wm.behind else 0)
        self.on_print.setChecked(wm.on_print)
        self.on_screen.setChecked(wm.on_screen)
        self.halign.setCurrentIndex(self.halign.findData(wm.halign))
        self.valign.setCurrentIndex(self.valign.findData(wm.valign))
        self.units.setCurrentIndex(self.units.findData(wm.units))
        self.hoffset.setValue(wm.hoffset)
        self.voffset.setValue(wm.voffset)

    def own_values(self) -> dict:
        text = self.is_text.isChecked()
        return dict(
            text=self.text.text() if text else "", source="" if text else self.source.text().strip(),
            source_page=self.source_page.value(), font=self.font_box.currentData(), size=self.font_size.value(),
            color=self.color.color, bold=self.bold.isChecked(), italic=self.italic.isChecked(),
            rotation=float(self.rotation.value()), opacity=self.opacity.value() / 100,
            scale=float(self.scale.value()) if self.relative.isChecked() else 0.0,
            behind=bool(self.behind.currentData()), on_print=self.on_print.isChecked(),
            on_screen=self.on_screen.isChecked(), halign=self.halign.currentData(), valign=self.valign.currentData(),
            units=self.units.currentData(), hoffset=self.hoffset.value(), voffset=self.voffset.value())


def ask_watermark(parent: QWidget, wm: Watermark, source: Path, password: str, labels: list[str], page: int = 1,
                  existing: bool = False) -> tuple[Watermark, bool] | None:
    """(the settings, whether to keep the watermarks already on the pages) the user applies (None if
    cancelled)."""
    return ask(WatermarkDialog, parent, wm, source, password, labels, page, existing)
