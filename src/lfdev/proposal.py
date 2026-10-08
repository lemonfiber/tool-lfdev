"""`lfdev propose` and `lfdev gap`: open a proposal pull request against the
specification, in the shape its RFC process gives (GOV-R40).

Run in a checkout of spec. It writes one Draft proposal under
`10-functional/proposals/`, with no identifier, on a branch of its own cut from
`main`, commits it signed with the `Spec:` line and a sign-off, pushes it and
opens the pull request through REST as the person (REPO-R75, REPO-R77). A
proposal states new or changed behaviour as MUST, SHOULD or MAY statements and
may name the feature or page it amends; a gap names the one that is silent and
says what it does not say.

What it writes is held to the shape `integrity.py` checks, against the areas
and features the published board snapshot names (REPO-R76), before anything is
written.
"""

from __future__ import annotations

import pathlib
import re
import urllib.error
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from lfdev import forge
from lfdev.spec_scripts import Runner
from lfdev.status import DEFAULT, Asker

#: Where proposals are added, from the root of a checkout of spec.
PROPOSALS = pathlib.Path("10-functional/proposals")
#: The repository a proposal is opened against.
SPEC = "spec"
#: What a proposal cites: the RFC process.
REQUIREMENT = "GOV-R40"
#: A statement of behaviour uses one of RFC 2119's keywords.
KEYWORD = re.compile(r"\b(MUST|SHOULD|MAY)\b")
#: A requirement row, which a proposal never carries: numbers come on approval.
DEFINITION = re.compile(r"^\|\s*\*\*[A-Z]+\d*-R\d+\*\*\s*\|", re.MULTILINE)
#: A feature's identifier, which `amends` may name.
FEATURE = re.compile(r"[A-N]\d+")


@dataclass(frozen=True)
class Asked:
    """What a proposal or a gap says."""

    kind: str
    area: str
    title: str
    amends: str | None = None
    problem: str = ""
    statements: list[str] = field(default_factory=list)
    rationale: str = ""
    missing: str = ""


def prose(value: str) -> str:
    """A field as Markdown prose; a line that would open a heading is escaped."""
    return "\n".join(
        f"\\{line}" if line.lstrip().startswith("#") else line for line in value.strip().splitlines()
    )


def slug(title: str) -> str:
    """A proposal's file name, from its title."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:56].rstrip("-")


def faults(asked: Asked, board: Mapping[str, Any], root: pathlib.Path) -> list[str]:
    """What is wrong with what was asked, against the board and the checkout."""
    found = []
    areas = {a["id"] for a in board.get("areas", [])}
    features = {f["id"] for f in board.get("features", [])}
    if asked.area not in areas:
        found.append(f"area {asked.area!r} is not one the catalogue holds ({', '.join(sorted(areas))})")
    if not asked.title.strip() or "\n" in asked.title or not slug(asked.title):
        found.append("the title is one line naming the capability")
    amends = asked.amends
    if amends and not (FEATURE.fullmatch(amends) and amends in features) and not _page(root, amends):
        found.append(f"amends {amends!r}, which is neither a feature nor a page of the specification")
    if asked.kind == "proposal" and (
        not asked.statements or not all(KEYWORD.search(s) for s in asked.statements)
    ):
        found.append("every statement uses MUST, SHOULD or MAY, and there is at least one")
    if asked.kind == "gap" and (not amends or not asked.missing.strip()):
        found.append("a gap names the feature or page that is silent (--amends) and what it does not say")
    if any(
        DEFINITION.search(text) for text in (asked.problem, asked.rationale, asked.missing, *asked.statements)
    ):
        found.append("it carries a requirement row; identifiers are allocated when it is approved")
    return found


def _page(root: pathlib.Path, path: str) -> bool:
    """Whether a path names a Markdown page inside the checkout."""
    target = (root / path).resolve()
    return target.suffix == ".md" and target.is_file() and target.is_relative_to(root.resolve())


def text(asked: Asked) -> str:
    """The proposal file, in the template's shape."""
    head = ["---", f"kind: {asked.kind}", f"area: {asked.area}", f"title: {asked.title.strip()}"]
    head += [f"amends: {asked.amends}"] if asked.amends else []
    head += ["status: draft", "---", "", f"# {asked.title.strip()}", ""]
    if asked.kind == "gap":
        body = ["## What the specification does not say", "", prose(asked.missing), ""]
    else:
        body = ["## Problem", "", prose(asked.problem) or "(none given)", "", "## Proposed behaviour", ""]
        body += [f"- {prose(s)}" for s in asked.statements]
        body += ["", "## Rationale", "", prose(asked.rationale) or "(none given)", ""]
    return "\n".join(head + body)


