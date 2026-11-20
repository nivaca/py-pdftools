"""The user's settings, kept in the configuration file (config.toml,
[parameters]; see config.py) next to the language:

* ``author``: written in new annotations;
* the style of new annotations of each kind, and how its tool behaves, as
  ``KIND_FIELD`` (``highlight_color = "#ffeb3b"``, ``note_icon = "Key"``,
  ``rect_sticky = false``...): see Style;
* the colours offered in the menus, with what each one means to the user,
  as ``palette_N_color`` and ``palette_N_meaning`` (N from 1);
* the keyboard shortcuts, as ``shortcut_ACTION`` (``shortcut_highlight = "H"``);
* ``categories``: the categories annotations can be put in, as
  ``"Definitions; Questions; ..."`` (if there is none, the usual ones);
* ``pdfconform``: the path of pdf2iso, which makes PDF/A and PDF/X ('' to
  look for it; see conform.py);
* ``ocr_language``: the languages of the text of scanned pages, for OCR
  (Tesseract's names: ``"eng"``, or several, ``"lat+eng"``);
* ``pen_pressure`` and ``pen_curve``: how the pressure of a tablet's pen counts
  (``along`` the stroke, once for the whole ``stroke``, or ``off``), and how
  hard it must press (``soft``, ``normal``, ``firm``); ``pen_button``: what its side
  button does (``pan``: moves the page while held; ``menu``: a right click);
* ``autosave``: every how many minutes a recovery copy of the annotations
  is kept (0: never; see recovery.py).

Only what differs from the usual values is written. Each setting is checked
when it is read: a value that is missing, of the wrong type or out of range
gives the usual one, so a file edited by hand can never stop the program.
"""

from __future__ import annotations

import dataclasses
import re

from ..core import config
from .annots import ALIGNS, ANNOTATING, DASHABLE, ENDED, ENDS, FILLED, FONTS, ICONS, STAMPS, STROKED, TEXTUAL
from ..core.interface import N_

# Only lowercase hex digits: values are lowercased before they are checked (see valid and _value).
COLOR = re.compile(r"#[0-9a-f]{6}")
SHOW = {"": N_("Nothing"), "text": N_("A field for its text"), "comment": N_("The field of its comment"),
        "properties": N_("Its properties")}  # (what opens after an annotation is made)


@dataclasses.dataclass(frozen=True)
class Style:
    color: str
    fill: str = ""
    opacity: float = 1.0
    width: float = 1.5
    font_size: float = 12.0
    font: str = "helv"
    align: str = "left"
    icon: str = "Note"
    start: str = "None"  # (the ends of a line)
    end: str = "None"
    dashed: bool = False
    stamp: str = "Approved"  # a standard stamp, or "text:THE TEXT" for one of the user's
    stamp_date: bool = True  # (a stamp of the user's: with the author and the date under its text)
    sticky: bool = True  # the tool stays chosen after an annotation is made (else, back to Select)
    show: str = ""  # what opens after an annotation is made: see SHOW


# Los estilos de fábrica de cada tipo; lo que el usuario cambie se guarda como KIND_FIELD en config.toml.
STYLES = {
    "highlight": Style("#ffeb3b"), "underline": Style("#1e88e5"), "strikeout": Style("#e53935"),
    "squiggly": Style("#43a047"), "caret": Style("#1e88e5", show="text"),
    "note": Style("#ffd54f", show="text"),
    "freetext": Style("#000000", fill="#fffde7", width=0, show="text"),
    "callout": Style("#000000", fill="#ffffff", width=1, end="OpenArrow", show="text"),
    "area": Style("#ffeb3b", fill="#ffeb3b", opacity=0.4, width=0),
    "rect": Style("#e53935"), "ellipse": Style("#e53935"), "polygon": Style("#e53935"), "cloud": Style("#e53935"),
    "line": Style("#e53935"), "arrow": Style("#e53935", end="OpenArrow"), "polyline": Style("#e53935"),
    "ink": Style("#1e88e5", width=2.0), "marker": Style("#ffeb3b", width=12.0, opacity=0.4), "stamp": Style("#c62828", stamp="Approved"), "attachment": Style("#1e88e5"),
}
# The style of the kinds outside ANNOTATING (a redaction box, for one).
OTHER_STYLE = Style("#000000")
STYLE_FIELDS = tuple(f.name for f in dataclasses.fields(Style))


