"""Allow ``python -m py_pdftools.gui``."""

from . import main

# (guarded: a process that renders pages imports the main module again)
if __name__ == "__main__":
    raise SystemExit(main())
