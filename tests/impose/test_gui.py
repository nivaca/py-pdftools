"""The mode Impose of the window: py-imposition's workspace in it, driven as the user would (from the
tests of py-imposition's window; those of what is now the window's own, the language, recent files,
the settings, are in the tests of the window)."""

from __future__ import annotations

import os
import shlex
import shutil
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from py_pdftools.impose.common import COMMANDS  # noqa: E402
from py_pdftools.impose.runner import build_parser  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "example" / "numbers-100.pdf"


def main(argv):
    from py_pdftools.cli import main as pdftools_main

    return pdftools_main(["impose", *argv])


@pytest.fixture(scope="module")
def app():
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield a


@pytest.fixture()
def window(app, tmp_path, monkeypatch):
    """The workspace of the mode Impose, in a window of its own; open_path opens a document in the window."""
    from PySide6.QtCore import QSettings

    from py_pdftools.gui.window import MainWindow
    monkeypatch.setenv("HOME", str(tmp_path))
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "config"))
    host = MainWindow()
    host.ask_recover = lambda when: False
    host.set_mode("impose")
    w = host.workspace

    def open_path(path):
        host.open_path(Path(path))
        host.set_mode("annotate")
        host.set_mode("impose")

    w.open_path = open_path
    w.set_mode("advanced")  # (most tests drive the command forms)
    yield w
    w.runner.stop()
    host.annotations = host.saved = []
    host.drop_work()
    host.close()


def namespace(tokens):
    """Parse a step the way the CLI would (adding placeholder inputs where needed)."""
    cmd = COMMANDS[tokens[0]]
    argv = list(tokens)
    if cmd.needs_input is True:
        argv.insert(1, "in.pdf")
    if tokens[0] == "replay":
        argv.append("in.pdf")
    return vars(build_parser().parse_args(argv))


def test_every_command_has_a_form_with_clean_defaults(app):
    from py_pdftools.gui.impose.forms import CommandForm, subparsers
    parsers = subparsers()
    assert set(parsers) == set(COMMANDS)
    for name, parser in parsers.items():
        form = CommandForm(name, parser)
        assert form.tokens() == [name], f"{name} emits options at their defaults: {form.tokens()}"


ROUND_TRIP = [
    "booklet --binding saddle --paper a4 --margin 1cm --crop-marks --sides separate",
    "nup --cols 2 --rows 2 --scale fit --hspace '0 40' --align center --mirror h --background bg.pdf",
    "step-repeat --paper 9x14in --orientation tall --rotate --align-rows",
    "shuffle --rule '8 1 5* 4* 2 7 3* 6*' --repeat saddle",
    "trim-shift --trim left=1cm --trim top=5mm --shift right=2mm --parity odd",
    "resize --percent 50",
    "text --text 'Page [#] of [Doc:NumPages]' --start 007 --size 12.5 --rotation 90",
    "insert --blank 999 --after LAST-1 --until multiple:4",
    "mask --rect 0,0,3,2 --rect 5,5,1,1",
    "split --by equal --size 4 --part-steps '1=reverse' --merge",
    "run --sequence s.toml a.pdf b.pdf --out-dir out",
    "watch hot --sequence s.toml --interval 5",
    "replay --from done.pdf",
    "booklet --units mm --registration all",
]


@pytest.mark.parametrize("line", ROUND_TRIP)
def test_form_round_trip(app, line):
    from py_pdftools.gui.impose.forms import CommandForm, subparsers
    tokens = shlex.split(line)
    form = CommandForm(tokens[0], subparsers()[tokens[0]])
    form.set_tokens(tokens)
    assert namespace(form.tokens()) == namespace(tokens)


def wait(app, window, timeout=60):
    end = time.time() + timeout
    while (window.runner.busy() or window.timer.isActive()) and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()


def test_preview_apply_undo(app, window, tmp_path):
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "6", "--paper", "a5", "-o", str(sample), "-q"]) == 0
    window.auto.setChecked(False)
    window.open_path(sample)
    window.select_command("nup")
    window.form("nup").set_tokens(["nup", "--cols", "2", "--rows", "1", "--scale", "fit", "--paper", "a4",
                                   "--orientation", "wide"])
    window.preview()
    wait(app, window)
    assert len(window.result_files) == 1
    assert window.res_pane.doc.page_count == 3
    window.apply()
    wait(app, window)
    assert window.source != sample and len(window.host.undo_stack) == 1 and window.host.count == 3
    assert window.src_pane.doc.page_count == 3
    window.undo()
    assert window.source == sample