def relevant(kind: str, field: str) -> bool:
    """Whether FIELD of a Style means something for annotations of KIND."""
    # color, opacity, sticky y show valen para todos los tipos; los demás dependen de lo que dibuja cada uno.
    if field in ("color", "opacity", "sticky", "show"):
        return True
    if field == "fill":
        return kind in FILLED
    if field == "width":
        return kind in STROKED
    if field in ("font_size", "font", "align"):
        return kind in TEXTUAL
    if field == "icon":
        return kind == "note"
    if field in ("start", "end"):
        return kind in ENDED or kind == "arrow"
    if field == "dashed":
        return kind in DASHABLE
    if field in ("stamp", "stamp_date"):
        return kind == "stamp"
    return False


# the colours offered in the menus: (colour, its name, what it means) — the meanings are the user's to change
PALETTE = (("#ffeb3b", N_("Yellow"), N_("Important")), ("#43a047", N_("Green"), N_("Definitions and concepts")),
           ("#1e88e5", N_("Blue"), N_("References and citations")), ("#ec407a", N_("Pink"), N_("Questions")),
           ("#fb8c00", N_("Orange"), N_("Arguments and conclusions")),
           ("#8e24aa", N_("Purple"), N_("Context and history")), ("#e53935", N_("Red"), N_("Errors, to check")),
           ("#000000", N_("Black"), ""), ("#ffffff", N_("White"), ""))
PALETTE_SIZE = len(PALETTE)

# the actions that have a shortcut, besides the tools (annots.ANNOTATING, and select, hand, eraser): the usual keys
SHORTCUTS = {
    "select": "V", "selecttext": "X", "hand": "M", "zoomarea": "Z", "eraser": "E", "highlight": "H", "area": "Shift+H", "underline": "U",
    "strikeout": "S", "squiggly": "Q", "caret": "I", "note": "N", "freetext": "T", "callout": "Shift+T",
    "rect": "R", "ellipse": "O", "polygon": "G", "cloud": "Shift+G", "line": "L", "arrow": "A",
    "polyline": "Shift+L", "ink": "P", "stamp": "Shift+S", "comment": "C", "next": "Alt+Down",
    "previous": "Alt+Up", "marker": "Shift+P", "copy": "Ctrl+C", "paste": "Ctrl+V", "duplicate": "Ctrl+D", "properties": "Alt+Return",
    "group": "Ctrl+G", "ungroup": "Ctrl+Shift+G", "replace": "Shift+I", "typewriter": "Y", "mark": "K", "attachment": "Shift+A", "signature": "Shift+K",
}


# how the pressure of a tablet's pen counts, and how hard it must press for it
PEN_PRESSURE = {"stroke": N_("Once for each drawing (by its first stroke)"),
                "along": N_("Along each stroke (cut into pieces of different widths)"), "off": N_("Not at all")}
PEN_CURVES = {"soft": N_("Soft (a light touch is enough)"), "normal": N_("Normal"),
              "firm": N_("Firm (it must press harder)")}
PEN_BUTTON = {"pan": N_("Moves the page, while it is held"), "menu": N_("A right click (the menu)")}


# the usual categories (translated where they are shown, while they are the usual ones)
CATEGORIES = (N_("Main arguments"), N_("Definitions"), N_("Historical references"), N_("Primary sources"),
              N_("Secondary literature"), N_("Important quotations"), N_("Questions"), N_("Contradictions"),
              N_("Methodological observations"), N_("Editorial problems"))


