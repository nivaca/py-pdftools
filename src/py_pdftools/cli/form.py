"""py-pdftools form: the data of PDF forms from the command line: shown or written (JSON, CSV, XFDF, FDF),
a form filled from a file of data (checked, formatted and summed as the form says), the forms of many copies
put in one table, and the fields flattened. See forms/data.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core.interface import tr
from ..forms import data
from ..forms.formats import Refused


def build_parser(prog: str = "py-pdftools form") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=tr("The data of PDF forms: show it, fill a form from a "
                                                          "file, put many filled forms in one table, or "
                                                          "flatten the fields."))
    sub = p.add_subparsers(dest="command", metavar=tr("COMMAND"), required=True)
    sp = sub.add_parser("show", help=tr("the values of the fields of a form"))
    sp.add_argument("input", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    sp.add_argument("--format", choices=data.FORMATS, default="json", help=tr("how they are written (default: json)"))
    sp.add_argument("-o", "--output", type=Path, metavar=tr("FILE"), help=tr("write them there, not on the screen"))
    sp.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    sp = sub.add_parser("fill", help=tr("fill a form with the values of a file (JSON, CSV, XFDF, FDF)"))
    sp.add_argument("input", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    sp.add_argument("values", type=Path, metavar=tr("DATA"), help=tr("the file of values"))
    sp.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FILE"), help=tr("the PDF made"))
    sp.add_argument("--flatten", action="store_true", help=tr("flatten the fields once filled"))
    sp.add_argument("--raw", action="store_true", help=tr("write the values as they are: no checks, formats or "
                                                         "sums"))
    sp.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    sp = sub.add_parser("table", help=tr("the forms of many PDFs in one table (CSV), a row for each"))
    sp.add_argument("inputs", nargs="+", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    sp.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FILE"), help=tr("the CSV made"))
    sp.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    sp = sub.add_parser("flatten", help=tr("make the fields part of the pages"))
    sp.add_argument("input", type=Path, metavar=tr("FILE"), help=tr("source PDF"))
    sp.add_argument("-o", "--output", required=True, type=Path, metavar=tr("FILE"), help=tr("the PDF made"))
    sp.add_argument("--password", default="", help=tr("the password of the PDFs, if they have one"))
    return p


def main(argv: list[str] | None = None, prog: str = "py-pdftools form") -> int:
    a = build_parser(prog).parse_args(argv)
    try:
        if a.command == "show":
            with data.open_form(a.input, a.password) as doc:
                text = data.dumps(data.values_of(doc), a.format, a.input.name, data.button_names(doc))
            if a.output:
                a.output.write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
        elif a.command == "fill":
            done = data.fill_file(a.input, data.load(a.values), a.output, a.password, a.flatten, not a.raw)
            print(tr("Wrote {path} ({count} fields filled)", path=a.output, count=len(done)))
        elif a.command == "table":
            rows = []
            for path in a.inputs:
                with data.open_form(path, a.password) as doc:
                    rows.append((path.name, data.values_of(doc)))
            a.output.write_text(data.table(rows), encoding="utf-8")
            print(tr("Wrote {path} ({count} forms)", path=a.output, count=len(rows)))
        else:
            count = data.flatten_file(a.input, a.output, a.password)
            print(tr("Wrote {path} ({count} fields flattened)", path=a.output, count=count))
    except (data.DataError, Refused, OSError) as e:
        print(f"{prog}: {e}", file=sys.stderr)
        return 1
    return 0
