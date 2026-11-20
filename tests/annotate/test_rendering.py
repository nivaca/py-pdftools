"""The rendering of pages in the processes of their own (core/rendering.py): a page drawn without the
annotations the window draws itself (bare) must not lose them for the next time it is drawn with them."""

from __future__ import annotations

import pymupdf

from py_pdftools.annotate import annots
from py_pdftools.core import rendering


def test_bare_and_whole_pages_apart(tmp_path):
    path = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    doc.new_page()
    annots.apply(doc, [annots.Annotation("rect", 0, (100, 100, 400, 400), "#ff0000", fill="#ff0000")])
    doc.save(path)
    stamp = (path.stat().st_mtime_ns, path.stat().st_size)

    def red(pixels) -> int:  # (how many red pixels the page has)
        w, h, stride, data = pixels
        return sum(1 for y in range(0, h, 4) for x in range(0, w, 4)
                   if data[y * stride + 3 * x] > 200 and data[y * stride + 3 * x + 1] < 80)

    whole = red(rendering.render(str(path), "", stamp, 0, 0.5))
    bare = red(rendering.render(str(path), "", stamp, 0, 0.5, bare=True))
    again = red(rendering.render(str(path), "", stamp, 0, 0.5))
    assert whole > 100 and bare == 0 and again == whole
