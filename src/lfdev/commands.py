"""The command table: every `lfdev` command and the one line that says what it
does, written to `commands.json` at the repository's root.

The board snapshot reads that file as its `tools[]`, and the frontpage's
contribute page holds its table of assists to it, so the list of what the tool
can do is said once, by the parser itself (REPO-R76). A test fails when the
committed file and the parser disagree.

    python -m lfdev.commands        rewrite commands.json from the parser
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from lfdev import cli

#: The file, at the repository's root.
FILE = pathlib.Path(__file__).resolve().parents[2] / "commands.json"


def table(parser: argparse.ArgumentParser | None = None) -> list[dict[str, str]]:
    """Every command, in the order the parser declares them, with its purpose."""
    built = parser or cli.parser()
    commands = next(a for a in built._actions if isinstance(a, argparse._SubParsersAction))
    return [{"name": c.dest, "purpose": str(c.help)} for c in commands._choices_actions]


def written(rows: list[dict[str, str]]) -> str:
    """The file's text."""
    return json.dumps({"generated_by": "python -m lfdev.commands", "commands": rows}, indent=2) + "\n"


def main() -> int:
    FILE.write_text(written(table()), "utf-8")
    print(f"wrote {FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
