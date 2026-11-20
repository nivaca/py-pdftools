"""Recognising the text of scanned pages (OCR) with the tesseract program.

Each page is drawn at DPI and read by tesseract in a process of its own,
several at once (see run): the words come back with where they are on the
page as it is shown, and how sure tesseract is of each (its confidence, from
0 to 100); those below DOUBTFUL are doubtful, and come with a small picture
of themselves, to be checked (see the window's review). write_words then
puts them on the page as invisible text, where the picture shows them, so
that they can be found, copied and marked.

A page scanned sideways or upside down can be turned first (ROTATE): its
orientation is found with tesseract's own model for it (osd), which may have
to be downloaded.

The languages are tesseract's: those installed with it (its tessdata
folder), and the more accurate models of tessdata_best, which download puts
in py-pdftools' own folder (own_tessdata). For each run, a folder of links
gives tesseract, for each language asked for, the better model if there is
one, else the installed one (see tessdata_for).
"""

from __future__ import annotations

import csv
import dataclasses
import functools
import io
import multiprocessing
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import pymupdf

from .interface import tr

DPI = 300  # (at which the pages are read)
DOUBTFUL = 60  # words read with a confidence below this are doubtful
OSD_DPI = 150  # (at which the orientation of a page is found)
OSD_CONFIDENCE = 2.0  # below this, tesseract's guess of the orientation is not trusted
TIMEOUT = 600  # seconds for one page
BEST_URL = "https://github.com/tesseract-ocr/tessdata_best/raw/main/{name}.traineddata"
# Un código de idioma de Tesseract: letras, cifras y guiones bajos (chi_sim, deu_latf, script/Latin no).
LANGUAGE = re.compile(r"[A-Za-z0-9_]+")


class OcrError(Exception):
    """OCR that can't be done, or failed."""


@dataclasses.dataclass(frozen=True)
class Word:
    text: str
    rect: tuple[float, float, float, float]  # in points, on the page as it is shown (turned, if it was)
    confidence: float  # 0 to 100
    line: tuple[int, int, int]  # (block, paragraph, line), for the reading order
    crop: bytes = b""  # a PNG of the word (only of doubtful words)


@dataclasses.dataclass(frozen=True)
class PageResult:
    number: int  # 0-based
    rotate: int  # degrees (clockwise) the page was turned before it was read (0: as it was)
    words: tuple[Word, ...]

    def doubtful(self, below: float = DOUBTFUL) -> list[Word]:
        return [w for w in self.words if w.confidence < below]


# ----------------------------------------------------------------- tesseract and its languages

@functools.cache
def program() -> str | None:
    """The tesseract program (None if it is not installed)."""
    return shutil.which("tesseract")


@functools.cache
def version() -> str:
    """Tesseract's version ('5.5.4'), '' if it is not installed."""
    exe = program()
    if exe is None:
        return ""
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"tesseract\s+v?([\d.]+)", out)
    return m.group(1) if m else ""


def available() -> bool:
    return program() is not None and system_tessdata() is not None


@functools.cache
def system_tessdata() -> Path | None:
    """The folder of the languages installed with tesseract (as it says, or TESSDATA_PREFIX)."""
    exe = program()
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    # 'List of available languages in "/usr/share/tesseract/tessdata/" (3):'
    m = re.search(r'in "([^"]+)"', out.stdout + out.stderr)
    if m and Path(m.group(1)).is_dir():
        return Path(m.group(1))
    prefix = os.environ.get("TESSDATA_PREFIX")
    return Path(prefix) if prefix and Path(prefix).is_dir() else None


def own_tessdata() -> Path:
    """py-pdftools' own folder of models (those downloaded): LOCALAPPDATA on Windows, else
    XDG_DATA_HOME or ~/.local/share, py-pdftools/tessdata."""
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "py-pdftools" / "tessdata"


