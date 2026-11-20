"""Annotations written to a PDF and read back from it."""

from __future__ import annotations

import dataclasses

import pymupdf
import pytest

from py_pdftools.annotate import annots, exchange
from py_pdftools.annotate.annots import Annotation


def lines(path, page: int) -> list[annots.Rect]:
    """The two lines of text of PAGE of the sample, as the page is shown."""
    found = annots.words(pymupdf.open(path)[page])
    return annots.text_rects(found, 0, len(found) - 1)


def one_of_each(path, page: int) -> list[Annotation]:
    first, second = lines(path, page)
    tri = ((60.0, 500.0), (160.0, 520.0), (110.0, 580.0))
    zig = ((300.0, 760.0), (340.0, 780.0), (380.0, 760.0))
    cloud = ((420.0, 600.0), (520.0, 600.0), (520.0, 680.0), (420.0, 680.0))
    return [
        Annotation("highlight", page, first, quads=(first,), contents="look"),
        Annotation("underline", page, second, "#1e88e5", quads=(second,)),
        Annotation("strikeout", page, first, "#e53935", quads=(first,)),
        Annotation("squiggly", page, annots.union([first, second]), "#43a047", quads=(first, second)),
        Annotation("caret", page, (500, 150) + tuple(map(sum, zip((500, 150), annots.shown_size(90 if page == 2 else 0, annots.CARET_SIZE)))),
                   "#1e88e5", contents="insert this"),
        Annotation("note", page, (300, 200, 316, 216), "#ffd54f", contents="A note", author="Me", icon="Key"),
        Annotation("freetext", page, (300, 300, 480, 340), "#0000ff", fill="#ffff00", contents="Some text",
                   font_size=14, width=0, font="tiro", align="center"),
        Annotation("freetext", page, (300, 250, 480, 290), "#000000", contents="Bordered", width=1, dashed=True,
                   font="cour"),
        Annotation("callout", page, (380, 350, 540, 390), "#000000", fill="#ffffff", contents="Look here", width=0,
                   paths=(((320.0, 420.0),),), ends=("None", "ClosedArrow")),
        Annotation("area", page, (60, 440, 200, 480), "#ffeb3b", fill="#ffeb3b", opacity=0.4, width=0),
        Annotation("rect", page, (100, 400, 200, 430), "#ff0000", fill="#00ff00", width=2, opacity=0.5,
                   dashed=True, locked=True),
        Annotation("ellipse", page, (250, 400, 350, 460), "#ff0000", width=3),
        Annotation("polygon", page, annots.frame("polygon", (tri,), 1.5), "#000000", fill="#c0c0c0", paths=(tri,)),
        Annotation("cloud", page, annots.frame("cloud", (cloud,), 1.5), "#e53935", paths=(cloud,)),
        Annotation("line", page, annots.frame("line", (((100, 600), (300, 650)),), 2), "#000000", width=2,
                   paths=(((100, 600), (300, 650)),), ends=("Circle", "Square")),
        Annotation("arrow", page, annots.frame("arrow", (((100, 700), (300, 700)),), 2), "#000000", width=2,
                   paths=(((100, 700), (300, 700)),), ends=("OpenArrow", "OpenArrow")),
        Annotation("polyline", page, annots.frame("polyline", (zig,), 1.5), "#000000", paths=(zig,),
                   ends=("None", "ClosedArrow")),
        Annotation("ink", page, annots.frame("ink", (((100, 740), (120, 760), (150, 730)),), 1.5), "#1e88e5",
                   paths=(((100, 740), (120, 760), (150, 730)),)),
        Annotation("stamp", page, (300, 480, 460, 520), "#000000", stamp="Approved", contents="ok"),
    ]


def close(a, b, tolerance=1.5):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


