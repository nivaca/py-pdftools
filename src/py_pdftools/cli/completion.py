"""Completion scripts for bash, fish and zsh, made from the parser of the
command line, so that they always know its commands and options.

    py-pdftools completion bash > ~/.local/share/bash-completion/completions/py-pdftools
    py-pdftools completion fish > ~/.config/fish/completions/py-pdftools.fish
    py-pdftools completion zsh  > ~/.zfunc/_py-pdftools    (with fpath+=~/.zfunc)

The commands come in two levels (``py-pdftools labels set``, ``py-pdftools
impose booklet``); a command is known by its path, the words that lead to it.
(It started as py-foliation's, which had one level.)
"""

from __future__ import annotations

import argparse

PROG = "py-pdftools"
FILE_OPTIONS = ("-o", "--output", "-f", "--from-file", "--output-dir")
QUIET_OPTIONS = ("--password", "--remove", "-l", "--label")  # (that take a value no list can give)


def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    return next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)


def commands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    sub = _subparsers(parser)
    return dict(sub.choices) if sub else {}


def tree(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], argparse.ArgumentParser]:
    """{path: parser} of PARSER and every command under it (the path of PARSER is ())."""
    out = {path: parser}
    for name, sub in commands(parser).items():
        out.update(tree(sub, path + (name,)))
    return out


def options(parser: argparse.ArgumentParser) -> list[tuple[list[str], argparse.Action]]:
    return [(a.option_strings, a) for a in parser._actions if a.option_strings]


def _option_words(parser: argparse.ArgumentParser) -> str:
    return " ".join(o for strings, _ in options(parser) for o in strings)


def _positionals(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [a for a in parser._actions if not a.option_strings and not isinstance(a, argparse._SubParsersAction)]


def _choices(parser: argparse.ArgumentParser) -> list[str]:
    """The values its first positional with choices takes ([] if none)."""
    return next((list(map(str, a.choices)) for a in _positionals(parser) if a.choices), [])


def _help(action: argparse.Action) -> str:
    text = (action.help or "").split(";")[0].split(" (")[0]
    return text.replace("'", "").replace("\n", " ")[:70]


def _help_of(parser: argparse.ArgumentParser, name: str) -> str:
    sub = _subparsers(parser)
    choice = next((c for c in sub._choices_actions if c.dest == name), None) if sub else None
    return _help(choice) if choice else ""


def bash(parser: argparse.ArgumentParser) -> str:
    cases = []
    for path, sub in tree(parser).items():
        words = " ".join(commands(sub)) or " ".join(_choices(sub))
        files = "0" if commands(sub) or (_choices(sub) and not _positionals(sub)[1:]) else "1"
        cases.append(f'        "{" ".join(path)}") opts="{_option_words(sub)}"; words="{words}"; files={files} ;;')
    return f"""# bash completion for {PROG} (made by '{PROG} completion bash')
_py_pdftools() {{
    local cur prev path opts words files i w
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    case "$prev" in
        --interface) COMPREPLY=($(compgen -W "$({PROG} interface 2>/dev/null | awk 'NR>1 && NF>=2 {{print $(NF-1)}}')" -- "$cur")); return ;;
        {"|".join(FILE_OPTIONS)}) COMPREPLY=($(compgen -f -- "$cur")); return ;;
        {"|".join(QUIET_OPTIONS)}) return ;;
    esac
    # the path: the words before this one that name commands
    path=""
    for ((i = 1; i < COMP_CWORD; i++)); do
        w="${{COMP_WORDS[i]}}"
        case "$w" in -*) continue ;; esac
        [ "${{COMP_WORDS[i-1]}}" = "--interface" ] && continue
        _py_pdftools_case "${{path:+$path }}$w"
        if [ -n "$known" ]; then path="${{path:+$path }}$w"; fi
    done
    _py_pdftools_case "$path"
    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "$opts" -- "$cur"))
    else
        COMPREPLY=($(compgen -W "$words" -- "$cur"))
        if [ "$files" = 1 ]; then
            COMPREPLY+=($(compgen -f -X '!*.[pP][dD][fF]' -- "$cur") $(compgen -d -- "$cur"))
        fi
    fi
}}
_py_pdftools_case() {{
    known=1
    case "$1" in
{chr(10).join(cases)}
        *) known="" ;;
    esac
}}
complete -o filenames -F _py_pdftools {PROG}
"""


def fish(parser: argparse.ArgumentParser) -> str:
    nodes = tree(parser)
    paths = " ".join(f"'{' '.join(path)}'" for path in nodes if path)
    lines = [f"# fish completion for {PROG} (made by '{PROG} completion fish')",
             f"complete -c {PROG} -f",
             f"set -g __py_pdftools_paths {paths}",
             "function __py_pdftools_at --description 'whether the commands typed are those of PATH'",
             "    set -l path ''",
             "    set -l skip 0",
             "    for w in (commandline -opc)[2..-1]",
             "        if test $skip = 1; set skip 0; continue; end",
             "        if test \"$w\" = --interface; set skip 1; continue; end",
             "        string match -q -- '-*' $w; and continue",
             "        set -l longer (string trim -- \"$path $w\")",
             "        contains -- $longer $__py_pdftools_paths; and set path $longer",
             "    end",
             "    test \":$path\" = \":$argv[1]\"",
             "end"]
    for path, sub in nodes.items():
        cond = f"'__py_pdftools_at \"{' '.join(path)}\"'"
        for name in commands(sub):
            lines.append(f"complete -c {PROG} -n {cond} -a {name} -d '{_help_of(sub, name)}'")
        for strings, action in options(sub):
            lines.append(_fish_option(strings, action, cond))
        if path and not commands(sub):
            choices = _choices(sub)
            if choices:
                lines.append(f"complete -c {PROG} -n {cond} -a '{' '.join(choices)}'")
            elif _positionals(sub):
                lines.append(f"complete -c {PROG} -n {cond} -F -a '(__fish_complete_suffix .pdf)'")
    return "\n".join(lines) + "\n"


def _fish_option(strings: list[str], action: argparse.Action, cond: str) -> str:
    parts = [f"complete -c {PROG} -n {cond}"]
    for s in strings:
        parts.append(f"-l {s[2:]}" if s.startswith("--") else f"-s {s[1:]}")
    takes = action.nargs != 0
    if action.choices:
        parts.append(f"-x -a '{' '.join(map(str, action.choices))}'")
    elif takes and any(s in FILE_OPTIONS for s in strings):
        parts.append("-r -F")
    elif takes:
        parts.append("-x")
    parts.append(f"-d '{_help(action)}'")
    return " ".join(parts)


def zsh(parser: argparse.ArgumentParser) -> str:
    return (f"#compdef {PROG}\n# zsh completion for {PROG} (made by '{PROG} completion zsh'): the bash one\n"
            "autoload -U +X bashcompinit && bashcompinit\n" + bash(parser))


def script(shell: str, parser: argparse.ArgumentParser) -> str:
    return {"bash": bash, "fish": fish, "zsh": zsh}[shell](parser)
