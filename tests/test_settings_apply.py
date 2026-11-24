"""Aplicar, en Configuración (como en KDE Plasma): apagado hasta que algo cambia; pone los cambios en efecto
sin cerrar la ventana; Cancelar después de Aplicar deja lo aplicado; un atajo repetido no se aplica."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QKeySequenceEdit, QMessageBox

from py_pdftools.core import config


def test_apply(tmp_path, monkeypatch):
    from py_pdftools.gui.prefs import SettingsDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    try:
        dialog = SettingsDialog(w.prefs, w)
        dialog.on_apply = w._settings_applied
        assert not dialog.apply_button.isEnabled()  # (nothing changed yet)
        dialog.author.setText("Ana")
        dialog.author.textEdited.emit("Ana")
        dialog.memory.setCurrentIndex(dialog.memory.findData("high"))
        assert dialog.apply_button.isEnabled()
        dialog.show()
        assert dialog.apply()
        # In effect at once, the window open, and Apply off until the next change
        assert w.prefs.author == "Ana" and config.get("memory") == "high"
        assert dialog.isVisible() and not dialog.apply_button.isEnabled() and dialog.applied
        dialog.transparency.setChecked(not dialog.transparency.isChecked())
        assert dialog.apply_button.isEnabled()
        # Cancel after Apply: what was applied stays
        dialog.reject()
        assert w.prefs.author == "Ana"
        # Two actions with one key: not applied, Apply stays on, and the window says why
        dialog = SettingsDialog(w.prefs, w)
        edits = dialog.keys.findChildren(QKeySequenceEdit)
        warned = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
        key = edits[0].keySequence()
        edits[1].setKeySequence(key if not key.isEmpty() else "Ctrl+Alt+Q")
        if key.isEmpty():
            edits[0].setKeySequence("Ctrl+Alt+Q")
        assert dialog.apply_button.isEnabled()
        assert not dialog.apply() and warned and dialog.apply_button.isEnabled()
    finally:
        w.close()


def test_settings_dialog_with_apply_then_cancel(tmp_path, monkeypatch):
    """Through the window: Apply, then Cancel; the settings are those applied."""
    from py_pdftools.gui.prefs import SettingsDialog
    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("HOME", str(tmp_path))
    w = MainWindow()
    try:
        def drive():
            d = next(x for x in QApplication.topLevelWidgets() if isinstance(x, SettingsDialog) and x.isVisible())
            d.author.setText("Bea")
            d.author.textEdited.emit("Bea")
            d.apply_button.click()
            d.reject()

        QTimer.singleShot(0, drive)
        w.settings_dialog()
        assert w.prefs.author == "Bea"
    finally:
        w.close()
