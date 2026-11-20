"""The properties of the annotations selected (their colours, line, text,
opacity, comment, author, lock), or of a tool: how the annotations it makes
look, and how it behaves."""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt
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
    QVBoxLayout,
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

SAME = object()  # (a property that differs among the annotations: left as each has it)


class ColorButton(QPushButton):
    """A button that shows a colour and lets the user choose another; NONE
    allows 'no colour' ('')."""

    def __init__(self, color, none: bool = False, parent=None, none_text: str = ""):
        super().__init__(parent)
        self.none = none
        self.none_text = none_text  # (what 'no colour' means here, if not that)
        self.color = color
        self.clicked.connect(self._choose)
        self._show()

    def _show(self):
        if self.color is SAME:
            self.setText(tr("(several)"))
            self.setIcon(swatch("#808080"))
        else:
            self.setText(self.none_text if not self.color and self.none_text else color_name(self.color))
            self.setIcon(swatch(self.color))

    def _choose(self):
        menu = QMenu(self)
        for value, name in swatches():
            menu.addAction(swatch(value), name, lambda v=value: self.set_color(v))
        if self.none:
            menu.addAction(swatch(""), self.none_text or tr("No colour"), lambda: self.set_color(""))
        menu.addSeparator()
        menu.addAction(tr("Other colour…"), self._dialog)
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _dialog(self):
        start = QColor(self.color) if isinstance(self.color, str) and self.color else QColor("#000000")
        chosen = QColorDialog.getColor(start, self, tr("Colour"))
        if chosen.isValid():
            self.set_color(chosen.name())

    def set_color(self, color: str):
        self.color = color
        self._show()


def _combo(choices: dict, value) -> QComboBox:
    """A list of CHOICES ({value: name to translate}), with VALUE chosen (none if SAME)."""
    box = QComboBox()
    for key, name in choices.items():
        box.addItem(tr(name), key)
    box.setCurrentIndex(-1 if value is SAME else max(box.findData(value), 0))
    if value is SAME:
        box.setPlaceholderText(tr("(several)"))
    return box


class PropertiesDialog(QDialog):
    """The properties of ANNOTATIONS; or, with TOOL, of the tool that makes
    annotations of their kind (ANNOTATIONS: one, made with its style)."""

    def __init__(self, annotations: list[Annotation], parent=None, tool: settings.Style | None = None,
                 categories: list[str] | None = None):
        super().__init__(parent)
        self.annotations = annotations
        self.tool = tool
        kinds = {a.kind for a in annotations}
        if tool is not None:
            self.setWindowTitle(tr("Properties of the tool ({kind})", kind=tr(NAMES[annotations[0].kind]).lower()))
        elif len(annotations) == 1:
            self.setWindowTitle(tr("Properties of the annotation ({kind})", kind=annotations[0].name().lower()))
        else:
            self.setWindowTitle(ntr("Properties of the annotation", "Properties of the {count} annotations",
                                    len(annotations)))

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
            self.width = self._number(common("width", STROKED), 0 if kinds & set(TEXTUAL) else 0.25, 20, " pt")
            form.addRow(tr("Border width:") if kinds <= set(TEXTUAL) else tr("Line width:"), self.width)
        if kinds & set(DASHABLE):
            self.dashed = self._check(tr("Dashed"), common("dashed", DASHABLE))
            form.addRow("", self.dashed)
        if kinds & (set(ENDED) | {"arrow"}):
            ends = common("ends", ENDED + ("arrow",))
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
        self.opacity.setValue(100 if opacity is SAME else round(opacity * 100))
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
            self.contents = QPlainTextEdit("" if contents is SAME else contents)
            self.contents.setPlaceholderText(tr("(several)") if contents is SAME else "")
            self.contents.setMinimumHeight(110)
            self._contents_given = contents is not SAME
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
            names = list(categories or [])
            for a in annotations:
                names += [c for c in a.categories if c not in names]
            for name in names:
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                have = sum(name in a.categories for a in annotations)
                if 0 < have < len(annotations):
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserTristate)
                    item.setCheckState(Qt.CheckState.PartiallyChecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked if have else Qt.CheckState.Unchecked)
                self.categories.addItem(item)
            self.categories.setMaximumHeight(110)
            form.addRow(tr("Categories:"), self.categories)
            self.locked = self._check(tr("Locked: can't be moved, resized, erased or deleted"), common("locked"))
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
            if len(annotations) == 1:
                lay.addWidget(self._critical_box(annotations[0].critical))
            self.as_default.setToolTip(tr("The colours, the line, the font and the opacity"))
            self.as_default.setVisible(len(kinds) == 1)
            lay.addWidget(self.as_default)
        else:
            behaviour = QGroupBox(tr("Behaviour"))
            form = QFormLayout(behaviour)
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
        """The entry of textual criticism of the annotation: ticked, it has one."""
        self.critical = box = QGroupBox(tr("Textual criticism"))
        box.setCheckable(True)
        box.setChecked(entry is not None)
        entry = entry or Critical("variant")
        form = QFormLayout(box)
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
        self.c_confidence = _combo(CONFIDENCE, entry.confidence)
        form.addRow(tr("Confidence:"), self.c_confidence)
        return box

    def critical_entry(self) -> Critical | None:
        if not self.critical.isChecked():
            return None
        return Critical(self.c_type.currentData() or "variant", confidence=self.c_confidence.currentData() or "",
                        **{k: " ".join(f.text().split()) for k, f in self.c_fields.items()})

    @staticmethod
    def _number(value, low: float, high: float, suffix: str) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(2 if high <= 20 else 1)
        box.setSingleStep(0.5)
        box.setSuffix(suffix)
        if value is SAME:  # (a value below the range, shown as "(several)")
            box.setRange(low - 0.01, high)
            box.setSpecialValueText(tr("(several)"))
            box.setValue(low - 0.01)
        else:
            box.setRange(low, high)
            box.setValue(value)
        return box

    @staticmethod
    def _check(text: str, value) -> QCheckBox:
        box = QCheckBox(text)
        if value is SAME:
            box.setTristate(True)
            box.setCheckState(box.checkState().PartiallyChecked)
        else:
            box.setChecked(bool(value))
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
            if self._contents_given or text:
                out["contents"] = text.strip("\n")
        if self.author is not None and (self.author.text() or len({a.author for a in self.annotations}) == 1):
            out["author"] = " ".join(self.author.text().split())
        if self.critical is not None:
            out["critical"] = self.critical_entry()
        if self.tags is not None and (self._tags_given or self.tags.text().strip()):
            out["tags"] = tuple(t for t in (" ".join(x.split()) for x in self.tags.text().split(",")) if t)
        return out

    def apply(self, annotation: Annotation) -> Annotation:
        changes = dict(self.changes())
        kind = annotation.kind
        start, end = changes.pop("start", None), changes.pop("end", None)
        if (start or end) and (kind in ENDED or kind == "arrow"):
            changes["ends"] = (start or annotation.ends[0], end or annotation.ends[1])
        if annotation.rich and changes.get("contents", annotation.contents) != annotation.contents:
            changes["rich"] = ""  # (its text written here, plain: its formatting would no longer fit it)
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
        fields = {k: v for k, v in changes.items() if k in settings.STYLE_FIELDS}
        style = dataclasses.replace(self.tool, **fields, sticky=self.sticky.isChecked(),
                                    show=self.show_after.currentData() or "")
        if self.stamp is not None:
            style = dataclasses.replace(style, stamp=self.stamp.currentData())
        return style