@dataclasses.dataclass(frozen=True)
class Settings:
    author: str = ""  # written in new annotations
    # Tuples of pairs rather than dicts, so that the frozen dataclass is also hashable.
    styles: tuple[tuple[str, Style], ...] = tuple(STYLES.items())
    palette: tuple[tuple[str, str | None], ...] = tuple((c, None) for c, _, _ in PALETTE)  # (colour, meaning; None: usual)
    shortcuts: tuple[tuple[str, str], ...] = tuple(SHORTCUTS.items())
    autosave: int = 2  # minutes between recovery copies; 0: none
    pdfconform: str = ""  # the path of pdf2iso; '' to look for it (see conform.find)
    categories: tuple[str, ...] | None = None  # None: the usual ones (CATEGORIES, translated)
    ocr_language: str = "eng"  # of the text of scanned pages (see ocr.py)
    pen_pressure: str = "stroke"  # see PEN_PRESSURE
    pen_curve: str = "normal"  # see PEN_CURVES
    pen_button: str = "pan"  # see PEN_BUTTON

    def category_list(self) -> list[str]:
        from ..core.interface import tr

        return list(self.categories) if self.categories is not None else [tr(c) for c in CATEGORIES]

    def style(self, kind: str) -> Style:
        # (a kind of another mode, a redaction box: a style that opens nothing, and keeps its tool)
        return dict(self.styles).get(kind, STYLES.get(kind, OTHER_STYLE))

    def with_style(self, kind: str, style: Style) -> Settings:
        styles = dict(self.styles)
        styles[kind] = style
        return dataclasses.replace(self, styles=tuple(styles.items()))

    def shortcut(self, action: str) -> str:
        return dict(self.shortcuts).get(action, SHORTCUTS.get(action, ""))


DEFAULTS = Settings()


def valid(field: str, value) -> bool:
    # bool es subclase de int: sin esta exclusión, True pasaría por un número válido.
    number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if field in ("author", "meaning"):
        return isinstance(value, str) and "\n" not in value and len(value) <= 200
    if field == "color":
        return isinstance(value, str) and bool(COLOR.fullmatch(value.lower()))
    if field == "fill":
        return isinstance(value, str) and (value == "" or bool(COLOR.fullmatch(value.lower())))
    # Límites razonables: con una opacidad menor que 0,1 la anotación sería casi invisible.
    if field == "opacity":
        return number and 0.1 <= value <= 1
    if field == "width":
        return number and 0 <= value <= 20
    if field == "font_size":
        return number and 4 <= value <= 72
    if field == "font":
        return value in FONTS
    if field == "align":
        return value in ALIGNS
    if field == "icon":
        return value in ICONS
    if field in ("start", "end"):
        return value in ENDS
    if field in ("dashed", "sticky", "stamp_date"):
        return isinstance(value, bool)
    # A stamp of the user's is 'text:' and then 1 to 75 characters, on one line.
    if field == "stamp":
        return isinstance(value, str) and (value in STAMPS or (value.startswith("text:") and "\n" not in value
                                                                and 5 < len(value) <= 80))
    if field == "show":
        return value in SHOW
    if field == "shortcut":
        return isinstance(value, str) and "\n" not in value and len(value) <= 40
    if field == "categories":
        return isinstance(value, str) and "\n" not in value and len(value) <= 5000
    if field == "pdfconform":
        return isinstance(value, str) and "\n" not in value and len(value) <= 1000
    if field == "ocr_language":
        return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z_]+(\+[A-Za-z_]+)*", value)) and len(value) <= 200
    if field == "pen_pressure":
        return value in PEN_PRESSURE
    if field == "pen_curve":
        return value in PEN_CURVES
    if field == "pen_button":
        return value in PEN_BUTTON
    if field == "autosave":
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 120
    return False


def _value(value, field: str):
    # Colours are kept in lowercase and sizes as floats, so that a value read compares equal to the usual one.
    if isinstance(value, str) and field in ("color", "fill"):
        return value.lower()
    if field in ("opacity", "width", "font_size") and not isinstance(value, bool):
        return float(value)
    return value