def _models(folder: Path | None) -> dict[str, Path]:
    if folder is None or not folder.is_dir():
        return {}
    return {p.stem: p for p in folder.glob("*.traineddata")}


def models() -> dict[str, Path]:
    """Each model there is ({name: its file}): the downloaded ones over those installed with tesseract."""
    return {**_models(system_tessdata()), **_models(own_tessdata())}


def languages() -> list[str]:
    """The languages tesseract can read here ('eng', 'lat', 'spa'...), without osd (not a language)."""
    return sorted(name for name in models() if name != "osd")


def better(name: str) -> bool:
    """Whether the more accurate model of NAME has been downloaded."""
    return name in _models(own_tessdata())


def has_osd() -> bool:
    """Whether the orientation of pages can be found (tesseract's osd model is there)."""
    return "osd" in models()


def parse_languages(spec: str) -> list[str]:
    """'lat+spa' as ['lat', 'spa'], each one there (else OcrError)."""
    names = [s.strip() for s in spec.split("+") if s.strip()]
    if not names:
        raise OcrError(tr("no language given"))
    there = models()
    for name in names:
        if not LANGUAGE.fullmatch(name) or name == "osd":
            raise OcrError(tr("{name} is not a language of tesseract", name=name))
        if name not in there:
            raise OcrError(tr("the language {name} is not installed (tesseract has {names}; better models can be "
                              "downloaded with the settings, or py-pdftools ocr --download {name})",
                              name=name, names=", ".join(languages()) or "none"))
    return names


def tessdata_for(names: list[str], folder: Path, osd: bool = False) -> Path:
    """FOLDER made a tessdata folder for NAMES (and osd, if OSD): a link (or a copy, where links can't be
    made) to the better model of each, if downloaded, else the installed one."""
    there = models()
    folder.mkdir(parents=True, exist_ok=True)
    for name in [*names, *(["osd"] if osd else [])]:
        if name not in there:
            raise OcrError(tr("the language {name} is not installed", name=name))
        link = folder / f"{name}.traineddata"
        try:
            link.symlink_to(there[name])
        except OSError:  # (Windows, without the right to make links)
            shutil.copyfile(there[name], link)
    return folder


# ----------------------------------------------------------------- reading a page (in a process of its own)

def _env() -> dict[str, str]:
    # Un hilo por proceso: ya se leen varias páginas a la vez, y los hilos de cada tesseract solo estorbarían.
    return {**os.environ, "OMP_THREAD_LIMIT": "1"}


def _tesseract(image: bytes, args: list[str]) -> str:
    try:
        r = subprocess.run([program() or "tesseract", "stdin", "stdout", *args], input=image, capture_output=True,
                           timeout=TIMEOUT, env=_env())
    except subprocess.TimeoutExpired:
        raise OcrError(tr("tesseract took too long")) from None
    except OSError as e:
        raise OcrError(str(e)) from None
    if r.returncode != 0:
        raise OcrError(tr("tesseract failed: {error}", error=r.stderr.decode(errors="replace").strip()[-300:]))
    return r.stdout.decode("utf-8", errors="replace")


def orientation(page: pymupdf.Page, tessdata: str) -> int:
    """The degrees (clockwise) PAGE, as it is shown, must turn for its text to stand upright (0 if it does,
    or if tesseract is not sure)."""
    image = page.get_pixmap(dpi=OSD_DPI, colorspace=pymupdf.csGRAY).tobytes("png")
    try:
        out = _tesseract(image, ["--psm", "0", "--tessdata-dir", tessdata])
    except OcrError:  # (too little text to tell, for instance)
        return 0
    found = dict(re.findall(r"^([A-Za-z ]+):\s*([-\d.]+)\s*$", out, flags=re.M))
    try:
        turn, sure = int(found.get("Rotate", 0)), float(found.get("Orientation confidence", 0))
    except ValueError:
        return 0
    return turn % 360 if sure >= OSD_CONFIDENCE else 0


