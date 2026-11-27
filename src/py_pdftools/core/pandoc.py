"""Pandoc, el programa que convierte documentos de un formato a otro, para
exportar e importar documentos que no son PDF. Es opcional, como tesseract y
Ghostscript: sin él, las entradas que lo usan quedan desactivadas.

Exportar: el informe de las anotaciones, el aparato crítico y el texto del
documento se hacen en Markdown (véanse annotate/exchange.py y pages/export.py)
y Pandoc los convierte en Word (.docx), ODT, EPUB, HTML o LaTeX. Las imágenes
que el Markdown nombra van dentro del archivo (Word, ODT, EPUB, HTML) o en una
carpeta junto a él (LaTeX, que las cita).

Importar: un documento en Markdown, Word, ODT, HTML, EPUB, LaTeX u otro de los
que Pandoc lee se convierte en un PDF nuevo. Pandoc no escribe PDF por sí
mismo: lo hace con otro programa, el primero que haya de ENGINES (LuaLaTeX,
XeLaTeX, Typst...). El aspecto es el de Pandoc, no el del original (los
márgenes, las fuentes y los estilos de un archivo de Word no se conservan).

Todo corre en una carpeta temporal propia: los archivos auxiliares de LaTeX
y las imágenes sacadas de un .docx no quedan junto a los documentos.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .interface import N_, tr

COMMAND = "Pandoc"
# (the formats written: extension -> (Pandoc's name, the name shown))
OUTPUTS = {"docx": ("docx", N_("Word documents (*.docx)")), "odt": ("odt", N_("OpenDocument texts (*.odt)")),
           "epub": ("epub3", N_("E-books (*.epub)")), "html": ("html5", N_("Web pages (*.html)")),
           "tex": ("latex", N_("LaTeX documents (*.tex)"))}
# (the formats read, by extension: those Pandoc tells from the name; .txt is read as Markdown)
INPUTS = {"md": "markdown", "markdown": "markdown", "txt": "markdown", "docx": "docx", "odt": "odt",
          "html": "html", "htm": "html", "epub": "epub", "tex": "latex", "rst": "rst", "org": "org",
          "rtf": "rtf", "fb2": "fb2", "ipynb": "ipynb", "typ": "typst", "textile": "textile",
          "dokuwiki": "dokuwiki", "muse": "muse", "opml": "opml"}
# Los programas que hacen el PDF, en el orden en que se prueban: LuaLaTeX y XeLaTeX leen Unicode y las fuentes
# del sistema; Typst es mucho más liviano; pdflatex, el último de los LaTeX.
ENGINES = ("lualatex", "xelatex", "typst", "pdflatex", "weasyprint", "wkhtmltopdf")
LATEX = ("lualatex", "xelatex", "pdflatex")
TIMEOUT = 600  # seconds (a long document through LaTeX takes a while)


class PandocError(Exception):
    """A conversion that could not be made."""


@functools.cache
def program() -> str | None:
    """Where Pandoc is (None if it isn't installed)."""
    return shutil.which("pandoc")


def available() -> bool:
    return program() is not None


@functools.cache
def version() -> str:
    exe = program()
    if exe is None:
        return ""
    try:
        out = _run([exe, "--version"], timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.splitlines()[0] if out else ""


@functools.cache
def engine() -> str | None:
    """The program that makes the PDFs (None if there is none)."""
    return next((name for name in ENGINES if shutil.which(name)), None)


# Fuentes con griego, cirílico y los signos de las ediciones, que la de LaTeX (Latin Modern) no tiene: la
# primera que esté instalada (preguntado a fontconfig; donde no lo hay, Windows o macOS, la de LaTeX).
SERIF_FONTS = ("Libertinus Serif", "Noto Serif", "DejaVu Serif", "FreeSerif", "Linux Libertine O")


@functools.cache
def serif_font() -> str | None:
    """The font of the PDFs made through LuaLaTeX or XeLaTeX (None: LaTeX's own)."""
    exe = shutil.which("fc-list")
    if exe is None:
        return None
    try:
        out = _run([exe, ":", "family"], timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    have = {name.strip() for line in out.splitlines() for name in line.split(",")}
    return next((name for name in SERIF_FONTS if name in have), None)


def input_kind(path: Path) -> str | None:
    """How Pandoc reads PATH (by its extension), or None if it can't."""
    return INPUTS.get(path.suffix.lower().lstrip("."))


def _run(args: list[str], timeout: float = TIMEOUT, **kw) -> subprocess.CompletedProcess:
    # En Windows, sin la consola que se abriría un instante para cada orden.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=flags, **kw)


def _convert(args: list[str], cwd: Path, text: str | None = None) -> None:
    exe = program()
    if exe is None:
        raise PandocError(tr("Needs {command}: install it", command=COMMAND))
    try:
        r = _run([exe, *args], cwd=cwd, input=text)
    except subprocess.TimeoutExpired:
        raise PandocError(tr("{command} took too long, and was stopped", command=COMMAND)) from None
    except OSError as e:
        raise PandocError(tr("{command} could not be run: {error}", command=COMMAND, error=e)) from None
    if r.returncode != 0:
        # Las últimas líneas: el error, no las páginas de LaTeX que lo preceden.
        lines = [line for line in (r.stderr or r.stdout).splitlines() if line.strip()]
        raise PandocError(tr("{command} failed: {error}", command=COMMAND,
                             error="\n".join(lines[-6:]) or str(r.returncode)))


def output_kind(target: Path) -> str:
    """The format of TARGET (by its extension: see OUTPUTS)."""
    ext = target.suffix.lower().lstrip(".")
    if ext not in OUTPUTS:
        raise PandocError(tr("{path}: not a format that can be written", path=target.name))
    return ext


def from_markdown(text: str, target: Path, title: str = "", resources: Path | None = None) -> None:
    """The Markdown TEXT written as TARGET, in the format of its extension (see OUTPUTS). RESOURCES: the folder
    where the pictures the text names are. A LaTeX file gets its pictures in a folder beside it,
    NAME_files."""
    ext = output_kind(target)
    with tempfile.TemporaryDirectory(prefix="py-pdftools-pandoc-") as tmp:
        work = Path(tmp)
        out = work / f"out.{ext}"
        # (markdown sin las extensiones que tomarían por fórmulas o atributos lo que un PDF trae como texto)
        args = ["--from", "markdown-tex_math_dollars-raw_tex-raw_attribute", "--to", OUTPUTS[ext][0],
                "--standalone", "--output", str(out)]
        if title:
            args += ["--metadata", f"title={title}"]
        if resources is not None:
            args += ["--resource-path", str(resources)]
        if ext == "html":
            args.append("--embed-resources")
        elif ext == "tex" and resources is not None:
            args.append(f"--extract-media={target.stem}_files")
        _convert(args, work, text)
        try:
            if ext == "tex" and (work / f"{target.stem}_files").is_dir():
                media = target.with_name(f"{target.stem}_files")
                shutil.rmtree(media, ignore_errors=True)
                shutil.copytree(work / f"{target.stem}_files", media)
            _place(out, target)
        except OSError as e:
            raise PandocError(tr("{path} cannot be written: {error}", path=target, error=e)) from None


def _place(made: Path, target: Path) -> None:
    """MADE put as TARGET (a copy of its own first, in TARGET's folder: a file half written never replaces the
    good one)."""
    fd, tmp = tempfile.mkstemp(suffix=target.suffix, dir=target.parent)
    os.close(fd)
    try:
        shutil.copyfile(made, tmp)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def to_pdf(source: Path, target: Path) -> str:
    """The document SOURCE made a PDF, as TARGET, with the first program of ENGINES there is. Returns that
    program's name."""
    kind = input_kind(source)
    if kind is None:
        raise PandocError(tr("{path}: not a kind of document {command} can read", path=source.name,
                             command=COMMAND))
    maker = engine()
    if maker is None:
        raise PandocError(tr("Needs a program to make the PDF: LuaLaTeX, XeLaTeX or Typst; install one"))
    with tempfile.TemporaryDirectory(prefix="py-pdftools-pandoc-") as tmp:
        work = Path(tmp)
        out = work / "out.pdf"
        # Las imágenes de un .docx, un .odt o un .epub, sacadas aquí; las que el documento cita, buscadas junto a él.
        args = ["--from", kind, str(source.resolve()), "--standalone", "--output", str(out),
                f"--pdf-engine={maker}", "--extract-media=media", "--resource-path",
                os.pathsep.join([str(source.resolve().parent), "."])]
        if maker in LATEX:
            # Márgenes razonables (los de LaTeX son anchos), y los enlaces en color, no en recuadros.
            args += ["--variable", "geometry:margin=2.5cm", "--variable", "colorlinks=true"]
            font = serif_font() if maker != "pdflatex" else None
            if font:
                args += ["--variable", f"mainfont={font}"]
        title = _title(source, kind)
        if title:
            args += ["--metadata", f"pagetitle={title}"]
        _convert(args, work)
        if not out.is_file():
            raise PandocError(tr("{command} failed: {error}", command=COMMAND, error=tr("no PDF was made")))
        try:
            _place(out, target)
        except OSError as e:
            raise PandocError(tr("{path} cannot be written: {error}", path=target, error=e)) from None
    return maker


def _title(source: Path, kind: str) -> str:
    # (the name of the file, for the PDF's title, when the document gives none; HTML asks for one)
    return re.sub(r"[_-]+", " ", source.stem).strip() if kind == "html" else ""
