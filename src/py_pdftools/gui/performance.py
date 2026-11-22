"""Performance (Settings > Performance): how much memory the window may use, whether selections are
drawn with transparency, and whether text and graphics are antialiased.

The memory profile sets the caches of the window: the renderings of pages and tiles kept (canvas.py),
the thumbnails kept and how far beyond those in view they are made (window.py), how far ahead of the view
pages are drawn, and how many processes draw them (renderer.py, from the next start). 'all' keeps every
page and thumbnail it can, within half of the memory free when it is chosen.
"""

from __future__ import annotations

import os

import pymupdf

from ..core import config
from ..core.interface import N_

# (name, title, tip)
PROFILES = [
    ("low", N_("Low"), N_("Little memory: few pages kept drawn, one process to draw them")),
    ("normal", N_("Normal"), N_("Good for every computer")),
    ("high", N_("High"), N_("More pages and thumbnails kept, drawn further ahead, by more processes")),
    ("all", N_("All pages"), N_("Every page and thumbnail kept once drawn, within half of the free memory")),
]
# the caches of each profile: pages kept, tiles kept, thumbnails kept, screens of pages drawn ahead (and
# behind), processes for the pages in view and for the thumbnails
LIMITS = {
    "low": dict(pages=4, tiles=12, thumbs=100, ahead=0.25, view=1, thumbs_workers=1),
    "normal": dict(pages=16, tiles=48, thumbs=400, ahead=0.5, view=2, thumbs_workers=None),
    "high": dict(pages=48, tiles=128, thumbs=1500, ahead=1.5, view=3, thumbs_workers=None),
    "all": dict(pages=None, tiles=256, thumbs=None, ahead=3.0, view=3, thumbs_workers=None),
}
PAGE_BYTES = 4_000_000  # (about what one page drawn at a usual zoom takes)
THUMB_BYTES = 40_000  # (and one thumbnail)
# The antialiasing of text and graphics: MuPDF's levels (8: the smoothest, 0: none).
AA_ON, AA_OFF = 8, 0
# What the renderers of other processes are given with each page (see renderer.py and rendering.py).
ANTIALIAS: tuple[int, int] = (AA_ON, AA_ON)  # (text, graphics)


def settings() -> dict:
    """The settings of performance in the configuration file, with their usual values."""
    out = {"memory": "normal", "transparency": True, "text_antialias": True, "graphics_antialias": True,
           "smooth": True}
    for key in out:
        try:
            value = config.get(key)
        except config.ConfigError:
            continue
        if value is not None and type(value) is type(out[key]):
            out[key] = value
    if out["memory"] not in LIMITS:
        out["memory"] = "normal"
    return out


def available_memory() -> int:
    """The memory free now, in bytes (Linux: MemAvailable; elsewhere a guess of 2 GB)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 2 << 30


def apply(values: dict | None = None) -> dict:
    """Put VALUES (else those of the configuration file) in effect: the caches, the transparency of
    selections, the antialiasing. Returns the values."""
    from . import canvas, renderer, scrolling, textselect, window

    global ANTIALIAS
    values = values or settings()
    limits = LIMITS[values["memory"]]
    budget = available_memory() // 2
    canvas.CACHED_PAGES = limits["pages"] or max(16, budget // PAGE_BYTES)
    canvas.MAX_TILES = limits["tiles"]
    canvas.AHEAD = limits["ahead"]
    window.MAX_THUMBS = limits["thumbs"] or max(400, budget // 4 // THUMB_BYTES)
    window.ALL_THUMBS = values["memory"] == "all"
    renderer.WORKERS["view"] = limits["view"]
    if limits["thumbs_workers"] is not None:
        renderer.WORKERS["thumbs"] = limits["thumbs_workers"]
    else:
        renderer.WORKERS["thumbs"] = max(1, min(3 if values["memory"] == "normal" else 4, (os.cpu_count() or 2) // 4))
    canvas.TRANSPARENT = textselect.TRANSPARENT = values["transparency"]
    ANTIALIAS = (AA_ON if values["text_antialias"] else AA_OFF, AA_ON if values["graphics_antialias"] else AA_OFF)
    set_antialias(ANTIALIAS)
    scrolling.SMOOTH = values.get("smooth", True)
    return values


def set_antialias(levels: tuple[int, int]) -> None:
    """MuPDF's antialiasing in this process: (text, graphics)."""
    pymupdf.mupdf.fz_set_text_aa_level(levels[0])
    pymupdf.mupdf.fz_set_graphics_aa_level(levels[1])
