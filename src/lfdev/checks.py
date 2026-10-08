"""`lfdev checks <repo>#<number>`: a pull request's checks, read through REST
at most once every ten minutes for each pull request (GOV-R54, REPO-R75).

A read within ten minutes of the last one for the same pull request is not
made: the answer recorded then is printed, with how long until another read is
allowed. The record is kept in `~/.cache/lfdev/checks.json`.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
from collections.abc import Callable
from typing import Any

#: The least time between two reads of one pull request's checks.
FLOOR = datetime.timedelta(minutes=10)
#: `owner/repo#123` or `repo#123`, a repository in the organisation then.
TARGET = re.compile(r"^(?:(?P<owner>[\w.-]+)/)?(?P<repo>[\w.-]+)#(?P<number>\d+)$")
#: The organisation a bare repository name is read in.
ORG = "lemonfiber"

Getter = Callable[[str], Any]


def parse_target(text: str) -> tuple[str, int]:
    """`owner/repo` and the number, from what the person typed."""
    match = TARGET.match(text)
    if match is None:
        raise ValueError(f"{text!r} is not owner/repo#number or repo#number")
    owner = match["owner"] or ORG
    return f"{owner}/{match['repo']}", int(match["number"])


def cache_file(home: pathlib.Path | None = None) -> pathlib.Path:
    """Where the last read of each pull request is recorded: a fixed place
    under the user's home, which nothing typed or set can move."""
    return (home or pathlib.Path.home()) / ".cache" / "lfdev" / "checks.json"


def _load(path: pathlib.Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read(repo: str, number: int, get: Getter) -> list[dict[str, str]]:
    """Each check run on the pull request's head commit: name, status, conclusion."""
    head = get(f"repos/{repo}/pulls/{number}")["head"]["sha"]
    runs = get(f"repos/{repo}/commits/{head}/check-runs?per_page=100")["check_runs"]
    return sorted(
        ({"name": r["name"], "status": r["status"], "conclusion": r.get("conclusion") or ""} for r in runs),
        key=lambda r: r["name"],
    )


def checks(
    repo: str,
    number: int,
    get: Getter,
    now: datetime.datetime,
    path: pathlib.Path,
) -> tuple[list[dict[str, str]], datetime.timedelta | None]:
    """The checks, and how long until another read where this answer is the one
    recorded less than ten minutes ago."""
    key = f"{repo}#{number}"
    record = _load(path)
    seen = record.get(key)
    if seen is not None:
        at = datetime.datetime.fromisoformat(seen["at"])
        if now - at < FLOOR:
            return seen["checks"], FLOOR - (now - at)
    found = read(repo, number, get)
    record[key] = {"at": now.isoformat(), "checks": found}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1), "utf-8")
    return found, None


def verdict(found: list[dict[str, str]]) -> str:
    """One word for the whole: pending, failing or passing."""
    if any(c["status"] != "completed" for c in found):
        return "pending"
    if any(c["conclusion"] in ("failure", "timed_out", "cancelled", "action_required") for c in found):
        return "failing"
    return "passing"


def view(key: str, found: list[dict[str, str]], wait: datetime.timedelta | None) -> str:
    """What the command prints."""
    when = (
        "read now"
        if wait is None
        else f"recorded earlier; another read in {int(wait.total_seconds() // 60) + 1} min"
    )
    lines = [f"{key}: {verdict(found)} ({len(found)} checks, {when})"]
    lines += [f"  {c['conclusion'] or c['status']:<11} {c['name']}" for c in found]
    return "\n".join(lines)
