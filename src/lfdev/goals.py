"""`lfdev goals <version> --add <id> --remove <id>`: change the goals a version
promises, and open the pull request that asks for it (OPS-R30, OPS-R31).

It runs in a checkout of spec, on a branch. It rewrites the manifest's `goals`
list, commits it signed with the `Spec:` line and a sign-off, pushes the branch
and opens the pull request through REST as the person (REPO-R75, REPO-R77). A
version past `planned` has frozen goals, and its pull request carries the
`goals-change` label that `check_goals_change.py` asks of it.
"""

from __future__ import annotations

import pathlib
import re
import tomllib
import urllib.error
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from lfdev import forge, tracker
from lfdev.spec_scripts import Runner
from lfdev.status import DEFAULT, Asker

#: The manifests, from the root of a checkout of spec.
VERSIONS = pathlib.Path("70-operations/versions")
#: The repository the pull request is opened against.
REPO = f"{forge.ORG}/spec"
#: The one status whose goals are not yet locked.
UNLOCKED = "planned"
#: The label a pull request moving locked goals carries.
LABEL = "goals-change"
#: What the commit serves.
REQUIREMENTS = "OPS-R30, OPS-R31"
#: A version, as a manifest is named.
VERSION = re.compile(r"\d+\.\d+\.\d+")
#: The line the goals list opens on.
GOALS = re.compile(r"^goals\s*=\s*\[")

#: One POST to the forge: its path and body, then the JSON it answers with.
Poster = Callable[[str, Mapping[str, Any]], Any]


@dataclass(frozen=True)
class Asked:
    """What `lfdev goals` was asked to change."""

    version: str
    add: list[str]
    remove: list[str]


def changed(goals: list[str], asked: Asked) -> list[str]:
    """The goals with the asked ones added and removed, or why not."""
    if not asked.add and not asked.remove:
        raise ValueError("name a goal to --add or --remove")
    for ident in [*asked.add, *asked.remove]:
        if not tracker.IDENTIFIER.fullmatch(ident):
            raise ValueError(f"{ident!r} is not a requirement identifier")
    present = [ident for ident in asked.add if ident in goals]
    absent = [ident for ident in asked.remove if ident not in goals]
    if present:
        raise ValueError(f"{asked.version} already promises {', '.join(present)}")
    if absent:
        raise ValueError(f"{asked.version} does not promise {', '.join(absent)}")
    kept = [ident for ident in goals if ident not in asked.remove]
    return kept + list(dict.fromkeys(asked.add))


def with_goals(text: str, goals: list[str]) -> str:
    """The manifest with its goals list written out, one goal to a line."""
    lines = text.split("\n")
    start = next((at for at, line in enumerate(lines) if GOALS.match(line)), None)
    if start is None:
        raise ValueError("the manifest has no goals list")
    opening = lines[start]
    head = opening[: opening.index("[") + 1]
    if "]" in opening:
        end, tail = start, opening[opening.rindex("]") + 1 :]
    else:
        end = next((at for at in range(start + 1, len(lines)) if lines[at].startswith("]")), None)
        if end is None:
            raise ValueError("the manifest's goals list does not close")
        tail = lines[end][1:]
    lines[start : end + 1] = [head, *(f'    "{ident}",' for ident in goals), f"]{tail}"]
    return "\n".join(lines)


def edited(text: str, asked: Asked) -> tuple[str, bool]:
    """The rewritten manifest, and whether its goals are locked."""
    before = tomllib.loads(text)
    goals = changed(list(before.get("goals", [])), asked)
    after = with_goals(text, goals)
    parsed = tomllib.loads(after)
    if parsed != {**before, "goals": goals}:
        raise ValueError("rewriting the goals list would change more than the goals")
    return after, before.get("status") != UNLOCKED


def describe(asked: Asked, locked: bool) -> str:
    """The pull request's body."""
    lines = [f"This changes the goals {asked.version} promises."]
    lines += [f"- adds `{ident}`" for ident in asked.add]
    lines += [f"- removes `{ident}`" for ident in asked.remove]
    if locked:
        lines += [
            "",
            f"{asked.version} is past `{UNLOCKED}`, so its goals are locked and this carries `{LABEL}`.",
        ]
    return "\n".join(lines)


def propose(asked: Asked, ask: Asker, run: Runner, post: Poster) -> tuple[int, str]:
    """Rewrite, commit, push and open the pull request; the exit code and what to say."""
    if not VERSION.fullmatch(asked.version):
        return 2, f"{asked.version!r} is not a version (major.minor.patch)"
    code, top = ask(["git", "rev-parse", "--show-toplevel"])
    if code != 0:
        return 2, "not inside a git repository"
    root = pathlib.Path(top)
    relative = str(VERSIONS / f"{asked.version}.toml")
    path = root / relative
    if not path.is_file():
        return 2, f"no {relative} here: run this in a checkout of spec"
    _, branch = ask(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == DEFAULT:
        return 2, f"on {DEFAULT}: make a branch for the change first (git switch -c <name>)"
    try:
        after, locked = edited(path.read_text("utf-8"), asked)
    except ValueError as refused:  # a TOMLDecodeError is a ValueError
        return 2, str(refused)
    path.write_text(after, "utf-8")
    title = f"chore(goals): what {asked.version} promises"
    done = run(["git", "add", "--", relative], root)
    if done == 0:
        message = ["-m", title, "-m", describe(asked, locked), "-m", f"Spec: {REQUIREMENTS}"]
        done = run(["git", "commit", "-S", "-s", *message, "--", relative], root)
    if done != 0:
        return done, f"{relative} is written, and git did not commit it"
    if run(["git", "push", "--set-upstream", "origin", branch], root) != 0:
        return 1, f"{relative} is committed on {branch}, and git did not push it"
    body = {"title": title, "head": branch, "base": DEFAULT, "body": describe(asked, locked)}
    try:
        pull = post(f"repos/{REPO}/pulls", body)
    except urllib.error.URLError as broken:
        return 1, f"{branch} is pushed, and the pull request was not opened: {broken}"
    if not locked:
        return 0, f"opened {pull['html_url']}"
    try:
        post(f"repos/{REPO}/issues/{pull['number']}/labels", {"labels": [LABEL]})
    except urllib.error.URLError as broken:
        return 1, f"opened {pull['html_url']}, and it is not labelled {LABEL}: {broken}"
    return 0, f"opened {pull['html_url']}, labelled {LABEL}"
