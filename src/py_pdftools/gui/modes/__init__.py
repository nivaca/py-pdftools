"""The modes of the window: what the toolbars, the panel and the menus offer.

The window shows one document, with its pages, thumbnails, undo and saving,
whatever the mode. A mode brings its own toolbars, panels (docks) and menus,
which the window shows while the mode is on and hides otherwise; and it says
which annotations are its own (``owns``): those the mouse, the list and the
Edit menu work on. The others are shown on the pages, but can't be touched.

* Annotate: highlights, notes, text boxes, shapes, drawings... (py-annotate)
* Redact: boxes over what is to be removed (py-redact), kept as the PDF's
  redaction marks (annotations of kind ``redact``) until a redacted copy is made
* Pages: labels, the view on opening, headers, footers, watermarks and the
  order of the pages (py-foliation)
* Impose: booklets, n-up and the rest of py-imposition
"""

from __future__ import annotations

import dataclasses
from typing import Callable

from ...annotate.annots import Annotation
from ...core.interface import N_

# Títulos y descripciones se marcan con N_ y se traducen al construir la barra de los modos (tr).
TITLES = {"annotate": N_("Annotate"), "redact": N_("Redact"), "pages": N_("Pages"), "impose": N_("Impose")}
TIPS = {"annotate": N_("Highlights, notes, text boxes, shapes and drawings"),
        "redact": N_("Mark what is to be removed, and write a redacted copy"),
        "pages": N_("Page labels, headers and footers, watermarks, and the order of the pages"),
        "impose": N_("Booklets, n-up, step and repeat and the rest of imposition, for printing")}


# The window builds one Mode per key (see MainWindow._build_modes); the dictionaries above use the same
# keys.
@dataclasses.dataclass
class Mode:
    key: str
    owns: Callable[[Annotation], bool]  # its annotations
    bars: list = dataclasses.field(default_factory=list)  # QToolBar
    docks: list = dataclasses.field(default_factory=list)  # QDockWidget
    menus: list = dataclasses.field(default_factory=list)  # QAction of a menu of the menu bar
    actions: list = dataclasses.field(default_factory=list)  # QAction: enabled only in the mode
    without: tuple = ()  # the object names of toolbars of every mode it has no use for (hidden while it is on)
    # Por defecto no hacen nada; Imponer las usa para cambiar el área central de la ventana.
    entered: Callable[[], None] = lambda: None  # (called when the mode is turned on)
    left: Callable[[], None] = lambda: None  # (and off)