def load() -> Settings:
    # Un archivo dañado, o una sección [parameters] que no es una tabla, da los valores de fábrica.
    try:
        params = config.read().get("parameters", {})
    except config.ConfigError:
        params = {}
    if not isinstance(params, dict):
        params = {}
    author = params.get("author", "")
    styles = []
    # Cada campo del estilo se acepta solo si es válido y tiene sentido para el tipo; si no, queda el de fábrica.
    for kind in ANNOTATING:
        values = {}
        for field in STYLE_FIELDS:
            value = params.get(f"{kind}_{field}")
            if valid(field, value) and relevant(kind, field):
                values[field] = _value(value, field)
        styles.append((kind, dataclasses.replace(STYLES[kind], **values)))
    palette = []
    # The palette goes by position: palette_1 is the first colour of PALETTE, and so on.
    for n, (usual, _, _) in enumerate(PALETTE, 1):
        color, meaning = params.get(f"palette_{n}_color"), params.get(f"palette_{n}_meaning")
        palette.append((color.lower() if valid("color", color) else usual, meaning if valid("meaning", meaning)
                        else None))
    shortcuts = []
    for action, usual in SHORTCUTS.items():
        key = params.get(f"shortcut_{action}")
        shortcuts.append((action, key if valid("shortcut", key) else usual))
    # TODO: los valores usuales ('eng', 'stroke', 'normal', 'pan') se repiten aquí, en save() y en
    # Settings; convendría tomarlos de DEFAULTS, para que no se separen al cambiar uno.
    autosave = params.get("autosave")
    pdfconform = params.get("pdfconform", "")
    categories = params.get("categories")
    return Settings(author if valid("author", author) else "", tuple(styles), tuple(palette), tuple(shortcuts),
                    autosave if valid("autosave", autosave) else DEFAULTS.autosave,
                    pdfconform if valid("pdfconform", pdfconform) else "",
                    tuple(c.strip() for c in categories.split(";") if c.strip())
                    if valid("categories", categories) else None,
                    params["ocr_language"] if valid("ocr_language", params.get("ocr_language")) else "eng",
                    params["pen_pressure"] if valid("pen_pressure", params.get("pen_pressure")) else "stroke",
                    params["pen_curve"] if valid("pen_curve", params.get("pen_curve")) else "normal",
                    params["pen_button"] if valid("pen_button", params.get("pen_button")) else "pan")


def save(settings: Settings) -> None:
    """Keep SETTINGS in the configuration file (raises OSError, or ValueError
    for a value that isn't allowed). Usual values are left out of it."""
    if not valid("author", settings.author):
        raise ValueError(f"author = {settings.author!r}")
    # None means 'take the key out': config.set_many drops it, so only what differs from the usual is written.
    values: dict = {"author": settings.author or None}
    for kind in ANNOTATING:
        style, usual = settings.style(kind), STYLES[kind]
        for field in STYLE_FIELDS:
            value = getattr(style, field)
            if not valid(field, value):
                raise ValueError(f"{kind}_{field} = {value!r}")
            # Un campo sin sentido para el tipo no se escribe, aunque difiera, para no llenar el archivo de ruido.
            keep = relevant(kind, field) and value != getattr(usual, field)
            values[f"{kind}_{field}"] = value if keep else None
    for n, ((color, meaning), (usual, _, _)) in enumerate(zip(settings.palette, PALETTE, strict=True), 1):
        if not valid("color", color) or (meaning is not None and not valid("meaning", meaning)):
            raise ValueError(f"palette_{n} = {color!r}, {meaning!r}")
        values[f"palette_{n}_color"] = color if color != usual else None
        # The meaning is written whenever the user gave one, even if it is the usual text.
        values[f"palette_{n}_meaning"] = meaning
    for action, key in settings.shortcuts:
        if action in SHORTCUTS:
            values[f"shortcut_{action}"] = key if key != SHORTCUTS[action] else None
    if not valid("autosave", settings.autosave):
        raise ValueError(f"autosave = {settings.autosave!r}")
    values["autosave"] = settings.autosave if settings.autosave != DEFAULTS.autosave else None
    if not valid("pdfconform", settings.pdfconform):
        raise ValueError(f"pdfconform = {settings.pdfconform!r}")
    values["pdfconform"] = settings.pdfconform or None
    if not valid("ocr_language", settings.ocr_language):
        raise ValueError(f"ocr_language = {settings.ocr_language!r}")
    values["ocr_language"] = settings.ocr_language if settings.ocr_language != "eng" else None
    for name, usual in (("pen_pressure", "stroke"), ("pen_curve", "normal"), ("pen_button", "pan")):
        if not valid(name, getattr(settings, name)):
            raise ValueError(f"{name} = {getattr(settings, name)!r}")
        values[name] = getattr(settings, name) if getattr(settings, name) != usual else None
    # ';' separa las categorías en el archivo: ninguna puede contenerlo.
    if settings.categories is not None and any(";" in c or "\n" in c for c in settings.categories):
        raise ValueError(f"categories = {settings.categories!r}")
    values["categories"] = "; ".join(settings.categories) if settings.categories is not None else None
    config.set_many(values)
