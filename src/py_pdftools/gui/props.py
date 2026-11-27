"""The properties of the annotations selected (their colours, line, text,
opacity, comment, author, lock), or of a tool: how the annotations it makes
look, and how it behaves."""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..annotate import settings
from ..annotate.annots import (
    ALIGNS,
    CONFIDENCE,
    CRITICAL,
    DASHABLE,
    ENDED,
    ENDS,
    FILLED,
    FONTS,
    ICONS,
    NAMES,
    STAMPS,
    STROKED,
    TEXTUAL,
    Annotation,
    Critical,
    date_text,
)
from ..core.interface import ntr, tr
from .colors import color_name, swatch, swatches

# Un centinela propio y no None: None o '' pueden ser valores reales de una propiedad (sin color).
SAME = object()  # (a property that differs among the annotations: left as each has it)


class ColorButton(QPushButton):
    """A button that shows a colour and lets the user choose another; NONE
    allows 'no colour' (''). CHOICES gives the colours its menu offers ((value,
    name), the palette if not given), NAME the name of a colour."""

    BARE = QSize(56, 18)  # (the colour alone: its size, as a wide patch)

    def __init__(self, color, none: bool = False, parent=None, none_text: str = "", choices=None, name=None,
                 bare: bool = False):
        super().__init__(parent)
        # Solo el color, sin su nombre (que queda en el consejo): donde el nombre ya se lee al lado
        self.bare = bare
        if bare:
            self.setIconSize(self.BARE)
        self.none = none
        self.none_text = none_text  # (what 'no colour' means here, if not that)
        # (the mode Redact gives its own: no palette, and the names of its fills)
        self._choices = swatches if choices is None else choices
        self._name = color_name if name is None else name
        self.color = color
        self.clicked.connect(self._choose)
        self._show()

    def _show(self):
        if self.color is SAME:
            self.setText(tr("(several)"))
            self.setIcon(swatch("#808080"))
        else:
            # Para el relleno o el borde, '' significa sin color; none_text dice qué pasa entonces.
            name = self.none_text if not self.color and self.none_text else self._name(self.color)
            if self.bare:
                self.setText("")
                self.setToolTip(name)
                self.setIcon(swatch(self.color, self.BARE.height(), self.BARE.width()))
                return
            self.setText(name)
            self.setIcon(swatch(self.color))

    def _choose(self):
        menu = QMenu(self)
        offered = self._choices()
        for value, name in offered:
            menu.addAction(swatch(value), name, lambda v=value: self.set_color(v))
        if self.none:
            menu.addAction(swatch(""), self.none_text or tr("No colour"), lambda: self.set_color(""))
        if offered:
            menu.addSeparator()
        menu.addAction(tr("Other colour…") if offered else tr("Choose…"), self._dialog)
        # The menu opens under the button, as a drop-down list would.
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _dialog(self):
        # Con varios colores distintos (SAME) o sin color, el diálogo empieza en negro.
        start = QColor(self.color) if isinstance(self.color, str) and self.color else QColor("#000000")
        chosen = QColorDialog.getColor(start, self, tr("Colour"))
        if chosen.isValid():
            self.set_color(chosen.name())

    def set_color(self, color: str):
        self.color = color
        self._show()


def tristate_check(text: str, value) -> QCheckBox:
    """A check box for VALUE; SAME (it differs among those chosen) is its third state, 'several', which
    leaves each as it is."""
    box = QCheckBox(text)
    if value is SAME:
        box.setTristate(True)
        box.setCheckState(box.checkState().PartiallyChecked)
    else:
        box.setChecked(bool(value))
    return box


def _combo(choices: dict, value) -> QComboBox:
    """A list of CHOICES ({value: name to translate}), with VALUE chosen (none if SAME)."""
    box = QComboBox()
    for key, name in choices.items():
        box.addItem(tr(name), key)
    # Index -1 leaves the box empty, so the placeholder '(several)' shows and changes() can tell that
    # the user did not choose anything.
    box.setCurrentIndex(-1 if value is SAME else max(box.findData(value), 0))
    if value is SAME:
        box.setPlaceholderText(tr("(several)"))
    return box



class ShortText(QPlainTextEdit):
    """The text or comment of an annotation in its properties: LINES lines high at first, three at least, with a
    scroll bar for a longer one; it grows with the dialog, if the dialog is made taller."""

    LINES = 5

    def _height(self, lines: int) -> int:
        margin = 2 * (self.frameWidth() + round(self.document().documentMargin()))
        return lines * self.fontMetrics().lineSpacing() + margin

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self._height(self.LINES))

    def minimumSizeHint(self) -> QSize:
        return QSize(super().minimumSizeHint().width(), self._height(3))

