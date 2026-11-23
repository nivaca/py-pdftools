"""Herramientas > Aplicar pasos a varios archivos: elegir los archivos, los pasos (marcados, en el orden en que se
arrastren) y sus ajustes, la carpeta y el sufijo de los resultados, y aplicarlos; el trabajo corre en un hilo
aparte (pages/steps.py), con su avance y un botón para detenerlo, y al final se dice qué fue de cada archivo.
Una serie de pasos se guarda con un nombre, para la próxima vez."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ..core.interface import N_, ntr, tr
from ..pages import steps

STEP = Qt.ItemDataRole.UserRole  # (the Step of an item of the list of steps)
LEVEL_NAMES = {"high": N_("Good quality"), "medium": N_("Medium"), "small": N_("Smallest"),
               "lossless": N_("Without touching the pictures")}


class _Signals(QObject):
    """The thread's news, carried to the window's thread."""
    progress = Signal(int, int, str)
    finished = Signal(object)


class StepsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr("Run steps on several files"))
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.signals = _Signals()
        self.signals.progress.connect(self._progress)
        self.signals.finished.connect(self._finished)

        # La serie guardada, por nombre
        self.recipe = QComboBox()
        self.recipe.setAccessibleName(tr("Recipe"))
        self.recipe.activated.connect(lambda _i: self.load_recipe(self.recipe.currentData()))
        b_keep = QPushButton(tr("Save as…"))
        b_keep.setToolTip(tr("Keep these steps, with their settings, under a name"))
        b_keep.clicked.connect(self.keep_recipe)
        self.b_forget = QPushButton(tr("Delete"))
        self.b_forget.setToolTip(tr("Forget the steps kept under this name"))
        self.b_forget.clicked.connect(self.forget_recipe)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Recipe:")))
        top.addWidget(self.recipe, 1)
        top.addWidget(b_keep)
        top.addWidget(self.b_forget)

        # Los archivos
        self.files = QListWidget()
        self.files.setAccessibleName(tr("Files"))
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.files.setAcceptDrops(True)
        self.files.dragEnterEvent = self._drag_enter
        self.files.dragMoveEvent = self._drag_enter
        self.files.dropEvent = self._drop
        b_add = QPushButton(tr("Add…"))
        b_add.clicked.connect(self.add_files)
        b_remove = QPushButton(tr("Remove"))
        b_remove.clicked.connect(lambda: [self.files.takeItem(self.files.row(i)) for i in self.files.selectedItems()])
        files_box = QGroupBox(tr("Files (drop PDFs here)"))
        fl = QVBoxLayout(files_box)
        fl.addWidget(self.files, 1)
        row = QHBoxLayout()
        row.addWidget(b_add)
        row.addWidget(b_remove)
        row.addStretch(1)
        fl.addLayout(row)

        # The steps: ticked ones are done, in the order of the list (dragged to change it)
        self.steps = QListWidget()
        self.steps.setAccessibleName(tr("Steps"))
        self.steps.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.steps.currentItemChanged.connect(lambda item, _old: self._show_settings(item))
        self.settings = QStackedWidget()
        self.editors: dict[str, QWidget] = {}
        self.fields: dict[str, dict[str, QWidget]] = {}
        for kind in steps.KINDS:
            self.editors[kind] = self._editor(kind)
            self.settings.addWidget(self.editors[kind])
        steps_box = QGroupBox(tr("Steps: those ticked, in this order (drag them to change it)"))
        sl = QHBoxLayout(steps_box)
        sl.addWidget(self.steps, 1)
        sl.addWidget(self.settings, 1)

        middle = QHBoxLayout()
        middle.addWidget(files_box, 1)
        middle.addWidget(steps_box, 2)

        # Adónde van los resultados
        self.folder = QLineEdit(str(Path(window.last_dir())))
        b_folder = QPushButton(tr("Choose…"))
        b_folder.clicked.connect(self.choose_folder)
        self.suffix = QLineEdit(tr("-processed"))
        self.suffix.setToolTip(tr("Put after the name of each file written; the originals are never written over"))
        where = QFormLayout()
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(b_folder)
        where.addRow(tr("Save in:"), folder_row)
        where.addRow(tr("Name ending:"), self.suffix)

        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(130)
        self.report.setAccessibleName(tr("What became of each file"))
        self.b_run = QPushButton(tr("Run"))
        self.b_run.setDefault(True)
        self.b_run.clicked.connect(self.start)
        self.b_stop = QPushButton(tr("Stop"))
        self.b_stop.setEnabled(False)
        self.b_stop.clicked.connect(self.stop.set)
        b_close = QPushButton(tr("Close"))
        b_close.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.bar, 1)
        buttons.addWidget(self.b_run)
        buttons.addWidget(self.b_stop)
        buttons.addWidget(b_close)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(middle, 1)
        lay.addLayout(where)
        lay.addLayout(buttons)
        lay.addWidget(self.report)
        self.resize(960, 640)

        self._fill_recipes()
        self.load_steps([])  # (todos los pasos, ninguno marcado)
        if window.path is not None:
            self.add_paths([window.path])

    # ----------------------------------------------------------------- the settings of each step

    def _editor(self, kind: str) -> QWidget:
        """The fields of the settings of a step of KIND."""
        page = QWidget()
        form = QFormLayout(page)
        fields: dict[str, QWidget] = {}
        if kind == "ocr":
            fields["languages"] = QLineEdit()
            fields["languages"].setToolTip(tr("As tesseract names them; several with +: lat+eng"))
            form.addRow(tr("Languages:"), fields["languages"])
            fields["rotate"] = QCheckBox(tr("Turn the pages lying sideways or upside down"))
            form.addRow("", fields["rotate"])
        elif kind == "headfoot":
            for name, label in (("header", tr("Header, center:")), ("footer", tr("Footer, center:"))):
                fields[name] = QLineEdit()
                fields[name].setToolTip(tr("Variables such as $page, $pagelabel, $totalpages, $date, $bates"))
                form.addRow(label, fields[name])
        elif kind == "watermark":
            fields["text"] = QLineEdit()
            form.addRow(tr("Text:"), fields["text"])
            fields["opacity"] = QSpinBox()
            fields["opacity"].setRange(1, 100)
            fields["opacity"].setSuffix(" %")
            form.addRow(tr("Opacity:"), fields["opacity"])
        elif kind == "reduce":
            fields["level"] = QComboBox()
            for level in steps.LEVELS:
                fields["level"].addItem(tr(LEVEL_NAMES[level]), level)
            form.addRow(tr("How much smaller:"), fields["level"])
        elif kind == "pdfa":
            fields["standard"] = QComboBox()
            from ..core import conform

            for standard in steps.STANDARDS:
                fields["standard"].addItem(conform.label(standard), standard)
            form.addRow(tr("Standard:"), fields["standard"])
        for name, widget in fields.items():
            if isinstance(widget, QLineEdit):
                widget.textEdited.connect(lambda text, n=name: self._set(n, text))
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(lambda on, n=name: self._set(n, on))
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(lambda v, n=name: self._set(n, v))
            elif isinstance(widget, QComboBox):
                widget.activated.connect(lambda _i, n=name, w=widget: self._set(n, w.currentData()))
        self.fields[kind] = fields
        return page

    def _set(self, name: str, value):
        item = self.steps.currentItem()
        if item is not None:
            item.data(STEP).settings[name] = value

    def _show_settings(self, item):
        if item is None:
            return
        step = item.data(STEP)
        self.settings.setCurrentWidget(self.editors[step.kind])
        for name, widget in self.fields[step.kind].items():
            value = step.value(name)
            widget.blockSignals(True)
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(value)))
            widget.blockSignals(False)

    # ----------------------------------------------------------------- the list of steps

    def load_steps(self, chosen: list[steps.Step]):
        """The steps CHOSEN ticked, in their order, and the others after them, not ticked."""
        self.steps.clear()
        kinds = [s.kind for s in chosen]
        for step in chosen + [steps.Step(k) for k in steps.KINDS if k not in kinds]:
            item = QListWidgetItem(step.title())
            item.setData(STEP, step)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if step.kind in kinds else Qt.CheckState.Unchecked)
            self.steps.addItem(item)
        self.steps.setCurrentRow(0)

    def chosen_steps(self) -> list[steps.Step]:
        return [self.steps.item(r).data(STEP) for r in range(self.steps.count())
                if self.steps.item(r).checkState() == Qt.CheckState.Checked]

    # ----------------------------------------------------------------- recipes

    def _fill_recipes(self, current: str = ""):
        self.recipe.clear()
        self.recipe.addItem(tr("(none)"), "")
        for name in sorted(steps.recipes(), key=str.casefold):
            self.recipe.addItem(name, name)
        self.recipe.setCurrentIndex(max(0, self.recipe.findData(current)))
        self.b_forget.setEnabled(bool(current))

    def load_recipe(self, name: str):
        self.b_forget.setEnabled(bool(name))
        if name:
            self.load_steps(steps.recipes().get(name, []))

    def keep_recipe(self) -> bool:
        if not self.chosen_steps():
            self.report.setPlainText(tr("Choose a step at least"))
            return False
        name, ok = QInputDialog.getText(self, tr("Save as"), tr("A name for these steps:"),
                                        text=self.recipe.currentData() or "")
        name = name.strip()
        if not ok or not name:
            return False
        try:
            steps.keep_recipe(name, self.chosen_steps())
        except OSError as e:
            QMessageBox.warning(self, self.windowTitle(), str(e))
            return False
        self._fill_recipes(name)
        return True

    def forget_recipe(self):
        name = self.recipe.currentData()
        if name:
            steps.keep_recipe(name, None)
            self._fill_recipes()

    # ----------------------------------------------------------------- the files

    def paths(self) -> list[Path]:
        return [Path(self.files.item(r).data(Qt.ItemDataRole.UserRole)) for r in range(self.files.count())]

    def add_paths(self, paths):
        have = {str(p) for p in self.paths()}
        for path in paths:
            path = Path(path)
            if path.suffix.lower() == ".pdf" and str(path) not in have:
                item = QListWidgetItem(path.name)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                item.setToolTip(str(path))
                self.files.addItem(item)
                have.add(str(path))

    def add_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, tr("Add files"), self.window.last_dir(),
                                                tr("PDF files (*.pdf)"))
        self.add_paths(names)

    def _drag_enter(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop(self, event):
        self.add_paths(u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile())
        event.acceptProposedAction()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Save in"), self.folder.text())
        if folder:
            self.folder.setText(folder)

    # ----------------------------------------------------------------- running them

    def start(self) -> bool:
        files, chosen = self.paths(), self.chosen_steps()
        if not files:
            self.report.setPlainText(tr("Add the files first"))
            return False
        if not chosen:
            self.report.setPlainText(tr("Choose a step at least"))
            return False
        missing = [m for m in (s.needs() for s in chosen) if m]
        if missing:
            self.report.setPlainText("\n".join(missing))
            return False
        folder = Path(self.folder.text().strip() or self.window.last_dir()).expanduser()
        self.stop.clear()
        self.b_run.setEnabled(False)
        self.b_stop.setEnabled(True)
        self.report.setPlainText(tr("Working…"))
        plan = [steps.Step(s.kind, dict(s.settings)) for s in chosen]  # (una copia: el hilo no ve más cambios)

        def work():
            try:
                result = steps.run(files, plan, folder, self.suffix.text(), progress=self.signals.progress.emit,
                                   stop=self.stop)
            except (steps.StepsError, OSError) as e:
                result = e
            self.signals.finished.emit(result)

        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()
        return True

    def _progress(self, done: int, total: int, what: str):
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(done)
        self.bar.setFormat(what or "%p%")

    def _finished(self, result):
        self.b_run.setEnabled(True)
        self.b_stop.setEnabled(False)
        self.bar.setFormat("%p%")
        if isinstance(result, Exception):
            self.report.setPlainText(str(result))
            return
        made = [o for o in result if o.target is not None]
        lines = [ntr("{count} file written", "{count} files written", len(made))
                 + (" " + tr("in {folder}", folder=made[0].target.parent) if made else "")]
        lines += [f"✓ {o.source.name} → {o.target.name}" if o.target else f"✗ {o.source.name}: {o.error}"
                  for o in result]
        self.report.setPlainText("\n".join(lines))

    def reject(self):
        # (al cerrar con un trabajo en marcha, se detiene tras el paso que esté haciendo)
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=120)
        super().reject()
