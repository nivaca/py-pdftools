"""Page numbers and page ranges.

Page numbers are 1-based and may be written relative to the last page:
``LAST``, ``LAST-1``. Ranges are written ``a-b`` or ``a..b`` (``LAST-3..LAST``),
and an open range ``a-`` or ``a..`` goes on to the last page. Items are
separated by commas, semicolons or spaces. ``all``, ``odd`` and ``even`` are
whole specs.

(py-imposition and py-redact each had a version of this; this one does what
both did. Imposition refuses pages beyond the last one and can keep the order
of a list; redaction leaves those pages out, with ``allow_out_of_range``.)
"""

from __future__ import annotations

import re

from .interface import tr

_NUM = r"(?:LAST(?:-\d+)?|\d+)"


class PageError(ValueError):
    """A list of pages that cannot be read."""


def page_number(token: str, n: int) -> int:
    """One page number (1-based, LAST allowed) as a 1-based int."""
    t = token.strip().upper().replace(" ", "")
    if t.startswith("LAST"):
        rest = t[4:]
        if not rest:
            return n
        if rest.startswith("-") and rest[1:].isdigit():
            return n - int(rest[1:])
    elif t.isdigit():
        return int(t)
    raise PageError(tr("{token} is not a page number", token=token.strip()))


def _split_range(token: str) -> tuple[str, str] | None:
    t = token.strip().upper().replace(" ", "")
    if ".." in t:
        a, b = t.split("..", 1)
        return a, b or "LAST"
    if re.fullmatch(r"LAST-\d+", t):  # (LAST-1 on its own is a page)
        return None
    m = re.fullmatch(rf"({_NUM})-({_NUM})?", t)
    if m:
        return m.group(1), m.group(2) or "LAST"
    return None


def parse_pages(spec: str | None, n: int, *, allow_out_of_range: bool = False,
                keep_order: bool = False) -> list[int]:
    """The 0-based indices of the pages SPEC names, sorted, each once (unless
    KEEP_ORDER: then as written, a range b-a backwards). A page beyond the last
    raises PageError, or is left out if ALLOW_OUT_OF_RANGE."""
    s = (spec or "").strip().lower()
    if s in ("", "all"):
        return list(range(n))
    if s == "odd":
        return list(range(0, n, 2))
    if s == "even":
        return list(range(1, n, 2))
    out: list[int] = []
    for token in re.split(r"[,;\s]+", s):
        if not token:
            continue
        rng = _split_range(token)
        if rng:
            a, b = page_number(rng[0], n), page_number(rng[1], n)
            step = 1 if b >= a else -1
            nums = list(range(a, b + step, step))
        else:
            nums = [page_number(token, n)]
        for p in nums:
            if not 1 <= p <= n:
                if allow_out_of_range:
                    continue
                raise PageError(tr('page {page} is out of range (document has {number} pages)', page=p, number=n))
            out.append(p - 1)
    if keep_order:
        return out
    return sorted(set(out))


def check(spec: str) -> str:
    """'' if SPEC can be read, else why not."""
    try:
        parse_pages(spec, 1000, allow_out_of_range=True)
    except PageError as e:
        return str(e)
    return ""


def filter_parity(indices: list[int], parity: str | None) -> list[int]:
    """Keep only odd/even page numbers (1-based parity)."""
    if parity in (None, "all", "both"):
        return indices
    if parity == "odd":
        return [i for i in indices if i % 2 == 0]
    if parity == "even":
        return [i for i in indices if i % 2 == 1]
    raise ValueError(tr('invalid parity {parity!r}', parity=parity))


def select(spec: str | None, n: int, parity: str | None = None) -> list[int]:
    return filter_parity(parse_pages(spec, n), parity)
