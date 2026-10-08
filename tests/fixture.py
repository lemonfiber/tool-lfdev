"""A small board snapshot in format 1, shaped as the specification documents
it, for every test that reads one."""

from __future__ import annotations

import copy
from typing import Any


def goal(ident: str, verdict: str, claims: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": ident, "verdict": verdict, "claims": claims or []}


BOARD: dict[str, Any] = {
    "format": 1,
    "generated_at": "2026-10-08T00:00:00Z",
    "sources": {"spec": "a" * 40},
    "features": [
        {
            "id": "A1",
            "title": "First run",
            "area": "A",
            "audience": "operator",
            "maturity": "shipped",
            "status": "accepted",
            "labels": ["ux"],
            "versions": [{"version": "0.1.0", "status": "released"}],
        },
        {
            "id": "B1",
            "title": "Forms",
            "area": "B",
            "audience": "both",
            "maturity": "building",
            "status": "accepted",
            "labels": [],
            "versions": [{"version": "0.3.0", "status": "planned"}],
        },
    ],
    "requirements": [
        {"id": "A1-R1", "text": "The tool MUST start."},
        {"id": "B1-R1", "text": "The tool MUST run a form."},
    ],
    "versions": [
        {"version": "0.1.0", "status": "released", "goals": [goal("A1-R1", "met")]},
        {"version": "0.2.0", "status": "releasable", "goals": [goal("A1-R1", "met")]},
        {
            "version": "0.3.0",
            "status": "planned",
            "goals": [
                goal("B1-R1", "open"),
                goal("B1-R2", "claimed", [{"repo": "lemonfiber", "number": 7}]),
                goal("GOV-R1", "unknown"),
                goal("A1-R1", "met"),
            ],
        },
        {"version": "0.4.0", "status": "planned", "goals": [goal("B1-R3", "open")]},
        {"version": "0.5.0", "status": "planned", "goals": [goal("B1-R4", "open")]},
    ],
    "trackers": [
        {
            "repo": "lemonfiber",
            "rows": [
                {"id": "A1-R1", "state": "done"},
                {"id": "B1-R1", "state": "open"},
            ],
        },
        {"repo": "sdk-ts", "rows": [{"id": "B1-R1", "state": "done"}]},
    ],
    "pulls": [{"repo": "lemonfiber", "number": 7, "cites": ["B1-R2"]}],
}


def board() -> dict[str, Any]:
    """A fresh copy, so a test may change it."""
    return copy.deepcopy(BOARD)