@pytest.mark.parametrize("page", [0, 2])  # (page 3 is turned)
def test_round_trip(sample, tmp_path, page):
    wanted = one_of_each(sample, page)
    target = tmp_path / "out.pdf"
    assert annots.write(sample, wanted, target) == len(wanted)
    doc = annots.open_pdf(target)
    got = annots.read(doc)
    assert [a.kind for a in got] == [a.kind for a in wanted]
    for w, g in zip(wanted, got):
        assert g.page == page and g.xref and g.created and g.modified
        assert g.color == w.color or w.kind == "stamp", w.kind  # (a standard stamp has its own)
        assert g.fill == w.fill, w.kind
        assert g.contents == w.contents and g.author == w.author
        assert abs(g.opacity - w.opacity) < 0.01
        assert (g.dashed, g.locked, g.ends) == (w.dashed, w.locked, w.ends), w.kind
        if w.kind in annots.MARKUP:
            assert all(close(a, b) for a, b in zip(g.quads, w.quads))
        elif w.paths and w.kind != "callout":
            assert all(close(p, q, 0.5) for path_g, path_w in zip(g.paths, w.paths) for p, q in zip(path_g, path_w))
            assert g.width == w.width
        elif w.kind == "stamp":
            assert g.stamp == "Approved" and g.image.startswith(b"\x89PNG")
            # (MuPDF gives a standard stamp its own proportions, around the same centre)
            centre = lambda r: ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
            assert close(centre(g.rect), centre(w.rect), 3)
        else:
            assert close(g.rect, w.rect), (w.kind, g.rect, w.rect)
        if w.kind in annots.TEXTUAL:
            assert (g.font_size, g.font, g.align, g.width) == (w.font_size, w.font, w.align, w.width)
        if w.kind == "callout":
            assert close(g.paths[0][0], w.paths[0][0], 0.5)
        if w.kind == "note":
            assert g.icon == "Key"
    assert annots.text_under(doc[page], got[0].quads) == f"First line of page {page + 1}"


def test_only_changes_are_written(sample, tmp_path):
    first = tmp_path / "first.pdf"
    annots.write(sample, one_of_each(sample, 0), first)
    got = annots.read(annots.open_pdf(first))
    xrefs = {a.kind: a.xref for a in got}
    stamp = next(a for a in got if a.kind == "stamp")
    # the rectangle moved, the note deleted, a new ellipse; the rest as it was
    changed = [annots.moved(a, 10, 0) if a.kind in ("rect", "stamp") else a for a in got if a.kind != "note"]
    changed.append(Annotation("ellipse", 1, (10, 10, 50, 50), "#000000"))
    second = tmp_path / "second.pdf"
    assert annots.write(first, changed, second) == 3
    again = annots.read(annots.open_pdf(second))
    kinds = [a.kind for a in again]
    assert "note" not in kinds and kinds.count("ellipse") == 2
    assert {a.kind: a.xref for a in again if a.page == 0}["highlight"] == xrefs["highlight"]  # (untouched)
    rect = next(a for a in again if a.kind == "rect")
    assert close(rect.rect, (110, 400, 210, 430))
    moved_stamp = next(a for a in again if a.kind == "stamp")
    assert moved_stamp.xref == stamp.xref and close(moved_stamp.rect[:2], (stamp.rect[0] + 10, stamp.rect[1]))


def _watermark_annotation(doc, page, rect) -> int:
    """A /Watermark annotation on PAGE of DOC (one of the kinds no tool makes): its xref."""
    xref = doc.get_new_xref()
    doc.update_object(xref, "<</Type/Annot/Subtype/Watermark/Rect[%g %g %g %g]/F 4>>" % rect)
    kind, value = doc.xref_get_key(doc[page].xref, "Annots")
    doc.xref_set_key(doc[page].xref, "Annots", (value.rstrip("]") if kind == "array" else "[") + f" {xref} 0 R]")
    return xref


