#!/usr/bin/env python3
"""Where a path handed to a gate on its command line is allowed to point.

Every gate here is run by a workflow with paths a step assembled, and a gate that
will read any file it is pointed at is a way to read any file. So each path from
a command line is resolved and refused if it leaves the working directory, in
one place, so that two gates cannot disagree about what is inside it.
"""

from __future__ import annotations

import pathlib


def within_cwd(raw: str) -> pathlib.Path:
    """Resolve a CLI-supplied path, refusing anything outside the working tree."""
    path = pathlib.Path(raw).resolve()
    if not path.is_relative_to(pathlib.Path.cwd().resolve()):
        print(f"::error::path escapes the working directory: {raw}")
        raise SystemExit(2)
    return path
