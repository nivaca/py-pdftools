"""Word index (pages/wordfinder.py, from pdf-word-finder): its terms and patterns, the text made ready, the search
by labelled pages, the report; the command find-words, and the dialog Edit > Word index."""

from __future__ import annotations

import pymupdf
import pytest

from py_pdftools.pages import wordfinder as wf

# Siete páginas; con etiquetas: i, ii, y 1-5 desde la tercera. La sexta, vacía, como un escaneo sin OCR.
PAGES = [
    "Prefacio sobre el amor y la philología.",
    "Índice general. Sharahzad aparece aquí.",
    "Capítulo uno. El amor de Sharahzad y la vir-\ntus romana. Leña y lengua.",
    "De rerum\nnatura: amor, amoris, amorem. Marcolphus habla.",
    "Página sin nada que buscar.",
    "",
    "Virtus, virtutem, virtutis. ÁMBITO y ambito. Nombre de Dios.",
]


def make_pdf(path, labels=True):
    doc = pymupdf.open()
    for text in PAGES:
        page = doc.new_page()
        for n, line in enumerate(text.split("\n")):
            page.insert_text((72, 72 + 14 * n), line, fontsize=12)
    if labels:
        doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
                             {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1}])
    doc.save(path)
    return path


@pytest.fixture
def labelled(tmp_path):
    return make_pdf(tmp_path / "labelled.pdf")


@pytest.fixture
def plain(tmp_path):
    return make_pdf(tmp_path / "plain.pdf", labels=False)


def found(term, text, **kw):
    return [m.group(0) for m in wf.build_pattern(term, **kw).finditer(text)]


def test_patterns():
    assert found("amor", "amor, amoris, Amor") == ["amor", "Amor"]  # (whole words, any case)
    assert found("amor", "amor, amoris", substring=True) == ["amor", "amor"]
    assert found("Amor", "amor Amor", case_sensitive=True) == ["Amor"]
    assert found("de rerum natura", "de  rerum\nnatura") == ["de  rerum\nnatura"]  # (a phrase across lines)
    assert found("O'Brien", "Mr O'Brien said") == ["O'Brien"]
    assert found("re:virtu(s|tem)", "virtus virtutem") == ["virtus", "virtutem"]
    assert found("am(oris|or)", "amor amoris", as_regex=True) == ["amor", "amoris"]
    assert found("re:amor", "clamor") == ["amor"] and found("re:amor", "clamor", regex_word=True) == []
    assert found("philología", "philologia", ignore_accents=True) == ["philologia"]
    with pytest.raises(wf.PatternError):
        wf.build_pattern("re:(")
    assert wf.display_term("re:amor|virtus") == "amor|virtus" and wf.display_term("amor") == "amor"


def test_the_text():
    assert wf.strip_accents("philología ÁMBITO") == "philologia AMBITO"
    assert wf.normalise("ﬁn  de la\tpágina\n") == "fin de la página "
    assert wf.normalise("vir-\ntus") == "virtus" and wf.normalise("vir­ \n tus") == "virtus"
    assert wf.normalise("vir-\ntus", dehyphenate=False) == "vir- tus"
    assert wf.normalise("greco-latino") == "greco-latino"
    words = ["leña", "lengua", "Ámbito", "ambar", "zorro", "llave", "luz"]
    assert sorted(words, key=wf.sort_key) == ["ambar", "Ámbito", "lengua", "leña", "llave", "luz", "zorro"]
    assert wf.read_terms(["amor\n", "# a comment\n", "  virtus  # Latin\n", "\n"]) == ["amor", "virtus"]


