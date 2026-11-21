"""What most forms ask of their fields, done without JavaScript: the scripts of format, keystroke, validation
and calculation of nearly every form are calls to a few standard functions (AFNumber_Format,
AFSimple_Calculate and the like), and those are done here, in Python. A field with another script is filled
as it is typed; its script is not run.

- format (F): how a number, a percentage, a date or a phone number is shown (the field keeps the value);
- keystroke (K): whether what was typed is a number, a date... (else it is refused, and the reason said);
- validation (V): whether a number is within its range;
- calculation (C): sums, products, averages, least and greatest of other fields, in the order the form says
  (its /CO), whenever a field changes."""

from __future__ import annotations

import datetime as dt
import re

from ..core.interface import tr
from .fields import Field

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
# AFDate_Format(n) y AFTime_Format(n): los formatos que numeran
DATE_FORMATS = ("m/d", "m/d/yy", "mm/dd/yy", "mm/yy", "d-mmm", "d-mmm-yy", "dd-mmm-yy", "yy-mm-dd", "mmm-yy",
                "mmmm-yy", "mmm d, yyyy", "mmmm d, yyyy", "m/d/yy h:MM tt", "m/d/yy HH:MM")
TIME_FORMATS = ("HH:MM", "h:MM tt", "HH:MM:ss", "h:MM:ss tt")
SPECIAL = ("99999", "99999-9999", "(999) 999-9999", "999-99-9999")  # código postal, postal+4, teléfono, seguridad social


class Refused(ValueError):
    """What was typed doesn't fit the field (the message says why)."""


# ----------------------------------------------------------------- reading the calls

_CALL = re.compile(r"\b(AF\w+)\s*\(")
_TOKEN = re.compile(r'\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|(new\s+Array)\s*\(|([-+]?\d+(?:\.\d*)?)'
                    r'|(true|false)|(\))|(,))')


def calls(js: str) -> list[tuple[str, list]]:
    """The calls of the standard functions in the script JS, with their arguments: [('AFNumber_Format',
    [2, 0, 0, 0, '$', True]), ...]. Strings, numbers, true/false and new Array(...) are read."""
    found = []
    for m in _CALL.finditer(js or ""):
        args, pos = _arguments(js, m.end())
        if args is not None:
            found.append((m.group(1), args))
    return found


def _unescape(text: str) -> str:
    """A JavaScript string's escapes (\\n, \\", \\u20ac...) read; the rest, letters of any language, as it is."""
    def one(m):
        c = m.group(1)
        if c.startswith("u"):
            return chr(int(c[1:], 16))
        return {"n": "\n", "t": "\t", "r": "\r"}.get(c, c)
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", one, text)


def _arguments(js: str, pos: int):
    out, stack = [], []
    current = out
    while pos < len(js):
        m = _TOKEN.match(js, pos)
        if not m:
            return None, pos
        pos = m.end()
        dq, sq, array, number, boolean, close, _comma = m.groups()
        if dq is not None or sq is not None:
            current.append(_unescape(dq if dq is not None else sq))
        elif array:
            inner: list = []
            current.append(inner)
            stack.append(current)
            current = inner
        elif number is not None:
            current.append(float(number) if "." in number else int(number))
        elif boolean:
            current.append(boolean == "true")
        elif close:
            if not stack:
                return out, pos
            current = stack.pop()
    return None, pos


def _call(field: Field, key: str) -> tuple[str, list] | None:
    found = calls(field.script(key))
    return found[0] if found else None


# ----------------------------------------------------------------- numbers

def _separators(style: int) -> tuple[str, str]:
    """(thousands, decimal) of the separator style of AFNumber_Format (0: 1,234.56 ... 4: 1'234.56)."""
    return {0: (",", "."), 1: ("", "."), 2: (".", ","), 3: ("", ","), 4: ("'", ".")}.get(style, (",", "."))


def number(text: str, style: int = 0) -> float | None:
    """TEXT read as a number written with the separators of STYLE (or plainly); None if it is not one."""
    t = text.strip().replace(" ", "").replace(" ", "")
    if not t:
        return None
    negative = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    t = re.sub(r"[^\d,.'+-]", "", t)  # (sin el símbolo de la moneda ni el %)
    thousands, decimal = _separators(style)
    if thousands:
        t = t.replace(thousands, "")
    if decimal != ".":
        t = t.replace(".", "").replace(decimal, ".") if decimal in t else t
    try:
        value = float(t)
    except ValueError:
        return None
    return -value if negative else value


def plain(value: float) -> str:
    """VALUE as a field keeps it: '12.5', '3' (no exponent, no trailing zeros)."""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _grouped(value: float, decimals: int, style: int) -> str:
    thousands, decimal = _separators(style)
    whole, _, frac = f"{abs(value):.{max(0, decimals)}f}".partition(".")
    if thousands:
        whole = f"{int(whole):,}".replace(",", thousands)
    return whole + (decimal + frac if frac else "")


