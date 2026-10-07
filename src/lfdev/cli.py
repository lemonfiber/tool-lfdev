"""The `lfdev` command: one entry point, one subcommand per operation a
contributor repeats in every repository. This module parses the command line;
each subcommand gets a module of its own.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from lfdev import __version__


def parser() -> argparse.ArgumentParser:
    """The command line, with every subcommand it knows."""
    built = argparse.ArgumentParser(
        prog="lfdev",
        description="The lemonfiber developer command line.",
    )
    built.add_argument("--version", action="version", version=f"lfdev {__version__}")
    built.add_subparsers(dest="command", metavar="<command>")
    return built


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command; with none named, print what there is."""
    parser().parse_args(argv)
    parser().print_help(sys.stdout)
    return 0
