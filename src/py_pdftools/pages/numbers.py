"""Numbers in the styles of page labels: arabic, roman, letters and folios."""

from __future__ import annotations

import re

ROMAN = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
         (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def to_roman(n: int) -> str:
    """N in uppercase roman numerals (thousands beyond 3999 as more Ms)."""
    out = []
    for value, digits in ROMAN:
        count, n = divmod(n, value)
        out.append(digits * count)
    return "".join(out)


def from_roman(s: str) -> int | None:
    """The number S writes in roman numerals, if S is how to_roman writes it."""
    s = s.upper()
    if not s or any(c not in ROMAN_VALUES for c in s):
        return None
    n = 0
    for i, c in enumerate(s):
        v = ROMAN_VALUES[c]
        n += -v if i + 1 < len(s) and ROMAN_VALUES[s[i + 1]] > v else v
    return n if n > 0 and to_roman(n) == s else None


def to_letters(n: int) -> str:
    """N as the PDF numbers pages with letters: A ... Z, AA ... ZZ, AAA ..."""
    return chr(ord("A") + (n - 1) % 26) * ((n - 1) // 26 + 1)


def from_letters(s: str) -> int:
    """The number S (one letter, repeated: as to_letters writes it, in either case) stands for."""
    return (len(s) - 1) * 26 + ord(s[0].lower()) - ord("a") + 1


def to_folio(side: int) -> str:
    """SIDE (1, 2, 3 ...) as a folio: 1r, 1v, 2r ..."""
    return f"{(side + 1) // 2}{'r' if side % 2 else 'v'}"


def folio_side(leaf: int, side: str) -> int:
    """The side (1, 2, 3 ...) of LEAF's recto ('r' or '') or verso ('v')."""
    return 2 * leaf - (0 if side == "v" else 1)


def parse_folio(text: str) -> int | None:
    """The side TEXT names: a leaf from 1 on and its side, as 12r or 12v (12 is 12r)."""
    m = re.fullmatch(r"(\d+)([rv]?)", text)
    if not m or int(m[1]) < 1:
        return None
    return folio_side(int(m[1]), m[2])


def format_number(n: int, style: str) -> str:
    """N in STYLE (D, r, R, a, A or f; '' for no number)."""
    if style == "D":
        return str(n)
    if style in ("r", "R"):
        s = to_roman(n)
    elif style in ("a", "A"):
        s = to_letters(n)
    elif style == "f":
        return to_folio(n)
    else:
        return ""
    return s.lower() if style.islower() else s