def format_number(value: float, decimals: int = 2, style: int = 0, negative: int = 0, currency: str = "",
                  prepend: bool = True) -> str:
    """VALUE as AFNumber_Format shows it: DECIMALS, the separators of STYLE, negatives with a minus (NEGATIVE
    0, 1) or in parentheses (2, 3), CURRENCY before (PREPEND) or after."""
    body = _grouped(value, decimals, style)
    if currency:
        body = currency + body if prepend else body + currency
    if value < 0:
        return f"({body})" if negative in (2, 3) else "-" + body
    return body


# ----------------------------------------------------------------- dates

def _date_regex(fmt: str):
    """A pattern that reads a date written in the format FMT ('dd/mm/yyyy', 'mmm d, yyyy', 'HH:MM'...),
    and the parts it takes."""
    parts, out = [], ""
    for token in re.findall(r"mmmm|mmm|mm|m|dddd|ddd|dd|d|yyyy|yy|HH|H|hh|h|MM|M|ss|s|tt|t|[^a-zA-Z]+|[a-zA-Z]",
                            fmt):
        if token in ("mmmm", "mmm"):
            out += r"([A-Za-z]+)"
            parts.append("month_name")
        elif token in ("mm", "m"):
            out += r"(\d{1,2})"
            parts.append("month")
        elif token in ("dd", "d"):
            out += r"(\d{1,2})"
            parts.append("day")
        elif token in ("dddd", "ddd"):
            out += r"[A-Za-z]+"
        elif token == "yyyy":
            out += r"(\d{4})"
            parts.append("year")
        elif token == "yy":
            out += r"(\d{2})"
            parts.append("year2")
        elif token in ("HH", "H", "hh", "h"):
            out += r"(\d{1,2})"
            parts.append("hour")
        elif token in ("MM", "M"):
            out += r"(\d{1,2})"
            parts.append("minute")
        elif token in ("ss", "s"):
            out += r"(\d{1,2})"
            parts.append("second")
        elif token in ("tt", "t"):
            out += r"([AaPp][Mm]?)"
            parts.append("ampm")
        else:
            out += re.escape(token).replace(r"\ ", r"\s*")
    return re.compile(r"^\s*" + out + r"\s*$"), parts


def read_date(text: str, fmt: str) -> dt.datetime | None:
    """TEXT read as a date (and time) written in the format FMT, or as an ISO date; None if it is neither."""
    text = text.strip()
    if not text:
        return None
    regex, parts = _date_regex(fmt)
    m = regex.match(text)
    if m:
        got = dict(zip(parts, m.groups(), strict=True))
        try:
            year = int(got["year"]) if "year" in got else (2000 + int(got["year2"]) if int(got["year2"]) < 50
                                                           else 1900 + int(got["year2"])) if "year2" in got \
                else dt.date.today().year
            if "month_name" in got:
                month = next(i for i, name in enumerate(MONTHS, 1)
                             if name.lower().startswith(got["month_name"].lower()[:3]))
            else:
                month = int(got.get("month", 1))
            hour = int(got.get("hour", 0))
            if got.get("ampm", "").lower().startswith("p") and hour < 12:
                hour += 12
            elif got.get("ampm", "").lower().startswith("a") and hour == 12:
                hour = 0
            return dt.datetime(year, month, int(got.get("day", 1)), hour, int(got.get("minute", 0)),
                               int(got.get("second", 0)))
        except (ValueError, StopIteration):
            return None
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def write_date(when: dt.datetime, fmt: str) -> str:
    """WHEN written in the format FMT."""
    def part(token: str) -> str:
        return {"mmmm": MONTHS[when.month - 1], "mmm": MONTHS[when.month - 1][:3], "mm": f"{when.month:02}",
                "m": str(when.month), "dddd": when.strftime("%A"), "ddd": when.strftime("%a"),
                "dd": f"{when.day:02}", "d": str(when.day), "yyyy": f"{when.year:04}", "yy": f"{when.year % 100:02}",
                "HH": f"{when.hour:02}", "H": str(when.hour), "hh": f"{(when.hour - 1) % 12 + 1:02}",
                "h": str((when.hour - 1) % 12 + 1), "MM": f"{when.minute:02}", "M": str(when.minute),
                "ss": f"{when.second:02}", "s": str(when.second), "tt": "am" if when.hour < 12 else "pm",
                "t": "a" if when.hour < 12 else "p"}.get(token, token)
    return "".join(part(t) for t in re.findall(
        r"mmmm|mmm|mm|m|dddd|ddd|dd|d|yyyy|yy|HH|H|hh|h|MM|M|ss|s|tt|t|[^a-zA-Z]+|[a-zA-Z]", fmt))


def _date_format(name: str, args: list) -> str:
    if name in ("AFDate_FormatEx", "AFDate_KeystrokeEx", "AFTime_FormatEx", "AFTime_KeystrokeEx"):
        return str(args[0]) if args else "mm/dd/yyyy"
    table = TIME_FORMATS if name.startswith("AFTime") else DATE_FORMATS
    n = args[0] if args and isinstance(args[0], int) else 0
    return table[n] if 0 <= n < len(table) else table[0]


# ----------------------------------------------------------------- special formats

def _special_mask(args: list) -> str:
    if args and isinstance(args[0], int) and 0 <= args[0] < len(SPECIAL):
        return SPECIAL[args[0]]
    return str(args[0]) if args else ""


