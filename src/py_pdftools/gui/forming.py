"""Filling forms (mixed into MainWindow): the panel Form (View > Form fields, F6) has an editor for each field
of the document (a text, a check box, a choice of radio buttons, a list), in the order of the form, so that
Tab goes from one to the next; on the page, a click on a check box or a radio button sets it, and one on
another field takes the panel to it. Each value written is a step of the history (see
working.edit_document); Edit > Undo takes it back. The panel opens by itself with a document that has
fields."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDockWidget, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core.interface import ntr, tr
from ..forms import fields
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
        self.form_buttons = QHBoxLayout()
        self.form_buttons.addWidget(self.b_form_reset)
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
        self.b_form_reset.setEnabled(bool(filled))
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
        can't be written (the value refused)."""
        return {name: value}, {}

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
        done = self.edit_document(lambda doc: fields.fill(doc, values), message=message)
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
