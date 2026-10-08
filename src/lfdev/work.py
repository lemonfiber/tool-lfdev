"""What the board and the list of work to pick up show, computed the way the
frontpage computes them, so a filter means the same in a terminal as in the
address bar (`lemonfiber.app/board/?area=F` and `lfdev board --area F`).

Pure functions over the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The columns of the board, in the order work moves through them.
MATURITIES = ("planned", "building", "built", "shipped")
#: The lifecycle states of a version that has gone out.
FINISHED = ("released", "yanked")
#: The lifecycle states of a version still taking work.
TAKING_WORK = ("staged", "in_progress", "planned")
#: The board's filters, in the order the frontpage's form shows them.
FILTERS = ("version", "area", "audience", "repo", "maturity", "status", "claimed", "label", "q")


def feature_of(requirement: str) -> str:
    """The feature a requirement belongs to, read off its identifier."""
    at = requirement.rfind("-R")
    return requirement if at == -1 else requirement[:at]


@dataclass(frozen=True)
class Card:
    """One feature as the board shows and filters it."""

    id: str
    title: str
    area: str
    audience: str
    maturity: str
    status: str
    labels: tuple[str, ...]
    versions: tuple[str, ...]
    repos: tuple[str, ...]
    open_goals: int
    claims: int


def _by_feature(pairs: list[tuple[str, str]]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for ident, value in pairs:
        found.setdefault(feature_of(ident), set()).add(value)
    return found


def cards(board: dict[str, Any]) -> list[Card]:
    """Every feature of the snapshot as a card, in the catalogue's order."""
    pulls = board["pulls"]
    claims = _by_feature([(i, f"{p['repo']}#{p['number']}") for p in pulls for i in p["cites"]])
    repos = _by_feature(
        [(r["id"], t["repo"]) for t in board["trackers"] for r in t["rows"]]
        + [(i, p["repo"]) for p in pulls for i in p["cites"]]
    )
    open_goals: dict[str, int] = {}
    for version in board["versions"]:
        if version["status"] in FINISHED:
            continue
        for goal in version["goals"]:
            if goal["verdict"] != "met":
                feature = feature_of(goal["id"])
                open_goals[feature] = open_goals.get(feature, 0) + 1
    return [
        Card(
            id=f["id"],
            title=f["title"],
            area=f["area"],
            audience=f["audience"],
            maturity=f["maturity"],
            status=f["status"],
            labels=tuple(f["labels"]),
            versions=tuple(v["version"] for v in f["versions"]),
            repos=tuple(sorted(repos.get(f["id"], ()))),
            open_goals=open_goals.get(f["id"], 0),
            claims=len(claims.get(f["id"], ())),
        )
        for f in board["features"]
    ]


def _in(value: str | None, values: tuple[str, ...]) -> bool:
    return value is None or value in values


def matches(card: Card, filters: dict[str, str]) -> bool:
    """Whether a card passes every filter set, as the frontpage's board decides."""
    q = (filters.get("q") or "").lower()
    claimed = filters.get("claimed")
    return (
        _in(filters.get("version"), card.versions)
        and _in(filters.get("area"), (card.area,))
        and _in(filters.get("audience"), (card.audience,))
        and _in(filters.get("repo"), card.repos)
        and _in(filters.get("maturity"), (card.maturity,))
        and _in(filters.get("status"), (card.status,))
        and (claimed is None or (card.claims > 0) == (claimed == "yes"))
        and _in(filters.get("label"), card.labels)
        and (not q or card.id.lower() == q or q in card.title.lower())
    )


def taking_work(board: dict[str, Any]) -> list[dict[str, Any]]:
    """The version in flight and the next: the first two on the train, in train
    order, still taking work."""
    return [v for v in board["versions"] if v["status"] in TAKING_WORK][:2]


@dataclass(frozen=True)
class Pickable:
    """One goal nobody has claimed that is not met."""

    id: str
    version: str
    verdict: str
    repos: tuple[str, ...]
    area: str | None
    text: str | None = field(default=None)


def pickable(board: dict[str, Any]) -> list[Pickable]:
    """Every unmet, unclaimed goal of the versions taking work, in train order."""
    area_of = {f["id"]: f["area"] for f in board["features"]}
    text_of = {r["id"]: r["text"] for r in board["requirements"]}
    return [
        Pickable(
            id=g["id"],
            version=v["version"],
            verdict=g["verdict"],
            repos=tuple(
                t["repo"]
                for t in board["trackers"]
                if any(r["id"] == g["id"] and r["state"] != "done" for r in t["rows"])
            ),
            area=area_of.get(feature_of(g["id"])),
            text=text_of.get(g["id"]),
        )
        for v in taking_work(board)
        for g in v["goals"]
        if g["verdict"] != "met" and not g["claims"]
    ]


def pick_matches(goal: Pickable, filters: dict[str, str]) -> bool:
    """Whether a goal has every facet value set, as the frontpage's pages split
    them."""
    return (
        _in(filters.get("version"), (goal.version,))
        and (filters.get("area") is None or goal.area == filters["area"])
        and _in(filters.get("repo"), goal.repos)
    )
