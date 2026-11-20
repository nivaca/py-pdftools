"""Imposition: booklets, n-up, step and repeat, shuffling, bleeds, stamps, sequences
and hot folders (from py-imposition)."""

from __future__ import annotations

import sys
from pathlib import Path

from pikepdf import Pdf

from . import (  # noqa: F401  (importing registers the commands)
    bleed, datamerge, impose, info, insert, manual, pagetools, sequence, shuffle, simple, split, stamp,
)
from .common import COMMANDS, Context, ImpositionError
from .runner import build_parser, make_context, record, save_result, strip_io
from ..core import conform, interface
from ..core.interface import ntr, tr

from .. import __version__

__all__ = ["main", "COMMANDS", "Context", "ImpositionError", "__version__"]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    interface.use_configured(interface.option(argv))
    interface.translate_argparse()
    # "py-pdftools impose file.pdf [options]" -> booklet with the default settings
    first = next((t for t in argv if not t.startswith("-")), None)
    if first and first not in COMMANDS and first.lower().endswith(".pdf"):
        argv.insert(argv.index(first), "booklet")
    parser = build_parser()
    ns = parser.parse_args(argv)
    if not ns.command:
        parser.print_help()
        return 1
    cmd = COMMANDS[ns.command]
    inp: Path | None = getattr(ns, "input", None)
    ctx = make_context(ns, input_path=inp)
    # Los comandos que no necesitan entrada (run, watch, sample...) reciben pdf=None.
    try:
        pdf = None
        if inp is not None:
            if not inp.is_file():
                raise ImpositionError(tr('{inp} not found', inp=inp))
            pdf = Pdf.open(inp)
        result = cmd.run(pdf, ns, ctx)
        if result is None:  # command handled its own output (info, run, watch...)
            return 0
        record(pdf, result, strip_io(argv, ns))
        out = ns.output
        # Sin -o, la salida va junto a la entrada como <entrada>-<comando>.pdf; sin entrada, <comando>.pdf en el
        # directorio actual.
        if out is None:
            stem = inp.with_suffix("") if inp is not None else Path(ns.command)
            out = Path(f"{stem}-{ns.command}.pdf")
        checks: dict[Path, str] = {}
        paths = save_result(result, out, ctx.conform, checks)
    except ImpositionError as e:
        print(tr('error: {error}', error=e), file=sys.stderr)
        return 1
    # Each saved file is reopened to count its pages; if that fails, the message goes out without the count.
    for p in paths:
        try:
            n = len(Pdf.open(p).pages)
            print(ntr('Wrote {path} ({count} page)', 'Wrote {path} ({count} pages)', n, path=p))
        except Exception:
            print(tr("Wrote {path}", path=p))
        if ctx.conform:
            print("  " + conform.label(ctx.conform) + (f" ({checks[p]})" if checks.get(p) else ""))
    return 0
