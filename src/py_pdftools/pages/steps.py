"""Una serie de pasos sobre muchos archivos (Herramientas > Aplicar pasos a varios archivos): por ejemplo, leer el
texto (OCR), poner un pie de página, una marca de agua, reducir el tamaño y pasar a PDF/A, en ese orden, a
cada PDF de una lista. Cada paso es una orden de la línea de órdenes (py-pdftools ocr, header-footer,
watermark, reduce, pdf2iso), ya probada por sí misma, que lee un archivo temporal y escribe el siguiente; el
último se guarda en la carpeta elegida, con un sufijo, sin escribir nunca sobre los originales ni sobre un
archivo que ya exista. Un archivo que falla en un paso no detiene los demás: se dice al final.

Las series se guardan con un nombre (recipes.json, en la carpeta de configuración), para volver a usarlas.
Aquí no hay nada de Qt."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..core.interface import N_, tr

# Each kind of step: its name, and the settings it has, with their defaults
KINDS = {
    "ocr": (N_("Recognise text (OCR)"), {"languages": "eng", "rotate": False}),
    "headfoot": (N_("Header and footer"), {"header": "", "footer": "$pagelabel"}),
    "watermark": (N_("Watermark"), {"text": "DRAFT", "opacity": 30}),
    "reduce": (N_("Reduced file size"), {"level": "medium"}),
    "pdfa": (N_("PDF/A or PDF/X"), {"standard": "a-2b"}),
}
LEVELS = ("high", "medium", "small", "lossless")  # (those of py-pdftools reduce)
STANDARDS = ("a-1b", "a-2b", "a-3b", "x-4")
RECIPES = "recipes.json"


class StepsError(Exception):
    """A step that can't be run as it is set (no text for a watermark, an unknown level...)."""


@dataclass
class Step:
    kind: str
    settings: dict = field(default_factory=dict)

    def title(self) -> str:
        return tr(KINDS[self.kind][0])

    def value(self, name: str):
        return self.settings.get(name, KINDS[self.kind][1][name])

    def argv(self, source: Path, target: Path) -> list[str]:
        """The command line of this step, reading SOURCE and writing TARGET."""
        src, out = str(source), str(target)
        if self.kind == "ocr":
            argv = ["ocr", src, "-o", out, "-l", str(self.value("languages")).strip() or "eng"]
            return argv + (["--rotate"] if self.value("rotate") else [])
        if self.kind == "headfoot":
            header, footer = str(self.value("header")), str(self.value("footer"))
            if not header.strip() and not footer.strip():
                raise StepsError(tr("A header or a footer needs a text"))
            return ["header-footer", src, "-o", out, "--header-center", header, "--footer-center", footer]
        if self.kind == "watermark":
            if not str(self.value("text")).strip():
                raise StepsError(tr("A watermark needs a text"))
            return ["watermark", src, "-o", out, "--text", str(self.value("text")),
                    "--opacity", f"{int(self.value('opacity'))}%"]
        if self.kind == "reduce":
            if self.value("level") not in LEVELS:
                raise StepsError(tr("Unknown level: {level}", level=self.value("level")))
            return ["reduce", src, "-o", out, "--level", self.value("level")]
        if self.kind == "pdfa":
            if self.value("standard") not in STANDARDS:
                raise StepsError(tr("Unknown standard: {standard}", standard=self.value("standard")))
            return ["pdf2iso", src, "-o", out, "-t", self.value("standard")]
        raise StepsError(tr("Unknown step: {step}", step=self.kind))

    def needs(self) -> str:
        """What this step needs and isn't installed ('' if nothing)."""
        if self.kind == "ocr":
            from ..core import ocr

            return "" if ocr.available() else tr("tesseract is not installed: there is no OCR")
        if self.kind == "pdfa":
            from ..core import conform

            return "" if conform.available() else tr("PDF/A and PDF/X need Ghostscript, which is not installed")
        return ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "settings": dict(self.settings)}

    @classmethod
    def from_dict(cls, data: dict) -> Step:
        if not isinstance(data, dict) or data.get("kind") not in KINDS:
            raise StepsError(tr("Unknown step: {step}", step=data.get("kind") if isinstance(data, dict) else data))
        known = KINDS[data["kind"]][1]
        settings = {k: v for k, v in (data.get("settings") or {}).items() if k in known}
        return cls(data["kind"], settings)


