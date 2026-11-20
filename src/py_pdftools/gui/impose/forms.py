"""Option forms generated from each command's argparse definition.

Generating the widgets from the same parser the CLI uses keeps the GUI and
the command line in step: every option of every command appears, with the
same names, defaults and help.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ...impose.common import COMMANDS
from ...core.interface import N_, tr
from ...impose.runner import build_parser, translate_paragraphs

# Options handled elsewhere in the window (input/output files, global preferences).
SKIP = {"help", "output", "units", "registration", "bleed", "pdfx", "quiet", "version", "interface",
        "conform"}
# Estas opciones globales no tienen campo en los formularios: las pone la barra del espacio de trabajo en cada comando.
PREFERENCE_DESTS = {"units", "registration", "bleed", "pdfx"}

# Por el nombre (dest) de la opción se decide qué campo usar: abrir un archivo, elegir una carpeta o guardar uno.
FILE_DESTS = {"file", "evens", "background", "layout", "fields", "data", "sequence", "example"}
DIR_DESTS = {"out_dir", "folder", "out", "done", "errors"}
SAVE_DESTS = {"export"}
def file_filter(kind: str) -> str:
    """The file-dialog filter for KIND (pdf, toml, data), in the language in use."""
    every = tr("All files (*)")
    if kind == "data":
        return tr("Data files (*.csv *.tsv *.txt)") + ";;" + every
    if kind == "toml":
        return tr("TOML files (*.toml)") + ";;" + every
    return tr("PDF files (*.pdf)") + ";;" + every


# Qué filtro ofrece el diálogo de cada opción de archivo; las demás abren PDF.
FILTERS = {"data": "data", "layout": "toml", "fields": "toml", "sequence": "toml", "export": "toml"}

# argparse's group titles (translated by argparse or by the commands) -> what the form shows
GROUP_TITLES = {"positional arguments": N_("Files"), "options": N_("Options"), "marks": N_("Marks"),
                "background": N_("Background")}


# What to show in an empty field, by the option's metavar: an example of what
# it takes (the metavar itself, LEN or RANGE, means little to a user).
EXAMPLES = {
    "LEN": N_("e.g. 5mm or 1.5cm"),
    "RANGE": N_("e.g. 1-4,7 or LAST"),
    "PAGE": N_("e.g. 3 or LAST-1"),
    "N": N_("a number"), "K": N_("a number"), "A": N_("a number"), "B": N_("a number"),
    "SIZE": N_("e.g. a4 or 21x29.7cm"),
    "WxH": N_("e.g. 4x3cm"),
    "COND": N_("e.g. multiple:4, odd or ge:8"),
    "LIST": N_("e.g. 0 40"),
    "PDF": N_("a PDF file"),
    "EDGE=LEN": N_("e.g. left=1cm"),
    "DIR=LEN": N_("e.g. right=3mm"),
    "DIR=FIRST:LAST": N_("e.g. right=0:3mm"),
    "COLSxROWS": N_("e.g. 2x1"),
    "WIDTHS/HEIGHTS": N_("e.g. 4in 4.5in / 4in 3in"),
    "PARTS": N_("e.g. 1..4 9..12; 5..8"),
    "N=STEPS": N_("e.g. 2=nup --cols 2 --rows 2"),
    "N=FILE": N_("e.g. 2=part2.toml"),
    "X,Y,W,H": N_("e.g. 0,0,3cm,2cm"),
}
SIDES = ("top", "bottom", "left", "right")


def example_for(action: argparse.Action) -> str:
    text = EXAMPLES.get(str(action.metavar or ""))
    return tr(text) if text else ""


def subparsers() -> dict[str, argparse.ArgumentParser]:
    parser = build_parser()
    # argparse no da una forma pública de llegar a los subcomandos; se buscan entre las acciones privadas del parser.
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def clean_help(text: str | None) -> str:
    # Las ayudas son cadenas de formato de argparse, donde un signo de porcentaje literal va doble.
    return (text or "").replace("%%", "%")


def long_option(action: argparse.Action) -> str | None:
    longs = [o for o in action.option_strings if o.startswith("--")]
    # The long form is preferred for the label and the command line; positionals have no option string at all.
    return longs[0] if longs else (action.option_strings[0] if action.option_strings else None)


def pretty(dest: str) -> str:
    return dest.replace("_", " ").capitalize()


# =========================================================================== fields


class Field(QWidget):
    """One option. Subclasses implement value get/set and token output."""

    changed = Signal()

    def __init__(self, action: argparse.Action, parent=None):
        super().__init__(parent)
        self.action = action
        self.option = long_option(action)
        self.dest = action.dest
        self.setToolTip(clean_help(action.help))

    # interface
    def tokens(self) -> list[str]:
        raise NotImplementedError

    def set_value(self, value) -> None:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError

    def has_value(self) -> bool:
        return bool(self.tokens())

    @property
    def positional(self) -> bool:
        return not self.action.option_strings


class FlagField(Field):
    """A checkbox named after the option; its help is shown beside it (wrapped)."""

    def __init__(self, action, parent=None):
        super().__init__(action, parent)
        # The checkbox is not put in this widget's layout: CommandForm places it as the row's label,
        # with the help beside it.
        self.box = QCheckBox((long_option(action) or action.dest).lstrip("-"))
        self.box.setToolTip(self.toolTip())
        self.help = QLabel(clean_help(action.help))
        self.help.setWordWrap(True)
        self.help.setToolTip(self.toolTip())
        self.help.setStyleSheet("color: palette(placeholder-text);")
        self.help.setMinimumWidth(120)
        # Un clic en el texto de ayuda también marca o desmarca la casilla, como haría una etiqueta asociada.
        self.help.mousePressEvent = lambda _e: self.box.toggle()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.help)
        self.reset()  # (an on/off option starts at its default, which may be on)
        self.box.toggled.connect(lambda _: self.changed.emit())

    @property
    def on_off(self) -> bool:
        """An option with a --no- form (argparse.BooleanOptionalAction), usually on by default."""
        return isinstance(self.action, argparse.BooleanOptionalAction)

    def tokens(self):
        checked = self.box.isChecked()
        # Una opción con forma --no- solo se escribe si difiere de su valor por defecto, en la forma que corresponda.
        if self.on_off:
            if checked == bool(self.action.default):
                return []
            return [self.option] if checked else ["--no-" + self.option[2:]]
        return [self.option] if checked else []

    def set_value(self, value):
        self.box.setChecked(bool(value))

    def reset(self):
        self.box.setChecked(bool(self.action.default) if self.on_off else False)


class ChoiceField(Field):
    def __init__(self, action, parent=None):
        super().__init__(action, parent)
        self.combo = QComboBox(self)
        if action.default is None:
            # Sin valor por defecto, la primera entrada vacía permite no pasar la opción.
            self.combo.addItem("")  # not set
        for c in action.choices:
            self.combo.addItem(str(c))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.combo)
        self.combo.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.reset()

    def tokens(self):
        v = self.combo.currentText()
        # El valor por defecto no se escribe: solo alargaría la línea de comandos.
        if v == "" or (self.action.default is not None and v == str(self.action.default)):
            return []
        return [self.option, v] if self.option else [v]

    def set_value(self, value):
        i = self.combo.findText(str(value))
        if i >= 0:
            self.combo.setCurrentIndex(i)

    def reset(self):
        if self.action.default is not None:
            self.set_value(self.action.default)
        else:
            self.combo.setCurrentIndex(0)


class SpinField(Field):
    def __init__(self, action, parent=None):
        super().__init__(action, parent)
        # Las opciones enteras usan un QSpinBox; las demás, un QDoubleSpinBox con tres decimales.
        is_int = action.type is int
        self.spin = QSpinBox(self) if is_int else QDoubleSpinBox(self)
        if is_int:
            self.spin.setRange(-1_000_000, 1_000_000)
        else:
            self.spin.setRange(-1e6, 1e6)
            self.spin.setDecimals(3)
        self.spin.setAccelerated(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.spin)
        lay.addStretch(1)
        self.spin.valueChanged.connect(lambda _: self.changed.emit())
        self.reset()

    def _fmt(self, v):
        return str(int(v)) if self.action.type is int else f"{v:g}"

    def tokens(self):
        v = self.spin.value()
        # A float default with more than three decimals is rounded by the spin box, so it no longer equals the
        # default and is written to the command line anyway.
        if v == self.action.default:
            return []
        return [self.option, self._fmt(v)]

    def set_value(self, value):
        self.spin.setValue(self.action.type(value))

    def reset(self):
        self.spin.setValue(self.action.default)


class TextField(Field):
    """Free text (lengths, page ranges, rules...), and optional numbers without a default."""

    def __init__(self, action, parent=None):
        super().__init__(action, parent)
        self.edit = QLineEdit(self)
        # SUPPRESS significa que la opción no tiene valor por defecto que mostrar; entonces se da un ejemplo.
        if action.default not in (None, argparse.SUPPRESS):
            self.edit.setPlaceholderText(tr('default: {default}', default=action.default))
        else:
            self.edit.setPlaceholderText(example_for(action))
        if action.type is int:
            self.edit.setValidator(QIntValidator(self.edit))
        self.edit.setToolTip(self.toolTip())
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.addWidget(self.edit, 1)
        self.edit.textChanged.connect(lambda _: self.changed.emit())

    def text(self) -> str:
        return self.edit.text().strip()

    def tokens(self):
        t = self.text()
        if not t or (self.action.default is not None and t == str(self.action.default)):
            return []
        if self.option and t.startswith("-"):  # (a negative length: joined, so it isn't taken for an option)
            return [f"{self.option}={t}"]
        return [self.option, t] if self.option else [t]

    def set_value(self, value):
        self.edit.setText("" if value is None else str(value))

    def reset(self):
        self.edit.clear()


class PathField(TextField):
    def __init__(self, action, parent=None, mode: str = "open"):
        super().__init__(action, parent)
        self.mode = mode
        btn = QPushButton(tr("Browse…"), self)
        btn.clicked.connect(self.browse)
        self.lay.addWidget(btn)

    def browse(self):
        # El diálogo arranca en la ruta ya escrita, si la hay, o en la carpeta personal.
        start = self.text() or str(Path.home())
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, pretty(self.dest), start)
        elif self.mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, pretty(self.dest), start,
                                                  file_filter(FILTERS.get(self.dest, "pdf")))
        else:
            path, _ = QFileDialog.getOpenFileName(self, pretty(self.dest), start,
                                                  file_filter(FILTERS.get(self.dest, "pdf")))
        if path:
            self.edit.setText(path)


class ListField(Field):
    """Repeatable options (one value per line) and multi-file positionals."""

    def __init__(self, action, parent=None, files: bool = False):
        super().__init__(action, parent)
        self.edit = QPlainTextEdit(self)
        example = example_for(action)
        self.edit.setPlaceholderText(tr("one per line, {example}", example=example) if example
                                     else tr("one per line"))
        self.edit.setFixedHeight(70)
        self.edit.setToolTip(self.toolTip())
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit, 1)
        if files:
            btn = QPushButton(tr("Add…"), self)
            btn.clicked.connect(self.add_files)
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
        self.edit.textChanged.connect(self.changed.emit)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, pretty(self.dest), str(Path.home()), file_filter("pdf"))
        for p in paths:
            self.edit.appendPlainText(p)

    def values(self) -> list[str]:
        return [ln.strip() for ln in self.edit.toPlainText().splitlines() if ln.strip()]

    def tokens(self):
        out = []
        # Una opción repetible se escribe una vez por valor: --opt a --opt b.
        for v in self.values():
            out += [self.option, v] if self.option else [v]
        return out

    def set_value(self, value):
        # set_value appends, so that a repeated option read from a command line accumulates its values;
        # reset() clears the field first.
        vals = value if isinstance(value, list) else [value]
        current = self.values()
        self.edit.setPlainText("\n".join(current + [str(v) for v in vals]))

    def reset(self):
        self.edit.clear()


def make_field(action: argparse.Action) -> Field:
    # El orden importa: los tipos más específicos (banderas, listas, opciones con valores fijos) se revisan antes
    # que los genéricos de archivo, número y texto.
    if isinstance(action, (argparse._StoreTrueAction, argparse.BooleanOptionalAction)):
        return FlagField(action)
    if isinstance(action, argparse._AppendAction):
        return ListField(action)
    if action.nargs in ("+", "*"):
        return ListField(action, files=action.type is Path)
    if action.choices:
        return ChoiceField(action)
    if action.dest in DIR_DESTS:
        return PathField(action, mode="dir")
    if action.dest in SAVE_DESTS:
        return PathField(action, mode="save")
    if action.type is Path or action.dest in FILE_DESTS:
        return PathField(action, mode="open")
    # Los números sin valor por defecto van a un TextField, porque un QSpinBox no puede quedar vacío.
    if action.type in (int, float) and action.default is not None:
        return SpinField(action)
    return TextField(action)


# =========================================================================== command form


class CommandForm(QWidget):
    """All options of one command, grouped as in ``--help``."""

    changed = Signal()

    def __init__(self, name: str, parser: argparse.ArgumentParser, parent=None):
        super().__init__(parent)
        self.name = name
        self.command = COMMANDS[name]
        self.parser = parser
        self.fields: list[Field] = []
        self.by_option: dict[str, Field] = {}
        self.extra: list[str] = []  # tokens loaded from a step that the form has no field for
        self._exclusive: list[list[Field]] = []
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        text = translate_paragraphs(self.command.description or self.command.help)
        # Only the first paragraph of the description is shown; the rest (examples, details) goes into a "Reference"
        # box, closed at first.
        desc = QLabel(clean_help(text).split("\n\n")[0])
        desc.setWordWrap(True)
        desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(desc)
        long_help = text.split("\n\n", 1)
        if len(long_help) > 1:
            ex = QLabel(f"<pre>{_escape(long_help[1])}</pre>")
            ex.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box = QGroupBox(tr("Reference"))
            box.setCheckable(True)
            box.setChecked(False)
            bl = QVBoxLayout(box)
            bl.addWidget(ex)
            ex.setVisible(False)
            box.toggled.connect(ex.setVisible)
            outer.addWidget(box)

        by_action = {}
        # Un grupo por cada grupo de argparse, con los mismos títulos que --help (traducidos).
        for group in parser._action_groups:
            actions = [a for a in group._group_actions if self._wanted(a)]
            if not actions:
                continue
            # argparse may have translated its own group titles already, so they are matched in their translated form.
            titles = {tr(k): tr(v) for k, v in GROUP_TITLES.items()}
            box = QGroupBox(titles.get(group.title, (group.title or "").capitalize()))
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for action in actions:
                field = make_field(action)
                self.fields.append(field)
                by_action[action] = field
                for opt in action.option_strings:
                    self.by_option[opt] = field
                # Argumento por defecto: cada lambda guarda su propio campo, no el último del bucle.
                field.changed.connect(lambda f=field: self._field_changed(f))
                if isinstance(field, FlagField):
                    form.addRow(field.box, field)
                else:
                    label = (long_option(action) or action.dest).lstrip("-")
                    # Las opciones obligatorias y los argumentos posicionales sin "?" ni "*" se marcan en negrita
                    # con asterisco.
                    if action.required or (field.positional and action.nargs not in ("?", "*")):
                        label = f"<b>{label}</b> *"
                    lab = QLabel(label)
                    lab.setToolTip(field.toolTip())
                    form.addRow(lab, field)
            outer.addWidget(box)
        # Exclusive groups of argparse are kept so that choosing one option clears the others (see _field_changed).
        for grp in parser._mutually_exclusive_groups:
            members = [by_action[a] for a in grp._group_actions if a in by_action]
            if len(members) > 1:
                self._exclusive.append(members)
        # --margin-top and the like: empty means "the same as --margin"
        by_dest = {f.dest: f for f in self.fields}
        for f in self.fields:
            # Un campo como margin_top cuyo campo base (margin) existe muestra "igual que --margin" cuando está vacío.
            base, _, side = f.dest.rpartition("_")
            if side in SIDES and base in by_dest and isinstance(f, TextField):
                f.edit.setPlaceholderText(tr("same as {option}", option=by_dest[base].option))
        outer.addStretch(1)

    def _wanted(self, action: argparse.Action) -> bool:
        if action.dest in SKIP:
            return False
        if action.dest == "input" and (self.command.needs_input in (True, "optional") or self.name == "replay"):
            # replay también recibe el documento abierto, aunque no lo declare como entrada.
            return False  # the window supplies the current document
        return True

    def _field_changed(self, field: Field):
        if self._loading:
            return
        # mutually exclusive options: setting one clears the others
        for members in self._exclusive:
            if field in members and field.has_value():
                for other in members:
                    if other is not field and other.has_value():
                        # _loading evita que el reinicio del otro campo vuelva a entrar aquí.
                        self._loading = True
                        other.reset()
                        self._loading = False
        self.changed.emit()

    # ----------------------------------------------------------------- tokens

    def tokens(self) -> list[str]:
        """The command line for this form (command name, options, positionals)."""
        opts, pos = [], []
        for f in self.fields:
            # Las opciones van antes que los posicionales; las opciones sin campo (extra) se conservan
            # entre unas y otros.
            (pos if f.positional else opts).extend(f.tokens())
        return [self.name] + opts + self.extra + pos

    def missing_required(self) -> list[str]:
        out = []
        for f in self.fields:
            a = f.action
            needed = a.required or (f.positional and a.nargs not in ("?", "*"))
            if needed and not f.has_value():
                out.append((long_option(a) or a.dest).lstrip("-"))
        for members in self._exclusive:
            # Un grupo exclusivo obligatorio se cumple con cualquiera de sus opciones;
            # si falta, se informa como "a / b".
            grp_required = any(g.required for g in self.parser._mutually_exclusive_groups
                               if any(m.action in g._group_actions for m in members))
            if grp_required and not any(m.has_value() for m in members):
                out.append(" / ".join((long_option(m.action) or m.dest).lstrip("-") for m in members))
        return out

    def reset(self):
        self._loading = True
        for f in self.fields:
            f.reset()
        self.extra = []
        self._loading = False
        self.changed.emit()

    def set_tokens(self, tokens: list[str]):
        """Fill the form from a command line (as stored in sequences and histories)."""
        if tokens and tokens[0] == self.name:
            tokens = tokens[1:]
        self._loading = True
        for f in self.fields:
            f.reset()
        self.extra = []
        positionals = [f for f in self.fields if f.positional]
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            # --opt=value se separa en opción y valor; otras fichas se buscan tal cual.
            opt, eq, inline = tok.partition("=") if tok.startswith("--") else (tok, "", "")
            field = self.by_option.get(opt)
            if field is not None:
                if isinstance(field, FlagField):
                    # Both --x and --no-x of an on/off option are keys of by_option and lead to the same field.
                    field.set_value(not opt.startswith("--no-"))
                else:
                    if eq:
                        value = inline
                    else:
                        i += 1
                        value = tokens[i] if i < len(tokens) else ""
                    # Una opción al final sin valor recibe una cadena vacía, en vez de fallar.
                    field.set_value(value)
            elif tok.startswith("-"):
                # The parser tells whether the unknown option takes a value, so that the value is kept with it.
                # an option without a field (preferences): keep it with its value
                self.extra.append(tok)
                action = self.parser._option_string_actions.get(opt)
                if action is not None and action.nargs != 0 and not eq and i + 1 < len(tokens):
                    i += 1
                    self.extra.append(tokens[i])
            elif positionals:
                # Positionals are filled in order; a list positional takes every value that remains.
                target = positionals[0]
                target.set_value(tok)
                if not isinstance(target, ListField):
                    positionals.pop(0)
            i += 1
        self._loading = False
        self.changed.emit()


def _escape(s: str) -> str:
    # Para mostrar texto de ayuda dentro de <pre>: QLabel lo interpreta como texto enriquecido.
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
