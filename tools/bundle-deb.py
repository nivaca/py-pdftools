#!/usr/bin/env python3
"""Hace el paquete de Debian (.deb) de py-pdftools, para Debian 12, Ubuntu 22.04 y posteriores:

    uv run python tools/bundle-deb.py [--appimage APPIMAGE] [-o CARPETA]

El paquete es dist/py-pdftools_VERSIÓN-1_amd64.deb. Se hace de la AppImage (tools/bundle-appimage.py;
dist/py-pdftools-VERSIÓN-x86_64.AppImage), que se desempaca: py-pdftools necesita Python 3.14, que Debian y
casi todos los Ubuntu no tienen, así que el paquete lo trae, con Qt y las bibliotecas, como la AppImage. Instala:

    /opt/py-pdftools/                      los archivos de la AppImage: su Python, con py-pdftools dentro
    /usr/bin/py-pdftools, py-pdftools-gui  la línea de órdenes y la ventana
    /usr/share/applications, icons, man, metainfo, doc/py-pdftools/copyright

Depende solo de las bibliotecas del sistema que Qt necesita (como la AppImage), y recomienda tesseract y
Ghostscript (OCR, PDF/A y PDF/X). No hacen falta las herramientas de Debian para hacerlo: un .deb es un archivo
ar de tres miembros (debian-binary, control.tar.xz, data.tar.xz), que se escribe aquí; los tar los hace GNU tar,
con root como dueño de todos los archivos.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
REVISION = "1"  # (the Debian revision: the package's own, after the program's version)
APP = "py-pdftools"
MAINTAINER = "Nicolas Vaughan <nicolasvaughan@proton.me>"
# Lo que Qt (PySide6) toma del sistema, como la AppImage: el resto viene dentro del paquete
DEPENDS = ("libc6 (>= 2.34), libegl1, libgl1, libxkbcommon0, libxkbcommon-x11-0, libfontconfig1, libdbus-1-3, "
           "libxcb-cursor0")
RECOMMENDS = "tesseract-ocr, ghostscript"
DESCRIPTION = """\
edit PDF documents: annotate, redact, OCR, foliate and impose them
 py-pdftools annotates PDF documents, fills their forms, redacts them
 (removing for good what is under the boxes), reads the text of scanned
 pages with tesseract (OCR), sets their page labels, headers, footers and
 watermarks, arranges, combines and splits their pages, imposes them for
 printing, signs them, and makes copies as PDF/A and PDF/X. It has a window
 (py-pdftools-gui) and a command line (py-pdftools), in English and Spanish.
 .
 This package brings its own Python 3.14, Qt and libraries, in
 /opt/py-pdftools."""

LAUNCHER = """#!/bin/sh
#  %(what)s of py-pdftools (its own Python, in /opt/py-pdftools: see tools/bundle-deb.py)
export APPDIR=/opt/py-pdftools
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP VIRTUAL_ENV
exec "$APPDIR/%(python)s" -m %(module)s "$@"
"""

COPYRIGHT = """\
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: py-pdftools
Upstream-Contact: Nicolas Vaughan <nicolasvaughan@proton.me>
Source: https://github.com/nivaca/py-pdftools

Files: *
Copyright: 2026 Nicolas Vaughan
License: GPL-3.0-or-later
 On Debian systems, the full text of the GNU General Public License version 3 can be found in
 /usr/share/common-licenses/GPL-3.