@dataclass
class Outcome:
    """What became of a file: the file written, or the step where it failed and why."""
    source: Path
    target: Path | None = None
    error: str = ""


def target_for(source: Path, folder: Path, suffix: str) -> Path:
    """Where SOURCE goes: in FOLDER, its name with SUFFIX, never over a file that is there (nor itself)."""
    base = folder / f"{source.stem}{suffix}.pdf"
    target, n = base, 2
    while target.exists() or target.resolve() == source.resolve():
        target = base.with_name(f"{base.stem} ({n}).pdf")
        n += 1
    return target


def run_command(argv: list[str]) -> tuple[int, str]:
    """A command of py-pdftools run here, with what it says kept: (its exit status, its last line of error)."""
    from ..cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as e:  # (argparse ends with SystemExit when an option is wrong)
            code = e.code if isinstance(e.code, int) else 1
        except Exception as e:  # (cualquier otro error de un paso: se dice, y se sigue con el próximo archivo)
            return 1, str(e)
    lines = [line for line in err.getvalue().splitlines() if line.strip()]
    return code or 0, lines[-1] if lines else ""


def run(files: list[Path], steps: list[Step], folder: Path, suffix: str,
        progress: Callable[[int, int, str], None] = lambda done, total, what: None,
        stop: threading.Event | None = None) -> list[Outcome]:
    """STEPS, in their order, on each of FILES; the results in FOLDER, named with SUFFIX. PROGRESS(done, total,
    what) is told before each step; STOP, when set, ends the work after the step running."""
    if not steps:
        raise StepsError(tr("Choose a step at least"))
    for step in steps:
        missing = step.needs()
        if missing:
            raise StepsError(missing)
    folder.mkdir(parents=True, exist_ok=True)
    outcomes = []
    total, done = len(files) * len(steps), 0
    for source in files:
        if stop is not None and stop.is_set():
            break
        outcome = Outcome(source)
        with tempfile.TemporaryDirectory(prefix="py-pdftools-steps-", ignore_cleanup_errors=True) as tmp:
            current = Path(tmp) / "0.pdf"
            shutil.copy2(source, current)
            for n, step in enumerate(steps, 1):
                if stop is not None and stop.is_set():
                    outcome.error = tr("Stopped")
                    break
                progress(done, total, f"{source.name}: {step.title()}")
                following = Path(tmp) / f"{n}.pdf"
                try:
                    code, said = run_command(step.argv(current, following))
                except StepsError as e:
                    code, said = 1, str(e)
                done += 1
                if code != 0 or not following.is_file():
                    # (el mensaje nombra los archivos temporales: se dice en su lugar el nombre del archivo)
                    for path in (current, following):
                        said = said.replace(str(path), source.name)
                    outcome.error = f"{step.title()}: {said or tr('it failed')}"
                    done += len(steps) - n  # (los pasos que quedaban de este archivo no se hacen)
                    break
                current = following
            else:
                outcome.target = target_for(source, folder, suffix)
                shutil.copy2(current, outcome.target)
        outcomes.append(outcome)
    progress(total, total, "")
    return outcomes


# ----------------------------------------------------------------- recipes: series of steps kept by name

def recipes_path() -> Path:
    from ..core import config

    return config.config_dir() / RECIPES


def recipes() -> dict[str, list[Step]]:
    """The series of steps kept, by name ({} if there are none, or the file can't be read)."""
    try:
        data = json.loads(recipes_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for name, items in (data.items() if isinstance(data, dict) else []):
        try:
            out[str(name)] = [Step.from_dict(item) for item in items]
        except (StepsError, TypeError):
            continue  # (una serie que no se puede leer se deja fuera; las demás sirven)
    return out


def keep_recipe(name: str, steps: list[Step] | None):
    """Keep STEPS as the series NAME (None: forget it)."""
    found = {n: [s.as_dict() for s in st] for n, st in recipes().items()}
    if steps is None:
        found.pop(name, None)
    else:
        found[name] = [s.as_dict() for s in steps]
    path = recipes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(found, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
