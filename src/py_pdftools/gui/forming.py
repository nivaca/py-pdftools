"""Filling forms (mixed into MainWindow): the panel Form (View > Form fields, F6) has an editor for each field
of the document (a text, a check box, a choice of radio buttons, a list), in the order of the form, so that
Tab goes from one to the next; what is typed is checked, shown and summed as the form says (numbers, dates,
sums: see forms/formats.py); on the page, a click on a check box or a radio button sets it, and one on
another field takes the panel to it. Each value written is a step of the history (see
working.edit_document); Edit > Undo takes it back. The panel opens by itself with a document that has
fields."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDockWidget, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core.interface import ntr, tr
from ..forms import fields, formats
from ..forms.fields import OFF, Field


class PlainEdit(QPlainTextEdit):
    """A text of several lines, which says when it is left (as QLineEdit does), and lets Tab go on."""

    def __init__(self, done):
        super().__init__()
        self.done = done
        self.setTabChangesFocus(True)
        self.setFixedHeight(64)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.done()


class FormMixin:
    """(Mixed into MainWindow: it uses its document, its canvas and edit_document.)"""

    def _build_form(self):
        self.form_fields: list[Field] = []
        self._form_order: list[str] = []  # (el orden de cálculo del formulario)
        self._form_editors: dict[str, QWidget] = {}
        self._form_shown_for = None  # (el documento para el que el panel se abrió solo, una vez)
        self.form_head = QLabel()
        self.form_head.setWordWrap(True)
        self.form_layout = QFormLayout()
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.addLayout(self.form_layout)
        column.addStretch(1)  # (las filas arriba, sin estirarse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        self.form_scroll = scroll
        self.b_form_reset = QPushButton(tr("Reset the form"))
        self.b_form_reset.setToolTip(tr("Every field back to its first value (or empty)"))
        self.b_form_reset.clicked.connect(lambda: self.reset_form())
        self.b_form_export = QPushButton(tr("Export…"))
        self.b_form_export.setToolTip(tr("The values of the fields, as JSON, CSV, XFDF or FDF"))
        self.b_form_export.clicked.connect(lambda: self.export_form_dialog())
        self.b_form_import = QPushButton(tr("Import…"))
        self.b_form_import.setToolTip(tr("Fill the form with the values of a file (JSON, CSV, XFDF, FDF)"))
        self.b_form_import.clicked.connect(lambda: self.import_form_dialog())
        self.form_buttons = QHBoxLayout()
        self.form_buttons.addWidget(self.b_form_reset)
        self.form_buttons.addWidget(self.b_form_export)
        self.form_buttons.addWidget(self.b_form_import)
        self.form_buttons.addStretch(1)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.form_head)
        lay.addWidget(scroll, 1)
        lay.addLayout(self.form_buttons)
        self.form_dock = dock = QDockWidget(tr("Form"), self)
        dock.setObjectName("form")
        dock.setWidget(inner)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.hide()
        self.a_form = dock.toggleViewAction()
        self.a_form.setText(tr("Form fields"))
        self.a_form.setShortcut(QKeySequence("F6"))
        self.a_form.setToolTip(tr("The fields of the document's form, to fill them in"))
        self.canvas.field_at = self.field_at
        self.canvas.field_clicked.connect(self.field_clicked)

    # ----------------------------------------------------------------- the panel

    def form_refresh(self):
        """The fields of the document as it is now: the editors made again if the fields are others, else only
        their values (the one being filled keeps the focus)."""
        found = fields.read(self.doc) if self.doc is not None else []
        self._form_order = formats.calculation_order(self.doc) if found else []
        same = [(f.name, f.kind, f.options) for f in found] == \
            [(f.name, f.kind, f.options) for f in self.form_fields] and bool(self._form_editors)
        self.form_fields = found
        if same:
            for f in found:
                self._form_set_editor(f)
        else:
            self._form_fill()
        filled = [f for f in found if f.kind in fields.FILLED]
        self.form_head.setText(ntr("{count} field", "{count} fields", len(filled)) if filled
                               else tr("This document has no form."))
        for b in (self.b_form_reset, self.b_form_export, self.b_form_import):
            b.setEnabled(bool(filled))
        if hasattr(self, "a_flat_form"):
            self.a_flat_form.setEnabled(bool(filled))
        if filled and self.path is not None and self._form_shown_for != self.path:
            self._form_shown_for = self.path
            self.form_dock.show()

    def _form_fill(self):
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)
        self._form_editors = {}
        for f in self.form_fields:
            if f.kind not in fields.FILLED:
                continue
            editor = self._form_editor(f)
            editor.setEnabled(not f.read_only)
            editor.setToolTip(f"{f.title} ({f.name})" if f.label else f.name)
            self._form_editors[f.name] = editor
            label = QLabel(f.title + (" *" if f.required else ""))
            label.setWordWrap(True)
            label.setBuddy(editor)
            self.form_layout.addRow(label, editor)
            self._form_set_editor(f)

    def _form_editor(self, f: Field) -> QWidget:
        name = f.name
        if f.kind == "text" and f.multiline:
            editor = PlainEdit(lambda: self.set_field(name, editor.toPlainText()))
        elif f.kind == "text":
            editor = QLineEdit()
            if f.max_len:
                editor.setMaxLength(f.max_len)
            if f.flags & fields.PASSWORD:
                editor.setEchoMode(QLineEdit.EchoMode.Password)
            editor.editingFinished.connect(lambda: self.set_field(name, editor.text()))
        elif f.kind == "check":
            editor = QCheckBox()
            on = f.states[0] if f.states else "Yes"
            editor.toggled.connect(lambda checked: self.set_field(name, on if checked else OFF))
        elif f.kind == "radio":
            editor = QComboBox()
            editor.addItem(tr("(none)"), OFF)
            for state in f.states:
                editor.addItem(state, state)
            editor.activated.connect(lambda _i: self.set_field(name, editor.currentData()))
        elif f.kind == "list":
            editor = QListWidget()
            editor.addItems(list(f.options))
            editor.setFixedHeight(min(120, 22 * max(2, len(f.options)) + 4))
            editor.currentTextChanged.connect(lambda text: self.set_field(name, text))
        else:  # combo
            editor = QComboBox()
            editor.setEditable(bool(f.flags & fields.EDITABLE_COMBO))
            editor.addItems(list(f.options))
            editor.activated.connect(lambda _i: self.set_field(name, editor.currentText()))
        return editor

    def _form_set_editor(self, f: Field):
        """The editor of F showing its value (without saying so: nothing is written)."""
        editor = self._form_editors.get(f.name)
        if editor is None:
            return
        editor.blockSignals(True)
        try:
            if isinstance(editor, QCheckBox):
                editor.setChecked(f.value != OFF)
            elif isinstance(editor, PlainEdit):
                if editor.toPlainText() != f.value:
                    editor.setPlainText(f.value)
            elif isinstance(editor, QLineEdit):
                if editor.text() != f.value:
                    editor.setText(f.value)
            elif isinstance(editor, QListWidget):
                items = editor.findItems(f.value, Qt.MatchFlag.MatchExactly)
                editor.setCurrentItem(items[0] if items else None)
            elif isinstance(editor, QComboBox):
                index = editor.findData(f.value) if f.kind == "radio" else editor.findText(f.value)
                if index >= 0:
                    editor.setCurrentIndex(index)
                elif editor.isEditable():
                    editor.setEditText(f.value)
        finally:
            editor.blockSignals(False)

    def field(self, name: str) -> Field | None:
        return next((f for f in self.form_fields if f.name == name), None)

    # ----------------------------------------------------------------- writing

    def form_values(self, name: str, value: str) -> tuple[dict[str, str], dict[str, str]] | None:
        """What writing VALUE into the field NAME writes: ({field: value}, {field: text shown}); None if it
        can't be written (the value refused by the field's checks: the reason is said). See forms/formats.py:
        the value as the field keeps it, the fields calculated from it, and how each is shown."""
        f = self.field(name)
        try:
            value = formats.check(f, value) if f is not None and f.kind == "text" else value
        except formats.Refused as e:
            self.status(str(e), error=True)
            return None
        return self._formatted({name: value})

    def _formatted(self, values: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
        """VALUES with the calculations they bring, and the text each of them shows."""
        current = {f.name: f.value for f in self.form_fields} | values
        values = values | formats.calculate(self.form_fields, current, self._form_order)
        shown = {}
        for n, v in values.items():
            f = self.field(n)
            if f is not None and f.kind == "text":
                text = formats.shown(f, v)
                if text != v:
                    shown[n] = text
        return values, shown

    def set_field(self, name: str, value: str) -> bool:
        """VALUE written into the field NAME, as a step of the history (nothing, if it has it already)."""
        f = self.field(name)
        if f is None or f.read_only or f.value == value:
            return False
        chosen = self.form_values(name, value)
        if chosen is None:
            self._form_set_editor(f)  # (valor rechazado: el editor vuelve a mostrar el del campo)
            return False
        values, shown = chosen
        done = self.edit_document(lambda doc: fields.fill(doc, values, shown),
                                  message=tr("{field} filled in", field=f.title))
        if done:
            self.form_refresh()
        return done

    def fill_fields(self, values: dict[str, str], message: str) -> bool:
        """Several VALUES written at once, as one step of the history."""
        values = {n: v for n, v in values.items() if (f := self.field(n)) is not None and f.value != v}
        if not values:
            return False
        values, shown = self._formatted(values)
        done = self.edit_document(lambda doc: fields.fill(doc, values, shown), message=message)
        if done:
            self.form_refresh()
        return done

    def reset_form(self) -> bool:
        return self.fill_fields(fields.reset_values(self.form_fields), tr("The form was reset"))

    # ----------------------------------------------------------------- on the page

    def field_at(self, page: int, x: float, y: float) -> tuple[str, str] | None:
        """(name, state of the button) of the field at (X, Y) of PAGE, as the page is shown; None if none."""
        for f in self.form_fields:
            if f.kind not in fields.FILLED:
                continue
            for w in f.widgets:
                x0, y0, x1, y1 = w.rect
                if w.page == page and x0 <= x <= x1 and y0 <= y <= y1:
                    return f.name, w.state
        return None

    def field_clicked(self, name: str, state: str):
        """A click on the field NAME on the page (on its button STATE): a check box or a radio button is set;
        another field is shown in the panel, ready to be filled."""
        f = self.field(name)
        if f is None or f.read_only:
            return
        if f.kind == "check":
            self.set_field(name, OFF if f.value != OFF else (state or "Yes"))
            return
        if f.kind == "radio":
            self.set_field(name, state)
            return
        self.form_dock.show()
        editor = self._form_editors.get(name)
        if editor is not None:
            self.form_scroll.ensureWidgetVisible(editor)
            editor.setFocus(Qt.FocusReason.MouseFocusReason)
            if isinstance(editor, QLineEdit):
                editor.selectAll()

    # ----------------------------------------------------------------- the data of the form

    def ask_form_file(self, saving: bool) -> Path | None:
        """A file of form data to write (SAVING) or read; None if cancelled."""
        from PySide6.QtWidgets import QFileDialog

        kinds = tr("Form data (*.json *.csv *.xfdf *.fdf)")
        start = str(Path(self.last_dir()) / f"{self.path.stem}.json") if saving else self.last_dir()
        if saving:
            name, _ = QFileDialog.getSaveFileName(self, tr("Export the form"), start, kinds)
        else:
            name, _ = QFileDialog.getOpenFileName(self, tr("Import the form"), start, kinds)
        return Path(name) if name else None

    def export_form_dialog(self) -> bool:
        from ..forms import data

        if not self.form_fields:
            return False
        target = self.ask_form_file(True)
        if target is None:
            return False
        fmt = target.suffix.lower().lstrip(".")
        if fmt not in data.FORMATS:
            fmt, target = "json", target.with_suffix(".json")
        values = {f.name: f.value for f in self.form_fields if f.kind in fields.FILLED}
        buttons = {f.name for f in self.form_fields if f.kind in ("check", "radio")}
        try:
            target.write_text(data.dumps(values, fmt, self.path.name, buttons), encoding="utf-8")
        except OSError as e:
            self.status(str(e), error=True)
            return False
        self.status(tr("Saved {path}", path=target))
        return True

    def import_form_dialog(self, source: Path | None = None) -> bool:
        """The form filled with the values of a file (those of fields it hasn't are left out; those a field
        refuses are said), as one step of the history."""
        from ..forms import data

        source = source or self.ask_form_file(False)
        if source is None:
            return False
        try:
            values = data.load(source)
        except data.DataError as e:
            self.status(str(e), error=True)
            return False
        kept, refused = {}, []
        for name, value in values.items():
            f = self.field(name)
            if f is None or f.kind not in fields.FILLED or f.read_only:
                continue
            try:
                kept[name] = formats.check(f, value) if f.kind == "text" else value
            except formats.Refused:
                refused.append(f.title)
        done = self.fill_fields(kept, ntr("{count} field filled from {file}", "{count} fields filled from {file}",
                                          len(kept), file=source.name))
        if refused:
            self.status(tr("Not filled, as their values don't fit them: {fields}", fields=", ".join(refused)),
                        error=True)
        elif not done:
            self.status(tr("{file} has no values for this form", file=source.name))
        return done

    def save_flat_form_dialog(self) -> bool:
        """File > Save a copy > With the form flattened: the fields become part of the pages."""
        from ..forms import data

        if self.path is None:
            return False
        target = self.ask_new_pdf(tr("Save a copy with the form flattened"), f"{self.path.stem}-flattened.pdf")
        if target is None or self._same_file(target):
            return False
        try:
            # De la copia de trabajo, si la hay: con los campos rellenados aunque no se hayan guardado.
            data.flatten_file(self.file, target, self.password)
        except data.DataError as e:
            self.status(str(e), error=True)
            return False
        self.status(tr("Saved {path}, with the form flattened", path=target))
        return True