Comment: /opt/py-pdftools holds the software py-pdftools uses, each under its own licence (listed in
 https://github.com/nivaca/py-pdftools/blob/main/docs/THIRD-PARTY.md): Python (PSF-2.0), PyMuPDF (AGPL-3.0),
 pikepdf (MPL-2.0), PySide6 and Qt (LGPL-3.0), reportlab (BSD-3-Clause) and the libraries they bring.
"""


def say(text: str):
    print(text, file=sys.stderr, flush=True)


def deb_name() -> str:
    return f"{APP}_{VERSION}-{REVISION}_amd64.deb"


def unpack(appimage: Path, into: Path) -> Path:
    """The files of APPIMAGE (its AppDir), unpacked into INTO."""
    say(f"Unpacking {appimage.name}")
    subprocess.run([str(appimage.resolve()), "--appimage-extract"], cwd=into, check=True,
                   stdout=subprocess.DEVNULL)
    return into / "squashfs-root"


def python_in(appdir: Path) -> str:
    """The Python of the AppDir, as its AppRun names it (relative to the AppDir)."""
    m = re.search(r'^PYTHON="\$APPDIR/([^"]+)"', (appdir / "AppRun").read_text(), re.M)
    if not m:
        sys.exit("bundle-deb.py: the AppRun of the AppImage doesn't name its Python")
    return m[1]


def lay_out(appdir: Path, tree: Path):
    """The files of the package in TREE, as they are installed (TREE is /)."""
    opt = tree / "opt" / APP
    shutil.copytree(appdir, opt, symlinks=True)
    python = python_in(appdir)
    bin_dir = tree / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    for name, module, what in ((APP, "py_pdftools", "The command line"),
                               (f"{APP}-gui", "py_pdftools.gui", "The window")):
        path = bin_dir / name
        path.write_text(LAUNCHER % {"python": python, "module": module, "what": what})
        path.chmod(0o755)
    share = tree / "usr" / "share"
    (share / "applications").mkdir(parents=True)
    shutil.copy2(ROOT / "packaging" / f"{APP}.desktop", share / "applications" / f"{APP}.desktop")
    shutil.copytree(ROOT / "src" / "py_pdftools" / "icons" / "linux" / "hicolor", share / "icons" / "hicolor")
    (share / "metainfo").mkdir()
    for meta in (ROOT / "packaging").glob("*.metainfo.xml"):
        shutil.copy2(meta, share / "metainfo" / meta.name)
    for lang, folder in (("", "man1"), ("es", "es/man1")):
        page = ROOT / "packaging" / "man" / lang / f"{APP}.1"
        target = share / "man" / folder / f"{APP}.1.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        # (gzip sin fecha ni nombre: el mismo paquete cada vez)
        with open(target, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(page.read_bytes())
    doc = share / "doc" / APP
    doc.mkdir(parents=True)
    (doc / "copyright").write_text(COPYRIGHT)
    for path in tree.rglob("*"):  # (todos legibles por todos; los ejecutables, también ejecutables)
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(0o755 if path.is_dir() or mode & 0o111 else 0o644)


def control(tree: Path, folder: Path):
    """The control files (control, md5sums) of the package whose files are in TREE, in FOLDER."""
    # Installed-Size is in KiB, the size of the files as installed
    size = sum(p.lstat().st_size for p in tree.rglob("*") if not p.is_dir())
    folder.mkdir()
    (folder / "control").write_text(
        f"Package: {APP}\nVersion: {VERSION}-{REVISION}\nArchitecture: amd64\nMaintainer: {MAINTAINER}\n"
        f"Installed-Size: {size // 1024 + 1}\nDepends: {DEPENDS}\nRecommends: {RECOMMENDS}\nSection: graphics\n"
        f"Priority: optional\nHomepage: https://github.com/nivaca/py-pdftools\nDescription: {DESCRIPTION}\n")
    lines = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file() and not p.is_symlink()):
        lines.append(f"{hashlib.md5(path.read_bytes()).hexdigest()}  {path.relative_to(tree)}")
    (folder / "md5sums").write_text("\n".join(lines) + "\n")


def tar_xz(folder: Path, target: Path):
    """A tar.xz of FOLDER's contents (./...), every file owned by root."""
    env = dict(os.environ, XZ_OPT="-6 -T0")  # (xz en todos los núcleos)
    subprocess.run(["tar", "--create", "--xz", "--file", str(target), "--directory", str(folder),
                    "--owner=0", "--group=0", "--numeric-owner", "--sort=name", "."], check=True, env=env)


def ar(target: Path, members: list[tuple[str, bytes | Path]]):
    """An ar archive (the format of a .deb) of MEMBERS: (name, its bytes or a file)."""
    now = int(time.time())
    with open(target, "wb") as out:
        out.write(b"!<arch>\n")
        for name, data in members:
            size = data.stat().st_size if isinstance(data, Path) else len(data)
            header = f"{name:<16}{now:<12}{0:<6}{0:<6}{'100644':<8}{size:<10}`\n".encode()
            assert len(header) == 60
            out.write(header)
            if isinstance(data, Path):
                with open(data, "rb") as f:
                    shutil.copyfileobj(f, out, 1 << 20)
            else:
                out.write(data)
            if size % 2:  # (ar pads each member to an even size)
                out.write(b"\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Make the Debian package of py-pdftools, from its AppImage.")
    parser.add_argument("--appimage", type=Path, default=DIST / f"{APP}-{VERSION}-x86_64.AppImage",
                        help="the AppImage to make it from (tools/bundle-appimage.py)")
    parser.add_argument("-o", "--output", type=Path, default=DIST, help="the folder of the package (dist)")
    args = parser.parse_args(argv)
    if not args.appimage.is_file():
        sys.exit(f"bundle-deb.py: there is no {args.appimage} (make it first: tools/bundle-appimage.py)")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "build" if (ROOT / "build").is_dir() else None) as tmp:
        work = Path(tmp)
        appdir = unpack(args.appimage, work)
        tree = work / "data"
        say("Laying out the files of the package")
        lay_out(appdir, tree)
        control(tree, work / "control")
        say("Compressing them (xz)")
        tar_xz(work / "control", work / "control.tar.xz")
        tar_xz(tree, work / "data.tar.xz")
        target = args.output / deb_name()
        ar(target, [("debian-binary", b"2.0\n"), ("control.tar.xz", work / "control.tar.xz"),
                    ("data.tar.xz", work / "data.tar.xz")])
    # Solo el paquete de esta versión en dist/: los de versiones anteriores se van
    for old in args.output.glob(f"{APP}_*_amd64.deb"):
        if old.name != deb_name():
            old.unlink()
    say(f"Wrote {target} ({target.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