def test_other_annotations_are_kept(sample, tmp_path):
    """Annotations of other kinds (a watermark annotation, a link) are read, to be listed, locked, and
    kept as they are: neither changed nor taken out, whatever is given for them."""
    doc = pymupdf.open(sample)
    doc[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(60, 60, 200, 80), "uri": "https://example.org"})
    _watermark_annotation(doc, 0, (300, 500, 400, 520))
    doc.save(tmp_path / "stamped.pdf")
    found = annots.read(annots.open_pdf(tmp_path / "stamped.pdf"))
    assert sorted((a.kind, a.other, a.locked) for a in found) == [("other", "Link", True), ("other", "Watermark", True)]
    link = next(a for a in found if a.other == "Link")
    assert link.contents == "https://example.org" and abs(link.rect[0] - 60) < 1 and abs(link.rect[1] - 60) < 1
    mark = next(a for a in found if a.other == "Watermark")
    assert mark.name() == "Watermark"
    changed = [dataclasses.replace(mark, color="#ff0000", contents="no")]  # (and the link left out)
    annots.write(tmp_path / "stamped.pdf", changed, tmp_path / "out.pdf")
    out = annots.open_pdf(tmp_path / "out.pdf")
    assert [a.type[1] for a in out[0].annots()] == ["Watermark"] and len(out[0].get_links()) == 1
    assert sorted(a.other for a in annots.read(out)) == ["Link", "Watermark"]


def test_redaction_boxes(sample, tmp_path):
    """A redaction box is written as the PDF's redaction mark, with all it has, on a page as it is and on
    a turned one, and read back; a mark made by another program is read as a box, with its fill."""
    boxes = [Annotation("redact", 0, (100, 100, 200, 130), "#ffffff", fill="#000000", font_size=0, align="center",
                        overlay="REDACTED", overlay_repeat=True, repeat="1-2, LAST", contents="a name", locked=True),
             Annotation("redact", 2, (100, 100, 200, 130), "#ff0000", fill="", font_size=9, align="left")]
    annots.write(sample, boxes, tmp_path / "marked.pdf")
    doc = annots.open_pdf(tmp_path / "marked.pdf")
    assert [a.type[1] for page in doc for a in page.annots()] == ["Redact", "Redact"]
    found = annots.read(doc)
    assert all(annots.same(a, b) for a, b in zip(boxes, found, strict=True))
    other = pymupdf.open(sample)
    other[1].add_redact_annot((300, 300, 400, 320), fill=(1, 0, 0))
    (box,) = annots.read(other)
    assert box.kind == "redact" and box.fill == "#ff0000" and box.page == 1 and not box.overlay


def test_attached_files(sample, tmp_path):
    """An attached file is written with its file and icon, read back, moved (written again, with its
    file), and kept through JSON."""
    path = tmp_path / "doc.pdf"
    a = Annotation("attachment", 0, (300, 300, 316, 316), "#1e88e5", contents="the draft", data=b"\x00draft\xff",
                   filename="draft.odt", icon="PushPin")
    annots.write(sample, [a], path)
    got = annots.read(annots.open_pdf(path))[0]
    assert (got.kind, got.data, got.filename, got.icon, got.contents) == ("attachment", b"\x00draft\xff",
                                                                         "draft.odt", "PushPin", "the draft")
    assert annots.same(a, got)
    annots.write(path, [annots.moved(got, 20, 10)], path)
    again = annots.read(annots.open_pdf(path))[0]
    assert again.data == a.data and abs(again.rect[0] - 320) < 1
    assert exchange.from_data(exchange.to_data(a)) == a


def test_remove_editable(sample, tmp_path):
    annots.write(sample, one_of_each(sample, 0), tmp_path / "out.pdf")
    doc = annots.open_pdf(tmp_path / "out.pdf")
    annots.remove_editable(doc)
    assert list(doc[0].annots()) == []


def test_fitted():
    a = Annotation("ink", 0, (0, 0, 10, 10), paths=(((0, 0), (10, 10)),))
    b = annots.fitted(a, (10, 10, 30, 20))
    assert b.paths == (((10, 10), (30, 20)),) and b.rect == (10, 10, 30, 20)
    assert annots.moved(b, 5, -5).paths == (((15, 5), (35, 15)),)
    assert dataclasses.replace(b, xref=3) != b