def read_page(path: str, password: str, number: int, language: str, tessdata: str, rotate: bool = False,
              dpi: int = DPI, doubtful: float = DOUBTFUL) -> PageResult:
    """Page NUMBER of the PDF at PATH read by tesseract in LANGUAGE ('lat+spa'), with the models of TESSDATA;
    turned first, if ROTATE and it lies sideways or upside down. (Run in a process of its own: see run.)"""
    doc = pymupdf.open(path)
    try:
        if doc.needs_pass:
            doc.authenticate(password)
        page = doc[number]
        turn = orientation(page, tessdata) if rotate else 0
        if turn:
            # (only in this copy, to read it upright; write_words turns the page of the document too)
            page.set_rotation((page.rotation + turn) % 360)
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        # (the table of words asked for with -c, not with the config file 'tsv': that one is in tesseract's own
        # tessdata folder, not in the folder of links given with --tessdata-dir)
        tsv = _tesseract(pix.tobytes("png"), ["-l", language, "--tessdata-dir", tessdata, "--psm", "3",
                                              "-c", "tessedit_create_tsv=1"])
        scale = 72 / dpi
        words = []
        for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
            text = (row.get("text") or "").strip()
            try:
                level, confidence = int(row["level"]), float(row["conf"])
                left, top, width, height = (int(row[k]) for k in ("left", "top", "width", "height"))
                line = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
            except (KeyError, TypeError, ValueError):
                continue
            # Nivel 5: una palabra. Una confianza de -1 marca bloques sin texto.
            if level != 5 or not text or confidence < 0:
                continue
            crop = b""
            if confidence < doubtful:
                # (the word with a margin around it, as it is on the page: to be checked)
                box = pymupdf.IRect(left - 12, top - 8, left + width + 12, top + height + 8) & pix.irect
                if not box.is_empty:
                    part = pymupdf.Pixmap(pymupdf.csGRAY, box, False)
                    part.copy(pix, box)
                    crop = part.tobytes("png")
            words.append(Word(text, (left * scale, top * scale, (left + width) * scale, (top + height) * scale),
                              confidence, line, crop))
        return PageResult(number, turn, tuple(words))
    finally:
        doc.close()


