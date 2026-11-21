"""Tests of the packaging: the versions agree, and the files that make the
RPM and the AppImage are sound."""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from py_pdftools import __version__

ROOT = Path(__file__).resolve().parent.parent


def spec_field(name: str) -> str:
    m = re.search(rf"^{name}:\s*(\S+)", (ROOT / "packaging/py-pdftools.spec").read_text(), re.M)
    return m.group(1) if m else ""


def test_versions_agree():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["version"] == __version__
    assert spec_field("Version") == __version__, "bump the spec: rpmdev-bumpspec -n VERSION"


def test_spec_changelog_has_this_version():
    changelog = (ROOT / "packaging/py-pdftools.spec").read_text().split("%changelog", 1)[1]
    first = next(line for line in changelog.splitlines() if line.startswith("*"))
    assert first.rstrip().endswith(f"- {__version__}-{spec_field('Release').split('%')[0]}")


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="desktop-file-utils not installed")
def test_desktop_file():
    r = subprocess.run(["desktop-file-validate", str(ROOT / "packaging/py-pdftools.desktop")],
                       capture_output=True, text=True)
    assert r.stdout + r.stderr == ""


def test_scripts_parse():
    assert subprocess.run(["bash", "-n", str(ROOT / "packaging/build-rpm.sh")]).returncode == 0
    for tool in ("release.py", "bundle-appimage.py"):
        compile((ROOT / "tools" / tool).read_text(), tool, "exec")


@pytest.mark.skipif(not shutil.which("rpmspec"), reason="rpm-build not installed")
def test_spec_parses():
    r = subprocess.run(["rpmspec", "-q", "--srpm", "--qf", "%{version}", str(ROOT / "packaging/py-pdftools.spec")],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == __version__, r.stderr


def pinned_key() -> str:
    m = re.search(r'SIGNING_KEY="\$\{SIGNING_KEY:-([0-9A-F]{40})\}"', (ROOT / "packaging/build-rpm.sh").read_text())
    assert m, "build-rpm.sh must pin the project's signing key"
    return m.group(1)


@pytest.mark.skipif(not shutil.which("gpg"), reason="gpg not installed")
def test_the_shipped_key_is_the_pinned_one(tmp_path):
    r = subprocess.run(["gpg", "--batch", "--with-colons", "--show-keys",
                        str(ROOT / "packaging/RPM-GPG-KEY-py-pdftools")],
                       capture_output=True, text=True, env={"GNUPGHOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    fprs = [line.split(":")[9] for line in r.stdout.splitlines() if line.startswith("fpr:")]
    assert fprs and fprs[0] == pinned_key()


@pytest.mark.skipif(not all(shutil.which(t) for t in ("gpg", "git", "rpmbuild", "rpmspec")),
                    reason="gpg, git or rpm-build not installed")
def test_signing_without_the_key_says_how_to_import_it(tmp_path):
    """--sign uses only the pinned key: with an empty keyring it stops before building."""
    env = {"GNUPGHOME": str(tmp_path), "PATH": "/usr/bin:/bin", "RPMSIGN": "/bin/true"}
    r = subprocess.run(["bash", str(ROOT / "packaging/build-rpm.sh"), "--sign"], capture_output=True, text=True,
                       env=env)
    assert r.returncode == 1
    assert f"no secret key matching {pinned_key()}" in r.stderr and "gpg --import" in r.stderr


@pytest.mark.skipif(not (ROOT / "install").is_dir(), reason="the installers are not here")
def test_installers(tmp_path):
    """The installers parse, explain themselves, and refuse what they can't do."""
    sh = ROOT / "install/install.sh"
    assert subprocess.run(["bash", "-n", str(sh)]).returncode == 0
    r = subprocess.run(["bash", str(sh), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--uninstall" in r.stdout and "#" not in r.stdout
    r = subprocess.run(["bash", str(sh), "--python", str(tmp_path / "none")], capture_output=True, text=True,
                       env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 1 and "3.14 or later" in r.stderr
    assert not (tmp_path / ".local").exists()  # (nothing made)
    ps1 = (ROOT / "install/install.ps1").read_text()
    assert "param(" in ps1 and "-m py_pdftools.gui" in ps1 and "LOCALAPPDATA" in ps1
    assert ps1.isascii()  # (Windows PowerShell reads a file without a BOM as ANSI)
    assert "install.ps1" in (ROOT / "install/install.bat").read_text()


def test_the_manual_is_up_to_date():
    """The manual pages are the help of the command line (tools/manpage.py)."""
    import sys

    r = subprocess.run([sys.executable, str(ROOT / "tools/manpage.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(not shutil.which("appstreamcli"), reason="appstream not installed")
def test_metainfo():
    r = subprocess.run(["appstreamcli", "validate", "--no-net", "--pedantic",
                        str(ROOT / "packaging/io.github.nivaca.py-pdftools.metainfo.xml")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_icons():
    """The icons of every size, made from the SVG by tools/icons.py, for the menus, macOS and Windows."""
    icons = ROOT / "src/py_pdftools/icons"
    for n in (16, 22, 24, 32, 48, 64, 96, 128, 192, 256, 512):
        assert (icons / f"linux/hicolor/{n}x{n}/apps/py-pdftools.png").is_file()
    assert (icons / "linux/hicolor/scalable/apps/py-pdftools.svg").read_bytes() == (icons / "py-pdftools.svg").read_bytes()
    assert (icons / "macos/py-pdftools.icns").read_bytes()[:4] == b"icns"
    assert (icons / "windows/py-pdftools.ico").is_file()


@pytest.mark.skipif(shutil.which("bash") is None or __import__("os").name == "nt", reason="AppRun is bash, for Linux")
def test_the_appimage_starts_the_window_or_the_command_line(tmp_path):
    """The AppImage's AppRun: the window with nothing, a file (with a place, too) or --background; any other
    word, a command of the command line (also those added after AppRun was written)."""
    import importlib.util
    import subprocess

    spec = importlib.util.spec_from_file_location("bundle", ROOT / "tools" / "bundle-appimage.py")
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    fake = tmp_path / "python"
    fake.write_text('#!/bin/bash\necho "$2"\n')  # (says which module it was asked to run)
    fake.chmod(0o755)
    apprun = tmp_path / "AppRun"
    apprun.write_text(bundle.APPRUN % {"python": "python"})
    apprun.chmod(0o755)
    book = tmp_path / "book.pdf"
    book.write_bytes(b"%PDF-1.4\n")

    def module(*args):
        return subprocess.run([str(apprun), *args], capture_output=True, text=True, check=True,
                              env={"PATH": "/usr/bin:/bin"}).stdout.strip()

    assert module() == "py_pdftools.gui"
    assert module(str(book)) == module(f"{book}#page=3") == module("--background") == "py_pdftools.gui"
    for command in ("impose", "combine", "export", "pdf-version", "form", "ocr", "--help"):
        assert module(command, "x") == "py_pdftools", command
