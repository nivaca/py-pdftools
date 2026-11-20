"""The workspace of the mode Impose: py-imposition's window, which lives in the
window of py-pdftools (a QMainWindow inside it, with its own toolbar and docks).

It imposes the document open in py-pdftools, as it is (its annotations and
changes written first, see ImposeMixin.impose_source): each command runs as
``python -m py_pdftools impose COMMAND`` in a process of its own, and its
result is shown on the right. Apply makes the result the document (a step of
the window's history, see working.py); Save writes the result as a new file.
Opening documents, the language and the settings are the window's.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QProcess, QProcessEnvironment, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFileDialog, QHBoxLayout, QMenu,
    QLabel, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSplitter, QStackedWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ...impose.common import COMMANDS
from ...core import config, conform, interface
from ...core.interface import N_, ntr, tr
from .basic import BasicPanel
from .forms import CommandForm, file_filter, subparsers
from .preview import PdfPane


# El árbol de comandos del modo avanzado, por categorías; un comando que no figure aquí va a "Otros".
CATEGORIES = [
    (N_("Impose"), ["impose", "booklet", "nup", "step-repeat", "join", "manual"]),
    (N_("Arrange pages"), ["shuffle", "evenodd", "reverse", "duplicate", "delete", "move", "insert", "split"]),
    (N_("Change pages"), ["trim-shift", "creep", "resize", "rotate", "tile", "bleed"]),
    (N_("Stick on / peel off"), ["text", "stick-pdf", "mask", "peel", "merge-data", "sample"]),
    (N_("Information & automation"), ["info", "run", "replay", "watch"]),
]

TITLES = {
    "impose": N_("Imposition"), "booklet": N_("Create booklet"), "nup": N_("n-Up pages"), "step-repeat": N_("Step and repeat"), "join": N_("Join two pages"),
    "manual": N_("Manual imposition"), "shuffle": N_("Shuffle pages"), "evenodd": N_("Even/odd pages"),
    "reverse": N_("Reverse pages"), "duplicate": N_("Duplicate pages"), "delete": N_("Delete pages"), "move": N_("Move pages"),
    "insert": N_("Insert pages"), "split": N_("Split / merge (partials)"), "trim-shift": N_("Trim and shift"),
    "creep": N_("Creep"), "resize": N_("Adjust page sizes"), "rotate": N_("Rotate pages"), "tile": N_("Tile pages"),
    "bleed": N_("Define bleeds"), "text": N_("Text and numbers"), "stick-pdf": N_("Stick on PDF pages"),
    "mask": N_("Masking tape"), "peel": N_("Peel off"), "merge-data": N_("Variable data merge"),
    "sample": N_("Sample document"), "info": N_("Imposition info"), "run": N_("Run sequence on files"),
    "replay": N_("Replay (imposition by example)"), "watch": N_("Hot folder"),
}

# Estos comandos no dejan un PDF que previsualizar: info muestra un texto; run y watch escriben archivos en otra parte.
NO_PREVIEW = {"info", "run", "watch"}
NOT_IN_WINDOW = {"interface"}  # (the window has Settings ▸ Language of the interface)
def wrote_paths(output: str) -> list[Path]:
    """The files a command says it wrote ("Wrote PATH (N pages)"), in the language in use."""
    # La salida de los comandos está traducida, así que los patrones se arman con las mismas plantillas
    # traducidas: cada {path} y {count} se vuelve un grupo de la expresión regular.
    patterns = []
    for template in (tr("Wrote {path} ({count} page)"), tr("Wrote {path} ({count} pages)"), tr("Wrote {path}")):
        rx = re.escape(template).replace(re.escape("{path}"), "(?P<path>.+?)")
        patterns.append(re.compile("^" + rx.replace(re.escape("{count}"), r"\d+") + "$"))
    found = []
    for line in output.splitlines():
        for rx in patterns:
            m = rx.match(line.strip())
            if m:
                found.append(Path(m.group("path")))
                break
    return found


def warning_prefix() -> str:
    # Only the text before {msg}: the stderr lines that start with it are counted as warnings.
    return tr("warning: {msg}").split("{msg}")[0]




def python_command() -> list[str]:
    """How to start the command line of imposition in a child process."""
    # Se usa el mismo intérprete que corre la ventana, así el proceso hijo ve el mismo entorno y los mismos paquetes.
    return [sys.executable, "-m", "py_pdftools", "impose"]


# =========================================================================== process runner


# Los comandos corren en otro proceso (QProcess) y no en un hilo: un comando largo o que falle no bloquea
# ni tumba la ventana, y Detener puede matarlo sin dejar estado a medias.
class Runner(QObject):
    """Runs one CLI command at a time in a child process."""

    output = Signal(str, bool)  # text, is_error
    finished = Signal(str, int, str, str)  # purpose, exit code, stdout, stderr

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: QProcess | None = None
        self.purpose = ""
        self._out: list[str] = []
        self._err: list[str] = []

    def busy(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def stop(self):
        if self.busy():
            p = self.proc
            # The finished signal is disconnected first, so that a job killed on purpose does not report
            # itself as failed.
            p.finished.disconnect()
            p.kill()
            p.waitForFinished(2000)
            self.proc = None

    def start(self, args: list[str], purpose: str):
        self.stop()
        self.purpose = purpose
        self._out, self._err = [], []
        p = QProcess(self)
        # Without unbuffered output, Python would hold the child's stdout until it ends, and the log would only
        # fill at the end of each command.
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        p.setProcessEnvironment(env)
        cmd = python_command()
        p.setProgram(cmd[0])
        p.setArguments(cmd[1:] + args)
        p.readyReadStandardOutput.connect(self._read_out)
        p.readyReadStandardError.connect(self._read_err)
        p.finished.connect(self._finished)
        self.proc = p
        self.output.emit("$ py-pdftools impose " + shlex.join(args), False)
        p.start()

    def _read_out(self):
        # La salida llega en trozos según se produce; se guarda entera para job_finished y se muestra ya en el registro.
        text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        self._out.append(text)
        self.output.emit(text.rstrip("\n"), False)

    def _read_err(self):
        text = bytes(self.proc.readAllStandardError()).decode(errors="replace")
        self._err.append(text)
        self.output.emit(text.rstrip("\n"), True)

    def _finished(self, code, _status):
        # proc se borra antes de emitir: quien reciba la señal puede lanzar otro comando enseguida.
        self.proc = None
        self.finished.emit(self.purpose, code, "".join(self._out), "".join(self._err))


# =========================================================================== sequence panel


class SequencePanel(QWidget):
    """Build, load, save and run sequences of commands."""

    def __init__(self, window: "Workspace"):
        super().__init__(window)
        self.w = window
        self.list = QListWidget()
        # Los pasos se reordenan arrastrándolos en la lista; cada uno es una línea de comando en sintaxis de shell.
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list.itemDoubleClicked.connect(lambda _: self.edit_selected())
        self.list.setFont(QFont("monospace"))

        def btn(text, tip, slot):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        left = QVBoxLayout()
        for b in (
            btn(tr("Add current"), tr("Add the command and options in the form as a step"), self.add_current),
            btn(tr("Replace"), tr("Replace the selected step with the form"), self.replace_selected),
            btn(tr("Edit"), tr("Load the selected step into the form (or double-click)"), self.edit_selected),
            btn(tr("Remove"), tr("Remove the selected step"), self.remove_selected),
            btn(tr("Clear"), tr("Remove all steps"), self.list.clear),
        ):
            left.addWidget(b)
        left.addStretch(1)
        right = QVBoxLayout()
        for b in (
            btn(tr("From document"), tr("Add the commands recorded in the current document (imposition by example)"),
                self.from_document),
            btn(tr("Load…"), tr("Load a sequence file"), self.load),
            btn(tr("Save…"), tr("Save the steps as a sequence file"), self.save),
            btn(tr("Run on document"), tr("Run all steps on the current document and preview the result"),
                self.run_on_document),
            btn(tr("Run on files…"), tr("Run all steps on several PDF files"), self.run_on_files),
        ):
            right.addWidget(b)
        right.addStretch(1)
        lay = QHBoxLayout(self)
        lay.addLayout(left)
        lay.addWidget(self.list, 1)
        lay.addLayout(right)

    def steps(self) -> list[list[str]]:
        # Cada paso se guarda como una línea con comillas de shell; shlex la vuelve a convertir
        # en la lista de argumentos.
        return [shlex.split(self.list.item(i).text()) for i in range(self.list.count())]

    def set_steps(self, steps: list[list[str]]):
        self.list.clear()
        for s in steps:
            self.list.addItem(shlex.join(s))

    def add_current(self):
        tokens = self.w.current_tokens(check=True)
        if tokens:
            self.list.addItem(shlex.join(tokens))
            self.list.setCurrentRow(self.list.count() - 1)

    def replace_selected(self):
        item = self.list.currentItem()
        tokens = self.w.current_tokens(check=True)
        if item and tokens:
            item.setText(shlex.join(tokens))

    def edit_selected(self):
        item = self.list.currentItem()
        if item:
            tokens = shlex.split(item.text())
            # Un paso de un comando desconocido (de otra versión, o editado a mano) no se carga en el formulario.
            if tokens and tokens[0] in COMMANDS:
                self.w.select_command(tokens[0])
                self.w.form(tokens[0]).set_tokens(tokens)

    def remove_selected(self):
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)

    def from_document(self):
        if not self.w.source:
            self.w.status(tr("Open a PDF first"), error=True)
            return
        # Imported here, as in the rest of the workspace: pikepdf and the engine are loaded only when needed.
        import pikepdf

        from ...impose.pdfutil import get_history
        # Imposition by example: the engine records each command it runs in the PDF it writes, and get_history reads
        # them back.
        with pikepdf.open(self.w.source) as pdf:
            hist = get_history(pdf)
        if not hist:
            self.w.status(tr("The current document has no recorded commands"), error=True)
            return
        for s in hist:
            self.list.addItem(shlex.join(s))
        self.w.status(tr('Added {count} recorded step(s)', count=len(hist)))

    def write_toml(self, path: Path, name: str):
        from ...impose.sequence import write_sequence
        # write_sequence escribe la primera línea (el nombre); las preferencias de la barra se insertan justo después,
        # y solo las que difieren de lo predeterminado, salvo las unidades.
        text = write_sequence(self.steps(), name)
        prefs = self.w.prefs()
        extra = [f'units = "{prefs["units"]}"']
        if prefs["registration"] != "black":
            extra.append(f'registration = "{prefs["registration"]}"')
        if prefs["bleed"] != "use":
            extra.append(f'bleed = "{prefs["bleed"]}"')
        if prefs["pdfx"]:
            extra.append("pdfx = true")
        lines = text.splitlines()
        path.write_text("\n".join(lines[:1] + extra + lines[1:]) + "\n")

    def load(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Load sequence"), self.w.last_dir(),
                                              file_filter("toml"))
        if not path:
            return
        from ...impose.common import ImpositionError
        from ...impose.sequence import load_sequence
        try:
            steps, prefs = load_sequence(Path(path))
        except ImpositionError as e:
            QMessageBox.warning(self, tr("Load sequence"), str(e))
            return
        self.set_steps(steps)
        # A sequence file may carry its own preferences (units, registration...), and they replace those of the toolbar.
        self.w.apply_prefs(prefs)
        self.w.status(tr('Loaded {count} step(s) from {name}', count=len(steps), name=Path(path).name))

    def save(self):
        if not self.list.count():
            self.w.status(tr("The sequence is empty"), error=True)
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("Save sequence"), self.w.last_dir(),
                                              file_filter("toml"))
        if not path:
            return
        p = Path(path)
        if p.suffix != ".toml":
            p = p.with_suffix(".toml")
        self.write_toml(p, p.stem)
        self.w.status(tr('Saved {page}', page=p))

    def _temp_sequence(self) -> Path | None:
        if not self.list.count():
            self.w.status(tr("The sequence is empty"), error=True)
            return None
        # Para correr la secuencia hace falta un archivo; se escribe uno temporal en la carpeta del espacio de trabajo,
        # con un número nuevo cada vez.
        p = self.w.tmp / f"sequence-{self.w.next_id()}.toml"
        self.write_toml(p, "sequence")
        return p

    def run_on_document(self):
        if not self.w.source:
            self.w.status(tr("Open a PDF first"), error=True)
            return
        seq = self._temp_sequence()
        if seq:
            # La clave identifica el resultado: Aplicar y Guardar la comparan para saber si la vista de la derecha
            # corresponde todavía al documento y a la secuencia.
            self.w._pending_key = ("sequence", str(self.w.source))
            self.w.run_tokens(["run", "--sequence", str(seq), str(self.w.source)], purpose="preview",
                              with_input=False, label="sequence")

    def run_on_files(self):
        seq = self._temp_sequence()
        if not seq:
            return
        files, _ = QFileDialog.getOpenFileNames(self, tr("PDF files to process"), self.w.last_dir(),
                                                file_filter("pdf"))
        if not files:
            return
        out = QFileDialog.getExistingDirectory(self, tr("Output folder"), str(Path(files[0]).parent))
        if not out:
            return
        # On several files the results go to the chosen folder; nothing is previewed, and the log reports each file.
        self.w.run_tokens(["run", "--sequence", str(seq), "--out-dir", out, "--suffix", "imposed", *files],
                          purpose="batch", with_input=False, add_output=False)


# =========================================================================== main window


class Workspace(QMainWindow):
    def __init__(self, host):
        """HOST: the window of py-pdftools, whose document this imposes."""
        super().__init__(host)
        self.host = host
        # The workspace is a QMainWindow so that it can have its own toolbars and docks, but this flag makes it
        # an ordinary widget inside the host window.
        self.setWindowFlags(Qt.WindowType.Widget)
        # (the options of the commands and the sequence start at their defaults, as in py-imposition)
        self.carry_options = False
        # Sus ajustes (estado de las barras, modo, comandos) se guardan aparte de los de la ventana principal.
        self.settings = QSettings("py-pdftools", "py-pdftools-impose")
        # Las vistas previas y las secuencias temporales van a una carpeta propia, que close_down borra.
        self._tmpdir = tempfile.TemporaryDirectory(prefix="py-pdftools-impose-")
        self.tmp = Path(self._tmpdir.name)
        self._id = 0
        self.original: Path | None = None
        self.source: Path | None = None
        self.undo_stack: list[Path] = []
        self.result_files: list[Path] = []
        # result_key dice de qué comando, opciones y documento salió el resultado mostrado; _pending_key es la del
        # trabajo en curso, que pasa a result_key cuando termina.
        self.result_key = None
        self._pending_key = None
        # Tras un trabajo puede quedar pendiente aplicar o guardar su resultado: Aplicar y Guardar lanzan el comando
        # si el resultado no está al día, y estas banderas dicen qué hacer al terminar.
        self._apply_after = False
        self._save_after = False
        self._save_standard = ""  # (the kind of PDF the save waiting for a result will write; see conform.py)
        # unsaved work: commands applied, or options changed (and a result made), since the last save
        self._applied_unsaved = False
        self._options_changed = False
        self.parsers = subparsers()
        self.forms: dict[str, CommandForm] = {}
        self.current = ""

        self.runner = Runner(self)
        self.runner.output.connect(self.log)
        self.runner.finished.connect(self.job_finished)
        # La vista previa automática espera 700 ms sin cambios en las opciones, para no lanzar un proceso por tecla.
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self.auto_preview)

        self._build_toolbar()
        self._build_central()
        self._build_docks()
        self._build_menus()
        self._restore()
        self.statusBar().hide()  # (the window's own status bar says what happens)

    # ----------------------------------------------------------------- construction

    def _build_toolbar(self):
        tb = QToolBar(tr("Preferences"))
        tb.setObjectName("prefs")
        self.addToolBar(tb)
        # Basic | Advanced
        self.a_basic = QAction(tr("Basic"), self, checkable=True)
        self.a_basic.setToolTip(tr("Basic mode: one imposition form with the usual options"))
        self.a_advanced = QAction(tr("Advanced"), self, checkable=True)
        self.a_advanced.setToolTip(tr("Advanced mode: every command and option, sequences and the log"))
        modes = QActionGroup(self)
        modes.setExclusive(True)
        for act, mode in ((self.a_basic, "basic"), (self.a_advanced, "advanced")):
            modes.addAction(act)
            tb.addAction(act)
            act.triggered.connect(lambda _=False, m=mode: self.set_mode(m))
        tb.addSeparator()
        self.a_save = QAction(tr("Save…"), self, triggered=self.save)
        self.a_save.setToolTip(tr("Save the result shown on the right (if it isn't up to date, the command runs "
                                  "first)"))
        tb.addAction(self.a_save)
        self.a_undo = QAction(tr("Undo apply"), self, triggered=self.undo)
        tb.addAction(self.a_undo)
        # Units, registration, bleeds and PDF/X apply to every command and are passed as global options
        # (see pref_tokens); the basic mode hides them.
        self._advanced_only = [tb.addSeparator()]
        self._advanced_only.append(tb.addWidget(QLabel(tr(" Units "))))
        self.units = QComboBox()
        self.units.addItems(["cm", "mm", "in", "pt"])
        self._advanced_only.append(tb.addWidget(self.units))
        self._advanced_only.append(tb.addWidget(QLabel(tr("  Registration "))))
        self.registration = QComboBox()
        self.registration.addItems(["black", "cmyk", "all"])
        self.registration.setToolTip(tr("Colour of crop marks and registration-coloured text"))
        self._advanced_only.append(tb.addWidget(self.registration))
        self._advanced_only.append(tb.addWidget(QLabel(tr("  Bleeds "))))
        self.bleed = QComboBox()
        self.bleed.addItems(["use", "ignore"])
        self.bleed.setToolTip(tr("Use page bleed boxes when imposing, or impose the visible page only"))
        self._advanced_only.append(tb.addWidget(self.bleed))
        self.pdfx = QCheckBox(tr("PDF/X"))
        self.pdfx.setToolTip(tr("Keep a TrimBox when bleeds are removed (to make a PDF/X-4 file, use File ▸ "
                                "Save as ▸ PDF/X-4)"))
        self._advanced_only.append(tb.addWidget(self.pdfx))
        # Cambiar una de estas opciones cambia la línea de comando, así que también programa una vista previa.
        for w in (self.units, self.registration, self.bleed):
            w.currentIndexChanged.connect(lambda _: self.schedule())
        self.pdfx.toggled.connect(lambda _: self.schedule())

    def _build_central(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(190)
        listed = set()
        for cat, names in CATEGORIES:
            top = QTreeWidgetItem([tr(cat)])
            # Las categorías solo sirven de encabezado: se pueden expandir pero no elegir.
            top.setFlags(Qt.ItemFlag.ItemIsEnabled)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            for n in names:
                # Only the commands that the engine has registered are listed; a name in CATEGORIES without one
                # is skipped.
                if n in COMMANDS:
                    it = QTreeWidgetItem([tr(TITLES.get(n, n))])
                    it.setData(0, Qt.ItemDataRole.UserRole, n)
                    it.setToolTip(0, f"{n}: {tr(COMMANDS[n].help)}")
                    top.addChild(it)
                    listed.add(n)
            self.tree.addTopLevelItem(top)
        # "interface" fija el idioma, que aquí es el de la ventana (menú Ajustes); por eso no se muestra.
        others = sorted(set(COMMANDS) - listed - NOT_IN_WINDOW)
        if others:
            top = QTreeWidgetItem([tr("Other")])
            for n in others:
                it = QTreeWidgetItem([n])
                it.setData(0, Qt.ItemDataRole.UserRole, n)
                top.addChild(it)
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self._tree_changed)

        # centre: title, form, actions
        self.cmd_title = QLabel()
        self.cmd_title.setStyleSheet("font-size: 15pt; font-weight: bold;")
        self.cmd_line = QLabel()
        self.cmd_line.setWordWrap(True)
        self.cmd_line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # (the theme's own text colour: readable in light and dark themes)
        self.cmd_line.setStyleSheet("font-family: monospace;")
        self.stack = QStackedWidget()
        # The stack holds the basic panel and, as they are first used, one form for each command (see form()).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.stack)
        self.basic = BasicPanel(self)
        self.stack.addWidget(self.basic)
        self.basic.changed.connect(self._form_changed)
        # El modo se fija aquí en "avanzado" solo como punto de partida: _restore pone luego el que estaba guardado.
        self.mode = "advanced"
        self._adv_command = "booklet"
        # _docks_shown remembers which docks were visible in advanced mode, since the basic mode hides them all.
        self._docks_shown = [True, True]

        self.b_preview = QPushButton(tr("Preview"))
        self.b_preview.setToolTip(tr("Run the command on the current document and show the result (F5)"))
        self.b_preview.clicked.connect(self.preview)
        self.b_apply = QPushButton(tr("Apply"))
        self.b_apply.setToolTip(tr("Make the result the current document, to continue with another command "
                                "(Ctrl+Enter)"))
        self.b_apply.clicked.connect(self.apply)
        self.b_save_result = QPushButton(tr("Save…"))
        self.b_save_result.setToolTip(self.a_save.toolTip())
        self.b_save_result.clicked.connect(self.save)
        self.b_reset = QPushButton(tr("Defaults"))
        self.b_reset.setToolTip(tr("Reset this command's options"))
        self.b_reset.clicked.connect(lambda: self.form(self.current).reset())
        self.b_add = QPushButton(tr("Add to sequence"))
        self.b_add.clicked.connect(lambda: self.seq.add_current())
        self.auto = QCheckBox(tr("Auto preview"))
        self.auto.setChecked(True)
        self.auto.setToolTip(tr("Preview automatically after changing options"))
        self.b_stop = QPushButton(tr("Stop"))
        self.b_stop.clicked.connect(self.stop)
        self.b_stop.setEnabled(False)

        actions = QVBoxLayout()
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for b in (self.b_preview, self.b_apply, self.b_save_result):
            row1.addWidget(b)
        row1.addStretch(1)
        row1.addWidget(self.b_stop)
        for b in (self.b_add, self.b_reset):
            row2.addWidget(b)
        row2.addStretch(1)
        row2.addWidget(self.auto)
        actions.addLayout(row1)
        actions.addLayout(row2)

        middle = QWidget()
        ml = QVBoxLayout(middle)
        ml.addWidget(self.cmd_title)
        ml.addWidget(self.cmd_line)
        ml.addWidget(scroll, 1)
        ml.addLayout(actions)

        # previews
        # Two panes: the document as it is now, and the result of the last command (with a list of outputs
        # when it made several files).
        self.src_pane = PdfPane(tr("Document"))
        self.res_pane = PdfPane(tr("Result"))
        self.res_pane.output_selected.connect(self._show_output)
        previews = QSplitter(Qt.Orientation.Horizontal)
        previews.addWidget(self.src_pane)
        previews.addWidget(self.res_pane)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.addWidget(self.tree)
        self.split.addWidget(middle)
        self.split.addWidget(previews)
        self.split.setStretchFactor(1, 2)
        self.split.setStretchFactor(2, 5)
        self.split.setSizes([210, 520, 900])
        self.setCentralWidget(self.split)

    def _build_docks(self):
        self.seq = SequencePanel(self)
        d1 = QDockWidget(tr("Sequence"), self)
        d1.setObjectName("sequence")
        d1.setWidget(self.seq)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, d1)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setFont(QFont("monospace"))
        self.logbox.setMaximumBlockCount(5000)
        d2 = QDockWidget(tr("Log"), self)
        d2.setObjectName("log")
        d2.setWidget(self.logbox)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, d2)
        # Secuencia y registro comparten lugar, como pestañas; primero se muestra la secuencia.
        self.tabifyDockWidget(d1, d2)
        d1.raise_()
        self.docks = (d1, d2)

    def _build_menus(self):
        """The menu Impose of the window (see ImposeMixin), in place of py-imposition's menus."""
        # The menu belongs to the host window (it is its parent), which adds it to its menu bar while this mode is on.
        m = QMenu(tr("&Impose"), self.host)
        self.menu = m
        m.setToolTipsVisible(True)
        m.addAction(QAction(tr("Preview"), self, shortcut="F5", triggered=self.preview))
        m.addAction(QAction(tr("Apply"), self, shortcut="Ctrl+Return", triggered=self.apply))
        m.addAction(self.a_undo)
        m.addAction(QAction(tr("Stop"), self, triggered=self.stop))
        m.addSeparator()
        m.addAction(self.a_save)
        self.m_output = m.addMenu(tr("Save as"))
        self.m_output.setToolTipsVisible(True)
        self.output_actions = {}
        # Una entrada "Guardar como" por cada estándar que pdf2iso sabe hacer, más el PDF simple.
        for value, name in [("", N_("PDF"))] + conform.STANDARDS:
            act = QAction(tr(name) + "…", self)
            act.triggered.connect(lambda _=False, v=value: self.save(v))
            self.m_output.addAction(act)
            self.output_actions[value] = act
        self._show_output()
        m.addSeparator()
        m.addAction(QAction(tr("Copy command line"), self, triggered=self.copy_command_line))
        m.addAction(QAction(tr("Command-line help for this command"), self, triggered=self.show_cli_help))
        m.addSeparator()
        self.a_show_document = QAction(tr("Show the original document"), self, checkable=True)
        self.a_show_document.setToolTip(tr("Show the document beside the result (kept in the configuration file)"))
        self.a_show_document.setChecked(bool(config.get("show_document")))
        self.a_show_document.toggled.connect(self.show_document)
        m.addAction(self.a_show_document)
        for d in self.docks:
            m.addAction(d.toggleViewAction())
        self.m_profiles = m.addMenu(tr("&Profiles"))
        self.basic.profiles_changed.connect(self._profiles_menu)
        self._profiles_menu()

    # ----------------------------------------------------------------- settings

    def _restore(self):
        # El estado guardado incluye barras y paneles; la primera vez no hay, y se da al panel de secuencia
        # una altura razonable cuando la ventana ya tiene tamaño.
        state = self.settings.value("state")
        if isinstance(state, QByteArray):
            self.restoreState(state)
        else:
            QTimer.singleShot(0, lambda: self.resizeDocks([self.docks[0]], [190], Qt.Orientation.Vertical))
        self.auto.setChecked(self.settings.value("auto_preview", "true") != "false")
        # carry_options is False here: py-pdftools always starts the commands at their defaults, so this branch
        # is kept only for py-imposition's behaviour.
        if self.carry_options:
            self.apply_prefs({k: self.settings.value(f"prefs/{k}") for k in ("units", "registration", "bleed")
                              if self.settings.value(f"prefs/{k}")})
            self.pdfx.setChecked(self.settings.value("prefs/pdfx", "false") == "true")
            try:
                self.seq.set_steps(json.loads(self.settings.value("sequence", "[]")))
            except (TypeError, ValueError):
                pass
            try:
                self.basic.set_tokens(json.loads(self.settings.value("basic/tokens", "[]")))
            except (TypeError, ValueError):
                pass
        try:
            self._docks_shown = [bool(v) for v in json.loads(self.settings.value("advanced/docks", "[true, true]"))]
        except (TypeError, ValueError):
            self._docks_shown = [True, True]
        last = self.settings.value("command", "booklet") if self.carry_options else "booklet"
        self.select_command(last if last in COMMANDS else "booklet")
        # set_mode va después de select_command, porque el modo básico recuerda el comando avanzado elegido.
        self.set_mode(self.settings.value("mode", "basic"))
        self.show_document(self.a_show_document.isChecked(), save=False)

    def close_down(self):
        """(The window closes.)"""
        self.runner.stop()
        self.save_settings()
        self._tmpdir.cleanup()

    def save_settings(self):
        self.settings.setValue("state", self.saveState())
        for k, v in self.prefs().items():
            # QSettings guarda los booleanos como texto en algunos formatos; se escriben como "true"/"false"
            # para leerlos siempre igual.
            self.settings.setValue(f"prefs/{k}", "true" if v is True else "false" if v is False else v)
        self.settings.setValue("auto_preview", "true" if self.auto.isChecked() else "false")
        self.settings.setValue("mode", self.mode)
        # In basic mode the docks are hidden by the mode itself; what is saved is the visibility the user had chosen.
        docks = self._docks_shown if self.mode == "basic" else [d.isVisible() for d in self.docks]
        self.settings.setValue("advanced/docks", json.dumps(docks))
        self.settings.setValue("command", self._adv_command if self.mode == "basic" else self.current)
        self.settings.setValue("basic/tokens", json.dumps(self.basic.tokens()))
        self.settings.setValue("sequence", json.dumps(self.seq.steps()))
        for name, form in self.forms.items():
            self.settings.setValue(f"forms/{name}", json.dumps(form.tokens()))
        self.settings.sync()

    def last_dir(self) -> str:
        return self.host.last_dir()

    def prefs(self) -> dict:
        return {"units": self.units.currentText(), "registration": self.registration.currentText(),
                "bleed": self.bleed.currentText(), "pdfx": self.pdfx.isChecked()}

    def apply_prefs(self, prefs: dict):
        for key, combo in (("units", self.units), ("registration", self.registration), ("bleed", self.bleed)):
            if key in prefs and combo.findText(str(prefs[key])) >= 0:
                combo.setCurrentText(str(prefs[key]))
        if "pdfx" in prefs:
            self.pdfx.setChecked(bool(prefs["pdfx"]))

    def pref_tokens(self) -> list[str]:
        p = self.prefs()
        # The language of the interface goes to every command, so that its messages (and the "Wrote" lines that
        # wrote_paths reads) come in the same language as the window.
        out = ["--interface", interface.code(), "--units", p["units"]]
        if p["registration"] != "black":
            out += ["--registration", p["registration"]]
        if p["bleed"] != "use":
            out += ["--bleed", p["bleed"]]
        if p["pdfx"]:
            out.append("--pdfx")
        return out

    # ----------------------------------------------------------------- commands and forms

    # ----------------------------------------------------------------- basic / advanced

    def set_mode(self, mode: str):
        """Basic: the one imposition form and the previews. Advanced: everything."""
        mode = "advanced" if mode == "advanced" else "basic"
        (self.a_basic if mode == "basic" else self.a_advanced).setChecked(True)
        basic = mode == "basic"
        # Al pasar al modo básico se recuerda el comando y los paneles del modo avanzado, para volver a ellos.
        if basic and self.mode != "basic":
            self._adv_command = self.current or self._adv_command
            if self.isVisible():  # (at start-up, the saved visibility is used)
                self._docks_shown = [d.isVisible() for d in self.docks]
        self.mode = mode
        self.tree.setVisible(not basic)
        for act in self._advanced_only:
            act.setVisible(not basic)
        self.b_add.setVisible(not basic)
        self.cmd_line.setVisible(not basic)
        for d, shown in zip(self.docks, self._docks_shown):
            d.setVisible(False if basic else shown)
        if basic:
            # El formulario básico tiene sus propias unidades; empieza con las de la barra.
            self.basic.units.setCurrentText(self.units.currentText())
            self.current = "impose"
            self.stack.setCurrentWidget(self.basic)
            self.cmd_title.setText(tr("Imposition"))
            self.b_preview.setText(tr("Preview"))
            self.b_apply.setEnabled(True)
            self.b_save_result.setEnabled(True)
            self._form_changed()
        else:
            self.select_command(self._adv_command if self._adv_command in COMMANDS else "booklet")
            self._activate(self.current)

    def show_document(self, on: bool, save: bool = True):
        """Show or hide the preview of the original document, and keep the choice."""
        self.src_pane.setVisible(on)
        if save and bool(config.get("show_document")) != on:
            try:
                config.set("show_document", on)
            except OSError as e:
                self.status(tr("Could not keep the setting: {error}", error=e), error=True)

    def _profiles_menu(self):
        m = self.m_profiles
        m.clear()
        shown = [n for n, p in sorted(self.basic.profiles().items(), key=lambda kv: kv[0].lower())
                 if p.get("menu")]
        for name in shown:
            m.addAction(QAction(name, self, triggered=lambda _=False, n=name: self._use_profile(n)))
        if not shown:
            act = QAction(tr("(profiles marked “Show on Menu” appear here)"), self)
            act.setEnabled(False)
            m.addAction(act)

    def _use_profile(self, name: str):
        self.set_mode("basic")
        self.basic.load_profile(name)
        self.status(tr("Profile {name}", name=name))

    def form(self, name: str) -> CommandForm:
        # El panel básico tiene la misma interfaz que un CommandForm (tokens, set_tokens, missing_required...),
        # así que el resto del código lo trata como el formulario de "impose".
        if name == "impose" and self.mode == "basic":
            return self.basic  # (it answers like a command form)
        # Los formularios se crean la primera vez que se eligen: son muchos comandos, cada uno con muchas opciones.
        if name not in self.forms:
            f = CommandForm(name, self.parsers[name])
            saved = self.settings.value(f"forms/{name}") if self.carry_options else None
            if saved:
                try:
                    f.set_tokens(json.loads(saved))
                except (TypeError, ValueError):
                    pass
            f.changed.connect(self._form_changed)
            self.forms[name] = f
            self.stack.addWidget(f)
        return self.forms[name]

    def select_command(self, name: str):
        it = self._find_item(name)
        # If the item is already current, setCurrentItem would not emit a signal, so the command is activated directly.
        if it is not None and self.tree.currentItem() is not it:
            self.tree.setCurrentItem(it)
        else:
            self._activate(name)

    def _find_item(self, name):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                if top.child(j).data(0, Qt.ItemDataRole.UserRole) == name:
                    return top.child(j)
        return None

    def _tree_changed(self, item, _prev):
        name = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if name:
            self._activate(name)

    def _activate(self, name: str):
        if self.mode == "basic":
            self._adv_command = name
            return
        self.current = name
        f = self.form(name)
        self.stack.setCurrentWidget(f)
        self.cmd_title.setText(tr(TITLES.get(name, name)))
        previewable = name not in NO_PREVIEW
        # info, run y watch no previsualizan, así que el botón principal dice lo que hacen de verdad.
        self.b_preview.setText(tr({"info": N_("Show info"), "run": N_("Run"),
                                   "watch": N_("Start watching")}.get(name, N_("Preview"))))
        self.b_apply.setEnabled(previewable)
        self.b_save_result.setEnabled(previewable)
        self._form_changed()

    def current_tokens(self, check: bool = False) -> list[str] | None:
        f = self.form(self.current)
        if check:
            missing = f.missing_required()
            if missing:
                self.status("Required: " + ", ".join(missing), error=True)
                return None
        return f.tokens()

    def _form_changed(self, by_user: bool = True, preview: bool = True):
        if not self.current:  # (still being built)
            return
        if by_user:
            self._options_changed = True
        tokens = self.form(self.current).tokens()
        cmd = COMMANDS[self.current]
        shown = list(tokens)
        # The input file is added to the command line shown, but not to the form's tokens: the steps of a sequence
        # must not name a file.
        if cmd.needs_input is True or (cmd.needs_input == "optional" and self.source):
            shown.append(self.source.name if self.source else "INPUT.pdf")
        self.cmd_line.setText("py-pdftools impose " + shlex.join(shown))
        if preview:
            self.schedule()

    def schedule(self):
        if self.auto.isChecked() and self.current not in NO_PREVIEW:
            self.timer.start()

    def auto_preview(self):
        # La vista previa automática se calla si falta algo (opciones obligatorias, documento); no tiene sentido
        # mostrar un error por cada cambio.
        f = self.form(self.current)
        if f.missing_required():
            return
        if COMMANDS[self.current].needs_input is True and not self.source:
            return
        # replay con --export escribe un archivo de secuencia, no un PDF: solo debe correr cuando se pide.
        if self.current == "replay" and f.by_option.get("--export") and f.by_option["--export"].has_value():
            return
        self.preview(quiet=True)

    # ----------------------------------------------------------------- running

    def next_id(self) -> int:
        self._id += 1
        return self._id

    def run_tokens(self, tokens: list[str], purpose: str, with_input: bool = True, add_output: bool = True,
                   label: str | None = None, quiet: bool = False):
        name = tokens[0]
        cmd = COMMANDS[name]
        # Las preferencias globales se ponen justo después del nombre del comando, antes de sus propias opciones.
        args = list(tokens[:1]) + self.pref_tokens() + list(tokens[1:])
        if with_input:
            if cmd.needs_input is True:
                if not self.source:
                    self.status(tr("Open a PDF first (File ▸ Open, or drop a file on the window)"), error=True)
                    return
                args.append(str(self.source))
            elif cmd.needs_input == "optional" and self.source:
                args.append(str(self.source))
            elif name == "replay":
                if not self.source:
                    self.status(tr("Open a PDF first"), error=True)
                    return
                args.append(str(self.source))
        # La salida va a un archivo temporal nuevo cada vez; un comando que escribe varios archivos les añade
        # un sufijo (result-3-a.pdf...), que job_finished busca después.
        self._out_base = None
        # "and" binds tighter than "or": a sequence run on the document also gets an output file, although "run"
        # is excluded in the first part.
        if add_output and name not in ("info", "watch", "run") or (name == "run" and label == "sequence"):
            self._out_base = self.tmp / f"result-{self.next_id()}.pdf"
            args += ["-o", str(self._out_base)]
        self._job_label = label or name
        # La clave del trabajo se fija ahora, porque las opciones pueden cambiar mientras corre.
        self._job_key = self._pending_key
        self.b_stop.setEnabled(True)
        if not quiet:
            self.status(tr('Running {job_label}…', job_label=self._job_label))
        else:
            # Las vistas previas automáticas solo se anuncian en la barra de estado, sin pasar al registro.
            self.host.statusBar().showMessage(tr('Previewing {job_label}…', job_label=self._job_label))
        self.runner.start(args, purpose)

    def key(self):
        # The key of a result: the command's options, the global options and the document. A result is up to date
        # while all three are the same.
        return (tuple(self.form(self.current).tokens()), tuple(self.pref_tokens()), str(self.source))

    def preview(self, quiet: bool = False):
        # Con watch, el mismo botón inicia y detiene la carpeta vigilada.
        if self.current == "watch" and self.runner.busy() and self.runner.purpose == "watch":
            self.stop()
            return
        tokens = self.current_tokens(check=True)
        if not tokens:
            return
        purpose = {"info": "info", "run": "batch", "watch": "watch"}.get(self.current, "preview")
        self._pending_key = self.key()
        self._apply_after = False
        self._save_after = False
        self.run_tokens(tokens, purpose, quiet=quiet)
        if purpose == "watch" and self.runner.busy():
            self.b_preview.setText(tr("Stop watching"))

    def apply(self):
        if self.current in NO_PREVIEW:
            return
        # Un resultado hecho por el panel de secuencia también cuenta como al día para el mismo documento.
        fresh = self.result_key in (self.key(), ("sequence", str(self.source)))
        if self.result_files and fresh and not self.runner.busy():
            self._apply_result()
            return
        tokens = self.current_tokens(check=True)
        if not tokens:
            return
        # Si el resultado no está al día, se lanza el comando y se aplica al terminar (ver job_finished).
        self._pending_key = self.key()
        self._apply_after = True
        self._save_after = False
        self.run_tokens(tokens, "preview")

    def stop(self):
        was = self.runner.purpose
        self.runner.stop()
        self.b_stop.setEnabled(False)
        if was == "watch":
            self.b_preview.setText(tr("Start watching"))
        self.status(tr("Stopped"))

    def job_finished(self, purpose: str, code: int, out: str, err: str):
        self.b_stop.setEnabled(False)
        if purpose == "watch":
            self.b_preview.setText(tr("Start watching"))
        if code != 0:
            # El mensaje de error útil suele ser la última línea de stderr; las anteriores son el rastro.
            lines = [ln for ln in err.strip().splitlines() if ln.strip()]
            msg = lines[-1] if lines else f"failed (exit code {code})"
            self.status(f"{self._job_label}: {msg}", error=True)
            self._apply_after = self._save_after = False
            return
        if purpose == "info":
            self.show_text(tr("Imposition info"), out)
            self.status(tr("Done"))
            return
        if purpose == "batch":
            n = len(wrote_paths(out))
            self.status(tr('Processed: {number} file(s) written', number=n))
            return
        files = []
        # Se busca primero el archivo pedido con -o; si no existe, el comando escribió varios con sufijos;
        # y si tampoco, se leen las líneas "Wrote ..." de su salida.
        if self._out_base is not None:
            if self._out_base.exists():
                files = [self._out_base]
            else:
                files = sorted(self._out_base.parent.glob(self._out_base.stem + "-*.pdf"))
        if not files:
            files = [f for f in wrote_paths(out) if f.suffix == ".pdf"]
        if not files:
            self.status(tr('{job_label}: done (no PDF produced)', job_label=self._job_label))
            return
        self.result_files = files
        self.result_key = self._job_key
        names = [self._suffix(f) or "result" for f in files]
        self.res_pane.set_outputs(names)
        self.res_pane.load(files[0])
        # Los avisos van al registro; aquí solo se cuentan.
        warn = [ln for ln in err.splitlines() if ln.startswith(warning_prefix())]
        self.status(ntr("{label}: done — {count} warning, see Log", "{label}: done — {count} warnings, see Log",
                        len(warn), label=self._job_label) if warn else tr("{label}: done", label=self._job_label),
                    error=False)
        self._update_modified()
        # Aplicar o guardar, si esperaban este resultado.
        if self._apply_after:
            self._apply_after = False
            self._apply_result()
        elif self._save_after:
            self._save_after = False
            self._write_result(self._save_standard)

    def _suffix(self, f: Path) -> str:
        if self._out_base is not None and f.stem.startswith(self._out_base.stem + "-"):
            return f.stem[len(self._out_base.stem) + 1:]
        return ""

    # TODO: this _show_output(index) is shadowed by the _show_output() defined further down (the Save as menu),
    # so choosing another output of the result pane does not switch the file shown; one of them needs a new name.
    def _show_output(self, index: int):
        if 0 <= index < len(self.result_files):
            self.res_pane.load(self.result_files[index])

    def _apply_result(self):
        if len(self.result_files) != 1:
            QMessageBox.information(self, tr("Apply"),
                                    tr("This command produced several documents. Use “Save…” to save them."))
            return
        # adopt_file makes the result a step of the window's history; the window then gives the workspace the new
        # document (set_source), so self.source is already that document here.
        if self.host.adopt_file(self.result_files[0], tr('Applied {current}. The result is now the current '
                                                         'document.', current=self.current)):
            # (the window gave the workspace its new document: the right pane shows it, until the options
            # change again)
            new = self.source
            self._out_base = None
            self.result_files = [new]
            self.result_key = ("document", str(new))
            self.res_pane.set_outputs(["result"])
            self.res_pane.load(new)
            self._options_changed = False

    # ----------------------------------------------------------------- documents

    def set_source(self, path: Path | None, preview: bool = True):
        self.source = path
        self.result_files = []
        self.result_key = None
        self.res_pane.set_outputs([])
        self.res_pane.clear("")
        # TODO: undo_stack and _applied_unsaved come from py-imposition and are never changed here (the window keeps
        # the history now): the note is always empty and is_modified only looks at the options.
        steps = len(self.undo_stack)
        note = ntr("{count} command applied", "{count} commands applied", steps) if steps else ""
        self.src_pane.load(path, note)
        self._form_changed(by_user=False, preview=preview)
        self._update_modified()

    def undo(self):
        """(Undo apply: the window's Undo, as the result applied is a step of its history.)"""
        self.host.undo()

    def _save_target(self, title: str, suggested: str) -> Path | None:
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path(self.last_dir()) / suggested),
                                              tr("PDF files (*.pdf)"))
        if not path:
            return None
        p = Path(path)
        if p.suffix.lower() != ".pdf":
            p = p.with_suffix(".pdf")
        # La carpeta elegida pasa a ser la última de la ventana, la que usan después los demás diálogos de archivo.
        self.host.settings.setValue("last_dir", str(p.parent))
        return p

    def save_document(self, standard: str = "") -> bool:
        """Save the current document as it is: the commands applied so far, not the current one
        (as a plain PDF or, if given, as STANDARD: 'a-2b', 'x-4'...)."""
        if not self.source:
            self.status(tr("Nothing to save"), error=True)
            return False
        stem = self.original.stem if self.original else "document"
        p = self._save_target(tr("Save the document as it is"), f"{stem}-imposed.pdf")
        if not p:
            return False
        # Copiar el documento sobre sí mismo no tiene sentido (shutil lo rechazaría con SameFileError); se avisa antes.
        if p.resolve() == self.source.resolve():
            self.status(tr("That is the file currently open"), error=True)
            return False
        shutil.copyfile(self.source, p)
        self._applied_unsaved = False
        self._update_modified()
        self.status(tr('Saved {page}', page=p) + self.make_standard([p], standard))
        return True

    def _result_is_fresh(self) -> bool:
        src = str(self.source)
        return (bool(self.result_files) and not self.runner.busy()
                and self.result_key in (self.key(), ("sequence", src), ("document", src)))

    def save(self, standard: str = ""):
        """Save what the right pane shows, as a plain PDF or, this once, as STANDARD ('a-2b',
        'x-4'...); if it isn't up to date, run the command first."""
        if not self.source:
            self.status(tr("Open a PDF first (File ▸ Open, or drop a file on the window)"), error=True)
            return
        if self._result_is_fresh():
            self._write_result(standard)
            return
        if self.current in NO_PREVIEW:
            self.status(tr("This command doesn't make a document to save"), error=True)
            return
        tokens = self.current_tokens(check=True)
        if not tokens:
            return
        self._pending_key = self.key()
        self._apply_after = False
        self._save_after = True
        self._save_standard = standard
        self.run_tokens(tokens, "preview")

    def _write_result(self, standard: str = "") -> bool:
        """Ask where, and save the result shown (all its files), or else the current document; as
        plain PDFs or, if given, as STANDARD ('a-2b', 'x-4'...)."""
        if not self.result_files:
            return self.save_document(standard)
        stem = self.original.stem if self.original else "document"
        # Un resultado ya aplicado se ofrece como "-imposed"; uno sin aplicar lleva el nombre del comando.
        applied = self.result_key is not None and self.result_key[0] == "document"
        title = tr("Save") if not standard else tr("Save as {standard}", standard=conform.label(standard))
        p = self._save_target(title, f"{stem}-imposed.pdf" if applied else f"{stem}-{self.current}.pdf")
        if not p:
            return False
        if self.source and p.resolve() == self.source.resolve():
            self.status(tr("That is the file currently open"), error=True)
            return False
        written = []
        # Varios archivos de resultado se guardan con el nombre elegido más el sufijo de cada uno.
        for f in self.result_files:
            suffix = self._suffix(f)
            target = p.with_name(f"{p.stem}-{suffix}.pdf") if suffix and len(self.result_files) > 1 else p
            shutil.copyfile(f, target)
            written.append(target)
        self._applied_unsaved = self._options_changed = False
        self._update_modified()
        self.status(tr('Saved {page}', page=", ".join(t.name for t in written)) + self.make_standard(written,
                                                                                                    standard))
        return True

    # ----------------------------------------------------------------- PDF/A and PDF/X

    def make_standard(self, paths: list[Path], standard: str) -> str:
        """Convert PATHS, just saved as plain PDFs, to STANDARD ('a-2b', 'x-4'...; '' for none)
        with pdf2iso. Returns what to add to the status bar."""
        if not standard:
            return ""
        label = conform.label(standard)
        if not conform.available():
            QMessageBox.warning(self, label, tr("The result was saved as a plain PDF: {command} is not installed "
                                                "(or not where Settings say)", command=conform.COMMAND))
            return ""
        checks = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            # Conversion runs in this process, one file at a time; processEvents lets the status bar show progress.
            for path in paths:
                self.host.statusBar().showMessage(tr("Making {standard} with {command}…", standard=label,
                                                command=conform.COMMAND))
                QApplication.processEvents()
                checks.append(conform.convert(path, path, standard))
        except conform.ConformError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, label, tr("The result was saved as a plain PDF, but it could not be made "
                                                "{standard}:\n\n{error}", standard=label, error=e))
            return ""
        QApplication.restoreOverrideCursor()
        # Las comprobaciones repetidas (iguales para todos los archivos) se muestran una sola vez, en orden.
        check = "; ".join(dict.fromkeys(c for c in checks if c))
        return " — " + label + (f" ({check})" if check else "")

    def _show_output(self):
        """The Save as menu: PDF/A and PDF/X greyed out if pdf2iso isn't there."""
        have = conform.available()
        for value, act in self.output_actions.items():
            if value:
                act.setEnabled(have)
                act.setToolTip("" if have else tr("Needs {command}: install it, or say where it is in Settings",
                                                  command=conform.COMMAND))

    # ----------------------------------------------------------------- unsaved changes

    def is_modified(self) -> bool:
        """Is there work that would be lost: commands applied, or options changed and a result made,
        since the document was opened or saved?"""
        if not self.source:
            return False
        # A result that is just the document applied is not unsaved work: the window's own history and Save cover it.
        made = bool(self.result_files) and not (self.result_key and self.result_key[0] == "document")
        return self._applied_unsaved or (self._options_changed and made)

    def _update_modified(self):
        self.setWindowModified(self.is_modified())

    def ask_unsaved(self) -> QMessageBox.StandardButton:
        box = QMessageBox(QMessageBox.Icon.Warning, tr("Unsaved changes"),
                          tr("The imposed document hasn't been saved. Save it before going on?"),
                          QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                          | QMessageBox.StandardButton.Cancel, self)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        return QMessageBox.StandardButton(box.exec())

    def maybe_discard(self) -> bool:
        """True if it is all right to go on (nothing unsaved, saved now, or discarded)."""
        if not self.is_modified():
            return True
        answer = self.ask_unsaved()
        if answer == QMessageBox.StandardButton.Save:
            # Save in the question saves what the right pane shows (or the document), as the Save button would.
            return self._write_result()
        return answer == QMessageBox.StandardButton.Discard

    # ----------------------------------------------------------------- drag and drop

    # ----------------------------------------------------------------- messages

    def status(self, text: str, error: bool = False):
        # Los errores también van al registro, para que el modo avanzado guarde constancia de ellos.
        self.host.status(text, error=error)
        if error:
            self.log(text, True)

    def log(self, text: str, is_error: bool = False):
        if text:
            self.logbox.appendPlainText(text)

    def show_text(self, title: str, text: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(760, 520)
        box = QPlainTextEdit(text)
        box.setReadOnly(True)
        box.setFont(QFont("monospace"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addWidget(box)
        lay.addWidget(bb)
        dlg.exec()

    def show_cli_help(self):
        self.show_text(tr('py-pdftools impose {current} --help', current=self.current),
                       self.parsers[self.current].format_help())

    def copy_command_line(self):
        QApplication.clipboard().setText(self.cmd_line.text())
        self.status(tr("Command line copied"))