def test_multiple_outputs_and_errors(app, window, tmp_path):
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "4", "-o", str(sample), "-q"]) == 0
    window.auto.setChecked(False)
    window.open_path(sample)
    window.select_command("evenodd")
    window.form("evenodd").set_tokens(["evenodd", "--mode", "split"])
    window.preview()
    wait(app, window)
    assert [window._suffix(f) for f in window.result_files] == ["even", "odd"]
    window.select_command("shuffle")
    window.form("shuffle").set_tokens(["shuffle", "--rule", "1 2 nonsense"])
    window.preview()
    wait(app, window)
    assert "invalid token" in window.host.statusBar().currentMessage()


def test_sequence_run_on_document(app, window, tmp_path):
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "8", "-o", str(sample), "-q"]) == 0
    window.auto.setChecked(False)
    window.open_path(sample)
    window.seq.set_steps([["text", "--text", "N[#]"], ["booklet", "--binding", "saddle", "--paper", "a3"]])
    window.seq.run_on_document()
    wait(app, window)
    assert len(window.result_files) == 1
    assert window.res_pane.doc.page_count == 4
    window.apply()
    assert len(window.host.undo_stack) == 1 and window.host.count == 4


def test_basic_mode_switch(app, window):
    window.set_mode("basic")
    assert window.current == "impose" and window.form("impose") is window.basic
    assert not window.tree.isVisibleTo(window) and not window.b_add.isVisibleTo(window)
    assert not window.units.isVisibleTo(window)  # (the form has its own Units)
    window.set_mode("advanced")
    assert window.current != "impose" or window.form("impose") is not window.basic
    assert window.tree.isVisibleTo(window)


def test_basic_form_round_trip_and_enabling(app, window):
    window.set_mode("basic")
    b = window.basic
    assert b.tokens() == ["impose"]  # the defaults: 2-up booklet, perfect, Legal landscape
    assert not b.cols.isEnabled() and not b.spread.isEnabled() and b.sheets.isEnabled()
    line = ["impose", "--layout", "8up-booklet", "--binding", "saddle", "--direction", "right", "--gutter-v",
            "1", "--spread", "2", "--creep", "0.1", "--media", "a3", "--orientation", "portrait", "--auto-rotate",
            "--margin-top", "1.5", "--trim-marks", "--registration-marks"]
    b.set_tokens(line)
    assert b.spread.isEnabled() and not b.sheets.isEnabled() and not b.cols.isEnabled()
    assert namespace(b.tokens()) == namespace(line)
    b.set_tokens(["impose", "--layout", "cut-stacks", "--cols", "3", "--rows", "2", "--single-sided",
                  "--media", "20x30cm"])
    assert b.cols.isEnabled() and not b.binding.isEnabled() and b.width.isEnabled()
    assert namespace(b.tokens())["media"] == "20x30cm"


def test_basic_units_convert(app, window):
    window.set_mode("basic")
    b = window.basic
    b.units.setCurrentText("cm")
    b.set_tokens(["impose", "--margin-top", "2.54"])
    b.units.setCurrentText("in")
    assert b.m_top.value() == pytest.approx(1.0)
    assert window.units.currentText() == "in"
    b.units.setCurrentText("cm")


def test_basic_profiles(app, window, monkeypatch):
    window.set_mode("basic")
    b = window.basic
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Cards", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    b.set_tokens(["impose", "--layout", "step-repeat", "--cols", "4", "--rows", "5", "--trim-marks"])
    b.save_profile(new_name=True)
    assert "Cards" in b.profiles() and b.profile.currentData() == "Cards"
    b.on_menu.setChecked(True)
    assert any(a.text() == "Cards" for a in window.m_profiles.actions())
    b.reset()
    assert b.tokens() == ["impose"]
    window._use_profile("Cards")
    assert namespace(b.tokens())["layout"] == "step-repeat" and namespace(b.tokens())["cols"] == 4
    b.delete_profile()
    assert "Cards" not in b.profiles()


def test_basic_preview(app, window, tmp_path):
    example = Path(__file__).resolve().parents[2] / "docs" / "example" / "numbers-100.pdf"
    window.auto.setChecked(False)
    window.open_path(example)
    window.set_mode("basic")
    window.basic.set_tokens(["impose", "--layout", "4up-booklet", "--binding", "saddle", "--media", "a3",
                             "--orientation", "portrait", "--trim-marks"])
    window.preview()
    wait(app, window)
    assert len(window.result_files) == 1
    assert window.res_pane.doc.page_count == 26  # 100 pages -> 104 -> 13 sheets, front and back