def test_password(tmp_path):
    path = tmp_path / "locked.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    with pytest.raises(annots.PasswordError):
        annots.open_pdf(path)
    annots.write(path, [Annotation("rect", 0, (10, 10, 50, 50), "#000000")], path, "secret")
    again = annots.open_pdf(path, "secret")
    assert again.needs_pass and [a.kind for a in annots.read(again)] == ["rect"]


def test_changed_in_place(sample, tmp_path):
    """A changed annotation keeps its xref and what other programs gave it."""
    path = tmp_path / "doc.pdf"
    annots.write(sample, one_of_each(sample, 0), path)
    doc = pymupdf.open(path)
    for annot in doc[0].annots():
        doc.xref_set_key(annot.xref, "NM", "(theirs)")
    doc.save(path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    doc.close()
    got = annots.read(annots.open_pdf(path))
    kinds = {a.kind for a in got}
    changed = []
    for a in got:
        if a.kind in ("callout", "stamp"):
            changed.append(a)
            continue
        a = dataclasses.replace(a, color="#123456", contents="changed", opacity=0.5)
        if a.kind not in annots.MARKUP:
            a = annots.moved(a, 5, 7)
        changed.append(a)
    kept: set[int] = set()
    before = path.read_bytes()
    assert annots.write(path, changed, path, kept=kept) == len(changed) - 2
    after = path.read_bytes()
    assert after.startswith(before) and len(after) > len(before)  # (an incremental save: added at the end)
    again = annots.read(annots.open_pdf(path))
    doc = pymupdf.open(path)
    assert {a.kind for a in again} == kinds
    by_xref = {a.xref: a for a in again}
    for a in changed:
        b = by_xref[a.xref]  # (the same xref: changed where it was)
        assert a.xref in kept and doc.xref_get_key(a.xref, "NM")[1] == "theirs", a.kind
        assert annots.same(a, b, tolerance=1.5), (a.kind, a, b)


def test_replies_status_tags(sample, tmp_path):
    a = Annotation("rect", 0, (100, 400, 200, 430), "#ff0000", tags=("Aristotle", "Ethics"),
                   categories=("Definitions",),
                   replies=(annots.Reply("B", "Is this right?"), annots.Reply("C", "Yes", state="Accepted")))
    m = Annotation("marker", 0, annots.frame("marker", (((100, 500), (200, 510)),), 12), "#ffeb3b", width=12,
                   opacity=0.4, paths=(((100, 500), (200, 510)),))
    path = tmp_path / "out.pdf"
    annots.write(sample, [a, m], path)
    got = annots.read(annots.open_pdf(path))
    assert [g.kind for g in got] == ["rect", "marker"]
    rect = got[0]
    assert rect.tags == ("Aristotle", "Ethics") and rect.categories == ("Definitions",)
    assert [(r.author, r.contents, r.state) for r in rect.replies] == [("B", "Is this right?", ""),
                                                                       ("C", "Yes", "Accepted")]
    assert rect.status() == "Accepted"
    # a reply more, one changed, one taken out: written where they are
    first = rect.replies[0]
    replies = (dataclasses.replace(first, contents="Is this right? (page 3)"),
               annots.Reply("D", "Rejected, after all", state="Rejected"))
    annots.write(path, [dataclasses.replace(rect, replies=replies), got[1]], path)
    again = annots.read(annots.open_pdf(path))[0]
    assert again.xref == rect.xref and again.replies[0].xref == first.xref
    assert [(r.contents, r.state) for r in again.replies] == [("Is this right? (page 3)", ""),
                                                              ("Rejected, after all", "Rejected")]
    assert again.status() == "Rejected"
    # the pages shown without them: no icons of replies left
    doc = annots.open_pdf(path)
    annots.remove_editable(doc)
    assert list(doc[0].annots()) == []
    # deleted with its replies
    annots.write(path, [], path)
    assert list(annots.open_pdf(path)[0].annots()) == []


def test_callout_box_in_the_other_order(sample, tmp_path):
    """A callout whose /RD gives its sides in the other order still has its box where it is."""
    path = tmp_path / "out.pdf"
    a = Annotation("callout", 0, (380, 350, 540, 390), "#000000", contents="Look", width=0,
                   paths=(((320.0, 420.0),),), ends=("None", "OpenArrow"))
    annots.write(sample, [a], path)
    doc = pymupdf.open(path)
    annot = next(doc[0].annots())
    rd = doc.xref_get_key(annot.xref, "RD")[1].strip("[]").split()
    doc.xref_set_key(annot.xref, "RD", f"[{rd[0]} {rd[3]} {rd[2]} {rd[1]}]")  # (above and below swapped)
    doc.save(tmp_path / "other.pdf")
    got = annots.read(annots.open_pdf(tmp_path / "other.pdf"))[0]
    assert close(got.rect, a.rect)


def test_stamp_upright_on_a_turned_page(sample, tmp_path):
    path = tmp_path / "out.pdf"
    annots.write(sample, [Annotation("stamp", 2, (100, 100, 260, 150), stamp="Approved")], path)
    got = annots.read(annots.open_pdf(path))[0]
    image = pymupdf.Pixmap(got.image)
    w, h = got.rect[2] - got.rect[0], got.rect[3] - got.rect[1]
    assert (image.width > image.height) == (w > h)


def test_find_text(sample):
    from py_pdftools.annotate.search import find_text

    doc = pymupdf.open(sample)
    found = find_text(doc, "line of")
    assert [m.page for m in found] == [0, 0, 1, 1, 2, 2] and all(len(m.rects) == 1 for m in found)
    assert found[0].context.startswith("First [line of] page 1")
    assert find_text(doc, "page 1 a second", whole_words=True)[0].rects.__len__() == 2  # (across two lines)
    assert [m.page for m in find_text(doc, r"page \d", regex=True, pages=[1])] == [1]
    assert annots.text_under(doc[2], list(found[4].rects)) == "line of"  # (on the turned page too)


@pytest.mark.parametrize("same_file", [True, False])
def test_what_write_says_is_what_the_file_has(sample, tmp_path, same_file):
    """The annotations write() gives back are those read() reads in the file it wrote (so the
    window needn't read it again)."""
    path = tmp_path / "doc.pdf"
    annots.write(sample, one_of_each(sample, 0), path)
    changed = annots.read(annots.open_pdf(path))
    changed[1] = annots.moved(changed[1], 0, 0)
    changed[6] = annots.moved(changed[6], 5, 5)
    changed.append(Annotation("rect", 1, (10, 10, 50, 50), "#000000"))
    target = path if same_file else tmp_path / "other.pdf"
    result: list = []
    annots.write(path, changed, target, result=result)
    assert result == annots.read(annots.open_pdf(target))


RICH = ('<p>Plain <span style="font-weight:bold">bold</span> <span style="color:#ff0000">red</span></p>'
        '<p><span style="font-family:Courier">mono</span></p>')


@pytest.mark.parametrize("rotation", [0, 90])
def test_rich_text_and_border(sample, tmp_path, rotation):
    """Text boxes and callouts with formatting, a border of another colour, or both, are written
    and read back as they were; other programs find their text in /Contents."""
    doc = annots.open_pdf(sample)
    doc[0].set_rotation(rotation)
    doc.save(tmp_path / "turned.pdf")
    path = tmp_path / "turned.pdf"
    made = [
        Annotation("freetext", 0, (60, 60, 260, 120), "#0000ff", fill="#ffffcc", contents="Plain bold red\nmono",
                   rich=RICH),
        Annotation("freetext", 0, (60, 160, 260, 200), "#0000ff", contents="plain, green border", border="#009900"),
        Annotation("callout", 0, (300, 300, 480, 350), "#000000", contents="Plain bold red\nmono", rich=RICH,
                   border="#cc0000", paths=(((200, 250),),), ends=("None", "OpenArrow")),
        Annotation("freetext", 0, (60, 400, 260, 440), "#000000", contents="just plain"),
    ]
    annots.write(path, made, path)
    doc = annots.open_pdf(path)
    got = annots.read(doc)
    assert len(got) == 4
    for a, b in zip(made, got, strict=True):
        assert annots.same(a, b, tolerance=2), (a, b)
        assert doc.xref_get_key(b.xref, "Contents")[1] == a.contents
    assert doc.xref_get_key(got[3].xref, "RC")[0] == "null"  # (a plain one stays plain)
    assert "1999/xhtml" in doc.xref_get_key(got[0].xref, "RC")[1]
    assert doc.xref_get_key(got[1].xref, "CL")[0] == "null"  # (no callout line in a text box)


def test_rich_text_changed(sample, tmp_path):
    """A text box changed from plain to rich, and back, and moved, is what it should be."""
    path = tmp_path / "doc.pdf"
    plain = Annotation("freetext", 0, (60, 60, 260, 120), "#0000ff", contents="Plain bold red\nmono")
    annots.write(sample, [plain], path)
    for change in ({"rich": RICH}, {"rect": (80, 80, 280, 140)}, {"border": "#00aa00"}, {"rich": "", "border": ""}):
        a = dataclasses.replace(annots.read(annots.open_pdf(path))[0], **change)
        annots.write(path, [a], path)
        got = annots.read(annots.open_pdf(path))
        assert len(got) == 1 and annots.same(a, got[0], tolerance=2), (change, got[0])


def test_groups(sample, tmp_path):
    """A group is written as the PDF writes them (the others answer the first, as its group), read
    back, survives taking out its first annotation, and a grouped note is not taken for a reply."""
    path = tmp_path / "doc.pdf"
    made = [Annotation("rect", 0, (60, 60, 120, 120), "#ff0000", group="g1"),
            Annotation("note", 0, (200, 60, 216, 76), "#ffd54f", contents="in the group", group="g1"),
            Annotation("ellipse", 1, (60, 60, 120, 120), "#0000ff", group="g1"),
            Annotation("rect", 0, (300, 300, 350, 350), "#000000")]
    annots.write(sample, made, path)
    doc = annots.open_pdf(path)
    got = annots.read(doc)
    assert [a.group for a in got] == ["g1", "g1", "", "g1"]  # (page by page)
    first = next(a for a in got if a.kind == "rect" and a.group)
    for a in got:
        if a.group and a is not first:
            assert doc.xref_get_key(a.xref, "IRT")[1] == f"{first.xref} 0 R"
            assert doc.xref_get_key(a.xref, "RT")[1] == "/Group"
    assert all(not a.replies for a in got)
    rest = [a for a in got if a.xref != first.xref]  # (the first taken out: the others stay, still a group)
    annots.write(path, rest, path)
    again = annots.read(annots.open_pdf(path))
    assert sorted(a.kind for a in again) == ["ellipse", "note", "rect"]
    assert sorted(a.group for a in again) == ["", "g1", "g1"]


def test_group_of_another_program(sample, tmp_path):
    """A group made by another program (only /IRT and /RT /Group) is read as a group, and kept."""
    path = tmp_path / "doc.pdf"
    annots.write(sample, [Annotation("rect", 0, (60, 60, 120, 120), "#ff0000"),
                          Annotation("rect", 0, (200, 60, 260, 120), "#00ff00")], path)
    doc = annots.open_pdf(path)
    a, b = annots.read(doc)
    doc.xref_set_key(b.xref, "IRT", f"{a.xref} 0 R")
    doc.xref_set_key(b.xref, "RT", "/Group")
    doc.save(tmp_path / "grouped.pdf")
    grouped = annots.read(annots.open_pdf(tmp_path / "grouped.pdf"))
    assert len(grouped) == 2 and grouped[0].group == grouped[1].group == f"#{a.xref}"
    moved = [grouped[0], annots.moved(grouped[1], 5, 5)]
    annots.write(tmp_path / "grouped.pdf", moved, tmp_path / "grouped.pdf")
    doc = annots.open_pdf(tmp_path / "grouped.pdf")
    again = annots.read(doc)
    assert [x.group for x in again] == [f"#{a.xref}"] * 2
    assert doc.xref_get_key(again[1].xref, "RT")[1] == "/Group"


def test_layers(sample, tmp_path):
    """Annotations in layers: written as optional content, read back, moved to another layer or out
    of any; a layer hidden is hidden in the file (MuPDF doesn't draw it)."""
    path = tmp_path / "doc.pdf"
    made = [Annotation("rect", 0, (60, 60, 160, 160), "#ff0000", width=4, layer="Mine"),
            Annotation("rect", 0, (300, 60, 400, 160), "#0000ff", width=4, layer="Theirs"),
            Annotation("rect", 0, (60, 300, 160, 400), "#00ff00", width=4)]
    annots.write(sample, made, path, shown={"Mine": True, "Theirs": False})
    doc = annots.open_pdf(path)
    got = annots.read(doc)
    assert [a.layer for a in got] == ["Mine", "Theirs", ""]
    assert annots.layers(doc) == {"Mine": True, "Theirs": False}
    pix = doc[0].get_pixmap(dpi=72)
    def ink(x0, x1, y0, y1):
        return sum(pix.pixel(x, y) != (255, 255, 255) for x in range(x0, x1, 2) for y in range(y0, y1, 2))
    assert ink(55, 165, 55, 165) and not ink(295, 405, 55, 165)
    changed = [dataclasses.replace(got[0], layer="Theirs"), dataclasses.replace(got[1], layer=""), got[2]]
    annots.write(path, changed, path, shown={"Theirs": True})
    doc = annots.open_pdf(path)
    assert [a.layer for a in annots.read(doc)] == ["Theirs", "", ""]
    assert annots.layers(doc) == {"Mine": True, "Theirs": True}


def test_smooth_segments():
    """The curve goes through every point of the stroke, from one to the next."""
    points = [(0, 0), (10, 10), (20, 0), (30, 10)]
    segments = annots.smooth_segments(points)
    assert [end for _, _, end in segments] == points[1:]
    c1, c2, _ = segments[1]  # (from (10, 10) to (20, 0): leaving along (20, 0) − (0, 0), arriving along (30, 10) − (10, 10))
    assert c1 == pytest.approx((10 + 20 / 6, 10)) and c2 == pytest.approx((20 - 20 / 6, 0))
    assert annots.smooth_segments([]) == [] and annots.smooth_segments([(1, 1)]) == []


def test_drawings_are_curves(sample, tmp_path):
    """A drawing is written as curves through its points (also after it is changed where it is); a
    dot, a stroke of one point, is written and read back."""
    path = tmp_path / "doc.pdf"
    word = Annotation("ink", 0, (0, 0, 0, 0), "#0000ff", width=2,
                      paths=(((100, 300), (110, 320), (120, 300), (130, 320), (140, 300)), ((150, 290),)))
    word = dataclasses.replace(word, rect=annots.frame("ink", word.paths, 2))
    annots.write(sample, [word], path)
    doc = annots.open_pdf(path)
    got = annots.read(doc)[0]
    assert len(got.paths) == 2 and len(got.paths[1]) == 1
    def appearance(doc, a):
        return doc.xref_stream(int(doc.xref_get_key(a.xref, "AP/N")[1].split()[0])).decode()
    text = appearance(doc, got)
    assert text.count(" c\n") == 4 and " l\n" in text  # (four curves; the dot, a line to where it is)
    moved = annots.moved(got, 10, 10)
    annots.write(path, [moved], path)
    doc = annots.open_pdf(path)
    again = annots.read(doc)[0]
    assert again.xref == got.xref and appearance(doc, again).count(" c\n") == 4
    pix = doc[0].get_pixmap(dpi=72)  # (the dot is drawn)
    assert any(pix.pixel(160 + dx, 300 + dy) != (255, 255, 255) for dx in range(-2, 3) for dy in range(-2, 3))
