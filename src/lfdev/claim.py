"""`lfdev claim <id>`: say you are working on a requirement, the way every
repository reads it (GOV-R57, GOV-R58).

A claim is a draft pull request in the repository the work happens in: a branch
cut from `main`, one empty signed commit carrying the `Spec:` line and a
sign-off, pushed and opened as a draft through REST as the person (REPO-R75,
REPO-R77). The board then shows the requirement as claimed.

It reads the published board snapshot first and refuses a requirement somebody
has already claimed and a repository already holding as many open pull requests
as the cap allows (REPO-R76).
"""

from __future__ import annotations

import pathlib
import urllib.error
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lfdev import forge, tracker
from lfdev.spec_scripts import Runner
from lfdev.status import DEFAULT, Asker


@dataclass(frozen=True)
class Claimable:
    """A requirement this repository may claim, and what the board says of it."""

    ident: str
    repo: str
    text: str


def holders(board: Mapping[str, Any], ident: str) -> list[str]:
    """The open pull requests that already claim a requirement, as `repo#n`; a
    bot's pull request claims nothing (GOV-R58)."""
    found = {
        f"{p['repo']}#{p['number']}"
        for p in board.get("pulls", [])
        if ident in p.get("cites", []) and not p.get("bot")
    }
    for version in board.get("versions", []):
        for goal in version.get("goals", []):
            if goal.get("id") == ident:
                found.update(f"{c['repo']}#{c['number']}" for c in goal.get("claims", []))
    return sorted(found)


def claimable(board: Mapping[str, Any], ident: str, repo: str) -> Claimable:
    """The requirement, or why it cannot be claimed here."""
    if not tracker.IDENTIFIER.fullmatch(ident):
        raise ValueError(f"{ident!r} is not a requirement identifier")
    text = next((r["text"] for r in board.get("requirements", []) if r["id"] == ident), None)
    if text is None:
        raise ValueError(f"the board snapshot defines no requirement {ident}")
    held = holders(board, ident)
    if held:
        raise ValueError(f"{ident} is already claimed by {', '.join(held)}")
    cap = board.get("claims", {}).get("cap")
    standing = next((r for r in board.get("repos", []) if r.get("name") == repo), {})
    counted = standing.get("counted_pulls")
    if cap is not None and counted is not None and counted >= cap:
        raise ValueError(
            f"{repo} already holds {counted} open pull requests from people and agents; the cap is {cap} "
            "(GOV-R58). Land or close one first"
        )
    return Claimable(ident, repo, text)


def this_repository(ask: Asker) -> str:
    """The organisation's repository this clone's `origin` names, or why not."""
    code, url = ask(["git", "remote", "get-url", "origin"])
    found = forge.REMOTE.search(url) if code == 0 else None
    if found is None or found["owner"] != forge.ORG:
        raise ValueError(f"origin is not a {forge.ORG} repository on the forge")
    return found["repo"]


def claim(
    ident: str, board: Mapping[str, Any], ask: Asker, run: Runner, post: forge.Poster
) -> tuple[int, str]:
    """Cut the branch, commit, push and open the draft; the exit code and what to say."""
    code, top = ask(["git", "rev-parse", "--show-toplevel"])
    if code != 0:
        return 2, "not inside a git repository"
    try:
        wanted = claimable(board, ident, this_repository(ask))
    except ValueError as refused:
        return 2, str(refused)
    root = pathlib.Path(top)
    branch = f"claim/{ident.lower()}"
    steps = [
        ["git", "fetch", "origin", DEFAULT],
        ["git", "switch", "-c", branch, f"origin/{DEFAULT}"],
        [
            "git",
            "commit",
            "--allow-empty",
            "-S",
            "-s",
            "-m",
            f"chore(claim): {ident}",
            "-m",
            f"Spec: {ident}",
        ],
        ["git", "push", "--set-upstream", "origin", branch],
    ]
    for step in steps:
        if run(step, root) != 0:
            return 1, f"`{' '.join(step[:3])}` did not succeed, so {ident} is not claimed"
    body = (
        f"Claiming {ident}: {wanted.text}\n\n"
        "A draft until the work is ready; the board shows the requirement as claimed meanwhile.\n\n"
        f"Spec: {ident}"
    )
    try:
        pull = post(
            f"repos/{forge.ORG}/{wanted.repo}/pulls",
            {"title": f"claim: {ident}", "head": branch, "base": DEFAULT, "body": body, "draft": True},
        )
    except urllib.error.URLError as broken:
        return 1, f"{branch} is pushed, and the draft pull request was not opened: {broken}"
    return 0, f"claimed {ident}: {pull['html_url']}"