def test_show_document_option(app, window, tmp_path):
    from py_pdftools.core import config
    from py_pdftools.gui.window import MainWindow
    assert not window.a_show_document.isChecked()  # off by default
    assert not window.src_pane.isVisibleTo(window)
    window.a_show_document.setChecked(True)
    assert window.src_pane.isVisibleTo(window)
    assert config.get("show_document") is True
    assert "show_document = true" in config.config_path().read_text()
    other = MainWindow()  # (a new window reads the configuration file)
    try:
        ws = other.workspace
        assert ws.a_show_document.isChecked() and ws.src_pane.isVisibleTo(ws)
        ws.a_show_document.setChecked(False)
        assert config.get("show_document") is False
    finally:
        other.close()


def test_basic_defaults_four_sheets_per_fold(app, window):
    from py_pdftools.impose.runner import build_parser
    assert build_parser().parse_args(["impose", "x.pdf"]).sheets_per_fold == 4
    window.basic.reset()
    assert window.basic.sheets.value() == 4 and window.basic.tokens() == ["impose"]
    window.basic.set_tokens(["impose", "--sheets-per-fold", "2"])
    assert window.basic.tokens() == ["impose", "--sheets-per-fold", "2"]


def test_basic_negative_margins_page_trim_enlarge(app, window):
    b = window.basic
    b.reset()
    b.m_left.setValue(-1)
    b.gutter_v.setValue(-0.5)
    b.t_top.setValue(1.5)
    b.enlarge.setChecked(True)
    t = b.tokens()
    assert "--margin-left=-1" in t and "--gutter-v=-0.5" in t and "--enlarge" in t
    assert t[t.index("--page-trim-top") + 1] == "1.5"
    b.reset()
    b.set_tokens(t)
    assert (b.m_left.value(), b.gutter_v.value(), b.t_top.value()) == (-1, -0.5, 1.5)
    assert b.enlarge.isChecked() and b.tokens() == t
    b.auto_scale.setChecked(False)
    assert not b.enlarge.isEnabled() and "--enlarge" not in b.tokens()


def _pages(path) -> int:
    import pikepdf
    with pikepdf.open(path) as pdf:
        return len(pdf.pages)


def test_save_saves_what_the_result_pane_shows(app, window, tmp_path, monkeypatch):
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "8", "--paper", "a5", "-o", str(sample), "-q"]) == 0
    targets = iter([tmp_path / "out1.pdf", tmp_path / "out2.pdf", tmp_path / "out3.pdf"])
    monkeypatch.setattr(window, "_save_target", lambda title, suggested: next(targets))
    window.auto.setChecked(False)
    window.open_path(sample)
    window.select_command("nup")
    window.form("nup").set_tokens(["nup", "--cols", "2", "--rows", "1", "--scale", "fit"])
    window.save()  # (no preview yet: the command runs first, then it is saved)
    wait(app, window)
    assert _pages(tmp_path / "out1.pdf") == 4
    window.apply()  # the right pane now shows the applied document; nothing runs again
    wait(app, window)
    assert window.result_key[0] == "document" and window.res_pane.doc.page_count == 4
    window.save()
    assert _pages(tmp_path / "out2.pdf") == 4  # (not n-up twice)
    window.select_command("reverse")
    window.preview()
    wait(app, window)
    window.save()
    assert _pages(tmp_path / "out3.pdf") == 4


def test_basic_gutters_only_where_there_are_two_columns_or_rows(app, window):
    b = window.basic
    b.reset()
    b.gutter_v.setValue(1)
    b.gutter_h.setValue(2)
    b.layout_type.setCurrentIndex(b.layout_type.findData("2up-booklet"))  # 2 columns, 1 row
    assert b.gutter_v.isEnabled() and not b.gutter_h.isEnabled()
    t = b.tokens()
    assert "--gutter-v" in t and "--gutter-h" not in t
    b.layout_type.setCurrentIndex(b.layout_type.findData("4up-booklet"))  # 2 x 2
    assert b.gutter_v.isEnabled() and b.gutter_h.isEnabled() and "--gutter-h" in b.tokens()
    b.layout_type.setCurrentIndex(b.layout_type.findData("sequential"))
    b.cols.setValue(1)
    b.rows.setValue(2)  # one above the other
    assert not b.gutter_v.isEnabled() and b.gutter_h.isEnabled()
    t = b.tokens()
    assert "--gutter-h" in t and "--gutter-v" not in t


def test_basic_page_info_is_on_by_default(app, window):
    from py_pdftools.impose.runner import build_parser
    assert build_parser().parse_args(["impose", "x.pdf"]).page_info is True
    b = window.basic
    b.reset()
    assert b.page_info.isChecked() and "--no-page-info" not in b.tokens()
    b.page_info.setChecked(False)
    assert "--no-page-info" in b.tokens()
    b.set_tokens(["impose", "--no-page-info"])
    assert not b.page_info.isChecked()
    b.set_tokens(["impose"])
    assert b.page_info.isChecked()
    form = window.form("impose")  # (the advanced form of the same command)
    form.set_tokens(["impose", "--no-page-info"])
    assert form.tokens() == ["impose", "--no-page-info"]
    form.set_tokens(["impose", "--page-info"])
    assert form.tokens() == ["impose"]


