"""La accesibilidad de la ventana: el nombre que un lector de pantalla dice de cada casilla, lista y vista, y el
paso del foco de un panel a otro con el teclado (Ver > Panel siguiente, Ctrl+F6; Panel anterior, Ctrl+Mayús+F6).

Las casillas y listas que no recibieron un nombre propio lo toman de su texto de ejemplo o de la primera frase
de su ayuda emergente; sin uno ni otra, el lector de pantalla solo diría «casilla» o «lista». Se nombran al
abrirse la ventana y al cambiar de modo, porque algunos paneles se hacen al entrar en el suyo."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QBoxLayout, QComboBox, QDockWidget, QFormLayout, QGraphicsView,
    QGridLayout, QGroupBox, QHeaderView, QLabel, QLayout, QLineEdit, QWidget,
)

KINDS = (QLineEdit, QComboBox, QAbstractSpinBox, QAbstractItemView, QGraphicsView)


def _first_clause(text: str) -> str:
    """The first clause of a tooltip (up to its first colon, full stop or semicolon), as a short name."""
    text = re.sub(r"<[^>]+>", "", text).strip()
    return re.split(r"[:.;(]\s", text + " ", maxsplit=1)[0].strip()


def _layout_of(w: QWidget) -> QLayout | None:
    """The layout W is in (that of its parent, or one inside it)."""
    parent = w.parentWidget()
    if parent is None:
        return None
    # (los layouts anidados se buscan entre los hijos del padre: los que da itemAt().layout() pueden borrarse
    # bajo los pies de PySide)
    for lay in [parent.layout(), *parent.findChildren(QLayout)]:
        if lay is not None and lay.indexOf(w) >= 0:
            return lay
    return None


def _label_beside(w: QWidget) -> str:
    """The text of the label beside W in its layout (that of its row in a form; the cell to its left, or above
    it, in a grid; the item before it in a row or a column), with the title of its group, if it has one."""
    lay, label = _layout_of(w), None
    if isinstance(lay, QFormLayout):
        label = lay.labelForField(w)
    elif isinstance(lay, QGridLayout):
        row, column, _, _ = lay.getItemPosition(lay.indexOf(w))
        for r, c in ((row, column - 1), (row - 1, column)):
            item = lay.itemAtPosition(r, c) if r >= 0 and c >= 0 else None
            if item is not None and isinstance(item.widget(), QLabel):
                label = item.widget()
                break
    elif isinstance(lay, QBoxLayout):
        i = lay.indexOf(w)
        item = lay.itemAt(i - 1) if i > 0 else None
        label = item.widget() if item is not None else None
    if not isinstance(label, QLabel) or not re.sub(r"<[^>]+>", "", label.text()).strip():
        return ""
    text = re.sub(r"<[^>]+>", "", label.text()).replace("&", "").strip().rstrip(":")
    group = w.parentWidget()
    if isinstance(group, QGroupBox) and group.title().strip():
        text = f"{group.title().replace('&', '').strip()}: {text}"
    return text


def name_widgets(root: QWidget) -> int:
    """Give every field, list and view of ROOT without an accessible name one, from its placeholder text or its
    tooltip; how many were named."""
    labelled = {id(label.buddy()) for label in root.findChildren(QLabel) if label.buddy() is not None}
    named = 0
    for kind in KINDS:
        for w in root.findChildren(kind):
            # (no la lista emergente de un desplegable, que es otra ventana: se nombra por el desplegable)
            if w.window() is not root.window() or w.accessibleName().strip() or id(w) in labelled \
                    or isinstance(w, QHeaderView):
                continue
            # (la casilla de un desplegable editable, o de un selector numérico, se nombra por él)
            if isinstance(w, QLineEdit) and isinstance(w.parent(), (QComboBox, QAbstractSpinBox)):
                continue
            name = w.placeholderText() if isinstance(w, QLineEdit) else ""
            try:
                name = name or _first_clause(w.toolTip()) or _label_beside(w)
                # (un campo envuelto en un widget propio, como los de Imponer: la etiqueta es la del envoltorio)
                wrapper = w.parentWidget()
                if not name and wrapper is not None and wrapper is not root and _layout_of(w) is wrapper.layout():
                    name = _first_clause(wrapper.toolTip()) or _label_beside(wrapper)
            except RuntimeError:  # (a layout PySide no longer has: no name from it)
                name = name or ""

            if name:
                w.setAccessibleName(name.rstrip("…"))
                named += 1
    return named


def focus_targets(window) -> list[QWidget]:
    """Where the focus goes, in turn: the thumbnails, the pages, and each panel shown (its first field or list),
    from left to right."""
    out = []
    if window.a_thumbs.isChecked() and window.pages.isVisible():
        out.append(window.pages)
    out.append(window.canvas)
    docks = [d for d in window.findChildren(QDockWidget) if d.parent() is window and d.isVisible()
             and d.widget() is not None]
    docks.sort(key=lambda d: (d.mapTo(window, d.rect().topLeft()).x(), d.mapTo(window, d.rect().topLeft()).y()))
    for dock in docks:
        part = next((w for kind in (QLineEdit, QAbstractItemView) for w in dock.widget().findChildren(kind)
                     if w.isVisible() and w.isEnabled() and w.focusPolicy() != Qt.FocusPolicy.NoFocus), None)
        if part is not None:
            out.append(part)
    return out


def focus_panel(window, step: int) -> QWidget | None:
    """The focus to the next panel (STEP 1) or the previous one (STEP -1), going round; its name said on the
    status bar. The widget that took it, or None."""
    targets = focus_targets(window)
    if not targets:
        return None
    now = window.focusWidget()
    here = next((i for i, t in enumerate(targets) if now is not None and (now is t or t.isAncestorOf(now))), -1)
    target = targets[(here + step) % len(targets)] if here >= 0 else targets[0 if step > 0 else -1]
    target.setFocus(Qt.FocusReason.TabFocusReason)
    dock = next((p for p in _parents(target) if isinstance(p, QDockWidget)), None)
    window.statusBar().showMessage(dock.windowTitle() if dock is not None else target.accessibleName(), 3000)
    return target


def _parents(w: QWidget):
    while w is not None:
        yield w
        w = w.parentWidget()
