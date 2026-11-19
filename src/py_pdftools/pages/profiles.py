"""Profiles: named settings of headers and footers, or of watermarks, kept to use again, in a
JSON file of the configuration folder (header-footer.json, watermark.json)."""

from __future__ import annotations

import json
from pathlib import Path

from ..core import config
from ..core.interface import tr
from .labels import LabelError


def path(filename: str) -> Path:
    return config.config_dir() / filename


def read(filename: str, make) -> dict:
    """The profiles kept in FILENAME, by name, each made by MAKE(dict) ({} if none, or if the
    file cannot be read; a profile MAKE refuses is left out)."""
    try:
        data = json.loads(path(filename).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for item in data.get("profiles", []) if isinstance(data, dict) else []:
        if isinstance(item, dict) and item.get("name"):
            try:
                settings = make(item)
            except LabelError:
                continue
            out[settings.name] = settings
    return out


def write(filename: str, profiles: dict) -> Path:
    """Keep PROFILES (settings with .name and .as_dict()) in FILENAME (raises OSError)."""
    target = path(filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"profiles": [p.as_dict() for p in sorted(profiles.values(), key=lambda p: p.name.casefold())]}
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def save(filename: str, settings, make) -> Path:
    if not settings.name.strip():
        raise LabelError(tr("a profile needs a name"))
    profiles = read(filename, make)
    profiles[settings.name] = settings
    return write(filename, profiles)


def delete(filename: str, name: str, make) -> bool:
    profiles = read(filename, make)
    if name not in profiles:
        return False
    del profiles[name]
    write(filename, profiles)
    return True