def test_basic_locks_keep_two_sides_the_same(app, window):
    from py_pdftools.gui.impose.basic import BasicPanel
    b = window.basic
    b.reset()
    (tb, top, bottom), (lr, left, right) = b.locks[0], b.locks[1]
    assert (top, bottom, left, right) == (b.m_top, b.m_bottom, b.m_left, b.m_right)
    assert len(b.locks) == 4 and b.locks[2][1:] == (b.t_top, b.t_bottom)
    b.m_top.setValue(1.5)
    tb.setChecked(True)  # locking makes the bottom like the top
    assert b.m_bottom.value() == 1.5
    b.m_bottom.setValue(-0.5)  # and then each follows the other
    assert b.m_top.value() == -0.5
    b.m_left.setValue(2)
    assert b.m_right.value() == 0  # (left and right are not locked)
    b.locks[3][0].setChecked(True)
    b.t_left.setValue(0.7)
    assert b.t_right.value() == 0.7
    assert [btn.isChecked() for btn, _, _ in BasicPanel(window).locks] == [False] * 4  # (a new session: open)
    window.carry_options = True  # (as when the window is built again in another language)
    try:
        other = BasicPanel(window)  # the locks are carried over
        assert [btn.isChecked() for btn, _, _ in other.locks] == [True, False, False, True]
    finally:
        window.carry_options = False
    b.set_tokens(["impose", "--margin-top", "1", "--margin-bottom", "2"])  # different values release a lock
    assert not tb.isChecked() and (b.m_top.value(), b.m_bottom.value()) == (1, 2)


def test_save_as_pdfa_or_pdfx(app, window, tmp_path, monkeypatch):
    """File ▸ Save as: what Save saves (running the command first if needed), then given to
    pdf2iso; greyed out without it."""
    from py_pdftools.impose import conform
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "8", "--paper", "a5", "-o", str(sample), "-q"]) == 0
    assert list(window.output_actions) == ["", "a-1b", "a-2b", "a-3b", "x-4"]
    monkeypatch.setattr(conform, "command", lambda path=None: None)
    window._show_output()
    assert window.output_actions[""].isEnabled() and not window.output_actions["x-4"].isEnabled()
    assert "pdf2iso" in window.output_actions["x-4"].toolTip()
    calls = []

    def fake(source, target, standard, password=""):
        calls.append((Path(target), standard))
        return "structural check: PASS"

    monkeypatch.setattr(conform, "command", lambda path=None: ["pdf2iso"])
    monkeypatch.setattr(conform, "convert", fake)
    window._show_output()
    assert window.output_actions["x-4"].isEnabled()
    targets = iter([tmp_path / "out1.pdf", tmp_path / "out2.pdf"])
    monkeypatch.setattr(window, "_save_target", lambda title, suggested: next(targets))
    window.auto.setChecked(False)
    window.open_path(sample)
    window.select_command("nup")
    window.form("nup").set_tokens(["nup", "--cols", "2", "--rows", "1", "--scale", "fit"])
    seen = []
    monkeypatch.setattr(window, "status", lambda text, error=False: seen.append(text))
    window.output_actions["x-4"].trigger()  # (no preview yet: the command runs first)
    wait(app, window)
    assert calls == [(tmp_path / "out1.pdf", "x-4")] and _pages(tmp_path / "out1.pdf") == 4
    assert "Saved out1.pdf — PDF/X-4 (structural check: PASS)" in seen
    window.output_actions[""].trigger()  # (a plain PDF: nothing converted)
    assert len(calls) == 1 and _pages(tmp_path / "out2.pdf") == 4


@pytest.mark.skipif(not __import__("shutil").which("pdf2iso"), reason="pdf2iso not installed")
def test_save_as_pdfx_for_real(app, window, tmp_path, monkeypatch):
    import pikepdf
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "4", "--paper", "a5", "-o", str(sample), "-q"]) == 0
    monkeypatch.setattr(window, "_save_target", lambda title, suggested: tmp_path / "out.pdf")
    window.auto.setChecked(False)
    window.open_path(sample)
    window.select_command("reverse")
    window.preview()
    wait(app, window)
    window.save("x-4")
    with pikepdf.open(tmp_path / "out.pdf") as pdf:
        assert "/OutputIntents" in pdf.Root and "/TrimBox" in pdf.pages[0].obj
