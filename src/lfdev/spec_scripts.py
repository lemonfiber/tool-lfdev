"""Running the copy of spec's scripts this package carries (`vendored/`), and
finding the checkout of spec `status_check.py` reads identifiers from."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence

#: Where the copy is.
VENDORED = pathlib.Path(__file__).resolve().parent / "vendored"
#: The variable naming a checkout of spec.
SPEC_VARIABLE = "LFDEV_SPEC"

#: Runs a program in a directory, its output passed through, and gives back its
#: exit code.
Runner = Callable[[Sequence[str], pathlib.Path | None], int]


def run(args: Sequence[str], cwd: pathlib.Path | None = None) -> int:
    """A program's exit code, its output left on the terminal."""
    return subprocess.run(list(args), cwd=cwd, check=False).returncode


def script(name: str, *args: str, cwd: pathlib.Path | None = None, runner: Runner = run) -> int:
    """One of spec's scripts, from the copy, with this Python. spec's scripts
    refuse a path outside the directory they run in, so the caller names one
    that holds every path it passes."""
    return runner([sys.executable, str(VENDORED / name), *args], cwd)


def spec_root(given: str | None, here: pathlib.Path, environ: Mapping[str, str] = os.environ) -> pathlib.Path:
    """The checkout of spec to read: the one named, else the variable's, else a
    clone beside this repository."""
    named = given or environ.get(SPEC_VARIABLE)
    found = pathlib.Path(named) if named else here.parent / "spec"
    if not (found / "10-functional").is_dir():
        raise FileNotFoundError(
            f"no checkout of spec at {found}: clone https://github.com/lemonfiber/spec beside "
            f"this repository, or name one with --spec or {SPEC_VARIABLE}"
        )
    return found
