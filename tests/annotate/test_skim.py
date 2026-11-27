"""Skim's notes (.skim files), in both its forms (a property list, and an archive of NSKeyedArchiver), imported
as annotations in their places."""

from __future__ import annotations

import datetime
import plistlib

import pymupdf
import pytest

from py_pdftools.annotate import annots, skim
from py_pdftools.annotate.annots import AnnotateError

RTF = (rb"{\rtf1\ansi\ansicpg1252\cocoartf2580{\fonttbl\f0\fswiss Helvetica;}{\colortbl;\red255\green255\blue255;}"
       b"\\f0\\fs24 \\cf0 Long text, with an \\'e9 and \\u8212  a dash\\par second line}")
WHEN = datetime.datetime(2026, 11, 26, 12, 30, tzinfo=datetime.UTC)


def notes(colour, font=None):
    """Notes of every kind on page 1 of SAMPLE (595 x 842 points); COLOUR(r, g, b, a) makes a colour, FONT(name,
    size) a font (else the property list's keys)."""
    freetext = {"type": "FreeText", "pageIndex": 0, "bounds": "{{300, 500}, {150, 40}}", "contents": "Typed",
                "color": colour(1, 1, 0, 1), "fontColor": colour(0, 0, 1, 1), "alignment": 1}
    freetext.update({"font": font("Times-Roman", 14)} if font else {"fontName": "Times-Roman", "fontSize": 14})
    return [
        {"type": "Square", "pageIndex": 0, "bounds": "{{100, 700}, {50, 40}}", "contents": "a box",
         "color": colour(1, 0, 0, 1), "interiorColor": colour(0, 1, 0, 1), "lineWidth": 2.0,
         "userName": "Ana", "modificationDate": WHEN},
        {"type": "Highlight", "pageIndex": 0, "bounds": "{{72, 760}, {200, 14}}",
         "quadrilateralPoints": ["{0, 14}", "{200, 14}", "{0, 0}", "{200, 0}"], "color": colour(1, 1, 0, 0.5)},
        {"type": "Line", "pageIndex": 0, "bounds": "{{100, 100}, {100, 50}}", "startPoint": "{0, 0}",
         "endPoint": "{100, 50}", "startLineStyle": 0, "endLineStyle": 5, "color": colour(0, 0, 0, 1)},
        {"type": "Ink", "pageIndex": 0, "bounds": "{{50, 300}, {40, 40}}",
         "pointLists": [["{0, 0}", "{10, 20}", "{40, 40}"]], "color": colour(0, 0, 1, 1)},
        {"type": "Note", "pageIndex": 1, "bounds": "{{200, 400}, {16, 16}}", "contents": "Label", "iconType": 1,
         "text": RTF if font is None else "Long text, with an é and — a dash\nsecond line"},
        freetext,
        {"type": "Widget", "pageIndex": 0, "bounds": "{{0, 0}, {10, 10}}"},  # (a form field: left out)
        {"type": "Circle", "pageIndex": 9, "bounds": "{{0, 0}, {10, 10}}"},  # (no such page: left out)
    ]


def plist_colour(r, g, b, a):
    return [r, g, b, a]


class Archiver:
    """A minimal NSKeyedArchiver, as Cocoa lays out its files: objects in a table, referred to by UID."""

    def __init__(self):
        self.objects = ["$null"]
        self.classes = {}

    def cls(self, name):
        if name not in self.classes:
            self.objects.append({"$classname": name, "$classes": [name, "NSObject"]})
            self.classes[name] = plistlib.UID(len(self.objects) - 1)
        return self.classes[name]

    def add(self, value):
        if isinstance(value, (int, float, bool)) and not isinstance(value, datetime.datetime):
            return value
        index = len(self.objects)
        self.objects.append(None)
        if isinstance(value, str):
            self.objects[index] = value
        elif isinstance(value, bytes):
            self.objects[index] = {"NS.data": value, "$class": self.cls("NSData")}
        elif isinstance(value, list):
            self.objects[index] = {"NS.objects": [self.add(v) for v in value], "$class": self.cls("NSArray")}
        elif isinstance(value, datetime.datetime):
            self.objects[index] = {"NS.time": (value - skim._EPOCH).total_seconds(), "$class": self.cls("NSDate")}
        elif isinstance(value, tuple) and value[0] == "color":
            self.objects[index] = {"NSColorSpace": 2, "NSRGB": " ".join(map(str, value[1:])).encode() + b"\0",
                                   "$class": self.cls("NSColor")}
        elif isinstance(value, tuple) and value[0] == "font":
            self.objects[index] = {"NSName": self.add(value[1]), "NSSize": value[2], "$class": self.cls("NSFont")}
        elif isinstance(value, tuple) and value[0] == "attributed":
            self.objects[index] = {"NSString": self.add(value[1]), "$class": self.cls("NSAttributedString")}
        elif isinstance(value, dict):
            keys = [self.add(k) for k in value]
            self.objects[index] = {"NS.keys": keys, "NS.objects": [self.add(v) for v in value.values()],
                                   "$class": self.cls("NSDictionary")}
        return plistlib.UID(index)

    def data(self, root) -> bytes:
        top = self.add(root)
        return plistlib.dumps({"$version": 100000, "$archiver": "NSKeyedArchiver", "$top": {"root": top},
                               "$objects": self.objects}, fmt=plistlib.FMT_BINARY)


