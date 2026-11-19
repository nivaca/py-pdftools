"""Reading and writing files: PDFs (keeping their protection) and lists of labels."""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile
from pathlib import Path

import pikepdf
from pikepdf import Pdf

from . import arrange, headfoot, labels
from ..core.interface import tr
from .labels import LabelError, Range
from .view import View, write_view


def open_pdf(path: Path, in_place: bool = False, password: str = "") -> Pdf:
    if not path.is_file():
        raise LabelError(tr("{path} not found", path=path))
    try:
        return Pdf.open(path, allow_overwriting_input=in_place, password=password)
    except pikepdf.PasswordError:
        raise LabelError(tr("{path} is protected by a password (give it with --password)", path=path)) from None
    except pikepdf.PdfError as e:
        raise LabelError(tr("{path} cannot be read as a PDF: {error}", path=path, error=e)) from None


def _save(pdf: Pdf, out: Path | str) -> None:
    """Save PDF as OUT, keeping its protection if it has one."""
    pdf.save(out, encryption=True if pdf.is_encrypted else None)


def save_pdf(pdf: Pdf, out: Path) -> None:
    """Save PDF as OUT, keeping its protection if it has one."""
    try:
        _save(pdf, out)
    except OSError as e:
        raise LabelError(tr("{path} cannot be written: {error}", path=out, error=e)) from None


def apply_all(pdf: Pdf, ranges: list[Range], view: View | None = None, changes=(), path: Path | None = None) -> None:
    """Make the CHANGES of the pages, in order (changes.Change: headers and footers, and watermarks;
    arrange.Operation: the pages moved, deleted, inserted...), then give PDF these page labels and
    VIEW (if given: see view.write_view): the labels and the view are those of the pages at the end.
    The variables of headers, footers and watermarks see PATH, and the labels the pages have when
    they are drawn (those at the end, taken back through the operations that come after)."""
    operations = [c for c in changes if isinstance(c, arrange.Operation)]
    steps, count = arrange.items_of(operations, len(pdf.pages))
    # the labels of the pages before each change, from those at the end, back through the operations
    current = labels.page_labels(ranges, count)
    before: list[list[str]] = [[]] * len(changes)
    k = len(steps)
    for i in range(len(changes) - 1, -1, -1):
        if isinstance(changes[i], arrange.Operation):
            k -= 1
            items = steps[k]
            n = len(steps[k - 1]) if k else len(pdf.pages)
            back = [""] * n
            for place, item in enumerate(items):
                if isinstance(item, int) and not back[item - 1]:
                    back[item - 1] = current[place]
            current = back
        before[i] = current
    for change, labels_then in zip(changes, before):
        if isinstance(change, arrange.Operation):
            change.apply(pdf)
        else:
            change.apply(pdf, headfoot.document_of(pdf, path, labels_then))
    labels.write_labels(pdf, ranges)
    if view is not None:
        write_view(pdf, view)


def write_copy(source: Path, ranges: list[Range], target: Path, password: str = "",
               view: View | None = None, changes=()) -> None:
    """SOURCE with these page labels, VIEW and header and footer CHANGES (see apply_all), saved
    as TARGET (safely: TARGET may be SOURCE), keeping its protection if it has one."""
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    try:
        with pikepdf.open(source, password=password) as pdf:
            apply_all(pdf, ranges, view, changes, source)
            _save(pdf, tmp)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_list(name: str) -> list[str]:
    """The labels of a list (a file, or - for the standard input): one on each
    line, or as 'show --all' writes them, after the page numbers."""
    try:
        text = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise LabelError(tr("{path} cannot be read: {error}", path=name, error=e)) from None
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    numbered = [re.fullmatch(r"\s*(\d+)(?:  (.*))?", line) for line in lines]
    if lines and all(numbered) and [int(m[1]) for m in numbered] == list(range(1, len(lines) + 1)):
        return [m[2] or "" for m in numbered]
    return lines


def batch_target(source: Path, folder: Path | None = None, prefix: str = "", suffix: str = "-labelled",
                 overwrite: bool = False) -> Path:
    """Where batch() saves SOURCE: itself (OVERWRITE), or its name with PREFIX and SUFFIX, in FOLDER (or
    next to it)."""
    if overwrite:
        return source
    return (folder or source.parent) / f"{prefix}{source.stem}{suffix}.pdf"


def batch(sources: list[Path], change, *, folder: Path | None = None, prefix: str = "", suffix: str = "-labelled",
          overwrite: bool = False) -> tuple[list[tuple[Path, Path | None, str]], int]:
    """Make CHANGE (a changes.Change) on each of SOURCES, in that order, the Bates numbers going on from
    one file to the next, and save them (see batch_target). ([(source, target or None, error or '')],
    the Bates numbers used)."""
    results, offset = [], 0
    for source in sources:
        target = batch_target(source, folder, prefix, suffix, overwrite)
        if not overwrite and target.resolve() == source.resolve():
            results.append((source, None, tr("the output is the input file; use --in-place to change it")))
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
            os.close(fd)
            try:
                with open_pdf(source) as pdf:
                    doc = headfoot.document_of(pdf, source)
                    change.apply(pdf, doc, bates_offset=offset)
                    offset += change.bates_pages(len(pdf.pages))
                    _save(pdf, tmp)
                os.replace(tmp, target)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except (LabelError, OSError, pikepdf.PdfError) as e:
            results.append((source, None, str(e)))
            continue
        results.append((source, target, ""))
    return results, offset


def write_parts(source: Path, ranges: list[Range], parts: list[tuple[Path, list[int]]], password: str = "",
                view: View | None = None, changes=()) -> None:
    """Some pages of SOURCE, with these page labels, VIEW and CHANGES made (see apply_all), saved as
    new files: PARTS, [(target, its pages)]; each page keeps its label."""
    with pikepdf.open(source, password=password) as pdf:
        apply_all(pdf, ranges, view, changes, source)
        data = io.BytesIO()
        _save(pdf, data)
        count = len(pdf.pages)
    for target, pages in parts:
        with pikepdf.open(io.BytesIO(data.getvalue()), password=password) as part:
            op = arrange.Order(tuple(pages))
            part_ranges = arrange.ranges_after(op, ranges, count)
            op.apply(part)
            labels.write_labels(part, part_ranges)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
            os.close(fd)
            try:
                _save(part, tmp)
                os.replace(tmp, target)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
