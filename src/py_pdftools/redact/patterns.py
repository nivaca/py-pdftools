"""Patterns to find: phone numbers, e-mail addresses, card numbers,
dates... Each is a regular
expression, in the forms used where the language of the patterns is spoken
(Settings: English, the U.S. forms; Spanish, those of Spain and Latin
America). They are written for the text as find_text reads it: words
separated by single spaces.
"""

from __future__ import annotations

from ..core.interface import N_

D = r"\d"
# (each: key, name shown, {language: regular expression})
PATTERNS = [
    ("email", N_("E-mail addresses"),
     # A loose form, not RFC 5322: enough for addresses as they are printed in documents.
     {"*": r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"}),
    ("phone", N_("Phone numbers"),
     {"en": r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)",
      # Los grupos deben ir separados (espacio, punto o guion) para no tomar por teléfono cualquier
      # número largo: cédulas, cuentas, referencias.
      "es": r"(?<![\w+.])(?:\+\d{1,3}[ .-]?)?(?:\(\d{1,4}\)[ .-]?)?\d{2,3}[ .-]\d{3}[ .-]\d{2,4}"
            r"(?:[ .-]\d{2})?(?![\w.]|[ .-]\d)"}),
    ("card", N_("Credit card numbers"),
     # De 13 a 16 cifras, en grupos de cuatro, con o sin espacios o guiones entre ellos.
     # TODO: filtrar lo hallado con el algoritmo de Luhn; hoy cualquier serie de 16 cifras
     # (un número de pedido, una referencia) pasa por tarjeta.
     {"*": r"(?<!\d)(?:\d{4}[ -]?){3}\d{1,4}(?!\d)"}),
    ("date", N_("Dates"),
     {"en": r"(?<!\d)(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|"
            r"Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4})(?!\d)",
      # Los meses van en minúsculas: con «Coincidir mayúsculas» activado, «3 de Marzo» no se encuentra.
      "es": r"(?<!\d)(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2} de (?:enero|febrero|marzo|abril|"
            r"mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)(?: de \d{4})?)(?!\d)"}),
    ("id", N_("Identity numbers"),
     {"en": r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)",  # (U.S. Social Security)
      # DNI (ocho cifras y letra) y NIE (X, Y o Z, siete cifras y letra) de España; cédulas y RUT
      # con puntos de miles, como en América Latina (el RUT puede terminar en -K).
      "es": r"(?<![\w.])(?:\d{8}-?[A-Za-z]|[XYZxyz]-?\d{7}-?[A-Za-z]|\d{1,3}(?:\.\d{3}){2,3}(?:-[\dkK])?)(?![\w])"}),
    ("iban", N_("Bank accounts (IBAN)"),
     # Upper case only when Match case is on; the check digits are not verified.
     {"*": r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,4})?\b"}),
]
LANGUAGES = [("en", N_("English (U.S. forms)")), ("es", N_("Spanish"))]


def regex(key: str, language: str = "en") -> str:
    for k, _, forms in PATTERNS:
        if k == key:
            # Sin forma para LANGUAGE se usa la común ('*'), y si tampoco la hay, la inglesa.
            return forms.get(language) or forms.get("*") or forms["en"]
    raise KeyError(key)
