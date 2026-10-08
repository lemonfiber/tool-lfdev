"""The board snapshot: what `lfdev` reports about versions, goals, claims and
repositories, read from the one file the specification publishes and the
frontpage renders (REPO-R76).

Its shape is documented in the specification's `70-operations/board-format.md`.
A snapshot that cannot be read, or names a `format` this tool does not know, is
refused rather than read as an empty board.
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.request
from collections.abc import Mapping
from typing import Any

from lfdev import forge

#: Where the newest snapshot is published.
BOARD_URL = "https://github.com/lemonfiber/spec/releases/download/board/board.json"
#: The one shape of `board.json` this tool reads.
FORMAT = 1
#: The variable naming another snapshot, a URL or a path, for a run that must
#: read a particular one.
SOURCE_VARIABLE = "LFDEV_SNAPSHOT"
#: How long the download may take before it is given up, in seconds.
TIMEOUT = 30

Board = dict[str, Any]


class Unreadable(Exception):
    """The snapshot could not be read, or is not one this tool knows."""


def parse(text: str) -> Board:
    """A snapshot from its text, refused unless it is in the format read here."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as broken:
        raise Unreadable(f"the board snapshot is not JSON: {broken}") from broken
    if not isinstance(data, dict):
        raise Unreadable("the board snapshot is not an object")
    if data.get("format") != FORMAT:
        raise Unreadable(f"the board snapshot is format {data.get('format')!r}; lfdev reads format {FORMAT}")
    return data


def fetch(url: str) -> str:
    """The text at a URL, over HTTPS."""
    if not url.startswith("https://"):
        raise Unreadable(f"{url} is not an https address")
    request = urllib.request.Request(url, headers={"User-Agent": forge.USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return answer.read().decode("utf-8")


def source(environ: Mapping[str, str] = os.environ) -> str:
    """Where to read the snapshot: the variable's value, or the published one."""
    return environ.get(SOURCE_VARIABLE) or BOARD_URL


def load(where: str) -> Board:
    """The snapshot at a URL or a path."""
    try:
        text = fetch(where) if "://" in where else pathlib.Path(where).read_text("utf-8")
    except OSError as broken:
        raise Unreadable(f"the board snapshot at {where} could not be read: {broken}") from broken
    return parse(text)
