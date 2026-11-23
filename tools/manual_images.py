#!/usr/bin/env python3
"""Make the pictures of the user manual (docs/MANUAL_en.tex, docs/MANUAL_es.tex), in English and Spanish:

    uv run python tools/manual_images.py [-o FOLDER]

It writes docs/img/manual/NAME_LANG.png: the window in each mode and with its panels, and the dialogs the
manual explains, on sample documents made here (an essay with bookmarks and labels, a form, a scanned page,
a page with text only covered), drawn offscreen with a configuration of its own: the user's settings are
never read or written (HOME, XDG_CONFIG_HOME, XDG_CACHE_HOME and PY_PDFTOOLS_CONFIG all point to a folder
of its own).
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
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "forms"))
SIZE = (1400, 860)


def settle(app, seconds: float = 1.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def essay(path: Path, lang: str) -> Path:
    """The essay of the READMEs' pictures, with bookmarks and page labels (i for the title page, then 1...)."""
    import pymupdf
    from screenshots import sample

    sample(path, lang)
    doc = pymupdf.open(path)
    titles = (["Title page", "The scribe", "The copy", "The editor", "The apparatus"] if lang == "en" else
              ["Portada", "El copista", "La copia", "El editor", "El aparato"])
    doc.set_toc([[1, titles[0], 1]] + [[1, t, n + 2] for n, t in enumerate(titles[1:])])
    doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
                         {"startpage": 1, "prefix": "", "style": "D", "firstpagenum": 1}])
    doc.saveIncr()
    return path


def scanned(path: Path, source: Path) -> Path:
    """A page of SOURCE as a picture only (as a scanner makes it): a page without text, for OCR."""
    import pymupdf

    src = pymupdf.open(source)
    pix = src[1].get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
    doc = pymupdf.open()
    page = doc.new_page(width=src[1].rect.width, height=src[1].rect.height)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(path)
    return path


