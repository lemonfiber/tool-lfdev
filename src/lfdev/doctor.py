"""`lfdev doctor`: whether this clone is set up to commit the way every
lemonfiber repository asks (GOV-R59).

Each check reads one thing from git or `gh` and says what to run where it
fails. Nothing here changes the clone.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

#: Runs a program and gives back its exit code and what it printed.
Runner = Callable[[Sequence[str]], tuple[int, str]]

#: Where every lemonfiber repository keeps its hooks.
HOOKS = ".githooks"


def run(args: Sequence[str]) -> tuple[int, str]:
    """A program's exit code and standard output, or 127 where it is missing."""
    try:
        done = subprocess.run(list(args), capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 127, ""
    return done.returncode, done.stdout.strip()


@dataclass(frozen=True)
class Check:
    """One thing the clone needs, and how it stands."""

    name: str
    ok: bool
    fix: str


def _config(runner: Runner, key: str) -> str:
    code, value = runner(["git", "config", "--get", key])
    return value if code == 0 else ""


def checks(runner: Runner = run) -> list[Check]:
    """Every check, in the order a new clone is set up."""
    name, email = _config(runner, "user.name"), _config(runner, "user.email")
    signing = _config(runner, "commit.gpgsign").lower() == "true"
    key = _config(runner, "user.signingkey")
    gh, _ = runner(["gh", "auth", "status"])
    return [
        Check(
            "hooks on",
            _config(runner, "core.hooksPath") == HOOKS,
            f"git config core.hooksPath {HOOKS}",
        ),
        Check(
            "sign-off identity",
            bool(name and email),
            'git config user.name "Your Name" && git config user.email you@example.org',
        ),
        Check(
            "commits signed",
            signing and bool(key),
            "git config commit.gpgsign true && git config user.signingkey <key>",
        ),
        Check("gh authenticated", gh == 0, "gh auth login"),
    ]


def report(found: list[Check]) -> tuple[int, str]:
    """The exit code and the lines `doctor` prints."""
    lines = [f"{'ok  ' if c.ok else 'FIX '} {c.name}" + ("" if c.ok else f"  ->  {c.fix}") for c in found]
    return (0 if all(c.ok for c in found) else 1), "\n".join(lines)
