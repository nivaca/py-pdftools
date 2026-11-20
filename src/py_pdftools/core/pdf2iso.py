# pdf2iso: Copyright (C) 2026 Nicolas Vaughan <nicolasvaughan@proton.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert PDF files to PDF/A (archiving) or PDF/X-4 (printing).

(This is the author's pdf2iso, version 2.1, included in py-pdftools: it is no longer a program
to install apart. conform.py runs it as ``python -m py_pdftools.core.pdf2iso``, and the command
line has it as ``py-pdftools pdf2iso``. It still needs Ghostscript, which does the conversion.)

Targets:
    a-1b, a-2b, a-3b   PDF/A, conformance level B (default: a-2b)
    x-4                PDF/X-4

The conversion is done by Ghostscript's pdfwrite device, which re-renders the
document and embeds all fonts. For PDF/A, colours are converted to sRGB and
an sRGB output intent is attached. For PDF/X-4, colours are converted to CMYK
for the printing condition of a CMYK ICC profile (by default Ghostscript's
SWOP-like profile; pass your printer's profile with --icc and its registered
name, e.g. FOGRA39, with --condition). Transparency is kept in PDF/X-4.

pikepdf is used before Ghostscript (to open encrypted or damaged files) and
after it (to restore document metadata and keep XMP and the Info dictionary
in sync, as both standards require).

Validation: PDF/A output is checked with veraPDF (https://verapdf.org) when
it is on the PATH or given with --verapdf. veraPDF does not cover PDF/X, so
PDF/X-4 output gets a built-in structural check instead; it is not a full
preflight, which needs a commercial tool such as callas pdfToolbox.

Requirements: Ghostscript >= 10 (``gs``) and pikepdf.

Examples:
    pdf2iso.py report.pdf                     # -> report_pdfa.pdf (PDF/A-2b)
    pdf2iso.py report.pdf -t a-1b -o archived.pdf
    pdf2iso.py *.pdf -d out/ --validate
    pdf2iso.py flyer.pdf -t x-4               # -> flyer_pdfx.pdf
    pdf2iso.py flyer.pdf -t x-4 --icc ISOcoated_v2_eci.icc --condition FOGRA39
    pdf2iso.py locked.pdf --password secret
    pdf2iso.py scan.pdf -t a-3b --light        # keep the pages if veraPDF allows

--light (PDF/A-2b and 3b, with veraPDF) first tries a light conversion with
pikepdf only, which keeps the pages as they are; scanned books whose images
Ghostscript cannot write back in their own compression (JBIG2, layered JPEG
2000) stay their size.  If veraPDF does not pass the result, the file is
converted with Ghostscript as usual.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import warnings as warnings_module
from dataclasses import dataclass
from pathlib import Path

VERSION = "2.1"

MIN_PYTHON = (3, 14)
MIN_PIKEPDF = 8
MIN_GHOSTSCRIPT = (10, 0)

# (as a script, pdf2iso checked the versions of Python and pikepdf here, and stopped; in py-pdftools
# the package's requirements give them, and a module must not stop the program that imports it)
import pikepdf  # noqa: E402


@dataclass(frozen=True)
class Target:
    key: str        # as typed on the command line, e.g. "a-2b"
    name: str       # e.g. "PDF/A-2b"
    family: str     # "A" or "X"
    part: int       # 1, 2, 3 for PDF/A; 4 for PDF/X
    version: str    # PDF version of the output

    @property
    def suffix(self) -> str:
        return "_pdfa" if self.family == "A" else "_pdfx"


TARGETS = {t.key: t for t in (
    Target("a-1b", "PDF/A-1b", "A", 1, "1.4"),
    Target("a-2b", "PDF/A-2b", "A", 2, "1.7"),
    Target("a-3b", "PDF/A-3b", "A", 3, "1.7"),
    Target("x-4", "PDF/X-4", "X", 4, "1.6"),
)}

# Ghostscript's own profile folders, then common system locations.
GS_ICC_DIRS = [
    "/usr/share/ghostscript/iccprofiles",
    "/usr/share/ghostscript/*/iccprofiles",
    "/usr/local/share/ghostscript/iccprofiles",
    "/usr/local/share/ghostscript/*/iccprofiles",
    "/opt/homebrew/share/ghostscript/iccprofiles",
    "/opt/homebrew/share/ghostscript/*/iccprofiles",
    "C:/Program Files/gs/*/iccprofiles",
]
ICC_CANDIDATES = {
    "A": [f"{d}/srgb.icc" for d in GS_ICC_DIRS] + [
        "/usr/share/color/icc/colord/sRGB.icc",
        "/usr/share/color/icc/sRGB.icc",
        "C:/Windows/System32/spool/drivers/color/sRGB Color Space Profile.icm",
    ],
    "X": [f"{d}/default_cmyk.icc" for d in GS_ICC_DIRS],
}

INFO_KEYS = ("/Title", "/Author", "/Subject", "/Keywords", "/Creator")

NS_PDFXID = "http://www.npes.org/pdfx/ns/id/"
NS_PDF = "http://ns.adobe.com/pdf/1.3/"
TRUE, FALSE = pikepdf.Name("/True"), pikepdf.Name("/False")

OUTPUT_INTENT = """%!
{docinfo}
/ICCProfile ({icc}) def
[/_objdef {{icc_OI}} /type /stream /OBJ pdfmark
[{{icc_OI}} << /N {n} >> /PUT pdfmark
[{{icc_OI}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent}} /type /dict /OBJ pdfmark
[{{OutputIntent}} <<
  /Type /OutputIntent
  /S /{subtype}
  /DestOutputProfile {{icc_OI}}
  /OutputCondition ({condition_text})
  /OutputConditionIdentifier ({condition})
  /Info ({condition_text})
  /RegistryName (http://www.color.org)
>> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent}} ] >> /PUT pdfmark
"""


class ConversionError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def parse_target(text: str) -> Target:
    """Accept "a-2b", "PDF/A-2b", "pdfa2b", "2b", "x-4", "PDF/X-4", "x4"..."""
    s = re.sub(r"[^a-z0-9]", "", text.lower())
    s = s.removeprefix("pdf")
    if re.fullmatch(r"[123]b", s):
        s = "a" + s
    for key, target in TARGETS.items():
        if s == key.replace("-", ""):
            return target
    raise argparse.ArgumentTypeError(
        f"unknown target {text!r}; choose from {', '.join(TARGETS)}")


def find_ghostscript() -> str:
    """Find the Ghostscript command and check that it is recent enough."""
    names = ["gswin64c", "gswin32c", "gs"] if os.name == "nt" else ["gs"]
    path = next(filter(None, map(shutil.which, names)), None)
    if path is None:
        raise ConversionError("Ghostscript not found (looked for: %s); install it "
                              "(the package is called ghostscript on most systems)"
                              % ", ".join(names))
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             timeout=30).stdout.strip()
        version = tuple(int(n) for n in re.findall(r"\d+", out)[:2])
    except (OSError, subprocess.SubprocessError, ValueError):
        version = ()
    if len(version) < 2:
        raise ConversionError(f"cannot tell the version of Ghostscript ({path})")
    if version < MIN_GHOSTSCRIPT:
        raise ConversionError("Ghostscript %d.%d or later is needed; %s is %s"
                              % (MIN_GHOSTSCRIPT + (path, out)))
    return path