def run(path: Path, password: str, pages: list[int], language: str, *, rotate: bool = False,
        doubtful: float = DOUBTFUL, workers: int | None = None,
        progress: Callable[[int, int], bool] | None = None) -> list[PageResult]:
    """Read PAGES (0-based) of the PDF at PATH (see read_page), several at once, in processes of their
    own. PROGRESS(done, of), if given, is told often (also while a page is being read), and stops it all by
    returning False (OcrError). The results, in the order of the pages."""
    if not available():
        raise OcrError(tr("tesseract is not installed: there is no OCR"))
    names = parse_languages(language)
    if rotate and not has_osd():
        raise OcrError(tr("the orientation of the pages can't be found: tesseract's osd model is not there "
                          "(it can be downloaded with the settings, or py-pdftools ocr --download osd)"))
    if not pages:
        return []
    workers = workers or max(1, min(len(pages), (os.cpu_count() or 2) // 2))
    results: dict[int, PageResult] = {}
    with tempfile.TemporaryDirectory(prefix="py-pdftools-tessdata-") as folder:
        tessdata = str(tessdata_for(names, Path(folder), osd=rotate))
        # Spawn, not fork: the program may have Qt running, whose state a forked child would inherit.
        pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
        try:
            futures = {pool.submit(read_page, str(path), password, n, "+".join(names), tessdata, rotate,
                                   DPI, doubtful): n for n in pages}
            waiting = set(futures)
            while waiting:
                if progress is not None and not progress(len(results), len(pages)):
                    raise OcrError(tr("Stopped"))
                done, waiting = wait(waiting, timeout=0.1, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        results[futures[future]] = future.result()
                    except OcrError:
                        raise
                    except Exception as e:  # (a process that died, a page that can't be drawn)
                        raise OcrError(tr("page {page} could not be read: {error}", page=futures[future] + 1,
                                          error=e)) from None
            if progress is not None:
                progress(len(results), len(pages))
        finally:
            # (stopped or failed: the pages not yet read are not read; those being read end with their process)
            pool.shutdown(wait=True, cancel_futures=True)
    return [results[n] for n in sorted(results)]


# ----------------------------------------------------------------- the text, on the page

def scanned(page: pymupdf.Page) -> bool:
    """Whether PAGE is a scan: it has images, and no text."""
    return not page.get_text("text").strip() and bool(page.get_images())


def write_words(page: pymupdf.Page, result: PageResult, corrections: dict[int, str] | None = None) -> int:
    """Put the words of RESULT on PAGE, invisible, where its picture shows them (turning the page first,
    as it was turned to be read). CORRECTIONS: {index of a word: its text as corrected ('' leaves it
    out)}. Returns how many words were written."""
    if result.rotate:
        page.set_rotation((page.rotation + result.rotate) % 360)
    back = page.derotation_matrix  # (from the page as shown to the page as it is stored)
    written = 0
    for i, word in enumerate(result.words):
        text = (corrections or {}).get(i, word.text).strip()
        if not text:
            continue
        x0, y0, x1, y1 = word.rect
        height, width = y1 - y0, x1 - x0
        # Un 85 % de la altura de la caja se acerca al cuerpo de la letra; la línea base queda a un 20 % del fondo.
        size = max(height * 0.85, 1)
        length = pymupdf.get_text_length(text, "helv", size) or 1
        start = pymupdf.Point(x0, y1 - height * 0.2) * back
        # render_mode=3: texto invisible, que se puede buscar y copiar pero no se dibuja; tan ancho como en la imagen.
        page.insert_text(start, text, fontsize=size, fontname="helv", render_mode=3, rotate=page.rotation,
                         morph=(start, pymupdf.Matrix(width / length, 0, 0, 1, 0, 0)))
        written += 1
    return written


# ----------------------------------------------------------------- better models

def download(names: list[str], progress: Callable[[int, int], bool] | None = None) -> list[Path]:
    """Download the most accurate models (tessdata_best) of NAMES ('lat', 'osd'...) into own_tessdata.
    PROGRESS(bytes so far, bytes in all, or 0 if not known), if given, stops it by returning False."""
    folder = own_tessdata()
    folder.mkdir(parents=True, exist_ok=True)
    made = []
    for name in names:
        if not LANGUAGE.fullmatch(name):
            raise OcrError(tr("{name} is not a language of tesseract", name=name))
        target = folder / f"{name}.traineddata"
        part = target.with_suffix(".part")
        try:
            # (a plain request: nothing about the user goes with it)
            request = urllib.request.Request(BEST_URL.format(name=name), headers={"User-Agent": "py-pdftools"})
            with urllib.request.urlopen(request, timeout=60) as answer, part.open("wb") as out:
                total, done = int(answer.headers.get("Content-Length") or 0), 0
                while chunk := answer.read(1 << 16):
                    out.write(chunk)
                    done += len(chunk)
                    if progress is not None and not progress(done, total):
                        raise OcrError(tr("Stopped"))
            os.replace(part, target)
        except OcrError:
            part.unlink(missing_ok=True)
            raise
        except OSError as e:  # (urllib's errors are OSErrors: no such language, no connection)
            part.unlink(missing_ok=True)
            reason = tr("there is no such language") if "404" in str(e) else str(e)
            raise OcrError(tr("{name} could not be downloaded: {error}", name=name, error=reason)) from None
        made.append(target)
    return made


def downloaded_at(name: str) -> float | None:
    """When the model NAME was downloaded (a time of time.time()), None if it wasn't."""
    target = own_tessdata() / f"{name}.traineddata"
    return target.stat().st_mtime if target.exists() else None

