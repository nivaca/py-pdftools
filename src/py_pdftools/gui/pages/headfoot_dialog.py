"""The dialog of headers and footers: what to write in each place, the margins, the
appearance, the pages and Bates numbering, with a preview of a page and the profiles kept."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMenu,
    QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from ...pages import headfoot
from ...pages.headfoot import HeaderFooter
from ...core.interface import tr
from .stamp_dialog import ColorButton, StampDialog, TextTarget, ask

SlotEdit = TextTarget  # (the text of one place)


class HeaderFooterDialog(StampDialog):
    """Settings for a header and footer, from HF; see StampDialog."""

    # Lo que StampDialog necesita saber del tipo de capa: el módulo que la valida, la dibuja y guarda sus perfiles,
    # y la clase de sus ajustes.
    module = headfoot
    settings_class = HeaderFooter

    def title(self) -> str:
        return tr("Header and Footer")

    def keep_text(self) -> str:
        return tr("Keep the headers and footers already on the pages (add another)")

    def preview_note(self) -> str:
        return tr("The header and footer don't go on this page.")

    def build(self):
        # ------------------------------------------------- the texts
        # Seis campos de texto, tres arriba y tres abajo; el nombre de cada uno (header_left...) es el del campo
        # de HeaderFooter que le corresponde.
        self.slots: dict[str, TextTarget] = {}
        texts = QGridLayout()
        for row, prefix in enumerate(("header", "footer")):
            for col, side in enumerate(("left", "center", "right")):
                slot = f"{prefix}_{side}"
                edit = TextTarget(self, slot)
                edit.setPlaceholderText(tr(headfoot.SLOT_TITLES[slot]))
                edit.setToolTip(tr(headfoot.SLOT_TITLES[slot]))
                edit.textChanged.connect(self.changed)
                self.slots[slot] = edit
                texts.addWidget(edit, row, col)
        # Until the user clicks a field, the buttons below insert into the centre of the footer, where page numbers
        # usually go.
        self.target = self.slots["footer_center"]
        insert = QHBoxLayout()
        insert.addWidget(QLabel(tr("Insert:")))
        date = QPushButton(tr("Date"))
        date.setToolTip(f"$date: {tr(headfoot.VARIABLES['date'])}")
        date.clicked.connect(lambda *_: self.insert("$date"))
        insert.addWidget(date)
        # date_format is built by StampDialog, which shares it with the watermark dialog; here it only takes a place.
        insert.addWidget(self.date_format)
        number = QToolButton()
        number.setText(tr("Page number"))
        number.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(number)
        # Los formatos de número de página se insertan traducidos ("Página $page de $totalpages"),
        # en el idioma de la interfaz.
        for shown, text in headfoot.PAGE_FORMATS.items():
            menu.addAction(tr(shown), lambda *_, t=text: self.insert(tr(t)))
        number.setMenu(menu)
        insert.addWidget(number)
        bates = QPushButton(tr("Bates number"))
        bates.setToolTip(f"$bates: {tr(headfoot.VARIABLES['bates'])}")
        bates.clicked.connect(lambda *_: self.insert("$bates"))
        insert.addWidget(bates)
        other = QToolButton()
        other.setText(tr("Other"))
        other.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(other)
        for variable, help_text in headfoot.VARIABLES.items():
            menu.addAction(f"${variable}  —  {tr(help_text)}", lambda *_, v=variable: self.insert("$" + v))
        other.setMenu(menu)
        insert.addWidget(other)
        insert.addStretch(1)
        texts_box = QGroupBox(tr("Header and footer"))
        lay = QVBoxLayout(texts_box)
        lay.addLayout(texts)
        lay.addLayout(insert)

        # ------------------------------------------------- margins
        self.units = QComboBox()
        for code, title in headfoot.UNIT_TITLES.items():
            self.units.addItem(tr(title), code)
        # Cambiar de unidad convierte los márgenes ya escritos (ver _units_changed),
        # en vez de reinterpretar sus números.
        self.units.currentIndexChanged.connect(self._units_changed)
        self.margins = {}
        margins = QFormLayout()
        margins.addRow(tr("Units"), self.units)
        for side, title in (("top", tr("Top")), ("bottom", tr("Bottom")), ("left", tr("Left side")),
                            ("right", tr("Right side"))):
            spin = QDoubleSpinBox()
            spin.setRange(0, 1000)
            spin.setDecimals(2)
            spin.valueChanged.connect(self.changed)
            self.margins[side] = spin
            margins.addRow(title, spin)
        # Shrinking scales the page content into the space left between the margins, so that nothing is covered.
        self.shrink = QCheckBox(tr("Shrink the pages"))
        self.shrink.setToolTip(tr("Scale the content of the pages down so that the header and footer don't "
                                  "cover it"))
        self.shrink.toggled.connect(self.changed)
        margins.addRow(self.shrink)
        margins_box = QGroupBox(tr("Margins"))
        margins_box.setLayout(margins)

        # ------------------------------------------------- appearance
        self.font_box = QComboBox()
        for code, title in headfoot.FAMILY_TITLES.items():
            self.font_box.addItem(title, code)
        self.font_box.currentIndexChanged.connect(self.changed)
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(1, 200)
        self.font_size.setDecimals(1)
        self.font_size.setSuffix(" pt")
        self.font_size.valueChanged.connect(self.changed)
        self.color = ColorButton()
        # ColorButton has no Qt signal: its colorChanged method is replaced by the dialog's own slot.
        self.color.colorChanged = self.changed
        self.bold = QCheckBox(tr("Bold"))
        self.italic = QCheckBox(tr("Italic"))
        for box in (self.bold, self.italic):
            box.toggled.connect(self.changed)
        font_row = QHBoxLayout()
        for w in (self.font_box, self.font_size, self.color, self.bold, self.italic):
            font_row.addWidget(w)
        self.border = QCheckBox(tr("Border"))
        self.border.toggled.connect(self.changed)
        self.border_color = ColorButton()
        self.border_color.colorChanged = self.changed
        self.border_width = QDoubleSpinBox()
        self.border_width.setRange(0, 20)
        self.border_width.setDecimals(2)
        self.border_width.setSuffix(" pt")
        self.border_width.valueChanged.connect(self.changed)
        border_row = QHBoxLayout()
        for w in (self.border, self.border_color, QLabel(tr("Width")), self.border_width):
            border_row.addWidget(w)
        border_row.addStretch(1)
        self.background = QCheckBox(tr("Background"))
        self.background.toggled.connect(self.changed)
        # El fondo se activa con la casilla; el color blanco solo es el valor inicial del botón.
        self.background_color = ColorButton("#ffffff")
        self.background_color.colorChanged = self.changed
        background_row = QHBoxLayout()
        background_row.addWidget(self.background)
        background_row.addWidget(self.background_color)
        background_row.addStretch(1)
        look = QVBoxLayout()
        look.addLayout(font_row)
        look.addLayout(border_row)
        look.addLayout(background_row)
        look_box = QGroupBox(tr("Appearance"))
        look_box.setLayout(look)

        left = QVBoxLayout()
        left.addWidget(texts_box)
        row = QHBoxLayout()
        row.addWidget(margins_box)
        row.addWidget(look_box, 1)
        left.addLayout(row)
        # pages_box y bates_box los construye la clase base; aquí solo se colocan debajo del resto.
        row = QHBoxLayout()
        row.addWidget(self.pages_box, 1)
        row.addWidget(self.bates_box)
        left.addLayout(row)
        return left

    def load_own(self, hf: HeaderFooter):
        for slot, edit in self.slots.items():
            edit.setText(getattr(hf, slot))
        self.units.setCurrentIndex(self.units.findData(hf.units))
        # _units remembers the unit the margins are written in, for the conversion when it changes.
        self._units = hf.units
        for side, spin in self.margins.items():
            spin.setValue(getattr(hf, side))
        self.shrink.setChecked(hf.shrink)
        self.font_box.setCurrentIndex(self.font_box.findData(hf.font))
        self.font_size.setValue(hf.size)
        self.color.set_color(hf.color)
        self.bold.setChecked(hf.bold)
        self.italic.setChecked(hf.italic)
        self.border.setChecked(hf.border)
        self.border_color.set_color(hf.border_color)
        self.border_width.setValue(hf.border_width)
        # An empty string means no background in HeaderFooter, so the color is kept only while the box is checked.
        self.background.setChecked(bool(hf.background))
        self.background_color.set_color(hf.background or "#ffffff")

    def own_values(self) -> dict:
        return dict(
            **{slot: edit.text() for slot, edit in self.slots.items()},
            units=self.units.currentData(), **{side: spin.value() for side, spin in self.margins.items()},
            shrink=self.shrink.isChecked(), font=self.font_box.currentData(), size=self.font_size.value(),
            color=self.color.color, bold=self.bold.isChecked(), italic=self.italic.isChecked(),
            border=self.border.isChecked(), border_color=self.border_color.color,
            border_width=self.border_width.value(),
            # Si el fondo está desmarcado se guarda "" y el color elegido se pierde;
            # al reabrir el diálogo vuelve a blanco.
            background=self.background_color.color if self.background.isChecked() else "")

    def _units_changed(self, *_):
        """Keep the margins where they are, in the new units."""
        new = self.units.currentData()
        # Mientras se cargan los ajustes no se convierte nada: los valores ya vienen en la unidad nueva.
        if not self._loading and new != getattr(self, "_units", new):
            # POINTS da cuántos puntos tiene cada unidad; el factor pasa de la unidad vieja a la nueva.
            factor = headfoot.POINTS[self._units] / headfoot.POINTS[new]
            for spin in self.margins.values():
                spin.setValue(round(spin.value() * factor, 2))
        self._units = new
        self.changed()


def ask_header_footer(parent: QWidget, hf: HeaderFooter, source: Path, password: str, labels: list[str],
                      page: int = 1, existing: bool = False) -> tuple[HeaderFooter, bool] | None:
    """(the settings, whether to keep those already on the pages) the user applies (None if cancelled)."""
    return ask(HeaderFooterDialog, parent, hf, source, password, labels, page, existing)
