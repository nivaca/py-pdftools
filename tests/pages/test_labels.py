"""Tests of the page labels themselves (labels.py)."""

from __future__ import annotations

import pikepdf
import pytest
from pikepdf import Array, Dictionary, Name

from py_pdftools.pages import labels
from py_pdftools.pages.labels import LabelError, Range, Request

N = 100


def test_numbers():
    assert [labels.to_roman(n) for n in (1, 4, 9, 14, 40, 90, 400, 1994, 3999)] == \
        ["I", "IV", "IX", "XIV", "XL", "XC", "CD", "MCMXCIV", "MMMCMXCIX"]
    assert [labels.to_letters(n) for n in (1, 26, 27, 52, 53)] == ["A", "Z", "AA", "ZZ", "AAA"]
    assert labels.format_number(12, "r") == "xii"
    assert labels.format_number(28, "a") == "bb"
    assert labels.format_number(7, "") == ""


def test_range_labels_and_specs():
    r = Range(215, "D", "App-", 1)
    assert r.label(215) == "App-1" and r.label(217) == "App-3"
    assert r.spec() == "215:D:1:App-"
    assert Range(9).spec() == "9:D"
    assert Range(1, "r", start=5).spec() == "1:r:5"
    assert Range(100, "", "Cover").spec() == "100:-::Cover"
    assert Range(100, "", "Cover").label(100) == "Cover"


@pytest.mark.parametrize("spec, expected", [
    ("9", (9, None)), ("9-20", (9, 20)), ("9..20", (9, 20)), ("90-", (90, N)),
    ("LAST", (N, None)), ("LAST-2", (N - 2, None)), ("last-2-LAST", (N - 2, N)), ("1..LAST-1", (1, N - 1)),
])
def test_pages(spec, expected):
    assert labels.parse_pages(spec, N) == expected


@pytest.mark.parametrize("spec", ["0", "101", "20-9", "x", "LAST-100", "9-x"])
def test_bad_pages(spec):
    with pytest.raises(LabelError):
        labels.parse_pages(spec, N)


def test_compact_and_named():
    assert labels.parse_compact("1:r", N) == Request(Range(1, "r"))
    assert labels.parse_compact("20-30:roman:3", N) == Request(Range(20, "r", "", 3), 30)
    assert labels.parse_compact("50:D:1:A:B", N) == Request(Range(50, "D", "A:B", 1))  # (colons in the prefix)
    assert labels.parse_compact("LAST:-::Cover", N) == Request(Range(N, "", "Cover", 1))
    assert labels.parse_compact("5:none:1:x", N) == Request(Range(5, "", "x", 1))
    assert labels.parse_named(["9-20", "style=LETTERS", "prefix=P-", "start=2"], N) == \
        Request(Range(9, "A", "P-", 2), 20)
    assert labels.parse_named(["9"], N) == Request(Range(9, "D"))
    for bad in ("9", "9:Q", "9:D:0", "9:D:x"):
        with pytest.raises(LabelError):
            labels.parse_compact(bad, N)
    for bad in ([], ["9", "colour=red"], ["9", "style"]):
        with pytest.raises(LabelError):
            labels.parse_named(bad, N)


def test_apply():
    book = labels.apply([], [labels.parse_compact(s, N) for s in ("1:r", "9:D")], N)
    assert book == [Range(1, "r"), Range(9, "D")]
    assert labels.page_labels(book, N)[:10] == ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "1", "2"]
    # a span: the pages after it keep the numbers they had
    out = labels.apply(book, [labels.parse_compact("50-52:A", N)], N)
    assert out == [Range(1, "r"), Range(9, "D"), Range(50, "A"), Range(53, "D", "", 45)]
    assert labels.page_labels(out, N)[48:54] == ["41", "A", "B", "C", "45", "46"]
    # no last page: up to the next range
    out = labels.apply(out, [labels.parse_compact("20:R", N)], N)
    assert labels.page_labels(out, N)[19:50] == [labels.to_roman(i) for i in range(1, 31)] + ["A"]
    # removing a range: the one before goes on
    out = labels.apply(out, [], N, remove=[20])
    assert out == [Range(1, "r"), Range(9, "D"), Range(50, "A"), Range(53, "D", "", 45)]
    with pytest.raises(LabelError):
        labels.apply(out, [], N, remove=[1])
    with pytest.raises(LabelError):
        labels.apply(out, [], N, remove=[21])
    # spans are laid over the ranges without a last page, whatever their order
    for order in (("50-52:A", "9:D"), ("9:D", "50-52:A")):
        out = labels.apply([], [labels.parse_compact(s, N) for s in order], N)
        assert out == [Range(1), Range(9, "D"), Range(50, "A"), Range(53, "D", "", 45)]
    # ranges that give the same numbering as the one before are merged
    assert labels.apply([], [labels.parse_compact("10:D:10", N)], N) == [Range(1)]


