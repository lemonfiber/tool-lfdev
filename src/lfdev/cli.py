"""The `lfdev` command: one entry point, one subcommand per operation a
contributor repeats in every repository. This module parses the command line;
each subcommand gets a module of its own.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from lfdev import __version__, doctor, snapshot, views, work


def parser() -> argparse.ArgumentParser:
    """The command line, with every subcommand it knows."""
    built = argparse.ArgumentParser(
        prog="lfdev",
        description="The lemonfiber developer command line.",
    )
    built.add_argument("--version", action="version", version=f"lfdev {__version__}")
    commands = built.add_subparsers(dest="command", metavar="<command>")
    commands.add_parser("doctor", help="check this clone is set up to commit")
    board = commands.add_parser("board", help="every feature by maturity, filtered")
    for name in work.FILTERS:
        board.add_argument(f"--{name}", choices=("yes", "no") if name == "claimed" else None)
    pick = commands.add_parser("next", help="goals nobody has claimed, to pick up")
    for name in ("version", "area", "repo"):
        pick.add_argument(f"--{name}")
    return built


def _filters(args: argparse.Namespace, names: Sequence[str]) -> dict[str, str]:
    return {name: value for name in names if (value := getattr(args, name))}


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command; with none named, print what there is."""
    args = parser().parse_args(argv)
    if args.command is None:
        parser().print_help(sys.stdout)
        return 0
    if args.command == "doctor":
        code, said = doctor.report(doctor.checks())
        print(said)
        return code
    try:
        board = snapshot.load(snapshot.source())
    except snapshot.Unreadable as broken:
        print(f"lfdev: {broken}", file=sys.stderr)
        return 2
    if args.command == "board":
        every = work.cards(board)
        filters = _filters(args, work.FILTERS)
        print(views.board_view(board, [c for c in every if work.matches(c, filters)], len(every)))
        return 0
    filters = _filters(args, ("version", "area", "repo"))
    print(views.next_view(board, [g for g in work.pickable(board) if work.pick_matches(g, filters)]))
    return 0