def where(asked: Asked, board: Mapping[str, Any], ask: Asker) -> tuple[pathlib.Path, str]:
    """The checkout and the head a pull request from it names, or why not."""
    code, top = ask(["git", "rev-parse", "--show-toplevel"])
    if code != 0:
        raise ValueError("not inside a git repository")
    root = pathlib.Path(top)
    if not (root / PROPOSALS).is_dir():
        raise ValueError(f"no {PROPOSALS} here: run this in a checkout of spec")
    code, url = ask(["git", "remote", "get-url", "origin"])
    remote = forge.REMOTE.search(url) if code == 0 else None
    if remote is None:
        raise ValueError("origin is not a repository on the forge")
    said = faults(asked, board, root)
    relative = PROPOSALS / f"{slug(asked.title)}.md"
    if not said and (root / relative).exists():
        said.append(f"{relative.as_posix()} already exists; choose another title")
    if said:
        raise ValueError("; ".join(said))
    branch = f"proposal/{slug(asked.title)}"
    return root, branch if remote["owner"] == forge.ORG else f"{remote['owner']}:{branch}"


def request(asked: Asked, head: str, relative: str) -> dict[str, Any]:
    """The pull request a proposal opens."""
    what = "a gap in" if asked.kind == "gap" else "a change to"
    return {
        "title": f"{'Gap' if asked.kind == 'gap' else 'Proposal'}: {asked.title.strip()}"[:120],
        "head": head,
        "base": DEFAULT,
        "body": (
            f"{asked.title.strip()}: {what} the specification, as `{relative}`. A maintainer "
            "approves it with `proposal:approved`, which allocates its identifiers.\n\n"
            f"Spec: {REQUIREMENT}"
        ),
        "maintainer_can_modify": True,
    }


def propose(
    asked: Asked, board: Mapping[str, Any], ask: Asker, run: Runner, post: forge.Poster
) -> tuple[int, str]:
    """Write, commit, push and open the proposal; the exit code and what to say."""
    try:
        root, head = where(asked, board, ask)
    except ValueError as refused:
        return 2, str(refused)
    branch = head.rpartition(":")[2]
    relative = (PROPOSALS / f"{slug(asked.title)}.md").as_posix()
    for step in (["git", "fetch", "origin", DEFAULT], ["git", "switch", "-c", branch, f"origin/{DEFAULT}"]):
        if run(step, root) != 0:
            return 1, f"`{' '.join(step[:3])}` did not succeed; nothing is written"
    (root / relative).write_text(text(asked), "utf-8")
    headline = f"docs(proposal): {asked.title.strip()}"[:100]
    steps = [
        ["git", "add", "--", relative],
        ["git", "commit", "-S", "-s", "-m", headline, "-m", f"Spec: {REQUIREMENT}", "--", relative],
        ["git", "push", "--set-upstream", "origin", branch],
    ]
    for step in steps:
        if run(step, root) != 0:
            return 1, f"{relative} is written on {branch}, and `{' '.join(step[:2])}` did not succeed"
    try:
        pull = post(f"repos/{forge.ORG}/{SPEC}/pulls", request(asked, head, relative))
    except urllib.error.URLError as broken:
        return 1, f"{branch} is pushed, and the pull request was not opened: {broken}"
    return 0, f"opened {pull['html_url']}"
