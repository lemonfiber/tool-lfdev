"""`lfdev status <id> <state>`: record in this repository's tracker that a
requirement is done, partial or open (GOV-R59).

It writes the row, has spec's own `status_check.py` check the tracker against
the specification and this repository, and commits the row, signed, with the
`Spec:` line and a sign-off (REPO-R77). A row the check refuses is taken back
and nothing is committed. It will not commit to `main`.
"""

from __future__ import annotations

import os
import pathlib
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from lfdev import spec_scripts, tracker

#: The branch a change never goes to directly.
DEFAULT = "main"

#: Runs a program and gives back its exit code and what it printed.
Asker = Callable[[Sequence[str]], tuple[int, str]]


@dataclass(frozen=True)
class Asked:
    """What `lfdev status` was asked to record."""

    ident: str
    state: str
    evidence: list[str]
    landed: str | None
    spec: str | None


def record(
    asked: Asked,
    ask: Asker,
    run: spec_scripts.Runner = spec_scripts.run,
) -> tuple[int, str]:
    """Write, check and commit one row; the exit code and what to say."""
    code, top = ask(["git", "rev-parse", "--show-toplevel"])
    if code != 0:
        return 2, "not inside a git repository"
    root = pathlib.Path(top)
    _, branch = ask(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == DEFAULT:
        return 2, f"on {DEFAULT}: make a branch for the change first (git switch -c <name>)"
    try:
        line = tracker.row(asked.ident, asked.state, asked.evidence, asked.landed)
        spec = spec_scripts.spec_root(asked.spec, root)
        path = tracker.path_for(root, asked.ident)
        before = path.read_text("utf-8") if path.is_file() else None
        after = tracker.with_row(before or "", asked.ident, line)
        tomllib.loads(after)
    except (ValueError, FileNotFoundError) as refused:  # a TOMLDecodeError is a ValueError
        return 2, str(refused)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(after, "utf-8")
    # Run where both the checkout and this repository sit, the way spec's own
    # CI runs it with spec checked out inside the repository.
    common = pathlib.Path(os.path.commonpath([spec.resolve(), root.resolve()]))
    checked = spec_scripts.script(
        "status_check.py",
        "check",
        "--spec",
        str(spec.resolve().relative_to(common)),
        "--repo-root",
        str(root.resolve().relative_to(common)),
        cwd=common,
        runner=run,
    )
    if checked != 0:
        if before is None:
            path.unlink()
        else:
            path.write_text(before, "utf-8")
        return checked, f"{path.relative_to(root)} left as it was: status_check refused the row"
    relative = str(path.relative_to(root))
    committed = run(["git", "add", "--", relative], root)
    if committed == 0:
        message = ["-m", f"chore(status): {asked.ident} is {asked.state}", "-m", f"Spec: {asked.ident}"]
        committed = run(["git", "commit", "-S", "-s", *message, "--", relative], root)
    if committed != 0:
        return committed, f"{relative} is written and checked, and git did not commit it"
    return 0, f"{asked.ident} is {asked.state} in {relative}, committed"