def find_verapdf(explicit: str | None, required: bool,
                 needed_by: str = "--validate") -> str | None:
    """Find the veraPDF command; None if it is not there and not required
    (NEEDED_BY, the option that requires it, goes into the message)."""
    if explicit:
        path = shutil.which(explicit)
        if path is None:
            raise ConversionError(f"veraPDF not found at {explicit}")
        return path
    path = shutil.which("verapdf")
    if path is None and required:
        raise ConversionError(f"{needed_by} given but veraPDF was not found; install it "
                              "from https://verapdf.org/software/ or give its path "
                              "with --verapdf")
    return path


@dataclass(frozen=True)
class IccProfile:
    path: Path
    colorspace: str     # "RGB", "CMYK", "GRAY", ...
    description: str

    @property
    def components(self) -> int:
        return {"GRAY": 1, "RGB": 3, "CMYK": 4}[self.colorspace]


def read_icc(path: Path) -> IccProfile:
    data = path.read_bytes()
    if len(data) < 132 or data[36:40] != b"acsp":
        raise ConversionError(f"not an ICC profile: {path}")
    colorspace = data[16:20].decode("ascii", "replace").strip()
    description = path.stem
    count = struct.unpack(">I", data[128:132])[0]
    for i in range(count):
        sig, off, size = struct.unpack(">4sII", data[132 + 12 * i:144 + 12 * i])
        if sig != b"desc":
            continue
        tag = data[off:off + size]
        if tag[:4] == b"desc":          # ICC v2: ASCII string
            length = struct.unpack(">I", tag[8:12])[0]
            description = tag[12:12 + length].split(b"\0")[0].decode("latin-1")
        elif tag[:4] == b"mluc":        # ICC v4: UTF-16BE records
            rec_len, rec_off = struct.unpack(">II", tag[20:28])
            description = tag[rec_off:rec_off + rec_len].decode("utf-16-be", "replace")
        break
    return IccProfile(path, colorspace, description.strip() or path.stem)