def test_the_search_by_labelled_pages(labelled, plain):
    pages = wf.pages_of(pymupdf.open(labelled))
    assert pages.has_labels and pages.labels == ["i", "ii", "1", "2", "3", "4", "5"]
    r = wf.search(pages, ["amor", "Sharahzad"], wf.Options())
    assert [h.label for h in r.hits["amor"]] == ["i", "1", "2"]
    assert [h.label for h in r.hits["Sharahzad"]] == ["ii", "1"]
    assert r.empty_pages == 1 and r.total_pages == 7
    assert [h.label for h in wf.search(pages, ["virtus"], wf.Options()).hits["virtus"]] == ["1", "5"]
    assert [h.label for h in wf.search(pages, ["virtus"], wf.Options(dehyphenate=False)).hits["virtus"]] == ["5"]
    r = wf.search(pages, ["re:virtu(s|tem|tis)"], wf.Options(context_width=10))
    last = r.hits["re:virtu(s|tem|tis)"][-1]
    assert (last.logical, last.label, last.count) == (7, "5", 3) and last.snippets[0].startswith("Virtus")
    assert r.total() == 4 and r.pages_with_hits() == 2
    assert wf.search(pages, ["ambito"], wf.Options(ignore_accents=True)).hits["ambito"][0].count == 2
    # Without labels: the pages by their place in the file, and a note that says so
    bare = wf.pages_of(pymupdf.open(plain))
    assert not bare.has_labels and bare.labels == [str(i) for i in range(1, 8)]
    report, notes = wf.build_report(wf.search(bare, ["amor", "nothing"], wf.Options()))
    assert report == "amor 1, 3, 4" and "no page labels" in notes and "Not found: nothing" in notes


def test_the_report(labelled, tmp_path):
    r = wf.search(wf.pages_of(pymupdf.open(labelled)), ["Sharahzad", "amor"], wf.Options())
    report, _ = wf.build_report(r, alphabetical=True)
    assert report == "amor i, 1, 2\nSharahzad ii, 1"
    report, _ = wf.build_report(r, show_logical=True)
    assert report.splitlines()[0] == "Sharahzad ii [seq. 2], 1 [seq. 3]"
    report, _ = wf.build_report(r, detailed=True)
    assert report.startswith("“Sharahzad”: 2 times on 2 pages")
    assert wf.write_txt(tmp_path / "i.txt", r) == 2
    assert (tmp_path / "i.txt").read_text().splitlines()[0] == "amor i, 1, 2"
    wf.write_csv(tmp_path / "i.csv", r)
    rows = (tmp_path / "i.csv").read_text().splitlines()
    assert rows[0] == ",".join(wf.CSV_HEADER) and rows[1] == "amor,1,i,1,"


def test_the_command_line(labelled, tmp_path, capsys):
    from py_pdftools.cli import main

    terms = tmp_path / "terms.txt"
    terms.write_text("Sharahzad\n# a comment\nre:virtu(s|tem|tis)\n", encoding="utf-8")
    assert main(["find-words", str(labelled), "amor", "--words-file", str(terms), "--sort",
                 "--txt", str(tmp_path / "out.txt"), "--csv", str(tmp_path / "out.csv")]) == 0
    out = capsys.readouterr()
    assert out.out.splitlines() == ["amor i, 1, 2", "Sharahzad ii, 1", "virtu(s|tem|tis) 1, 5"]
    assert "CSV written" in out.err and (tmp_path / "out.csv").exists()
    assert main(["find-words", str(labelled), "re:("]) == 1
    assert main(["find-words", str(tmp_path / "missing.pdf"), "x"]) == 1


def test_the_dialog(labelled, tmp_path):
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow
    from py_pdftools.gui.wordindex_dialog import WordIndexDialog

    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.ask_recover = lambda when: False
    assert not w.a_word_index.isEnabled()
    assert w.open_path(labelled) and w.a_word_index.isEnabled()
    d = WordIndexDialog(w)
    assert not d.find()  # (no terms)
    d.terms.setPlainText("Sharahzad\namor\n")
    d.alpha.setChecked(True)
    assert d.find()
    assert d.report.toPlainText() == "amor i, 1, 2\nSharahzad ii, 1"
    assert "2 terms found" in d.notes.text() and d.b_csv.isEnabled()
    d.context.setChecked(True)  # (the context makes the report detailed)
    assert d.detailed.isChecked() and d.find() and "“Sharahzad”: 2 times" in d.report.toPlainText()
    d.close()
    w.drop_work()
    w.close()


def test_the_button_on_the_toolbar_find():
    """Word index is also on the toolbar Find, with its own icon (a name no theme has, so it is always that)."""
    from PySide6.QtWidgets import QApplication

    from py_pdftools.gui.window import MainWindow

    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.ask_recover = lambda when: False
    bar = next(b for b in w.toolbars() if b.objectName() == "find")
    assert w.a_word_index in bar.actions() and not w.a_word_index.icon().isNull()
    assert "a_word_index" in w._tb_defaults["find"]  # (and Customize the toolbars can put it back there)
    w.close()
