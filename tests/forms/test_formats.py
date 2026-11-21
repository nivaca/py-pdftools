"""The standard form functions done in Python (forms/formats.py): their calls read from the scripts; numbers,
percentages, dates and special formats checked and shown; ranges; and sums in the calculation order."""

from __future__ import annotations

import datetime as dt

import pymupdf
import pytest
from sample_form import make

from py_pdftools.forms import fields
from py_pdftools.forms import formats as F


@pytest.fixture(scope="module")
def by(tmp_path_factory):
    path = make(tmp_path_factory.mktemp("f") / "f.pdf")
    doc = pymupdf.open(path)
    return {f.name: f for f in fields.read(doc)} | {"_order": F.calculation_order(doc)}


def test_calls():
    assert F.calls('AFSimple_Calculate("SUM", new Array ("a", "b"));\nAFNumber_Format(2,0,0,0,"€",false);') == \
        [("AFSimple_Calculate", ["SUM", ["a", "b"]]), ("AFNumber_Format", [2, 0, 0, 0, "€", False])]
    assert F.calls("event.value = 3;") == []


@pytest.mark.parametrize("text, style, value", [("1,234.50", 0, 1234.5), ("1.234,50", 2, 1234.5),
                                                ("(12)", 0, -12.0), ("$ 7", 0, 7.0), ("x", 0, None), ("", 0, None)])
def test_number(text, style, value):
    assert F.number(text, style) == value


def test_number_formats():
    assert F.format_number(1234.567, 2, 0, 0, "$", True) == "$1,234.57"
    assert F.format_number(-1234.5, 1, 2, 2, " €", False) == "(1.234,5 €)"
    assert F.format_number(-3, 0, 1) == "-3"
    assert F.plain(12.50) == "12.5" and F.plain(3.0) == "3" and F.plain(-0.0) == "0"


def test_dates():
    when = dt.datetime(2026, 7, 3, 14, 5)
    assert F.write_date(when, "dd/mm/yyyy") == "03/07/2026"
    assert F.write_date(when, "mmm d, yyyy") == "Jul 3, 2026"
    assert F.write_date(when, "h:MM tt") == "2:05 pm"
    assert F.read_date("3 July 2026", "d mmmm yyyy") == dt.datetime(2026, 7, 3)
    assert F.read_date("2:05 pm", "h:MM tt").hour == 14
    assert F.read_date("1/2/99", "m/d/yy") == dt.datetime(1999, 1, 2)
    assert F.read_date("nonsense", "dd/mm/yyyy") is None


def test_check_and_shown(by):
    assert F.check(by["qty"], "3") == "3" and F.shown(by["qty"], "1200") == "1,200"
    assert F.check(by["price"], "$1,234.5") == "1234.5" and F.shown(by["price"], "1234.5") == "$1,234.50"
    assert F.shown(by["share"], "0.125") == "12.5%" and F.check(by["share"], "50%") == "0.5"
    assert F.check(by["when"], "2026-07-03") == "03/07/2026"
    assert F.check(by["phone"], "(555) 123-4567") == "5551234567"
    assert F.shown(by["phone"], "5551234567") == "(555) 123-4567"
    assert F.check(by["name"], "anything") == "anything" and F.check(by["price"], " ") == ""
    for name, text in (("price", "abc"), ("when", "31/02/2026"), ("share", "1.5"), ("phone", "123")):
        with pytest.raises(F.Refused):
            F.check(by[name], text)


def test_calculate(by):
    found = [f for n, f in by.items() if n != "_order"]
    assert by["_order"] == ["total"]
    assert F.calculate(found, {"price": "10", "tax": "2.5"}, by["_order"]) == {"total": "12.5"}
    assert F.calculate(found, {"price": "10", "tax": "", "total": "10"}, by["_order"]) == {}