def find_icc_profile(explicit: str | None, target: Target) -> IccProfile:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ConversionError(f"ICC profile not found: {path}")
    else:
        path = None
        for pattern in ICC_CANDIDATES[target.family]:
            anchor = Path(pattern).anchor
            for match in sorted(Path(anchor).glob(pattern[len(anchor):])):
                if match.is_file():
                    path = match
                    break
            if path:
                break
        if path is None:
            kind = "sRGB" if target.family == "A" else "CMYK"
            raise ConversionError(f"no {kind} ICC profile found; pass one with --icc")
    profile = read_icc(path)
    wanted = "RGB" if target.family == "A" else "CMYK"
    if profile.colorspace != wanted:
        raise ConversionError(
            f"{target.name} needs a {wanted} profile, but {path} is {profile.colorspace}")
    return profile


def ps_string(text: str) -> str:
    """Escape text for use inside a PostScript string literal."""
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def read_info(pdf: pikepdf.Pdf) -> dict[str, str]:
    info = {}
    for key in INFO_KEYS:
        try:
            value = pdf.docinfo.get(key)
        except Exception:
            value = None
        if value is not None:
            text = str(value).strip()
            if text:
                info[key] = text
    return info


def pages_with_text(pdf: pikepdf.Pdf) -> int:
    """Count pages that use fonts; a drop after conversion means Ghostscript
    turned pages into images (it does so for transparency in PDF/A-1)."""
    count = 0
    for page in pdf.pages:
        try:
            if page.obj.get("/Resources", {}).get("/Font"):
                count += 1
        except Exception:
            pass
    return count


def count_annotations(pdf: pikepdf.Pdf) -> int:
    return sum(len(page.obj.get("/Annots", [])) for page in pdf.pages)


def set_print_flags(pdf: pikepdf.Pdf) -> None:
    """PDF/A wants every annotation printable and visible. Ghostscript drops
    the ones that are not (links made by pdfLaTeX, for example), so set the
    Print flag and clear Invisible, Hidden and NoView beforehand."""
    INVISIBLE, HIDDEN, PRINT, NOVIEW = 1, 2, 4, 32
    for page in pdf.pages:
        for annot in page.obj.get("/Annots", []):
            if not isinstance(annot, pikepdf.Dictionary):
                continue
            if annot.get("/Subtype") == pikepdf.Name.Popup:
                continue
            flags = int(annot.get("/F", 0))
            annot.F = (flags | PRINT) & ~(INVISIBLE | HIDDEN | NOVIEW)


@dataclass
class SourceFacts:
    info: dict[str, str]
    text_pages: int
    annotations: int
    mime_types: dict[str, str]  # attached file name -> MIME type


MIME_RE = re.compile(r"[a-z]+/[a-z0-9][a-z0-9.+_-]*", re.IGNORECASE)


def attachment_mime_types(pdf: pikepdf.Pdf) -> dict[str, str]:
    types = {}
    for name, spec in pdf.attachments.items():
        try:
            mime = spec.get_file().mime_type
        except Exception:
            mime = ""
        if MIME_RE.fullmatch(mime or ""):
            types[name] = mime
    return types


def remove_attachments(pdf: pikepdf.Pdf) -> int:
    """Remove embedded files (document-level and in annotations)."""
    count = len(pdf.attachments)
    names = pdf.Root.get("/Names")
    if names is not None and "/EmbeddedFiles" in names:
        del names["/EmbeddedFiles"]
    if "/AF" in pdf.Root:
        del pdf.Root["/AF"]
    for page in pdf.pages:
        annots = page.obj.get("/Annots")
        if annots is None:
            continue
        keep = [a for a in annots if a.get("/Subtype") != pikepdf.Name.FileAttachment]
        count += len(annots) - len(keep)
        page.obj.Annots = pikepdf.Array(keep)
    return count


def fix_attachments(pdf: pikepdf.Pdf, mime_types: dict[str, str]) -> None:
    """Give every attached file a valid MIME type and an AFRelationship, and
    list it in the catalog's AF array, as PDF/A-3 requires. Ghostscript
    garbles the MIME type ("text/csv" becomes "text#2?csv")."""
    specs = []
    for name, spec in pdf.attachments.items():
        obj = spec.obj
        stream = obj.get("/EF", {}).get("/F")
        if stream is not None:
            current = str(stream.get("/Subtype", "")).lstrip("/")
            if not MIME_RE.fullmatch(current):
                mime = mime_types.get(name, "application/octet-stream")
                stream.Subtype = pikepdf.Name("/" + mime)
        if "/AFRelationship" not in obj:
            obj.AFRelationship = pikepdf.Name.Unspecified
        specs.append(obj)
    if specs:
        af = pdf.Root.get("/AF", pikepdf.Array())
        listed = {s.objgen for s in af if s.is_indirect}
        for spec in specs:
            if not spec.is_indirect:
                continue
            if spec.objgen not in listed:
                af.append(spec)
        pdf.Root.AF = af


