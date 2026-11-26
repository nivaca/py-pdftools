Code signing policy
===================

Free code signing provided by [SignPath.io](https://about.signpath.io),
certificate by [SignPath Foundation](https://signpath.org).

What is signed
--------------

The installer for Windows (`py-pdftools-VERSION-windows-x64-setup.exe`) is
signed with Authenticode by SignPath Foundation's certificate. It is built
from the source of this repository, at the tag of each release, by the
workflow `.github/workflows/installers.yml` on GitHub's own runners, and it
is sent to SignPath from that same workflow; no installer built anywhere
else is signed. Each signing request is approved by hand.

The libraries that the installer carries (Python, Qt, PyMuPDF, pikepdf,
tesseract and the others, listed with their licences in
[docs/THIRD-PARTY.md](docs/THIRD-PARTY.md)) are not signed by this project:
they are those of their own maintainers.

Apart from that, every file of every release, the installers too, has a
detached signature (`FILE.asc`) made with the project's own GPG key,
[packaging/RPM-GPG-KEY-py-pdftools](packaging/RPM-GPG-KEY-py-pdftools);
see the README.

Team roles
----------

py-pdftools has one maintainer, who holds every role:

- Committers and reviewers: [Nicolas Vaughan](https://github.com/nivaca)
- Approvers: [Nicolas Vaughan](https://github.com/nivaca)

Changes proposed by anyone else (pull requests) are reviewed by him
before they are merged. Multi-factor authentication is used for GitHub and
for SignPath.

Privacy policy
--------------

This program will not transfer any information to other networked systems
unless specifically requested by the user or the person installing or
operating it.

py-pdftools works on the files one opens, on the computer itself. It
connects to the internet only in two cases, and only when the user asks:

- Help > Check for updates asks GitHub (api.github.com) for the latest
  release of py-pdftools. The program never asks by itself, and the
  request carries nothing about the user or the computer.
- OCR > Languages downloads the models of tesseract that the user chooses
  (tessdata_best and osd), from the repositories of the tesseract project
  on GitHub.

In both cases what GitHub records of a request (the address it comes from)
falls under [GitHub's privacy statement](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement).
