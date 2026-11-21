"""A form for the tests, made as form programs make them (reportlab's fields), with the scripts of format,
keystroke and calculation that most forms use, added with pikepdf."""

from __future__ import annotations

from pathlib import Path

import pikepdf
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

JS = {
    "qty": {"K": 'AFNumber_Keystroke(0, 0, 0, 0, "", true);', "F": 'AFNumber_Format(0, 0, 0, 0, "", true);'},
    "price": {"K": 'AFNumber_Keystroke(2, 0, 0, 0, "$", true);', "F": 'AFNumber_Format(2, 0, 0, 0, "$", true);'},
    "total": {"F": 'AFNumber_Format(2, 0, 0, 0, "$", true);',
              "C": 'AFSimple_Calculate("SUM", new Array ("price", "tax"));'},
    "tax": {"F": 'AFNumber_Format(2, 0, 0, 0, "$", true);'},
    "share": {"F": "AFPercent_Format(1, 0);", "V": "AFRange_Validate(true, 0, true, 1);"},
    "when": {"K": 'AFDate_KeystrokeEx("dd/mm/yyyy");', "F": 'AFDate_FormatEx("dd/mm/yyyy");'},
    "phone": {"F": "AFSpecial_Format(2);"},
}


def make(path: Path, scripts: bool = True, pages: int = 1) -> Path:
    c = canvas.Canvas(str(path), pagesize=A4)
    form = c.acroForm
    y = 780
    for label, name in (("Name", "name"), ("Quantity", "qty"), ("Price", "price"), ("Tax", "tax"),
                        ("Total", "total"), ("Share", "share"), ("Date", "when"), ("Phone", "phone")):
        c.drawString(72, y + 4, label)
        form.textfield(name=name, tooltip=label, x=180, y=y, width=200, height=18, borderWidth=1)
        y -= 30
    c.drawString(72, y + 4, "Agree")
    form.checkbox(name="agree", tooltip="Agree", x=180, y=y, size=14, checked=False, buttonStyle="check")
    y -= 30
    c.drawString(72, y + 4, "Size")
    for i, value in enumerate(("small", "large")):
        form.radio(name="size", tooltip="Size", value=value, selected=False, x=180 + 40 * i, y=y, size=14,
                   buttonStyle="circle")
    y -= 30
    c.drawString(72, y + 4, "Colour")
    form.choice(name="colour", tooltip="Colour", value="Red", options=["Red", "Green", "Blue"], x=180, y=y,
                width=120, height=18)
    y -= 60
    form.listbox(name="many", tooltip="Many", value="B", options=["A", "B", "C"], x=180, y=y, width=120,
                 height=50)
    c.showPage()
    for n in range(1, pages):
        c.drawString(72, 780, f"Page {n + 1}")
        c.acroForm.textfield(name=f"more{n}", x=180, y=760, width=200, height=18)
        c.showPage()
    c.save()
    if scripts:
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            fields = {str(f.T): f for f in pdf.Root.AcroForm.Fields}
            for name, actions in JS.items():
                aa = pikepdf.Dictionary()
                for key, js in actions.items():
                    aa[f"/{key}"] = pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String(js))
                fields[name].AA = aa
            pdf.Root.AcroForm.CO = pikepdf.Array([fields["total"]])
            pdf.save(path)
    return path