def archived():
    found = notes(lambda r, g, b, a: ("color", r, g, b, a), font=lambda name, size: ("font", name, size))
    note = found[4]
    note["text"] = ("attributed", note["text"])
    return Archiver().data(found)


@pytest.mark.parametrize("form", ["plist", "archive"])
def test_import(sample, tmp_path, form):
    source = tmp_path / "sample.skim"
    if form == "plist":
        found = notes(plist_colour)
        found[0]["modificationDate"] = WHEN.replace(tzinfo=None)  # (plistlib's dates are in UTC, without a zone)
        source.write_bytes(plistlib.dumps(found, fmt=plistlib.FMT_BINARY))
    else:
        source.write_bytes(archived())
    doc = annots.open_pdf(sample)
    got = skim.import_skim(doc, source)
    assert [a.kind for a in got] == ["rect", "highlight", "arrow", "ink", "note", "freetext"]
    box, mark, arrow, ink, note, text = got
    # (from the bottom left, in Skim; from the top left, here: y = 842 - y)
    assert box.rect == (100, 102, 150, 142) and (box.color, box.fill, box.width) == ("#ff0000", "#00ff00", 2.0)
    assert (box.contents, box.author, box.modified) == ("a box", "Ana", "D:20261126123000Z")
    assert mark.quads == ((72, 68, 272, 82),) and mark.color == "#ffff00" and mark.opacity == 0.5
    assert arrow.paths == (((100, 742), (200, 692)),) and arrow.ends == ("None", "ClosedArrow")
    assert ink.paths == (((50, 542), (60, 522), (90, 502)),)
    assert note.page == 1 and note.icon == "Key"
    assert note.contents == "Label\n\nLong text, with an é and — a dash\nsecond line"
    assert (text.color, text.fill, text.font, text.font_size, text.align) == ("#0000ff", "#ffff00", "tiro", 14, "center")
    # Written into the PDF, they are read back as they were imported.
    target = tmp_path / "out.pdf"
    assert annots.write(sample, got, target) == 6
    back = annots.read(annots.open_pdf(target))
    assert sorted(a.kind for a in back) == sorted(a.kind for a in got)


def test_page_turned(sample, tmp_path):
    # Page 3 of SAMPLE is turned 90 degrees: the note goes where the same rectangle of the PDF is shown.
    source = tmp_path / "turned.skim"
    source.write_bytes(plistlib.dumps([{"type": "Square", "pageIndex": 2, "bounds": "{{100, 700}, {50, 40}}"}]))
    doc = annots.open_pdf(sample)
    (got,) = skim.import_skim(doc, source)
    with pymupdf.open(sample) as d:
        page = d[2]
        # (MuPDF's own rectangle for that place of the PDF, turned as the page is shown)
        real = pymupdf.Rect(100, 842 - 740, 150, 842 - 700) if page.mediabox.height == 842 else None
        shown = (real * page.rotation_matrix).normalize()
    assert all(abs(a - b) < 0.01 for a, b in zip(got.rect, (shown.x0, shown.y0, shown.x1, shown.y1)))


def test_not_skim(tmp_path, sample):
    source = tmp_path / "bad.skim"
    source.write_bytes(b"not a plist")
    with pytest.raises(AnnotateError):
        skim.import_skim(annots.open_pdf(sample), source)
    source.write_bytes(plistlib.dumps({"a": 1}))
    with pytest.raises(AnnotateError):
        skim.import_skim(annots.open_pdf(sample), source)


def test_rtf():
    assert skim.rtf_text(RTF) == "Long text, with an é and — a dash\nsecond line"
