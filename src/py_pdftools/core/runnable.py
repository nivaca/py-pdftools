"""Archivos que el escritorio ejecutaría en lugar de abrir: un programa, un guion, un acceso directo, un
instalador. Un PDF puede traer uno adjunto (o enlazar uno con una dirección file:), y abrirlo con el programa
del escritorio lo pondría en marcha (en Windows, factura.exe corre con un doble clic); el programa no los abre,
solo deja guardarlos, para que el usuario decida. La lista sigue la de Calibre (safe_open_url), ampliada."""

from __future__ import annotations

from pathlib import PurePath

# Extensions of files that run, or install, when they are opened: Windows, macOS, Linux and the interpreters.
RUNNABLE = frozenset("""
    exe com cmd bat pif scr cpl msc msi msp msix appx appxbundle application gadget hta jar jnlp lnk url scf
    reg inf vb vbs vbe js jse ws wsf wsh wsc ps1 ps1xml ps2 psc1 psd1 psm1 psh vba vbx
    app command tool action workflow pkg mpkg dmg
    sh bash zsh csh ksh fish run bin desktop appimage deb rpm flatpak flatpakref snap
    py pyw pyc pyz rb pl php lua tcl
""".split())


def could_run(name: str) -> bool:
    """Whether the file NAME would be run (or installed) by the desktop, if opened: by its extension, whatever
    its case, with the dots and spaces at its end that Windows drops ('bill.exe.' is bill.exe)."""
    clean = PurePath(name.strip().rstrip(". ")).name.lower()
    suffix = PurePath(clean).suffix.lstrip(".")
    return suffix in RUNNABLE
