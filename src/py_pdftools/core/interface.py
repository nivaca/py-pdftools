"""The language of the interface: help, messages, the window's menus,
buttons and labels.

The interface is written in English. Another language has a file in the
``locale`` folder of the package, ``locale/CODE.xml``:

    <interface code="es" name="Spanish" native="Español">
      <text>
        <en>Wrote {path} ({count} pages)</en>
        <tr>Escrito {path} ({count} páginas)</tr>
      </text>
      ...
    </interface>

A text is found by its English, with its spaces made single (so a text may
be laid out on several lines); the translation is shown as written. A text
may have named parts, such as ``{path}``, which tr() fills in; the translation
has the same parts. What the file doesn't translate is shown in English.

The language is the setting ``interface`` of the configuration file
(``[parameters]``; ``en`` unless it says otherwise; see config.py), or
``--interface CODE`` for one run. The programs call use_configured() when
they start, and use() when it changes.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

REFERENCE = "en"
FOLDER = Path(__file__).resolve().parent / "locale"
PART = re.compile(r"\{(\w+)\}")

_code = REFERENCE
_texts: dict[str, str] = {}
_error = ""  # why the last language asked for was not used


class InterfaceError(Exception):
    """A file of the interface that cannot be read."""


def files() -> dict[str, Path]:
    """{code: path} of the languages of the interface besides English."""
    # Sin la carpeta locale (un paquete recortado, por ejemplo) el programa funciona solo en inglés.
    if not FOLDER.is_dir():
        return {}
    return {p.stem: p for p in sorted(FOLDER.glob("*.xml"))}


def names() -> dict[str, str]:
    """{code: name} of the languages of the interface, each in itself (English, Español...)."""
    out = {REFERENCE: "English"}
    for code, path in files().items():
        # A broken file is skipped here; use() tells the error when that language is chosen.
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        out[code] = root.get("native") or root.get("name") or code
    return out


def key_of(english: str) -> str:
    # Colapsa espacios y saltos de línea: un texto partido en varias líneas del XML coincide con el del código.
    return " ".join(english.split())


def read(path: Path) -> dict[str, str]:
    """The texts of an interface file: {English: translation} (raises InterfaceError)."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        raise InterfaceError(f"{path}: {e}") from None
    if root.tag != "interface":
        raise InterfaceError(f"{path}: the root element must be <interface>")
    texts = {}
    for item in root:
        english, translation = item.find("en"), item.find("tr")
        if item.tag != "text" or english is None or translation is None:
            raise InterfaceError(f"{path}: each <text> needs an <en> and a <tr>")
        key = key_of(english.text or "")
        value = translation.text or ""
        # Las partes {nombre} deben ser las mismas en los dos textos; si no, format() fallaría al mostrarlo.
        if sorted(PART.findall(key)) != sorted(PART.findall(value)):
            raise InterfaceError(f'{path}: the parts of "{key}" are not those of its translation')
        # A text given twice is an error rather than a silent override, so that the file stays easy to review.
        if key in texts:
            raise InterfaceError(f'{path}: "{key}" is there twice')
        texts[key] = value
    return texts


def use(code: str | None) -> bool:
    """Show the interface in language CODE (English if None, or if there is no
    such language or its file is wrong). Returns whether CODE is the one in use."""
    global _code, _texts, _error
    path = files().get(code or "")
    texts: dict[str, str] = {}
    # Pedir el inglés, o nada, no es un error; solo lo es un código sin archivo.
    _error = "" if path is not None or not code or code == REFERENCE \
        else f'there is no interface file for "{code}"'
    if path is not None:
        try:
            texts = read(path)
        except InterfaceError as e:
            path = None
            _error = str(e)
    _code = code if path is not None else REFERENCE
    _texts = texts
    return _code == (code or REFERENCE)


def error() -> str:
    """Why the language last given to use() is not the one in use ('' if it is)."""
    return _error


def use_configured(override: str | None = None) -> str:
    """Use OVERRIDE, or else the language of the configuration file. Returns its code."""
    from . import config

    code = override
    # --interface tiene prioridad; sin él, manda el archivo de configuración.
    if code is None:
        try:
            code = config.read().get("parameters", {}).get("interface")
        except config.ConfigError:
            code = None
    use(code if isinstance(code, str) else None)
    return _code


def option(argv: list[str]) -> str | None:
    """The value of --interface in ARGV (needed before the parser is built)."""
    # A small scan by hand: the language must be set before the parser is built, since its help texts
    # are translated as they are made.
    for i, tok in enumerate(argv):
        if tok == "--interface" and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith("--interface="):
            return tok.split("=", 1)[1]
    return None


def choose(language: str | None, fail: type[Exception]) -> None:
    """The command 'interface': with no LANGUAGE, list the languages; else use LANGUAGE and keep it in the
    configuration file (FAIL, the error of the command that asks, if it can't be done)."""
    from . import config

    found = names()
    if language is None:
        current = code()
        print(tr("Languages of the interface:"))
        for each, name in found.items():
            print(f"  {'*' if each == current else ' '} {each}  {name}")
        print(tr("Configuration file: {path}", path=config.config_path()))
        return
    # Se prueba el idioma antes de guardarlo, para no dejar en la configuración uno que no carga.
    if not use(language):
        raise fail(tr("the language {code} cannot be used: {error}", code=language, error=error()))
    try:
        path = config.set("interface", language)
    except OSError as e:
        raise fail(tr("Could not keep the setting: {error}", error=e)) from None
    print(tr("The interface is now in {name} (kept in {path}).", name=found[language], path=path))


def code() -> str:
    """The language of the interface in use."""
    return _code


#  Every new text given to tr() or N_() needs its entry in locale/es.xml, or
#  tests/test_interface.py fails. And so does an entry no longer used.
def tr(english: str, /, **parts) -> str:
    """ENGLISH, a text of the interface, in the language in use, with its
    PARTS ({path} ...) filled in."""
    # Sin traducción cargada no se busca nada: es el caso más frecuente, el inglés.
    text = _texts.get(key_of(english)) if _texts else None
    if text is None:
        text = english
    else:  # (keeping the spaces around the English)
        stripped = english.strip()
        if stripped:
            start = english.index(stripped[0])
            text = english[:start] + text.strip() + english[start + len(stripped):]
    # format() solo si hay partes: un texto sin ellas puede llevar llaves literales.
    return text.format(**parts) if parts else text


def ntr(one: str, many: str, count: int, /, **parts) -> str:
    """ONE or MANY (by COUNT), translated, with {count} and PARTS filled in."""
    return tr(one if count == 1 else many, count=count, **parts)


def N_(english: str) -> str:
    """Mark a text to be translated where it is shown (with tr): texts of
    tables made when the program starts."""
    return english


def translate_argparse() -> None:
    """Make argparse write its own texts (usage:, options...) in the language in use."""
    import argparse

    # argparse calls the module-level _ and ngettext for its own messages (usage:, error:...): they are replaced.
    argparse._ = tr
    argparse.ngettext = lambda one, many, n: tr(one if n == 1 else many)
