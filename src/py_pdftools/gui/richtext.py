"""The rich text of text boxes (see Annotation.rich) in Qt: a QTextDocument made of it, for
painting it and writing it on the page, and the rich text made of what was written.

The rich text is a small XHTML: a paragraph (<p>) for each line, with spans for what differs from
the box's own font and colour (font-weight:bold, font-style:italic, text-decoration:underline,
color, font-family). It is what py-pdftools writes; what other programs wrote is shown as Qt reads
it, and written as this once it is changed here."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QTextCharFormat,
    QTextDocument,
    QTextFormat,
    QTextOption,
)

from ..annotate.annots import FAMILIES, Annotation

# Sin márgenes entre párrafos: cada línea del cuadro de texto es un <p> y debe ir pegada a la anterior.
STYLE = "p {{ margin-top: 0; margin-bottom: 0; color: {color}; }}"
ALIGN = {"center": Qt.AlignmentFlag.AlignHCenter, "right": Qt.AlignmentFlag.AlignRight}


def prepare(doc: QTextDocument, a: Annotation, font: QFont, margin: float | None = 0) -> None:
    """Make DOC show the text of A (rich or plain) in FONT, its colour and alignment (with MARGIN
    around it; None: Qt's own)."""
    doc.setDefaultFont(font)
    doc.setDefaultStyleSheet(STYLE.format(color=a.color))
    # The editor on the page passes None and keeps Qt's margin, which canvas.py compensates for.
    if margin is not None:
        doc.setDocumentMargin(margin)
    option = doc.defaultTextOption()
    option.setAlignment(ALIGN.get(a.align, Qt.AlignmentFlag.AlignLeft))
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    doc.setDefaultTextOption(option)
    if a.rich:
        # Qt reads the rich text as HTML; what it doesn't understand of another program's XHTML is lost.
        doc.setHtml(a.rich)
    else:
        doc.setPlainText(a.contents)


def _family(fmt: QTextCharFormat) -> str:
    """The font of FMT, as py-pdftools names it ('helv', 'tiro', 'cour'), or '' if it has none."""
    if not fmt.hasProperty(QTextFormat.Property.FontFamilies):
        return ""
    # Qt devuelve una lista de familias; se juntan en minúsculas para buscar en ellas por subcadena.
    names = " ".join(fmt.fontFamilies() or []).lower()
    for key, family in FAMILIES.items():
        if family.lower() in names or key in names:
            return key
    # Una fuente desconocida se acerca a la base más parecida: con serifa a Times, monoespaciada a
    # Courier; si no, ninguna (la del cuadro).
    return "tiro" if "serif" in names and "sans" not in names else "cour" if "mono" in names else ""


def rich_of(doc: QTextDocument, a: Annotation) -> str:
    """The rich text of what DOC has, written in the text box A: '' if nothing in it differs from
    A's own font and colour."""
    paragraphs, special = [], False
    # Each block of the QTextDocument is a paragraph; each fragment, a run of text with one format.
    block = doc.begin()
    while block.isValid():
        parts = []
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            # The iterator is advanced before the checks, so 'continue' cannot loop for ever.
            it += 1
            if not fragment.isValid():
                continue
            # U+2028 es el salto de línea suave de Qt (Shift+Enter): se escribe como <br/> dentro del párrafo.
            text = html.escape(fragment.text(), quote=False).replace(" ", "<br/>")
            fmt = fragment.charFormat()
            style = []
            if fmt.fontWeight() > QFont.Weight.Normal:
                style.append("font-weight:bold")
            if fmt.fontItalic():
                style.append("font-style:italic")
            if fmt.fontUnderline():
                style.append("text-decoration:underline")
            # Solo se escribe el color si se puso a mano y difiere del color del cuadro.
            if fmt.hasProperty(QTextFormat.Property.ForegroundBrush):
                color = fmt.foreground().color().name()
                if color != QColor(a.color).name():
                    style.append(f"color:{color}")
            family = _family(fmt)
            if family and family != a.font:
                style.append(f"font-family:{FAMILIES[family]}")
            # Los fragmentos sin nada especial van sin <span>, para que el XHTML quede corto.
            if style:
                special = True
                parts.append(f'<span style="{";".join(style)}">{text}</span>')
            else:
                parts.append(text)
        paragraphs.append(f"<p>{''.join(parts)}</p>")
        block = block.next()
    # Nothing special anywhere: '' tells the caller to keep plain text only, in contents.
    return "".join(paragraphs) if special else ""


def toggle(cursor, what: str) -> None:
    """Make the text chosen with CURSOR (or what is written next) bold, italic or underlined
    (WHAT), or not, if it is already."""
    fmt = QTextCharFormat()
    # Se decide por el formato del carácter anterior al cursor: en una selección mixta, manda ese.
    now = cursor.charFormat()
    if what == "bold":
        fmt.setFontWeight(QFont.Weight.Normal if now.fontWeight() > QFont.Weight.Normal else QFont.Weight.Bold)
    elif what == "italic":
        fmt.setFontItalic(not now.fontItalic())
    else:
        fmt.setFontUnderline(not now.fontUnderline())
    # merge, not set: only the one property changes; the colour and the font stay.
    cursor.mergeCharFormat(fmt)


def set_look(cursor, color: str = "", family: str = "") -> None:
    """Give the text chosen with CURSOR a COLOR, or a font (FAMILY: 'helv', 'tiro' or 'cour')."""
    fmt = QTextCharFormat()
    if color:
        fmt.setForeground(QColor(color))
    if family:
        fmt.setFontFamilies([FAMILIES[family]])
    cursor.mergeCharFormat(fmt)


def plain(cursor) -> None:
    """Take every formatting out of the text chosen with CURSOR."""
    # Un formato vacío devuelve el texto al estilo por defecto del documento (el del cuadro).
    cursor.setCharFormat(QTextCharFormat())
