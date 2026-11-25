"""Los instaladores de Windows (Inno Setup) y de macOS (una imagen de disco con py-pdftools.app) tienen lo que
deben, aunque solo se hacen en su sistema (.github/workflows/installers.yml); la carpeta de cada uno se arma en
cualquier sistema con --stage-only, que aquí no se prueba (descarga cientos de MB)."""

from __future__ import annotations

import importlib.util
import plistlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "packaging" / "installer"


def tool(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_installer_script():
    iss = (INSTALLER / "py-pdftools.iss").read_text(encoding="utf-8")
    # (the AppId never changes: so Windows knows each version as the same program)
    assert "AppId={{C2BDCF32-2C91-4BE6-A40D-97138BBCA219}" in iss
    assert "PrivilegesRequired=lowest" in iss and "MinVersion=10.0" in iss
    assert '"compiler:Languages\\Spanish.isl"' in iss
    assert '"-s -m py_pdftools.gui"' in iss and "uninsdeletekey" in iss
    # PDFs in Open with, with a type of its own, taking no one's default program
    assert '#define ProgId "py-pdftools.pdf"' in iss
    assert "Software\\Classes\\.pdf\\OpenWithProgids" in iss and "uninsdeletevalue" in iss
    assert "slowdown" not in iss.lower()
    for define in ("AppVersion", "FileVersion", "SourceDir", "OutputDir", "OutputName"):
        assert f"/D{define}=" in (ROOT / "tools" / "bundle-installer.py").read_text(), define


def test_installer_tool():
    bundle = tool("bundle-installer")
    assert set(bundle.TRIPLES.values()) == set(bundle.PBS_SHA256)
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in bundle.PBS_SHA256.values())
    assert bundle.PYTHON_MINOR == "3.14"
    assert set(bundle.TRIPLES) == {("windows", "x64"), ("macos", "arm64")}  # (no Intel Mac: see MACOS_MINIMUM)
    assert bundle.name("windows", "x64") == f"py-pdftools-{bundle.VERSION}-windows-x64-setup.exe"
    assert bundle.name("macos", "arm64") == f"py-pdftools-{bundle.VERSION}-macos-arm64.dmg"
    plist = bundle.info_plist()
    assert plist["LSMinimumSystemVersion"] == "15.0" and plist["CFBundleExecutable"] == "py-pdftools"
    kinds = plist["CFBundleDocumentTypes"][0]
    assert kinds["CFBundleTypeExtensions"] == ["pdf"] and kinds["LSHandlerRank"] == "Alternate"
    plistlib.dumps(plist)  # (it is written without errors)
    assert "-m py_pdftools.gui" in bundle.MACOS_LAUNCHER
    compile((INSTALLER / "check.py").read_text(), "check.py", "exec")
    assert "slowdown" not in (ROOT / "tools" / "bundle-installer.py").read_text().lower()


def test_workflow_and_release_agree():
    """The names the workflow makes are those release.py --installers looks for."""
    release = (ROOT / "tools" / "release.py").read_text()
    workflow = (ROOT / ".github" / "workflows" / "installers.yml").read_text()
    for suffix in ("windows-x64-setup.exe", "macos-arm64.dmg"):
        assert suffix in release
    assert "macos-x86_64" not in release
    assert "--system windows" in workflow and "--system macos --arch arm64" in workflow
    # (only for tags and by hand: not on every push to main)
    assert workflow.count("if: github.event_name == 'workflow_dispatch' || startsWith(github.ref, 'refs/tags/')") == 2
