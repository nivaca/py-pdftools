"""Skim's notes (.skim files), in both its forms (a property list, and an archive of NSKeyedArchiver), imported
as annotations in their places."""

from __future__ import annotations

import dataclasses
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


# --------------------------------------------------------------------- export

def made(page=0):
    """Annotations of every kind Skim has, on PAGE of SAMPLE, as py-pdftools keeps them."""
    A = annots.Annotation
    return [
        A("rect", page, (100, 100, 150, 140), "#ff0000", fill="#00ff00", width=2.0, contents="a box",
          author="Ana", modified="D:20261126123000Z", dashed=True),
        A("ellipse", page, (200, 100, 260, 150), "#0000ff", width=1.0),
        A("highlight", page, (72, 60, 272, 88), "#ffeb3b", opacity=0.5,
          quads=((72, 60, 272, 74), (72, 74, 200, 88)), contents="marked"),
        A("strikeout", page, (72, 200, 172, 214), "#ff0000", quads=((72, 200, 172, 214),)),
        A("line", page, annots.frame("line", (((100, 300), (200, 350)),), 1.5), "#000000",
          paths=(((100, 300), (200, 350)),), ends=("Circle", "ClosedArrow")),
        A("ink", page, annots.frame("ink", (((50, 400), (60, 420), (90, 440)),), 1.5), "#0000ff",
          paths=(((50, 400), (60, 420), (90, 440)),)),
        A("note", page, (300, 300, 316, 316), "#ffd54f", icon="Key", contents="Label\n\nThe long text, with é — "
          "and 😀\nand a second line"),
        A("freetext", page, (300, 500, 450, 540), "#0000ff", fill="#ffff00", width=0.0, contents="Typed {here}",
          font="tiro", font_size=14.0, align="center"),
    ]


def comparable(a):
    """What a round trip through Skim keeps of A."""
    return (a.kind, a.page, tuple(round(v, 1) for v in a.rect), a.color, a.fill, a.contents, a.author,
            a.modified, a.dashed, a.icon, a.ends, a.font, a.font_size, a.align, round(a.opacity, 2),
            tuple(tuple(round(v, 1) for v in q) for q in a.quads),
            tuple(tuple((round(x, 1), round(y, 1)) for x, y in path) for path in a.paths))


@pytest.mark.parametrize("page", [0, 2])  # (page 3 of SAMPLE is turned 90 degrees)
def test_export_and_back(sample, tmp_path, page):
    doc = annots.open_pdf(sample)
    mine = made(page)
    target = tmp_path / "sample.skim"
    assert skim.export_skim(doc, mine, target) == len(mine)
    data = target.read_bytes()
    assert data.startswith(b"bplist00")  # (the binary property list, as Skim writes it)
    notes = plistlib.loads(data, aware_datetime=True)
    # Cada color con sus cuatro componentes: Skim lee siempre cuatro.
    for note in notes:
        for key in ("color", "interiorColor", "fontColor"):
            assert key not in note or len(note[key]) == 4
    assert [n["type"] for n in notes] == ["Square", "Circle", "Highlight", "StrikeOut", "Line", "Ink", "Note",
                                          "FreeText"]
    assert notes[6]["contents"] == "Label" and notes[6]["iconType"] == 1
    assert notes[0]["modificationDate"] == WHEN.replace(minute=30, second=0)
    back = skim.import_skim(doc, target)
    for one, other in zip(mine, back):
        if one.kind in ("line", "ink"):  # (their frame is made again, from the points)
            one = dataclasses.replace(one, rect=other.rect)
        assert comparable(one) == comparable(other), one.kind


def test_export_what_skim_lacks(sample, tmp_path):
    A = annots.Annotation
    doc = annots.open_pdf(sample)
    target = tmp_path / "other.skim"
    items = [A("squiggly", 0, (72, 60, 172, 74), quads=((72, 60, 172, 74),)),
             A("polygon", 0, (10, 10, 60, 60), paths=(((10, 10), (60, 10), (35, 60)),)),
             A("area", 0, (100, 100, 200, 200), "#ffeb3b", opacity=0.4),
             A("callout", 0, (300, 300, 400, 340), "#000000", contents="said", paths=(((250, 250),),)),
             A("caret", 0, (10, 10, 20, 20)), A("stamp", 0, (10, 10, 100, 50), stamp="Draft"),
             A("rect", 7, (10, 10, 20, 20))]  # (no such page)
    assert skim.export_skim(doc, items, target) == 4
    notes = plistlib.loads(target.read_bytes())
    assert [n["type"] for n in notes] == ["Underline", "Ink", "Square", "FreeText"]
    # El polígono se cierra: su trazo vuelve al primer punto.
    assert notes[1]["pointLists"][0][0] == notes[1]["pointLists"][0][-1]
    assert notes[2]["interiorColor"][3] == 0.4 and notes[2]["color"][3] == 0
    assert [a.kind for a in skim.import_skim(doc, target)] == ["underline", "ink", "rect", "freetext"]


def test_rtf_back():
    text = "a\\b {x}\né — 😀\tend"
    assert skim.rtf_text(skim.rtf_of(text)) == text
