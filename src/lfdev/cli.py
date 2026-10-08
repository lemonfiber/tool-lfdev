"""The `lfdev` command: one entry point, one subcommand per operation a
contributor repeats in every repository. This module parses the command line;
each subcommand gets a module of its own.
"""

from __future__ import annotations

import argparse
import datetime
import sys
import urllib.error
from collections.abc import Callable, Sequence

from lfdev import (
    __version__,
    checks,
    decide,
    doc,
    doctor,
    forge,
    goals,
    snapshot,
    spec_scripts,
    status,
    views,
    work,
)


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
    promise = commands.add_parser("goals", help="change what a version promises, and open the pull request")
    promise.add_argument("version")
    promise.add_argument("--add", action="extend", nargs="+", default=[], metavar="requirement")
    promise.add_argument("--remove", action="extend", nargs="+", default=[], metavar="requirement")
    page = commands.add_parser("doc", help="the repository and file a page on the sites is rendered from")
    page.add_argument("url")
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


def _say(code: int, said: str) -> int:
    """Print an answer, to standard error where it is a refusal, and pass its code on."""
    print(said, file=sys.stdout if code == 0 else sys.stderr)
    return code


def _as_person(act: Callable[[str], tuple[int, str]]) -> int:
    """Run something that talks to the forge with the person's token, or refuse."""
    try:
        auth = forge.token()
    except forge.Unauthenticated as broken:
        return _say(2, f"lfdev: {broken}")
    return _say(*act(auth))


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
        return _say(
            *status.record(
                status.Asked(args.ident, args.state, args.evidence, args.landed, args.spec), doctor.run
            )
        )
    if args.command == "decide":
        return _say(
            *decide.record(args.decision, args.where, doctor.run, spec_scripts.run, datetime.date.today())
        )
    if args.command == "doc":
        return _as_person(lambda auth: doc.doc(args.url, snapshot.fetch, lambda path: forge.get(path, auth)))
    if args.command == "goals":
        asked = goals.Asked(args.version, args.add, args.remove)
        return _as_person(
            lambda auth: goals.propose(
                asked, doctor.run, spec_scripts.run, lambda p, body: forge.post(p, auth, body)
            )
        )
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
