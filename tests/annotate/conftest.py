from __future__ import annotations

import pymupdf
import pytest

@pytest.fixture
def sample(tmp_path):
    """A PDF of 3 pages (595 × 842 points), with two lines of text on each; the
    third page is turned 90 degrees."""
    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 100), f"First line of page {i + 1}", fontsize=14)
        page.insert_text((72, 130), "A second line of text", fontsize=14)
        if i == 2:
            page.set_rotation(90)
    doc.save(path)
    return path
