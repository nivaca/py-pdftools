#!/usr/bin/env python3
"""Make the screenshots of the README, in English and in Spanish:

    uv run python tools/screenshots.py [-o FOLDER]

It writes, in docs/img/ (or FOLDER), for each language (en, es):

* window_LANG.png: the window, with an essay annotated in several ways (a
  highlight with replies and a review status, notes, a text box, a callout,
  shapes, a stamp);
* find_LANG.png: Find and highlight;
* properties_LANG.png: the properties of an annotation;
* summary_LANG.png: a page of the summary of the comments.

The window is drawn off the screen (Qt's offscreen platform), with
configuration folders of its own, so the user's settings are not touched.
The essay is made each time.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

ESSAY = {
    "en": ("On reading slowly",
           "A careful reader does not hurry. The first reading of a difficult page gives its outline; the second "
           "gives its argument; only the third shows where the argument is weak. Marking the text is part of this "
           "work: a highlight keeps what matters, a note in the margin keeps the question it raised, and a mark "
           "where a word is missing keeps the correction for later. The annotations of a book are a second text, "
           "written by its reader, and they deserve the same care as the first. ",
           "Is this the edition the author revised?", "Yes: the second, of 1874.", "reading"),
    "es": ("Sobre la lectura lenta",
           "Un lector cuidadoso no tiene prisa. La primera lectura de una página difícil da su contorno; la segunda, "
           "su argumento; solo la tercera muestra dónde flaquea el argumento. Marcar el texto es parte de ese "
           "trabajo: un resaltado guarda lo que importa, una nota al margen guarda la pregunta que surgió, y una "
           "marca donde falta una palabra guarda la corrección para después. Las anotaciones de un libro son un "
           "segundo texto, escrito por su lector, y merecen el mismo cuidado que el primero. ",
           "¿Es esta la edición que revisó el autor?", "Sí: la segunda, de 1874.", "lectura"),
}


def make_essay(path: Path, language: str):
    import pymupdf

    title, text, *_ = ESSAY[language]
    doc = pymupdf.open()
    for n in range(3):
        page = doc.new_page()
        page.insert_text((72, 80), title if n == 0 else f"{title} ({n + 1})", fontsize=20, fontname="tiro")
        page.insert_textbox(pymupdf.Rect(72, 105, 523, 470), text * 2, fontsize=11.5, fontname="tiro")
    doc.save(path)


def shoot(folder: Path, language: str):
    import pymupdf
    from PySide6.QtWidgets import QApplication

    from py_annotate import annots, interface
    from py_annotate.annots import Reply

    interface.use(language)
    from py_annotate.gui import renderer
    from py_annotate.gui.props import PropertiesDialog
    from py_annotate.gui.window import MainWindow, install_qt_translations

    renderer.ENABLED = False  # (each page drawn at once, here)
    app = QApplication.instance() or QApplication([])
    install_qt_translations()
    title, _text, question, answer, word = ESSAY[language]
    with tempfile.TemporaryDirectory() as tmp:
        essay = Path(tmp) / ("essay.pdf" if language == "en" else "ensayo.pdf")
        make_essay(essay, language)
        w = MainWindow()
        w.ask_recover = lambda when: False
        w.resize(1500, 950)
        w.show()
        w.open_path(essay)
        w.prefs = dataclasses.replace(w.prefs, author="N. V.")
        found = annots.words(w.doc[0])
        doc = pymupdf.open(essay)
        lines = annots.text_rects(found, 4, 20)
        first = annots.text_rects(found, 30, 41)
        a = w.new_annotation("highlight", 0, annots.union(lines), quads=tuple(lines))
        a = dataclasses.replace(a, contents="", tags=("method",), replies=(
            Reply("B. R.", question, created=annots.now()),
            Reply("N. V.", answer, created=annots.now()),
            Reply("N. V.", "", "Accepted", annots.now())))
        under = w.new_annotation("underline", 0, annots.union(first), quads=tuple(first))
        spot = doc[0].search_for(word)[-1]  # (in the text, not in the title)
        note = dataclasses.replace(w.new_annotation("note", 0, (530, 120, 546, 136)),
                                   contents=question, author="B. R.")
        box = dataclasses.replace(w.new_annotation("freetext", 0, (72, 500, 280, 545)),
                                  contents="Compare chapter 3" if language == "en" else "Compárese el capítulo 3")
        callout = dataclasses.replace(w.new_annotation("callout", 0, (330, 520, 520, 556),
                                                       (((spot.x0 + spot.width / 2, spot.y1),),)),
                                      contents="The key word" if language == "en" else "La palabra clave")
        ring = w.new_annotation("ellipse", 0, (66, 600, 260, 680))
        stamp = w.new_annotation("stamp", 0, (420, 640, 420, 640))
        w.change([a, under, note, box, callout, ring, stamp], [0])
        w.canvas.render_page_now()
        while w.thumb_timer.isActive():  # (all the thumbnails drawn)
            app.processEvents()
        app.processEvents()
        w.grab().save(str(folder / f"window_{language}.png"))
        w.find_dialog(word)
        f = w.finder
        f.search()
        f.results.setCurrentRow(-1)
        f.move(0, 0)
        app.processEvents()
        f.grab().save(str(folder / f"find_{language}.png"))
        f.close()
        d = PropertiesDialog([w.annotations[4]], w, categories=w.prefs.category_list())
        d.show()
        app.processEvents()
        d.grab().save(str(folder / f"properties_{language}.png"))
        d.close()
        from py_annotate import exchange
        from py_annotate.gui.colors import color_name

        summary = Path(tmp) / "summary.pdf"
        exchange.save_summary(essay, w.annotations, summary, color_name=color_name)
        pymupdf.open(summary)[0].get_pixmap(dpi=70).save(str(folder / f"summary_{language}.png"))
        w.annotations = w.saved = []
        w.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tools/screenshots.py", description="Make the README's screenshots.")
    parser.add_argument("-o", "--output", type=Path, default=ROOT / "docs" / "img")
    args = parser.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    with tempfile.TemporaryDirectory() as config:
        os.environ["PY_ANNOTATE_CONFIG"] = config
        os.environ["XDG_CONFIG_HOME"] = config  # (Qt's settings of the window, too)
        args.output.mkdir(parents=True, exist_ok=True)
        for language in ("en", "es"):
            shoot(args.output, language)
    for p in sorted(args.output.glob("*.png")):
        print(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p)


if __name__ == "__main__":
    main()