def remove_javascript(pdf: pikepdf.Pdf) -> int:
    """Remove JavaScript, which neither standard allows. Ghostscript moves a
    JavaScript OpenAction to a non-standard /A entry of the catalog, where
    validators do not look, so check the catalog, the pages and the
    annotations. Returns the number of actions removed."""
    def is_js(action) -> bool:
        return (isinstance(action, pikepdf.Dictionary)
                and action.get("/S") == pikepdf.Name.JavaScript)

    count = 0
    root = pdf.Root
    for key in ("/A", "/OpenAction"):
        if is_js(root.get(key)):
            del root[key]
            count += 1
    names = root.get("/Names")
    if names is not None and "/JavaScript" in names:
        del names["/JavaScript"]
        count += 1
    holders = [root] + [page.obj for page in pdf.pages]
    for page in pdf.pages:
        holders += [a for a in page.obj.get("/Annots", [])
                    if isinstance(a, pikepdf.Dictionary)]
    for holder in holders:
        if "/AA" in holder:       # additional actions: triggers, often scripts
            del holder["/AA"]
            count += 1
        if is_js(holder.get("/A")):
            del holder["/A"]
            count += 1
    return count


def remove_interpolation(pdf: pikepdf.Pdf) -> int:
    """PDF/A forbids Interpolate true in images (a hint to viewers to smooth
    them when enlarged); Ghostscript drops it, the light route must too.
    Returns how many images had it. (Inline images in content streams are
    not touched: if they have it, veraPDF rejects the light result.)"""
    count = 0
    for obj in pdf.objects:
        if (isinstance(obj, pikepdf.Stream)
                and obj.get("/Subtype") == pikepdf.Name.Image
                and "/Interpolate" in obj):
            if bool(obj.Interpolate):
                count += 1
            del obj["/Interpolate"]
    return count


def fix_optional_content(pdf: pikepdf.Pdf) -> bool:
    """Layers: PDF/A and PDF/X want a Name in every optional content
    configuration and no AS (automatic state) entries. Returns True if
    anything was changed."""
    props = pdf.Root.get("/OCProperties")
    if props is None:
        return False
    changed = False
    configs = [props.get("/D")] + list(props.get("/Configs", []))
    for number, config in enumerate(configs):
        if not isinstance(config, pikepdf.Dictionary):
            continue
        if not str(config.get("/Name", "")).strip():
            config.Name = pikepdf.String("Default" if number == 0 else f"Configuration {number}")
            changed = True
        if "/AS" in config:
            del config["/AS"]
            changed = True
    return changed


# --------------------------------------------------------------------------
# Conversion steps
# --------------------------------------------------------------------------

def prepare_input(src: Path, dst: Path, password: str) -> SourceFacts:
    """Decrypt/repair the input so Ghostscript can read it, and record what
    we need to compare against afterwards."""
    try:
        with pikepdf.open(src, password=password) as pdf:
            facts = SourceFacts(read_info(pdf), pages_with_text(pdf),
                                count_annotations(pdf),
                                attachment_mime_types(pdf))
            set_print_flags(pdf)
            # Saving without encryption also rewrites damaged xref tables.
            # pikepdf may warn about the input's own oddities (e.g. form
            # widgets outside /AcroForm); they are not ours to report.
            with warnings_module.catch_warnings():
                warnings_module.simplefilter("ignore")
                pdf.save(dst, encryption=False)
    except pikepdf.PasswordError:
        raise ConversionError(f"{src} is encrypted; supply the password with --password")
    except pikepdf.PdfError as exc:
        raise ConversionError(f"cannot read {src}: {exc}")
    return facts


