"""How `board` and `next` print what `work.py` computes."""

from __future__ import annotations

from typing import Any

from lfdev.work import MATURITIES, Card, Pickable


def as_of(board: dict[str, Any]) -> str:
    """When the snapshot was written, and the revision of spec it read."""
    spec = (board.get("sources") or {}).get("spec") or ""
    return f"read at {board['generated_at']} · spec at {spec[:7]}"


def board_view(board: dict[str, Any], shown: list[Card], total: int) -> str:
    """The board, one column per maturity, as lines."""
    lines = [as_of(board), f"{len(shown)} of {total} features", ""]
    for maturity in MATURITIES:
        column = [c for c in shown if c.maturity == maturity]
        lines.append(f"{maturity} ({len(column)})")
        for c in column:
            lines.append(f"  {c.id:<6} {c.title}  [area {c.area}, {c.open_goals} open, {c.claims} claimed]")
    return "\n".join(lines)


def next_view(board: dict[str, Any], shown: list[Pickable]) -> str:
    """The goals to pick up, by version, as lines."""
    lines = [as_of(board), f"{len(shown)} goals nobody has claimed", ""]
    versions = list(dict.fromkeys(g.version for g in shown))
    for version in versions:
        lines.append(version)
        for g in (g for g in shown if g.version == version):
            where = ", ".join(g.repos) or "no tracker yet"
            lines.append(f"  {g.id:<10} {g.verdict:<9} {where}")
            if g.text:
                lines.append(f"             {g.text}")
    return "\n".join(lines)