class PropertiesDialog(QDialog):
    """The properties of ANNOTATIONS; or, with TOOL, of the tool that makes
    annotations of their kind (ANNOTATIONS: one, made with its style)."""

    def __init__(self, annotations: list[Annotation], parent=None, tool: settings.Style | None = None,
                 categories: list[str] | None = None):
        super().__init__(parent)
        self.annotations = annotations
        self.tool = tool
        # Los campos que se muestran dependen de los tipos seleccionados: basta con que uno los use.
        kinds = {a.kind for a in annotations}
        if tool is not None:
            self.setWindowTitle(tr("Tool properties ({kind})", kind=tr(NAMES[annotations[0].kind]).lower()))
        elif len(annotations) == 1:
            self.setWindowTitle(tr("Properties of the annotation ({kind})", kind=annotations[0].name().lower()))
        else:
            self.setWindowTitle(ntr("Properties of the annotation", "Properties of the {count} annotations",
                                    len(annotations)))

        # Un valor común a todas (o solo a las de AMONG, los tipos que tienen esa propiedad); si difieren, SAME.
        def common(name, among=None):
            values = {getattr(a, name) for a in annotations if among is None or a.kind in among}
            return values.pop() if len(values) == 1 else SAME

        look = QGroupBox(tr("Appearance"))
        form = QFormLayout(look)
        self.color = ColorButton(common("color"))
        form.addRow(tr("Text colour:") if kinds <= set(TEXTUAL) else tr("Colour:"), self.color)
        self.fill = self.width = self.font_size = self.font = self.align = self.icon = self.border = None
        self.start = self.end = self.dashed = self.stamp = None
        if kinds & set(TEXTUAL):
            self.border = ColorButton(common("border", TEXTUAL), none=True, none_text=tr("As the text"))
            form.addRow(tr("Border colour:"), self.border)
        if kinds & set(FILLED):
            self.fill = ColorButton(common("fill", FILLED), none=True)
            form.addRow(tr("Fill:"), self.fill)
        if kinds & set(STROKED):
            # A text box may have no border (width 0); lines and shapes need at least a quarter of a point.
            self.width = self._number(common("width", STROKED), 0 if kinds & set(TEXTUAL) else 0.25, 20, " pt")
            form.addRow(tr("Border width:") if kinds <= set(TEXTUAL) else tr("Line width:"), self.width)
        if kinds & set(DASHABLE):
            self.dashed = tristate_check(tr("Dashed"), common("dashed", DASHABLE))
            form.addRow("", self.dashed)
        if kinds & (set(ENDED) | {"arrow"}):
            ends = common("ends", ENDED + ("arrow",))
            # Una llamada solo tiene extremo final, el que apunta: no se le ofrece el inicial.
            if not kinds & {"callout"}:
                self.start = _combo(ENDS, SAME if ends is SAME else ends[0])
                form.addRow(tr("Start:"), self.start)
            self.end = _combo(ENDS, SAME if ends is SAME else ends[1])
            form.addRow(tr("End:"), self.end)
        if kinds & set(TEXTUAL):
            self.font = _combo(FONTS, common("font", TEXTUAL))
            form.addRow(tr("Font:"), self.font)
            self.font_size = self._number(common("font_size", TEXTUAL), 4, 72, " pt")
            form.addRow(tr("Font size:"), self.font_size)
            self.align = _combo(ALIGNS, common("align", TEXTUAL))
            form.addRow(tr("Alignment:"), self.align)
        if "note" in kinds:
            self.icon = _combo(ICONS, common("icon", ("note",)))
            form.addRow(tr("Icon:"), self.icon)
        if tool is not None and kinds == {"stamp"}:
            self.stamp = _combo(STAMPS, tool.stamp if tool.stamp in STAMPS else "Approved")
            form.addRow(tr("Stamp:"), self.stamp)
        self.opacity = QSpinBox()
        self.opacity.setRange(10, 100)
        self.opacity.setSuffix(" %")
        opacity = common("opacity")
        # Opacidad entre 10 y 100 %: una anotación invisible no se podría encontrar en la página.
        self.opacity.setValue(100 if opacity is SAME else round(opacity * 100))
        # Values differ: 9, below the real range, stands for '(several)'; changes() ignores anything under 10.
        if opacity is SAME:
            self.opacity.setSpecialValueText(tr("(several)"))
            self.opacity.setMinimum(9)
            self.opacity.setValue(9)
        form.addRow(tr("Opacity:"), self.opacity)

        lay = QVBoxLayout(self)
        lay.addWidget(look)
        self.contents = self.author = self.locked = self.tags = self.categories = self.critical = None
        self.sticky = self.show_after = None
        self.as_default = QCheckBox(tr("Use this style for new annotations of this kind"))
        if tool is None:
            note = QGroupBox(tr("Annotation"))
            form = QFormLayout(note)
            contents = common("contents")
            self.contents = ShortText("" if contents is SAME else contents)
            self.contents.setPlaceholderText(tr("(several)") if contents is SAME else "")
            self._contents_given = contents is not SAME
            # For notes and text boxes the contents are the text itself; for the others, a comment on them.
            form.addRow(tr("Text:") if kinds <= {"note", "freetext", "callout", "caret"} else tr("Comment:"),
                        self.contents)
            author = common("author")
            self.author = QLineEdit("" if author is SAME else author)
            self.author.setPlaceholderText(tr("(several)") if author is SAME else "")
            form.addRow(tr("Author:"), self.author)
            tags = common("tags")
            self.tags = QLineEdit("" if tags is SAME else ", ".join(tags))
            self.tags.setPlaceholderText(tr("(several)") if tags is SAME else tr("Tags, separated by commas"))
            self._tags_given = tags is not SAME
            form.addRow(tr("Tags:"), self.tags)
            self.categories = QListWidget()
            # Las categorías del documento y, después, las que ya tengan las anotaciones aunque no estén en él.
            names = list(categories or [])
            for a in annotations:
                names += [c for c in a.categories if c not in names]
            for name in names:
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                # Una categoría que solo tienen algunas de las seleccionadas queda a medias (tres estados), y así
                # apply() la deja como está en cada una.
                have = sum(name in a.categories for a in annotations)
                if 0 < have < len(annotations):
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserTristate)
                    item.setCheckState(Qt.CheckState.PartiallyChecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked if have else Qt.CheckState.Unchecked)
                self.categories.addItem(item)
            # Cuatro filas a la vista, y una barra de desplazamiento si hay más.
            row = self.categories.sizeHintForRow(0) if self.categories.count() else \
                self.categories.fontMetrics().height() + 2
            self.categories.setMaximumHeight(4 * row + 2 * self.categories.frameWidth() + 2)
            form.addRow(tr("Categories:"), self.categories)
            self.locked = tristate_check(tr("Locked: can't be moved, resized, erased or deleted"), common("locked"))
            form.addRow("", self.locked)
            if len(annotations) == 1:
                a = annotations[0]
                dates = tr("Made: {made}; changed: {changed}", made=date_text(a.created) or "—",
                           changed=date_text(a.modified) or "—") if a.created or a.modified \
                    else tr("Not yet saved in the document")
                info = QLabel(dates)
                info.setStyleSheet("color: palette(placeholder-text);")
                form.addRow("", info)
            lay.addWidget(note)
            # La entrada de crítica textual solo se ofrece con una anotación seleccionada, no con varias.
            if len(annotations) == 1:
                lay.addWidget(self._critical_box(annotations[0].critical))
            self.as_default.setToolTip(tr("The colours, the line, the font and the opacity"))
            self.as_default.setVisible(len(kinds) == 1)
            lay.addWidget(self.as_default)
        else:
            behaviour = QGroupBox(tr("Behaviour"))
            form = QFormLayout(behaviour)
            # Only for a tool: what it does after making an annotation, not how it looks.
            self.sticky = QCheckBox(tr("Keep the tool chosen after making an annotation"))
            self.sticky.setToolTip(tr("Otherwise, the Select tool is chosen again"))
            self.sticky.setChecked(tool.sticky)
            form.addRow("", self.sticky)
            self.show_after = _combo(settings.SHOW, tool.show)
            form.addRow(tr("After making an annotation, open:"), self.show_after)
            lay.addWidget(behaviour)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(460, self.sizeHint().height())

    def _critical_box(self, entry: Critical | None) -> QGroupBox:
        """The entry of textual criticism of the annotation: ticked, it has one. Its fields fold under a
        line that sums them up, so that the dialog stays small; ticking the box unfolds them."""
        self.critical = box = QGroupBox(tr("Textual criticism"))
        box.setCheckable(True)
        box.setChecked(entry is not None)
        # An empty entry, so the fields exist even if the box is unticked; critical_entry() checks the box.
        entry = entry or Critical("variant")
        outer = QVBoxLayout(box)
        self.c_toggle = QToolButton()
        self.c_toggle.setAutoRaise(True)
        self.c_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.c_toggle.setCheckable(True)
        self.c_toggle.setToolTip(tr("Show or hide the fields of the entry"))
        outer.addWidget(self.c_toggle)
        self.c_body = QWidget()
        form = QFormLayout(self.c_body)
        form.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.c_body)
        self.c_type = _combo(CRITICAL, entry.type)
        form.addRow(tr("Kind:"), self.c_type)
        self.c_fields = {}
        for name, label, hint in (("lemma", tr("Reading of the text:"), tr("(the text marked)")),
                                  ("reading", tr("Other reading:"), tr("Proposed, or of the witness")),
                                  ("witness", tr("Witness:"), tr("Manuscript or edition (its siglum)")),
                                  ("location", tr("Location:"), tr("Folio, line…")),
                                  ("source", tr("Source:"), tr("Where the reading comes from")),
                                  ("rationale", tr("Rationale:"), "")):
            field = QLineEdit(getattr(entry, name))
            field.setPlaceholderText(hint)
            self.c_fields[name] = field
            form.addRow(label, field)
            field.textChanged.connect(self._critical_summary)
        self.c_confidence = _combo(CONFIDENCE, entry.confidence)
        form.addRow(tr("Confidence:"), self.c_confidence)
        self.c_type.currentIndexChanged.connect(self._critical_summary)
        self.c_toggle.toggled.connect(self._critical_fold)
        # Tickear la casilla despliega los campos (hay que llenarlos); quitarla los pliega.
        box.toggled.connect(self.c_toggle.setChecked)
        self._critical_fold(False)
        return box

    def _critical_fold(self, open_: bool):
        self.c_body.setVisible(open_)
        self.c_toggle.setArrowType(Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow)
        self._critical_summary()
        # El diálogo se ajusta a la altura nueva cuando Qt ha rehecho su disposición (antes, la medida es la vieja).
        if self.isVisible():
            QTimer.singleShot(0, self._fit_height)

    def _fit_height(self):
        # Se rehace a mano la disposición del grupo y la del diálogo: sin eso, el alto mínimo todavía cuenta
        # los campos plegados, y el diálogo no baja.
        self.critical.layout().activate()
        self.layout().activate()
        # (self.width es la casilla del grosor de la línea: el ancho, por size())
        self.resize(self.size().width(), self.sizeHint().height())

    def _critical_summary(self, *_):
        """The line over the fields: when folded, what the entry says ('Variant reading: lemma ] reading')."""
        if self.c_toggle.isChecked():
            self.c_toggle.setText(tr("Hide the fields"))
            return
        f = {k: " ".join(w.text().split()) for k, w in self.c_fields.items()}
        # Como en el aparato crítico: 'lema ] lectura testigo' (sin lema, '] lectura'; sin lectura, el lema).
        other = " ".join(x for x in (f["reading"], f["witness"]) if x)
        said = f"{f['lemma']} ] {other}" if f["lemma"] and other else f"] {other}" if other else f["lemma"]
        text = self.c_type.currentText() + (f": {said.strip()}" if said.strip() else "")
        # (larga, ensancharía el diálogo: se corta, y entera queda en la ayuda emergente)
        self.c_toggle.setToolTip(text if len(text) > 60 else tr("Show or hide the fields of the entry"))
        text = text if len(text) <= 60 else text[:59] + "…"
        self.c_toggle.setText(text if self.critical.isChecked() else tr("Show the fields"))

    def critical_entry(self) -> Critical | None:
        if not self.critical.isChecked():
            return None
        # Los espacios repetidos y los saltos de línea de cada campo se reducen a uno.
        return Critical(self.c_type.currentData() or "variant", confidence=self.c_confidence.currentData() or "",
                        **{k: " ".join(f.text().split()) for k, f in self.c_fields.items()})

    @staticmethod
    def _number(value, low: float, high: float, suffix: str) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(2 if high <= 20 else 1)
        box.setSingleStep(0.5)
        box.setSuffix(suffix)
        # Same trick as the opacity: a value 0.01 under the range reads '(several)'.
        if value is SAME:  # (a value below the range, shown as "(several)")
            box.setRange(low - 0.01, high)
            box.setSpecialValueText(tr("(several)"))
            box.setValue(low - 0.01)
        else:
            box.setRange(low, high)
            box.setValue(value)
        return box

    def changes(self) -> dict:
        """What to change in each annotation (what the user left as '(several)' isn't changed)."""
        out = {}
        if self.color.color is not SAME:
            out["color"] = self.color.color
        if self.fill is not None and self.fill.color is not SAME:
            out["fill"] = self.fill.color
        if self.border is not None and self.border.color is not SAME:
            out["border"] = self.border.color
        for name in ("width", "font_size"):
            box = getattr(self, name)
            # Solo se cambia si no es '(several)' o si el usuario movió el valor por encima del mínimo especial.
            if box is not None and (not box.specialValueText() or box.value() > box.minimum()):
                out[name] = round(box.value(), 2)
        for name in ("font", "align", "icon"):
            box = getattr(self, name)
            if box is not None and box.currentIndex() >= 0:
                out[name] = box.currentData()
        if self.end is not None and self.end.currentIndex() >= 0:
            out["end"] = self.end.currentData()
        if self.start is not None and self.start.currentIndex() >= 0:
            out["start"] = self.start.currentData()
        for name in ("dashed", "locked"):
            box = getattr(self, name)
            if box is not None and box.checkState() != box.checkState().PartiallyChecked:
                out[name] = box.isChecked()
        if self.opacity.value() >= 10:
            out["opacity"] = self.opacity.value() / 100
        if self.contents is not None:
            text = self.contents.toPlainText()
            # Con textos distintos, el campo empieza vacío: solo se cambian si el usuario escribió algo.
            if self._contents_given or text:
                out["contents"] = text.strip("\n")
        # An author left empty is kept as empty only when all had the same author; with several, nothing
        # changes.
        if self.author is not None and (self.author.text() or len({a.author for a in self.annotations}) == 1):
            out["author"] = " ".join(self.author.text().split())
        if self.critical is not None:
            out["critical"] = self.critical_entry()
        if self.tags is not None and (self._tags_given or self.tags.text().strip()):
            # Etiquetas separadas por comas, sin espacios sobrantes; las vacías se descartan.
            out["tags"] = tuple(t for t in (" ".join(x.split()) for x in self.tags.text().split(",")) if t)
        return out

    def apply(self, annotation: Annotation) -> Annotation:
        changes = dict(self.changes())
        kind = annotation.kind
        start, end = changes.pop("start", None), changes.pop("end", None)
        # Ends are stored as a pair: the side not chosen keeps the annotation's own value.
        if (start or end) and (kind in ENDED or kind == "arrow"):
            changes["ends"] = (start or annotation.ends[0], end or annotation.ends[1])
        if annotation.rich and changes.get("contents", annotation.contents) != annotation.contents:
            changes["rich"] = ""  # (its text written here, plain: its formatting would no longer fit it)
        # Una selección mixta: cada propiedad se aplica solo a los tipos que la tienen (el relleno no va
        # a un subrayado).
        for name, kinds in (("fill", FILLED), ("border", TEXTUAL), ("width", STROKED), ("font_size", TEXTUAL),
                            ("font", TEXTUAL),
                            ("align", TEXTUAL), ("dashed", DASHABLE), ("icon", ("note",))):
            if kind not in kinds:
                changes.pop(name, None)
        if self.categories is not None:  # (each ticked category in, each unticked out; half-ticked as it is)
            chosen = list(annotation.categories)
            for i in range(self.categories.count()):
                item = self.categories.item(i)
                if item.checkState() == Qt.CheckState.Checked and item.text() not in chosen:
                    chosen.append(item.text())
                elif item.checkState() == Qt.CheckState.Unchecked and item.text() in chosen:
                    chosen.remove(item.text())
            changes["categories"] = tuple(chosen)
        return dataclasses.replace(annotation, **changes)

    def style(self) -> settings.Style:
        """The tool's style, as the dialog leaves it."""
        changes = self.changes()
        # Only the style fields go to the tool; contents, author and the like belong to annotations.
        fields = {k: v for k, v in changes.items() if k in settings.STYLE_FIELDS}
        style = dataclasses.replace(self.tool, **fields, sticky=self.sticky.isChecked(),
                                    show=self.show_after.currentData() or "")
        if self.stamp is not None:
            style = dataclasses.replace(style, stamp=self.stamp.currentData())
        return style