def covered(path: Path, lang: str) -> Path:
    """A page 'redacted' by black boxes drawn over its text, which is still there."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    lines = (["Report on the meeting of 3 March", "Present: Ana Gómez, Luis Prado", "Phone of the witness: 555-0199",
              "The agreement was signed by both parties."] if lang == "en" else
             ["Informe de la reunión del 3 de marzo", "Presentes: Ana Gómez, Luis Prado",
              "Teléfono del testigo: 555-0199", "Ambas partes firmaron el acuerdo."])
    for i, line in enumerate(lines):
        page.insert_text((72, 100 + 28 * i), line, fontsize=13, fontname="tiro")
    for secret in ("Ana Gómez, Luis Prado", "555-0199"):
        for rect in page.search_for(secret):
            page.draw_rect(rect + (-1, -1, 1, 1), color=None, fill=(0, 0, 0))
    doc.save(path)
    return path


def shoot(lang: str, out: Path, work: Path):
    from py_pdftools.core import interface

    interface.use(lang)
    interface.translate_argparse()
    from PySide6.QtWidgets import QApplication, QTabWidget

    app = QApplication.instance() or QApplication([])
    from py_pdftools.annotate.annots import Annotation
    from py_pdftools.gui import renderer
    from py_pdftools.gui.window import MainWindow, install_qt_translations

    install_qt_translations()
    renderer.ENABLED = False

    def save(widget, name: str):
        from PySide6.QtWidgets import QLabel, QLineEdit

        if hasattr(widget, "statusBar"):  # (no paths of the sample files in the pictures)
            widget.statusBar().clearMessage()
        # (ni la de la carpeta temporal: se muestra como la carpeta personal)
        for child in widget.findChildren(QLabel) + widget.findChildren(QLineEdit):
            if str(work) in child.text():
                child.setText(child.text().replace(str(work / "config"), "~/.config/py-pdftools").replace(
                    str(work), "~/Documents"))
        widget.grab().save(str(out / f"{name}_{lang}.png"))

    def dialog(d, name: str, width: int | None = None):
        if width:
            d.resize(width, d.sizeHint().height())
        d.show()
        settle(app, 0.4)
        save(d, name)
        d.close()

    book = essay(work / f"essay-{lang}.pdf", lang)
    w = MainWindow()
    w.ask_recover = lambda when: False
    w.resize(*SIZE)
    w.show()
    w.open_path(book)

    # Read: the pages, their thumbnails and the bookmarks
    w.set_mode("read")
    w.outline_dock.show()
    w.show_page(1)
    w._fit("width")
    settle(app)
    w.hint.dismiss()
    save(w, "read")
    w.outline_dock.hide()

    # Anotar: un resaltado, una nota, un cuadro de texto, un rectángulo y un sello, en la página 2
    words = w.canvas.page_words(1)
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
    w.hint.dismiss()
    save(w, "annotate")
    from py_pdftools.gui.props import PropertiesDialog

    dialog(PropertiesDialog([w.annotations[2]], w), "annot_props")
    from py_pdftools.gui.finder import FindDialog

    finder = FindDialog(w)
    dialog(finder, "find_highlight")
    from py_pdftools.gui.linking import LinkDialog

    dialog(LinkDialog(w.count, w.page_labels(), {"kind": "page", "page": 3}), "link", 520)

    # Censurar: la línea del nombre, el teléfono y el correo, en todas las páginas desde la 2
    w.set_mode("redact")
    contact = [r for r, block, line in words if block == 1] or [r for r, _, _ in words[40:48]]
    if contact:
        x0, y0 = min(r[0] for r in contact), min(r[1] for r in contact)
        x1, y1 = max(r[2] for r in contact), max(r[3] for r in contact)
        w.add_redact_text(1, [(x0, y0, x1, y1)])
        w.set_redact_repeat("2-")
    w.pick([], False)
    settle(app)
    w.hint.dismiss()
    save(w, "redact")
    w.a_redact_result.setChecked(True)
    settle(app)
    save(w, "redact_result")
    w.a_redact_result.setChecked(False)
    from py_pdftools.gui.redact.find import FindDialog as RedactFind

    dialog(RedactFind(w), "redact_find")
    from py_pdftools.gui.redact.hidden_dialog import HiddenDialog
    from py_pdftools.redact import hidden
    from py_pdftools.redact.redact import open_pdf

    with open_pdf(book) as d:
        dialog(HiddenDialog(hidden.inspect(d), w), "hidden")
    w.change([a for a in w.annotations if a.kind != "redact"])
    from py_pdftools.gui.redact.covered_dialog import CoveredDialog
    from py_pdftools.redact import covered as covered_mod

    fake = covered(work / f"covered-{lang}.pdf", lang)
    dialog(CoveredDialog(covered_mod.find(fake), ["1"], w), "covered")

    # Índice de palabras: tres términos en el ensayo, con sus páginas rotuladas
    from py_pdftools.gui.wordindex_dialog import WordIndexDialog

    wi = WordIndexDialog(w)
    wi.terms.setPlainText("copy\neditor\nre:scribe\\w*\n" if lang == "en" else "copia\neditor\nre:copista\\w*\n")
    wi.alpha.setChecked(True)
    wi.logical.setChecked(True)
    wi.find()
    dialog(wi, "word_index")
    w.change([])  # (sin las anotaciones de Anotar: solo las etiquetas)
    # Foliar: las etiquetas, y los diálogos de numerar, encabezados y pies, marcas de agua y dividir
    w.set_mode("pages")
    w.show_page(1)
    settle(app)
    w.hint.dismiss()
    save(w, "pages")
    from py_pdftools.gui.pages.headfoot_dialog import HeaderFooterDialog
    from py_pdftools.gui.pages.watermark_dialog import WatermarkDialog
    from py_pdftools.gui.pages.widgets import NumberDialog
    from py_pdftools.gui.pages.arrange_dialog import ArrangeDialog
    from py_pdftools.pages import headfoot, watermark

    dialog(NumberDialog(w, 3), "number")
    dialog(HeaderFooterDialog(w, headfoot.HeaderFooter(footer_center="$pagelabel", pages="2-"), w.file, "",
                              w.page_labels(), 2), "headfoot")
    dialog(WatermarkDialog(w, watermark.Watermark(text="DRAFT" if lang == "en" else "BORRADOR"), w.file, "",
                           w.page_labels(), 2), "watermark")
    dialog(ArrangeDialog(w, "split", w.count, folder=work), "split")
    # El clasificador de páginas: la segunda girada y elegida
    from py_pdftools.gui.pages.sorter_dialog import SorterDialog

    sorter = SorterDialog(w)
    sorter.resize(1100, 520)
    sorter.show()
    settle(app, 0.3)
    sorter.grid.item(1).setSelected(True)
    sorter.turn(90)
    settle(app, 0.6)
    save(sorter, "sorter")
    sorter.close()

    # Impose: a booklet, in the basic form
    w.set_mode("impose")
    ws = w.workspace
    ws.set_mode("basic")
    ws.preview()
    end = time.time() + 60
    while (ws.runner.busy() or not ws.result_files) and time.time() < end:
        app.processEvents()
        time.sleep(0.05)
    ws.res_pane.page.setValue(3)
    settle(app)
    w.hint.dismiss()
    save(w, "impose")

    # OCR: una página escaneada, con su panel
    scan = scanned(work / f"scan-{lang}.pdf", book)
    w.set_mode("read")
    w.open_path(scan)
    w.set_mode("ocr")
    settle(app)
    w.hint.dismiss()
    save(w, "ocr")
    from py_pdftools.gui.ocr_languages import LanguagesDialog

    dialog(LanguagesDialog(w), "ocr_languages", 760)

    # Forms: the panel Form, on a form with formats and sums
    from sample_form import make

    form = make(work / f"form-{lang}.pdf")
    w.open_path(form)
    w.set_mode("read")
    w.set_field("name", "Ana Gómez")
    w.set_field("price", "1234.5")
    w.set_field("tax", "80")
    w.set_field("agree", "Yes")
    w.show_page(0)
    w._fit("page")
    settle(app)
    w.hint.dismiss()
    save(w, "form")
    w.drop_work()

    # La vista: dos páginas lado a lado, en blanco sobre negro
    w.open_path(book)
    w.form_dock.hide()
    w.set_mode("read")
    w.set_spread(True, True)
    w.set_reading("white")
    w._fit("page")
    w.show_page(1)
    settle(app)
    w.hint.dismiss()
    save(w, "view")
    w.set_reading("")
    w.set_spread(False, False)

    # Files: combining, pictures, smaller, exports, version, protection
    from py_pdftools.gui.combine_dialog import CombineDialog, ImagesDialog

    c = CombineDialog(w, (book, ""))
    c.add_paths([form])
    c.tree.topLevelItem(1).setText(1, "1")
    dialog(c, "combine", 760)
    # Aplicar pasos a varios archivos: dos archivos, una marca de agua y un tamaño reducido
    from PySide6.QtCore import Qt as _Qt

    from py_pdftools.gui.steps_dialog import StepsDialog

    sd = StepsDialog(w)
    sd.add_paths([form])
    for r in range(sd.steps.count()):
        if sd.steps.item(r).data(_Qt.ItemDataRole.UserRole).kind in ("watermark", "reduce"):
            sd.steps.item(r).setCheckState(_Qt.CheckState.Checked)
    sd.steps.setCurrentRow(2)
    sd.folder.setText(str(work / "processed"))
    dialog(sd, "steps", 900)
    pics = ImagesDialog(w)
    import pymupdf

    for n in range(3):
        p = work / f"scan{n + 1:02}.jpg"
        pymupdf.open(scan)[0].get_pixmap(dpi=40).save(p)
    pics.add_paths(sorted(work.glob("scan*.jpg")))
    dialog(pics, "images")
    from py_pdftools.gui.reduce_dialog import ReduceDialog
    from py_pdftools.pages import reduce

    dialog(ReduceDialog(reduce.where(scan), w), "reduce")
    from py_pdftools.gui.export_dialog import ExportDialog

    dialog(ExportDialog("pages", w.count, 1, w), "export")
    from py_pdftools.gui.version_dialog import VersionDialog
    from py_pdftools.pages import version

    vd = VersionDialog("1.7", lambda v: version.newer_than(book, v), w)
    vd.version.setCurrentIndex(vd.version.findData("1.3"))
    dialog(vd, "version")
    from py_pdftools.core.protection import Protection
    from py_pdftools.gui.protect_dialog import ProtectDialog

    dialog(ProtectDialog(Protection(), w), "protect")

    # Firmas (si pyHanko está instalado)
    try:
        from py_pdftools.gui.signing import IdDialog, SignaturesDialog, SignDialog
        from py_pdftools.signatures import ids, sign, verify

        dialog(IdDialog(w, "Ana Gómez"), "make_id")
        p12 = work / "ana.p12"
        os.environ["PY_PDFTOOLS_CONFIG"] = str(work / "config")
        ids.make_id(ids.Identity("Ana Gómez", "ana@example.org"), "secret1", p12)
        sd = SignDialog(w, str(p12), [], False, {"reason": "Approved" if lang == "en" else "Aprobado",
                                                 "location": "Bogotá"})
        dialog(sd, "sign")
        signed = work / f"signed-{lang}.pdf"
        sign.sign(book, signed, sign.Options(p12, "secret1", "Approved" if lang == "en" else "Aprobado",
                                             "Bogotá", page=1, rect=(330, 650, 530, 710)))
        dialog(SignaturesDialog(verify.check(signed), w), "signatures")
    except ImportError:
        print("(no pyHanko: no pictures of signatures)")

    # Settings, and the toolbars
    from py_pdftools.gui.prefs import SettingsDialog

    s = SettingsDialog(w.prefs, w)
    tabs = s.findChild(QTabWidget)
    for i, name in enumerate(("settings_general", "settings_appearance", "settings_documents")):
        tabs.setCurrentIndex(i)
        s.show()
        settle(app, 0.4)
        save(s, name)
    tabs.setCurrentIndex(tabs.count() - 1)
    settle(app, 0.3)
    save(s, "settings_performance")
    s.close()
    from py_pdftools.gui.toolbars import ToolbarsDialog

    td = ToolbarsDialog(w)
    td.bar.setCurrentIndex(td.bar.findData("navigation"))
    dialog(td, "toolbars")

    w.annotations = w.saved = []
    w.drop_work()
    w.workspace.close_down()
    w.hide()
    w.deleteLater()
    settle(app, 0.2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make the pictures of the user manual.")
    parser.add_argument("-o", "--output", type=Path, default=ROOT / "docs" / "img" / "manual",
                        help="the folder (docs/img/manual)")
    parser.add_argument("--lang", choices=("en", "es"), action="append", help="only this language")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        os.environ["QT_QPA_PLATFORM"] = os.environ.get("QT_QPA_PLATFORM", "offscreen")
        # (una configuración propia en todo lugar donde pudiera leerse: nunca la del usuario)
        os.environ["PY_PDFTOOLS_CONFIG"] = str(work / "config")
        os.environ["XDG_CONFIG_HOME"] = str(work / "xdg")
        os.environ["XDG_CACHE_HOME"] = str(work / "cache")
        os.environ["HOME"] = str(work)
        for lang in args.lang or ("en", "es"):
            shoot(lang, args.output, work)
            print(f"Wrote {args.output}/*_{lang}.png")


if __name__ == "__main__":
    main()
