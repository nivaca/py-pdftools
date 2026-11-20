#!/usr/bin/env python3
"""Make the screenshots of the READMEs, in English and Spanish:

    uv run python tools/screenshots.py [-o FOLDER]

It writes docs/img/MODE_LANG.png (MODE: annotate, redact, pages, impose;
LANG: en, es): the window in each mode, on a sample document made here (a
short essay of five pages), drawn offscreen with a configuration of its own
(the user's is not read).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
SIZE = (1500, 900)

TEXT = {
    "en": ["On the copying of manuscripts",
           "Every copy of a text is also a reading of it. The scribe who copies a page decides, line by line, "
           "what the page says: where a word ends, which abbreviation stands for which word, whether a letter "
           "that looks like an i is an i at all. Those decisions are not always visible in the copy, but they "
           "are always there.",
           "Contact: Juan Pérez, phone 555-1234, juan.perez@example.org",
           "The editor who compares several copies of the same text sees those decisions side by side. "
           "Where the copies agree, the text is probably what the author wrote; where they disagree, the "
           "editor has to choose, and to say why. The critical apparatus records those choices."],
    "es": ["Sobre la copia de manuscritos",
           "Toda copia de un texto es también una lectura de él. El copista que copia una página decide, "
           "renglón a renglón, qué dice la página: dónde termina una palabra, qué abreviatura vale por qué "
           "palabra, si una letra que parece una i es de veras una i. Esas decisiones no siempre se ven en la "
           "copia, pero siempre están ahí.",
           "Contacto: Juan Pérez, teléfono 555-1234, juan.perez@example.org",
           "El editor que compara varias copias del mismo texto ve esas decisiones lado a lado. Donde las "
           "copias coinciden, el texto es probablemente lo que escribió el autor; donde difieren, el editor "
           "tiene que elegir, y decir por qué. El aparato crítico registra esas elecciones."],
}


def sample(path: Path, lang: str) -> Path:
    """A short essay: a title page, then four pages of text."""
    import pymupdf

    title, *paragraphs = TEXT[lang]
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 300, 523, 400), title, fontsize=24, fontname="tiro", align=1)
    for n in range(4):
        page = doc.new_page()
        y = 80
        for paragraph in paragraphs:
            rect = pymupdf.Rect(72, y, 523, y + 200)
            left = page.insert_textbox(rect, paragraph, fontsize=12, fontname="tiro", lineheight=1.4)
            y += 200 - left + 18
    doc.save(path)
    return path


def settle(app, seconds: float = 1.5):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def shoot(lang: str, out: Path, work: Path):
    from py_pdftools.core import interface

    interface.use(lang)
    interface.translate_argparse()
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from py_pdftools.annotate.annots import Annotation
    from py_pdftools.gui import renderer
    from py_pdftools.gui.window import MainWindow, install_qt_translations
    from py_pdftools.pages.headfoot import HeaderFooter
    from py_pdftools.pages.labels import Range

    install_qt_translations()
    renderer.ENABLED = False
    doc = sample(work / f"essay-{lang}.pdf", lang)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(*SIZE)
    w.show()
    w.open_path(doc)
    words = w.canvas.page_words(1)

    # Annotate: a highlight, a note, a text box, a rectangle and a stamp, on page 2
    w.set_mode("annotate")
    w.show_page(1)
    first = [r for r, _, line in words if line == 0][:6]
    if first:
        x0, y0 = min(r[0] for r in first), min(r[1] for r in first)
        x1, y1 = max(r[2] for r in first), max(r[3] for r in first)
        w.add(w.new_annotation("highlight", 1, (x0, y0, x1, y1), quads=((x0, y0, x1, y1),)))
    w.add(Annotation("note", 1, (530, 90, 546, 106), "#ffd54f", contents="?", author="NV"))
    w.add(Annotation("freetext", 1, (300, 420, 520, 470), "#000000", fill="#fffde7", width=0,
                     contents="scribe = copista" if lang == "es" else "scribe = copyist"))
    w.add(Annotation("rect", 1, (66, 300, 530, 400), "#e53935"))
    w.add(Annotation("stamp", 1, (360, 520, 520, 580), "#c62828", stamp="Approved"))
    w.pick([], False)
    settle(app)
    w.grab().save(str(out / f"annotate_{lang}.png"))

    # Redact: the line with the name, the phone and the address
    w.set_mode("redact")
    contact = [r for r, block, line in words if block == 1] or [r for r, _, _ in words[40:48]]
    if contact:
        x0, y0 = min(r[0] for r in contact), min(r[1] for r in contact)
        x1, y1 = max(r[2] for r in contact), max(r[3] for r in contact)
        w.add_redact_text(1, [(x0, y0, x1, y1)])
        w.set_redact_repeat("2-")
    w.pick([], False)
    settle(app)
    w.grab().save(str(out / f"redact_{lang}.png"))
    w.change([a for a in w.annotations if a.kind != "redact"])

    # Pages: labels (the title page with none, then 1, 2...) and a footer
    w.set_mode("pages")
    w.set_ranges([Range(1, ""), Range(2, "D")])
    w.add_stamp(HeaderFooter(footer_center="$pagelabel", pages="2-"))
    w.show_page(1)
    settle(app)
    w.grab().save(str(out / f"pages_{lang}.png"))

    # Impose: a booklet, in the basic form
    w.set_mode("impose")
    ws = w.workspace
    ws.set_mode("basic")
    ws.preview()
    end = time.time() + 60
    while (ws.runner.busy() or not ws.result_files) and time.time() < end:
        app.processEvents()
        time.sleep(0.05)
    ws.res_pane.page.setValue(3)  # (a sheet with text on both halves)
    settle(app)
    w.grab().save(str(out / f"impose_{lang}.png"))

    w.annotations = w.saved = []
    w.drop_work()
    w.workspace.close_down()
    w.hide()
    w.deleteLater()
    settle(app, 0.2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make the screenshots of the READMEs.")
    parser.add_argument("-o", "--output", type=Path, default=ROOT / "docs" / "img", help="the folder (docs/img)")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        os.environ["QT_QPA_PLATFORM"] = os.environ.get("QT_QPA_PLATFORM", "offscreen")
        os.environ["PY_PDFTOOLS_CONFIG"] = str(work / "config")
        os.environ["XDG_CONFIG_HOME"] = str(work / "xdg")
        os.environ["HOME"] = str(work)  # (QSettings, and pdf2iso not found: the same shots everywhere)
        for lang in ("en", "es"):
            shoot(lang, args.output, work)
            print(f"Wrote {args.output}/*_{lang}.png")


if __name__ == "__main__":
    main()