def test_normalize_and_spans():
    assert labels.normalize([Range(9, "D"), Range(1, "r"), Range(9, "A")]) == [Range(1, "r"), Range(9, "A")]
    assert labels.normalize([Range(5, "r")]) == [Range(1), Range(5, "r")]
    assert labels.spans([Range(1, "r"), Range(9)], 20) == [(Range(1, "r"), 8), (Range(9), 20)]
    assert labels.page_labels([], 3) == ["1", "2", "3"]
    assert labels.describe(Range(1, "r"), 8) == "i … viii"
    assert labels.describe(Range(5, "", "X"), 9) == "X (every page)"


def test_read_and_write(tmp_path):
    src = tmp_path / "a.pdf"
    with pikepdf.new() as pdf:
        for _ in range(N):
            pdf.add_blank_page()
        ranges = [Range(1, "r"), Range(9, "D"), Range(90, "A", "App-"), Range(96, "D", "", 96),
                  Range(100, "", "Cover")]
        labels.write_labels(pdf, ranges)
        pdf.save(src)
    with pikepdf.open(src) as pdf:
        assert labels.read_labels(pdf) == ranges
        d = pdf.Root.PageLabels.Nums[1]
        assert d.Type == Name.PageLabel and d.S == Name.r and "/St" not in d
        assert "/S" not in pdf.Root.PageLabels.Nums[9]  # (no number: no /S)
        labels.write_labels(pdf, [])
        assert "/PageLabels" not in pdf.Root


def test_reading_odd_trees():
    with pikepdf.new() as pdf:
        for _ in range(10):
            pdf.add_blank_page()
        kid1 = pdf.make_indirect(Dictionary(Nums=Array([0, Dictionary(S=Name.r)])))
        kid2 = pdf.make_indirect(Dictionary(Nums=Array([
            4, Dictionary(S=Name.D, St=0),  # (a start below 1: 1)
            6, Dictionary(S=Name.Q),  # (an unknown style: no number)
            50, Dictionary(S=Name.D),  # (beyond the document: ignored)
            "x", Dictionary(S=Name.D)])))  # (not a number)
        pdf.Root.PageLabels = Dictionary(Kids=Array([kid1, kid2, kid1]))  # (kid1 twice)
        assert labels.read_labels(pdf) == [Range(1, "r"), Range(5, "D"), Range(7, "")]
        pdf.Root.PageLabels = Dictionary(Nums=Array([3, Dictionary(S=Name.R)]))  # (nothing at page 1)
        assert labels.read_labels(pdf) == [Range(1), Range(4, "R")]


# =========================================================================== folios, suffixes, lists


def test_folios():
    assert [labels.to_folio(s) for s in (1, 2, 3, 24)] == ["1r", "1v", "2r", "12v"]
    r = labels.parse_compact("5-90:f:12v", N).range
    assert r == Range(5, "f", "", 24) and r.virtual
    assert [r.label(p) for p in (5, 6, 7)] == ["12v", "13r", "13v"]
    assert r.spec() == "5:f:12v" and labels.parse_compact(r.spec(), N).range == r
    assert labels.parse_compact("5:folio", N).range == Range(5, "f", "", 1)
    assert labels.parse_named(["5", "style=folio", "start=3"], N).range.start == 5  # (3 = 3r)
    with pytest.raises(LabelError, match="leaf and its side"):
        labels.parse_compact("5:f:3x", N)


def test_suffixes():
    r = labels.parse_named(["1-4", "style=roman", "prefix=[", "suffix=]"], N).range
    assert r.label(2) == "[ii]" and r.virtual
    assert r.tokens() == ["--range", "1", "style=roman", "prefix=[", "suffix=]"]
    assert labels.parse_named(r.tokens()[1:], N).range == r
    assert Range(3, "", "x", 1, "y") == Range(3, "", "xy")  # (no number: one text)


