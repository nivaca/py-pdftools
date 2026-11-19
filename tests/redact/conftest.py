from __future__ import annotations

import pymupdf
import pytest

@pytest.fixture
def sample(tmp_path):
    """A PDF of 5 pages: a header on each, a name on each, and a body of text."""
    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    for i in range(5):
        page = doc.new_page()  # (595 × 842 points)
        page.insert_text((72, 60), f"HEADER{i + 1}", fontsize=14)
        page.insert_text((72, 120), f"Name: Person{i + 1}", fontsize=12)
        page.insert_text((72, 300), "Body text stays", fontsize=12)
    doc.save(path)
    return path