def run_ghostscript(gs: str, src: Path, dst: Path, target: Target,
                    icc: IccProfile, condition: str, title: str,
                    workdir: Path, verbose: bool) -> None:
    if target.family == "A":
        docinfo = ""
        subtype = "GTS_PDFA1"
        condition = "sRGB IEC61966-2.1"
        condition_text = "sRGB IEC61966-2.1"
        switches = [f"-dPDFA={target.part}", "-sColorConversionStrategy=RGB"]
    else:
        # PDF/X requires a title; Ghostscript keeps the input's if there is one.
        docinfo = ("[ /GTS_PDFXVersion (PDF/X-4) /Trapped /False "
                   f"/Title ({ps_string(title)}) /DOCINFO pdfmark")
        subtype = "GTS_PDFX"
        condition_text = icc.description
        switches = [f"-dPDFX={target.part}", "-sColorConversionStrategy=CMYK"]

    def_file = workdir / "intent.ps"
    def_file.write_text(OUTPUT_INTENT.format(
        docinfo=docinfo,
        icc=ps_string(icc.path.resolve().as_posix()),
        n=icc.components,
        subtype=subtype,
        condition=ps_string(condition),
        condition_text=ps_string(condition_text),
    ), encoding="latin-1")

    cmd = [
        gs,
        "-dBATCH", "-dNOPAUSE", "-dSAFER",
        "-q" if not verbose else "-dQUIET=false",
        f"--permit-file-read={icc.path.resolve().as_posix()}",
        "-sDEVICE=pdfwrite",
        *switches,
        "-dPDFACompatibilityPolicy=1",  # drop offending features, keep going
        f"-dCompatibilityLevel={target.version}",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=true",
        "-dAutoRotatePages=/None",
        # Keep images as they are: no downsampling.
        "-dDownsampleColorImages=false",
        "-dDownsampleGrayImages=false",
        "-dDownsampleMonoImages=false",
        f"-sOutputFile={dst}",
        str(def_file),
        str(src),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    messages = (proc.stdout + proc.stderr).strip()
    if verbose and messages:
        print(messages, file=sys.stderr)
    if proc.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        raise ConversionError(f"Ghostscript failed (exit {proc.returncode}):\n{messages}")
    # With PDFACompatibilityPolicy=1 Ghostscript gives up on the standard,
    # rather than failing, when it meets something it cannot fix.
    lowered = messages.lower()
    if any(s in lowered for s in ("aborting conversion", "not producing pdf/",
                                  "reverting to normal pdf output")):
        raise ConversionError(f"Ghostscript could not produce {target.name}:\n{messages}")


def add_output_intent(pdf: pikepdf.Pdf, icc: IccProfile) -> None:
    """Attach ICC as the PDF/A output intent (the light route, where
    Ghostscript does not do it)."""
    profile = pdf.make_stream(icc.path.read_bytes(), N=icc.components)
    intent = pikepdf.Dictionary(
        Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFA1,
        DestOutputProfile=profile,
        OutputCondition=pikepdf.String(icc.description),
        OutputConditionIdentifier=pikepdf.String(icc.description),
        Info=pikepdf.String(icc.description),
        RegistryName=pikepdf.String("http://www.color.org"))
    pdf.Root.OutputIntents = pikepdf.Array([pdf.make_indirect(intent)])


def finalize(path: Path, dst: Path, target: Target, facts: SourceFacts,
             title: str, intent: IccProfile | None = None) -> list[str]:
    """Restore lost metadata, sync XMP with DocInfo, check the markers.
    INTENT, if given, is attached as the output intent when the file has
    none (the light route).

    Returns a list of warnings."""
    warnings = []
    with pikepdf.open(path) as pdf:
        if pages_with_text(pdf) < facts.text_pages:
            warnings.append(
                "some pages were rasterized (text is no longer selectable); "
                "this happens with transparency under PDF/A-1, try -t a-2b")
        lost = facts.annotations - count_annotations(pdf)
        if lost > 0:
            why = ("PDF/X does not allow links or comments on the printed page"
                   if target.family == "X" else "Ghostscript could not keep them")
            warnings.append(f"{lost} annotation(s) (links, comments, form fields) "
                            f"were removed: {why}")

        if target.family == "X" or target.part < 3:
            removed = remove_attachments(pdf)
            if removed:
                if target.family == "X":
                    # Whether PDF/X-4 allows them is not clear from public
                    # sources; a file for the printer does not need them.
                    why = "a file for printing should not carry them"
                elif target.part == 1:
                    why = ("PDF/A-1 does not allow them; "
                           "use -t a-3b to keep them")
                else:
                    why = ("PDF/A-2 only allows attached files that are PDF/A "
                           "themselves; use -t a-3b to keep them")
                warnings.append(f"{removed} attached file(s) were removed: {why}")
        else:
            fix_attachments(pdf, facts.mime_types)
        fix_optional_content(pdf)
        if target.family == "A":
            remove_interpolation(pdf)
        if remove_javascript(pdf):
            warnings.append(f"JavaScript was removed: {target.name} does not allow it")

        for key, value in facts.info.items():
            if key not in pdf.docinfo or not str(pdf.docinfo[key]).strip():
                pdf.docinfo[key] = value

        if target.family == "X":
            if not str(pdf.docinfo.get("/Title", "")).strip():
                pdf.docinfo["/Title"] = title
            if pdf.docinfo.get("/Trapped") not in (TRUE, FALSE):
                pdf.docinfo["/Trapped"] = FALSE
            pdf.docinfo["/GTS_PDFXVersion"] = "PDF/X-4"

        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            with warnings_module.catch_warnings():
                # Keys with no XMP equivalent (Trapped, GTS_PDFXVersion) are
                # set by hand below; pikepdf would only warn about them.
                warnings_module.simplefilter("ignore", UserWarning)
                meta.load_from_docinfo(pdf.docinfo, raise_failure=False)
            if target.family == "A":
                meta["pdfaid:part"] = str(target.part)
                meta["pdfaid:conformance"] = "B"
            else:
                meta[f"{{{NS_PDFXID}}}GTS_PDFXVersion"] = "PDF/X-4"
                meta[f"{{{NS_PDF}}}Trapped"] = str(pdf.docinfo["/Trapped"]).lstrip("/")

        if intent is not None and "/OutputIntents" not in pdf.Root:
            add_output_intent(pdf, intent)
        if "/OutputIntents" not in pdf.Root:
            raise ConversionError("output has no OutputIntent; ICC profile was not embedded")

        # PDF/A-1 is based on PDF 1.4, which has no object streams.
        stream_mode = (pikepdf.ObjectStreamMode.disable if target.version == "1.4"
                       else pikepdf.ObjectStreamMode.preserve)
        with warnings_module.catch_warnings():
            # pikepdf may warn about the input's own oddities (e.g. form
            # widgets outside /AcroForm), which the light route keeps.
            warnings_module.simplefilter("ignore")
            pdf.save(dst, object_stream_mode=stream_mode,
                     force_version=target.version)
    return warnings


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_pdfa(verapdf: str, path: Path, target: Target) -> tuple[bool, str]:
    flavour = target.key.removeprefix("a-")
    proc = subprocess.run(
        [verapdf, "--flavour", flavour, "--format", "text", str(path)],
        capture_output=True, text=True, errors="replace",
    )
    out = (proc.stdout + proc.stderr).strip()
    passed = any(line.startswith("PASS") for line in out.splitlines())
    return passed, out


def _box(page: pikepdf.Dictionary, key: str):
    value = page.get(key)
    if value is None:
        return None
    x0, y0, x1, y1 = (float(v) for v in value)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _inside(inner, outer, tol=0.01) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def check_pdfx4(path: Path) -> list[str]:
    """Structural check of the main PDF/X-4 (ISO 15930-7) requirements.

    It covers metadata, output intent, page boxes and annotations. It does not
    check colour usage in content streams or fonts in depth."""
    problems = []
    with pikepdf.open(path) as pdf:
        if pdf.is_encrypted:
            problems.append("file is encrypted")
        if len(pdf.attachments):
            problems.append("file has attached files")

        meta = pdf.open_metadata()
        if meta.get(f"{{{NS_PDFXID}}}GTS_PDFXVersion") != "PDF/X-4":
            problems.append("XMP pdfxid:GTS_PDFXVersion is not 'PDF/X-4'")
        for key in ("dc:title", "xmp:CreateDate", "xmp:ModifyDate",
                    "xmpMM:DocumentID", "xmpMM:VersionID", "xmpMM:RenditionClass"):
            if not str(meta.get(key) or "").strip():
                problems.append(f"XMP {key} is missing")
        xmp_trapped = meta.get(f"{{{NS_PDF}}}Trapped")
        if xmp_trapped not in ("True", "False"):
            problems.append("XMP pdf:Trapped must be True or False")
        info_trapped = pdf.docinfo.get("/Trapped")
        if info_trapped is not None and str(info_trapped).lstrip("/") != xmp_trapped:
            problems.append("Info /Trapped does not match XMP pdf:Trapped")

        intents = [oi for oi in pdf.Root.get("/OutputIntents", [])
                   if oi.get("/S") == pikepdf.Name.GTS_PDFX]
        if len(intents) != 1:
            problems.append(f"expected one GTS_PDFX output intent, found {len(intents)}")
        else:
            oi = intents[0]
            if not str(oi.get("/OutputConditionIdentifier", "")).strip():
                problems.append("output intent has no OutputConditionIdentifier")
            profile = oi.get("/DestOutputProfile")
            if profile is None:
                problems.append("output intent has no DestOutputProfile")
            elif int(profile.get("/N", 0)) not in (1, 3, 4):
                problems.append("DestOutputProfile has an invalid /N")

        for number, page in enumerate(pdf.pages, start=1):
            obj = page.obj
            media = _box(obj, "/MediaBox")
            trim = _box(obj, "/TrimBox") or _box(obj, "/ArtBox")
            bleed = _box(obj, "/BleedBox") or media
            if trim is None:
                problems.append(f"page {number}: no TrimBox or ArtBox")
                continue
            if media and not _inside(bleed, media):
                problems.append(f"page {number}: BleedBox extends beyond MediaBox")
            if not _inside(trim, bleed):
                problems.append(f"page {number}: TrimBox extends beyond BleedBox")
            for annot in obj.get("/Annots", []):
                subtype = annot.get("/Subtype")
                if subtype in (pikepdf.Name.TrapNet, pikepdf.Name.PrinterMark):
                    continue
                rect = _box(annot, "/Rect")
                if rect is not None and _overlaps(rect, bleed):
                    problems.append(f"page {number}: {subtype} annotation "
                                    "inside the BleedBox")
    return problems


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def convert(src: Path, dst: Path, target: Target, *, icc: IccProfile, gs: str,
            password: str = "", condition: str = "Custom",
            verbose: bool = False) -> list[str]:
    """Convert src to the target standard at dst; return any warnings."""
    title = src.stem
    with tempfile.TemporaryDirectory(prefix="pdf2iso-") as tmp:
        work = Path(tmp)
        clean = work / "input.pdf"
        gs_out = work / "gs.pdf"
        final = work / "final.pdf"
        facts = prepare_input(src, clean, password)
        title = facts.info.get("/Title", title)
        run_ghostscript(gs, clean, gs_out, target, icc, condition, title,
                        work, verbose)
        warnings = finalize(gs_out, final, target, facts, title)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(final, dst)
    return warnings


def convert_light(src: Path, dst: Path, target: Target, *, icc: IccProfile,
                  password: str = "") -> list[str]:
    """The light route (--light): SRC made PDF/A at DST without Ghostscript,
    keeping the pages as they are; only what pikepdf can fix is fixed
    (metadata, output intent, JavaScript, attachments, layers, encryption).
    Whether the result is valid is for veraPDF to say."""
    title = src.stem
    with tempfile.TemporaryDirectory(prefix="pdf2iso-") as tmp:
        work = Path(tmp)
        clean = work / "input.pdf"
        final = work / "final.pdf"
        facts = prepare_input(src, clean, password)
        title = facts.info.get("/Title", title)
        warnings = finalize(clean, final, target, facts, title, intent=icc)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(final, dst)
    return warnings


@dataclass
class Outcome:
    """What happened to one file: status is "OK", "BAD" (converted, but the
    check failed) or "FAIL" (not converted)."""
    status: str
    check: str = ""                 # e.g. "veraPDF: PASS"
    warnings: list[str] = None
    details: list[str] = None       # the validator's report, the problems
    error: str = ""                 # why it failed
    skipped: bool = False           # (failed because it would overwrite)
    light: bool = False             # made by the light route (--light)

    def __post_init__(self):
        self.warnings = self.warnings or []
        self.details = self.details or []


def output_path(src: Path, target: Target, outdir: Path | None = None,
                suffix: str | None = None) -> Path:
    """Where the output of SRC goes: next to it, or in OUTDIR, with the
    target's suffix (_pdfa, _pdfx) unless SUFFIX says otherwise."""
    suffix = target.suffix if suffix is None else suffix
    return (outdir or src.parent) / f"{src.stem}{suffix}.pdf"


def try_light(src: Path, dst: Path, target: Target, *, icc: IccProfile,
              verapdf: str, password: str = "",
              verbose: bool = False) -> tuple[Outcome | None, str]:
    """The light route: (the Outcome, "") if veraPDF passes it, and then DST
    is written; or else (None, why not), and DST is left alone."""
    with tempfile.TemporaryDirectory(prefix="pdf2iso-light-") as tmp:
        attempt = Path(tmp) / "light.pdf"
        try:
            warnings = convert_light(src, attempt, target, icc=icc,
                                     password=password)
        except (ConversionError, OSError) as exc:
            return None, str(exc)
        passed, report = validate_pdfa(verapdf, attempt, target)
        if not passed:
            return None, "veraPDF did not pass it" + (f":\n{report}" if verbose else "")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(attempt, dst)
    return Outcome("OK", "veraPDF: PASS", warnings, [report] if verbose else [],
                   light=True), ""


def process(src: Path, dst: Path, target: Target, *, icc: IccProfile, gs: str,
            verapdf: str | None = None, password: str = "",
            condition: str = "Custom", verbose: bool = False,
            light: bool = False) -> Outcome:
    """Convert SRC to DST and check the result: with veraPDF (PDF/A, if
    VERAPDF is given) or with check_pdfx4 (PDF/X-4).  With LIGHT (PDF/A-2b
    and 3b, and VERAPDF needed), the light route is tried first, and
    Ghostscript is used only if veraPDF does not pass its result."""
    if dst.resolve() == src.resolve():
        return Outcome("FAIL", error="output would overwrite the input",
                       skipped=True)
    notes = []
    if light:
        outcome, why_not = try_light(src, dst, target, icc=icc, verapdf=verapdf,
                                     password=password, verbose=verbose)
        if outcome is not None:
            return outcome
        notes.append(f"the light conversion was not used ({why_not}); "
                     "converted with Ghostscript")
    try:
        warnings = notes + convert(src, dst, target, icc=icc, gs=gs,
                                   password=password, condition=condition,
                                   verbose=verbose)
    except (ConversionError, OSError) as exc:
        return Outcome("FAIL", error=str(exc))
    if target.family == "A" and verapdf:
        passed, report = validate_pdfa(verapdf, dst, target)
        return Outcome("OK" if passed else "BAD",
                       "veraPDF: PASS" if passed else "veraPDF: FAIL", warnings,
                       [report] if verbose or not passed else [])
    if target.family == "X":
        problems = check_pdfx4(dst)
        return Outcome("BAD" if problems else "OK",
                       "structural check: " + ("FAIL" if problems else "PASS"),
                       warnings, [f"  {p}" for p in problems])
    return Outcome("OK", "", warnings)


def build_parser(prog: str = "pdf2iso") -> argparse.ArgumentParser:
    """The command line of pdf2iso (py-pdftools puts it under its own: see cli/)."""
    ap = argparse.ArgumentParser(
        prog=prog, description="Convert PDF files to PDF/A or PDF/X-4 using Ghostscript and pikepdf.")
    ap.add_argument("inputs", nargs="+", type=Path, help="PDF file(s) to convert")
    out = ap.add_mutually_exclusive_group()
    out.add_argument("-o", "--output", type=Path,
                     help="output file (only with a single input)")
    out.add_argument("-d", "--outdir", type=Path,
                     help="directory for outputs (default: next to each input)")
    ap.add_argument("-t", "--target", type=parse_target, default=TARGETS["a-2b"],
                    metavar="{" + ",".join(TARGETS) + "}",
                    help="standard to convert to (default: a-2b)")
    ap.add_argument("-p", "--password", default="",
                    help="password for encrypted inputs")
    ap.add_argument("--suffix",
                    help="suffix added to output names (default: _pdfa or _pdfx)")
    ap.add_argument("--icc",
                    help="ICC profile for the output intent: sRGB for PDF/A, "
                         "the printer's CMYK profile for PDF/X "
                         "(default: Ghostscript's own profiles)")
    ap.add_argument("--condition", default="Custom",
                    help="PDF/X only: registered name of the printing condition "
                         "the --icc profile describes, e.g. FOGRA39, FOGRA51, "
                         "CGATS TR 006 (default: Custom)")
    ap.add_argument("--validate", action="store_true",
                    help="PDF/A only: validate with veraPDF and fail if it is missing "
                         "(PDF/X-4 output is always given a built-in structural check)")
    ap.add_argument("--light", action="store_true",
                    help="PDF/A-2b and 3b only: first try a light conversion that "
                         "keeps the pages as they are (pikepdf only, without "
                         "Ghostscript), and keep it if veraPDF passes it; otherwise "
                         "convert with Ghostscript. Useful for scans that "
                         "Ghostscript makes much larger. Needs veraPDF")
    ap.add_argument("--verapdf", help="path to the veraPDF command-line tool")
    ap.add_argument("--version", action="version",
                    version=f"pdf2iso {VERSION}")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="show Ghostscript and validator output")
    return ap


