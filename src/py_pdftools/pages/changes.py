"""Changes of the pages waiting to be made: headers and footers, and watermarks, to add, update
or take away. The window keeps them, undoably, until the file is saved."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pikepdf import Pdf

from . import headfoot, stamps, watermark
from .stamps import Document


@dataclass(frozen=True)
class Change:
    """SETTINGS (a HeaderFooter or a Watermark) to add, or (if None) layers to take away.

    Adding: KEEP adds it to the layers of its kind on its pages (else it replaces them);
    REPLACES, an addition taken away first (to update it). Taking away: the layers of KIND (or,
    with BATES_ONLY, the headers and footers with Bates numbers) on PAGES ('' for all)."""

    settings: headfoot.HeaderFooter | watermark.Watermark | None = None
    keep: bool = False
    replaces: int | None = None
    kind: str = stamps.HEADER_FOOTER
    pages: str = ""
    bates_only: bool = False

    def apply(self, pdf: Pdf, doc: Document, now: datetime | None = None, bates_offset: int = 0) -> int:
        if self.settings is None:
            return stamps.remove(pdf, self.pages, self.kind, bates_only=self.bates_only)
        if self.replaces is not None:
            stamps.remove(pdf, "", None, addition=self.replaces)
        module = headfoot if isinstance(self.settings, headfoot.HeaderFooter) else watermark
        return module.apply(pdf, self.settings, doc, now, keep=self.keep or self.replaces is not None,
                            bates_offset=bates_offset)

    def bates_pages(self, count: int) -> int:
        """How many Bates numbers this change uses, in a document of COUNT pages."""
        if self.settings is None or not self.uses_bates():
            return 0
        return len(stamps.chosen_pages(self.settings, count))

    def uses_bates(self) -> bool:
        if isinstance(self.settings, headfoot.HeaderFooter):
            return headfoot.uses_bates(self.settings)
        return self.settings is not None and watermark.uses_bates(self.settings)