def test_from_labels():
    book = ["[i]", "[ii]", "iii", "iv", "1", "2", "3", "3bis", "4", "A-1", "A-2", "1r", "1v", "2r",
            "5r", "5v", "Cover"]
    ranges = labels.from_labels(book)
    assert labels.page_labels(ranges, len(book)) == book
    assert ranges == [Range(1, "r", "[", 1, "]"), Range(3, "r", "", 3), Range(5), Range(8, "", "3bis"),
                      Range(9, "D", "", 4), Range(10, "D", "A-"), Range(12, "f"), Range(15, "f", "", 9),
                      Range(17, "", "Cover")]
    assert labels.from_labels(["c", "d", "e"]) == [Range(1, "a", "", 3)]  # (letters, not roman 100, 500)
    assert labels.from_labels(["x"]) == [Range(1, "r", "", 10)]
    assert labels.from_labels(["", ""]) == [Range(1, "", "")]
    assert labels.from_labels(["x", "x", "x", "4"]) == [Range(1, "", "x"), Range(4, "D", "", 4)]
    for odd in (["007", "008"], ["1.1", "1.2", "2.1"], ["iiii"], ["Chapter v", "Chapter vi"]):
        assert labels.page_labels(labels.from_labels(odd), len(odd)) == odd


def test_virtual_ranges_in_the_file(tmp_path):
    ranges = [Range(1, "r", "[", 1, "]"), Range(5, "D"), Range(50, "f", "", 3), Range(98, "", "Cover")]
    with pikepdf.new() as pdf:
        for _ in range(N):
            pdf.add_blank_page()
        labels.write_labels(pdf, ranges)
        nums = pdf.Root.PageLabels.Nums
        assert len(nums) == 2 * (4 + 1 + 48 + 1)  # (one entry for each page of the virtual ranges)
        assert str(nums[1].P) == "[i]" and "/S" not in nums[1]
        assert str(nums[2 * 5 + 1].P) == "2r"
        pdf.save(tmp_path / "v.pdf")
    with pikepdf.open(tmp_path / "v.pdf") as pdf:
        assert labels.read_labels(pdf) == ranges
        assert len(labels.read_native(pdf)) == 54


def test_find_label():
    ranges = [Range(1, "r"), Range(9)]
    assert labels.find_label(ranges, N, "xii") == []
    assert labels.find_label(ranges, N, "vii") == [7]
    assert labels.find_label(ranges, N, "VII") == [7]  # (ignoring case)
    assert labels.find_label(ranges, N, "7") == [15]


# =========================================================================== chosen pages


def test_blocks():
    assert labels.blocks([9, 3, 4, 5, 4]) == [(3, 5), (9, 9)]
    assert labels.blocks([]) == []


def test_number_pages():
    book = [Range(1, "r"), Range(9)]
    out = labels.number_pages(book, N, [20, 21, 22], "A", "Plate ")
    assert labels.page_labels(out, N)[18:24] == ["11", "Plate A", "Plate B", "Plate C", "15", "16"]
    out = labels.number_pages(book, N, [30, 32, 34], "D", "", 5)  # (not consecutive: one after the other)
    assert labels.page_labels(out, N)[29:34] == ["5", "23", "6", "25", "7"]
    out = labels.number_pages(book, N, [50, 51], "f", start=3)
    assert labels.page_labels(out, N)[49:52] == ["2r", "2v", "44"]


def test_continue_numbering():
    book = [Range(1, "r"), Range(9), Range(20, "", "Plate"), Range(22, "D", "", 12)]
    out = labels.continue_numbering(book, N, [20, 21])  # (the pages after them keep their numbers)
    assert out == [Range(1, "r"), Range(9), Range(22, "D", "", 12)]
    assert labels.continue_numbering(book, N, [20, 21, 22, 23]) == [Range(1, "r"), Range(9), Range(24, "D", "", 14)]
    assert labels.continue_numbering([Range(1, "", "Cover"), Range(2)], N, [2]) == \
        [Range(1, "", "Cover"), Range(3, "D", "", 2)]
    with pytest.raises(LabelError):
        labels.continue_numbering(book, N, [1])


def test_relabel():
    book = [Range(1, "r"), Range(9)]
    out = labels.relabel(book, N, {20: "Map", 21: "12bis", 40: "x", 41: "xi"})
    got = labels.page_labels(out, N)
    assert got[18:23] == ["11", "Map", "12bis", "14", "15"] and got[39:42] == ["x", "xi", "34"]
