"""A repository's tracker row, written the way every lemonfiber tracker writes
it (OPS-R74): one inline table per requirement in `requirement = [ … ]`, in
`status.toml` or, where the repository splits it, in `status/<feature>.toml`.

Pure functions over text and paths. `lfdev status` writes what these return and
hands the file to spec's own check.
"""

from __future__ import annotations

import json
import pathlib
import re

#: The states a row may be in.
STATES = ("done", "partial", "open")
#: A tracker kept whole.
FILE = "status.toml"
#: A tracker split by feature.
DIRECTORY = "status"
#: A requirement's identifier, the whole of what may name a tracker's file.
IDENTIFIER = re.compile(r"[A-Z][A-Z0-9]*-R\d+")
#: What a new tracker opens with.
HEADER = (
    "# What this repository implements, one row per requirement (OPS-R74);\n"
    "# read by spec's status_check.py and the release gate.\n\n"
)


def identifier(text: str) -> str:
    """A requirement's identifier, refused unless it is one, so nothing typed can
    name a file outside the tracker."""
    if not IDENTIFIER.fullmatch(text):
        raise ValueError(f"{text!r} is not a requirement identifier such as F8-R6")
    return text


def family(ident: str) -> str:
    """The feature or namespace a requirement belongs to: `F8` for `F8-R6`."""
    return identifier(ident).partition("-R")[0]


def path_for(root: pathlib.Path, ident: str) -> pathlib.Path:
    """The file a requirement's row is kept in."""
    split = root / DIRECTORY
    return split / f"{family(ident)}.toml" if split.is_dir() else root / FILE


def row(ident: str, state: str, evidence: list[str], landed: str | None) -> str:
    """One row, as a line. TOML's basic strings are JSON's, so each value is
    written by `json.dumps` and needs no quoting of its own."""
    identifier(ident)
    if state not in STATES:
        raise ValueError(f"{state!r} is not a state; a row is {', '.join(STATES)}")
    if state == "done" and not evidence:
        raise ValueError("a done row names its evidence: --evidence <path or path::test>")
    fields = [
        f"id = {json.dumps(ident)}",
        f"state = {json.dumps(state)}",
        f"evidence = [{', '.join(json.dumps(e) for e in evidence)}]",
    ]
    if landed:
        fields.append(f"landed = {json.dumps(landed)}")
    return "  { " + ", ".join(fields) + " },"


def with_row(text: str, ident: str, line: str) -> str:
    """The tracker's text with the requirement's row replaced, or added before
    the array closes; a tracker with no text yet is begun."""
    if not text.strip():
        return f"{HEADER}requirement = [\n{line}\n]\n"
    mine = re.compile(rf'^\s*\{{\s*id\s*=\s*"{re.escape(ident)}"\s*,.*$', re.MULTILINE)
    if mine.search(text):
        return mine.sub(lambda _: line, text, count=1)
    lines = text.rstrip("\n").split("\n")
    closing = max((i for i, ln in enumerate(lines) if ln.strip() == "]"), default=None)
    if closing is None:
        raise ValueError("the tracker holds no `requirement = [ … ]` array to add a row to")
    return "\n".join([*lines[:closing], line, *lines[closing:]]) + "\n"
