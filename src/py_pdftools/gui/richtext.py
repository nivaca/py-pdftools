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

STYLE = "p {{ margin-top: 0; margin-bottom: 0; color: {color}; }}"
ALIGN = {"center": Qt.AlignmentFlag.AlignHCenter, "right": Qt.AlignmentFlag.AlignRight}


def prepare(doc: QTextDocument, a: Annotation, font: QFont, margin: float | None = 0) -> None:
    """Make DOC show the text of A (rich or plain) in FONT, its colour and alignment (with MARGIN
    around it; None: Qt's own)."""
    doc.setDefaultFont(font)
    doc.setDefaultStyleSheet(STYLE.format(color=a.color))
    if margin is not None:
        doc.setDocumentMargin(margin)
    option = doc.defaultTextOption()
    option.setAlignment(ALIGN.get(a.align, Qt.AlignmentFlag.AlignLeft))
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    doc.setDefaultTextOption(option)
    if a.rich:
        doc.setHtml(a.rich)
    else:
        doc.setPlainText(a.contents)


def _family(fmt: QTextCharFormat) -> str:
    """The font of FMT, as py-pdftools names it ('helv', 'tiro', 'cour'), or '' if it has none."""
    if not fmt.hasProperty(QTextFormat.Property.FontFamilies):
        return ""
    names = " ".join(fmt.fontFamilies() or []).lower()
    for key, family in FAMILIES.items():
        if family.lower() in names or key in names:
            return key
    return "tiro" if "serif" in names and "sans" not in names else "cour" if "mono" in names else ""


def rich_of(doc: QTextDocument, a: Annotation) -> str:
    """The rich text of what DOC has, written in the text box A: '' if nothing in it differs from
    A's own font and colour."""
    paragraphs, special = [], False
    block = doc.begin()
    while block.isValid():
        parts = []
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            if not fragment.isValid():
                continue
            text = html.escape(fragment.text(), quote=False).replace(" ", "<br/>")
            fmt = fragment.charFormat()
            style = []
            if fmt.fontWeight() > QFont.Weight.Normal:
                style.append("font-weight:bold")
            if fmt.fontItalic():
                style.append("font-style:italic")
            if fmt.fontUnderline():
                style.append("text-decoration:underline")
            if fmt.hasProperty(QTextFormat.Property.ForegroundBrush):
                color = fmt.foreground().color().name()
                if color != QColor(a.color).name():
                    style.append(f"color:{color}")
            family = _family(fmt)
            if family and family != a.font:
                style.append(f"font-family:{FAMILIES[family]}")
            if style:
                special = True
                parts.append(f'<span style="{";".join(style)}">{text}</span>')
            else:
                parts.append(text)
        paragraphs.append(f"<p>{''.join(parts)}</p>")
        block = block.next()
    return "".join(paragraphs) if special else ""


def toggle(cursor, what: str) -> None:
    """Make the text chosen with CURSOR (or what is written next) bold, italic or underlined
    (WHAT), or not, if it is already."""
    fmt = QTextCharFormat()
    now = cursor.charFormat()
    if what == "bold":
        fmt.setFontWeight(QFont.Weight.Normal if now.fontWeight() > QFont.Weight.Normal else QFont.Weight.Bold)
    elif what == "italic":
        fmt.setFontItalic(not now.fontItalic())
    else:
        fmt.setFontUnderline(not now.fontUnderline())
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
    cursor.setCharFormat(QTextCharFormat())