def _masked(digits: str, mask: str) -> str:
    out, i = "", 0
    for c in mask:
        if c == "9":
            if i >= len(digits):
                break
            out += digits[i]
            i += 1
        elif i < len(digits):
            out += c
    return out


# ----------------------------------------------------------------- what the window asks

def check(field: Field, text: str) -> str:
    """TEXT, typed into FIELD, as the field keeps it (a date written in its format, a number plainly), if
    its keystroke and validation scripts take it; else Refused, saying why."""
    if not text.strip():
        return ""
    value = text
    keystroke = _call(field, "K")
    fmt = _call(field, "F")
    name, args = keystroke or fmt or ("", [])
    if name.startswith(("AFNumber_", "AFPercent_")):
        style = args[1] if len(args) > 1 and isinstance(args[1], int) else 0
        n = number(text, style)
        if n is None:
            raise Refused(tr("{field} takes a number", field=field.title))
        if name.startswith("AFPercent_") and "%" in text:
            n /= 100
        value = plain(n)
    elif name.startswith(("AFDate_", "AFTime_")):
        date_format = _date_format(name, args)
        when = read_date(text, date_format)
        if when is None:
            raise Refused(tr("{field} takes a date written as {format}", field=field.title, format=date_format))
        value = write_date(when, date_format)
    elif name.startswith("AFSpecial_"):
        mask = _special_mask(args)
        digits = re.sub(r"\D", "", text)
        if mask and len(digits) != mask.count("9"):
            raise Refused(tr("{field} takes {count} digits ({mask})", field=field.title, count=mask.count("9"),
                             mask=mask))
        value = digits
    validation = _call(field, "V")
    if validation and validation[0] == "AFRange_Validate":
        n = number(value)
        a = validation[1] + [False, 0, False, 0]
        if n is not None and ((a[0] and n < a[1]) or (a[2] and n > a[3])):
            low = plain(a[1]) if a[0] else "…"
            high = plain(a[3]) if a[2] else "…"
            raise Refused(tr("{field} must be between {low} and {high}", field=field.title, low=low, high=high))
    return value


def shown(field: Field, value: str) -> str:
    """VALUE as FIELD shows it, by its format script (VALUE itself, if it has none this program does)."""
    call = _call(field, "F")
    if call is None or not value.strip():
        return value
    name, args = call
    a = list(args)
    if name == "AFNumber_Format":
        a += [2, 0, 0, 0, "", True][len(a):]
        n = number(value)
        return value if n is None else format_number(n, int(a[0]), int(a[1]), int(a[2]), str(a[4]), bool(a[5]))
    if name == "AFPercent_Format":
        a += [2, 0][len(a):]
        n = number(value)
        return value if n is None else _grouped(n * 100, int(a[0]), int(a[1])) + "%"
    if name in ("AFDate_FormatEx", "AFDate_Format", "AFTime_FormatEx", "AFTime_Format"):
        date_format = _date_format(name, a)
        when = read_date(value, date_format)
        return value if when is None else write_date(when, date_format)
    if name in ("AFSpecial_Format", "AFSpecial_KeystrokeEx"):
        return _masked(re.sub(r"\D", "", value), _special_mask(a))
    return value


def calculate(found: list[Field], values: dict[str, str], order: list[str] | None = None) -> dict[str, str]:
    """The fields of FOUND with a calculation (AFSimple_Calculate), worked out from VALUES ({name: value}, the
    form's values as they are now), in ORDER (the names of the form's calculation order) and then the rest.
    Returns {name: value} of those whose value changes."""
    values = dict(values)
    changed: dict[str, str] = {}
    by = {f.name: f for f in found}
    names = [n for n in order or [] if n in by] + [f.name for f in found if f.name not in (order or [])]
    for name in names:
        call = _call(by[name], "C")
        if call is None or call[0] != "AFSimple_Calculate" or len(call[1]) < 2:
            continue
        how, which = str(call[1][0]).upper(), call[1][1]
        if isinstance(which, str):
            which = [w.strip() for w in which.split(",")]
        numbers = [number(values.get(str(w), "")) for w in which]
        numbers = [n if n is not None else 0.0 for n in numbers]
        if not numbers:
            continue
        result = {"SUM": sum, "MIN": min, "MAX": max,
                  "AVG": lambda xs: sum(xs) / len(xs),
                  "PRD": lambda xs: __import__("math").prod(xs)}.get(how, sum)(numbers)
        text = plain(result)
        if values.get(name) != text:
            values[name] = changed[name] = text
    return changed


def calculation_order(doc) -> list[str]:
    """The names of the fields in the calculation order of DOC's form (/AcroForm /CO); [] if it has none."""
    try:
        kind, value = doc.xref_get_key(doc.pdf_catalog(), "AcroForm/CO")
    except (RuntimeError, ValueError):
        return []
    names = []
    for xref in re.findall(r"(\d+)\s+0\s+R", value if kind == "array" else ""):
        k, t = doc.xref_get_key(int(xref), "T")
        if k == "string":
            names.append(t)
    return names