def main(argv: list[str] | None = None, prog: str = "pdf2iso") -> int:
    ap = build_parser(prog)
    args = ap.parse_args(argv)
    target: Target = args.target

    if args.output and len(args.inputs) > 1:
        ap.error("--output can only be used with a single input; use --outdir")
    if target.family == "A" and args.condition != "Custom":
        ap.error("--condition only applies to PDF/X")
    if args.light and not (target.family == "A" and target.part >= 2):
        ap.error("--light only works with -t a-2b and a-3b")

    # Check every dependency before touching any file.
    try:
        gs = find_ghostscript()
        icc = find_icc_profile(args.icc, target)
        verapdf = (find_verapdf(args.verapdf, args.validate or args.light,
                                "--light" if args.light else "--validate")
                   if target.family == "A" else None)
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    failures = 0
    for src in args.inputs:
        dst = args.output or output_path(src, target, args.outdir, args.suffix)
        result = process(src, dst, target, icc=icc, gs=gs, verapdf=verapdf,
                         password=args.password, condition=args.condition,
                         verbose=args.verbose, light=args.light)
        if result.status == "FAIL":
            print(f"{'skip' if result.skipped else 'FAIL'} {src}: {result.error}",
                  file=sys.stderr)
            failures += 1
            continue
        for w in result.warnings:
            print(f"warning: {src}: {w}", file=sys.stderr)
        for line in result.details:
            print(line, file=sys.stderr)
        check = f"({result.check})" if result.check else ""
        how = ", pages kept" if result.light else ""
        print(f"{result.status:<4}{check} {src} -> {dst} [{target.name}{how}]")
        failures += result.status != "OK"

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
