"""The `lfdev` command: one entry point, one subcommand per operation a
contributor repeats in every repository. This module parses the command line;
each subcommand gets a module of its own.
"""

from __future__ import annotations

import argparse
import datetime
import sys
import urllib.error
from collections.abc import Sequence

from lfdev import __version__, checks, decide, doctor, forge, snapshot, spec_scripts, status, views, work


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
    reading = commands.add_parser("checks", help="a pull request's checks, at most every ten minutes")
    reading.add_argument("target", metavar="repo#number")
    blocked = commands.add_parser("blocked", help="what a pull request is blocked on")
    blocked.add_argument("target", metavar="repo#number")
    record = commands.add_parser("status", help="record a requirement done, partial or open, and commit it")
    record.add_argument("ident", metavar="requirement")
    record.add_argument("state", choices=("done", "partial", "open"))
    record.add_argument("--evidence", action="append", default=[], metavar="path[::test]")
    record.add_argument("--landed", metavar="commit")
    record.add_argument("--spec", metavar="path", help="a checkout of spec; default ../spec")
    decision = commands.add_parser("decide", help="record a decision in spec's decision log, and commit it")
    decision.add_argument("decision", help="the decision, as it was made")
    decision.add_argument(
        "--where",
        required=True,
        help="the requirement or ADR it lives in, as links, or why it has neither yet",
    )
    pick = commands.add_parser("next", help="goals nobody has claimed, to pick up")
    for name in ("version", "area", "repo"):
        pick.add_argument(f"--{name}")
    return built


def _filters(args: argparse.Namespace, names: Sequence[str]) -> dict[str, str]:
    return {name: value for name in names if (value := getattr(args, name))}


def _checks(target: str) -> int:
    try:
        repo, number = checks.parse_target(target)
        auth = forge.token()
        found, wait = checks.checks(
            repo,
            number,
            lambda path: forge.get(path, auth),
            datetime.datetime.now(datetime.UTC),
            checks.cache_file(),
        )
    except (ValueError, forge.Unauthenticated, urllib.error.URLError) as broken:
        print(f"lfdev: {broken}", file=sys.stderr)
        return 2
    print(checks.view(f"{repo}#{number}", found, wait))
    return 1 if checks.verdict(found) == "failing" else 0


def _blocked(target: str) -> int:
    try:
        repo, number = checks.parse_target(target)
    except ValueError as broken:
        print(f"lfdev: {broken}", file=sys.stderr)
        return 2
    return spec_scripts.script("what_is_blocking.py", repo, str(number))


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command; with none named, print what there is."""
    args = parser().parse_args(argv)
    if args.command is None:
        parser().print_help(sys.stdout)
        return 0
    if args.command == "doctor":
        code, said = doctor.report(doctor.checks(doctor.run))
        print(said)
        return code
    if args.command == "checks":
        return _checks(args.target)
    if args.command == "blocked":
        return _blocked(args.target)
    if args.command == "status":
        code, said = status.record(
            status.Asked(args.ident, args.state, args.evidence, args.landed, args.spec), doctor.run
        )
        print(said, file=sys.stdout if code == 0 else sys.stderr)
        return code
    if args.command == "decide":
        code, said = decide.record(
            args.decision, args.where, doctor.run, spec_scripts.run, datetime.date.today()
        )
        print(said, file=sys.stdout if code == 0 else sys.stderr)
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
