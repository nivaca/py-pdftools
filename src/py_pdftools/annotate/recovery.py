"""Recovery copies of the annotations not yet saved: the window keeps one
for each document every few minutes (see settings.autosave), and removes it
when the document is saved or its changes are given up. If the program
stops before that, the copy is offered when the document is opened again,
as long as the file has not changed meanwhile.

They are JSON files (see exchange.py), in the folder ``recovery`` of the
configuration's (see config.py).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import tempfile
from pathlib import Path

from ..core import config
from .annots import Annotation
from .exchange import from_data, to_data


def folder() -> Path:
    return config.config_dir() / "recovery"


def stamp(path: Path) -> list[int]:
    """What tells whether the file at PATH changed: its time and size."""
    st = path.stat()
    return [st.st_mtime_ns, st.st_size]


def _file(path: Path) -> Path:
    key = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:20]
    return folder() / f"{key}.json"


def keep(path: Path, annotations: list[Annotation]) -> None:
    """Keep ANNOTATIONS, those of the document at PATH (raises OSError)."""
    target = _file(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"path": str(path.resolve()), "stamp": stamp(path), "kept": datetime.datetime.now().isoformat(timespec="seconds"),
            "annotations": [dict(to_data(a), xref=a.xref, replies=[dict(d, xref=r.xref) for d, r in
                                                                  zip(to_data(a)["replies"], a.replies)])
                            for a in annotations]}
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def find(path: Path) -> tuple[str, list[Annotation]] | None:
    """The annotations kept for the document at PATH, and when ('2026-11-19T14:30:00'):
    None if there are none, or the file changed since."""
    source = _file(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("stamp") != stamp(path):
            return None
        found = [from_data(d, keep_xref=True) for d in data.get("annotations", [])]
        return str(data.get("kept", "")), [a for a in found if a is not None]
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def discard(path: Path) -> None:
    try:
        _file(path).unlink(missing_ok=True)
    except OSError:
        pass
