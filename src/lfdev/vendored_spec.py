"""The specification's scripts `lfdev status` and `lfdev blocked` run, copied
into this package at one commit of spec.

They have one home, spec, where every repository's checks and the release gate
run them. This package carries a copy, as the SDKs carry the contract: `sync`
takes the files at a commit and records it in `REVISION`, and `check` holds the
copy to that commit, byte for byte, and to spec's main, so a copy that has gone
behind is a red check rather than a silence. A bot pull request runs `sync` when
spec's main moves past the copy.

Usage:
  python -m lfdev.vendored_spec sync <commit>
  python -m lfdev.vendored_spec check

`check` exits 0 where the copy is spec's main at the commit it names, 1 where it
is behind or was edited, naming each file and the command that takes it, and 2
where spec could not be read.
"""

from __future__ import annotations

import os
import pathlib
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence

#: Where the copy is kept.
HERE = pathlib.Path(__file__).resolve().parent / "vendored"
#: The commit of spec the copy was taken at.
REVISION = HERE / "REVISION"
#: The repository the scripts come from.
SPEC = "lemonfiber/spec"
#: Every file copied: the two scripts lfdev runs and each script they import.
FILES = (
    "status_check.py",
    "what_is_blocking.py",
    "catalogue.py",
    "integrity.py",
    "metafm.py",
    "paths.py",
    "patterns.py",
)

#: How long one request may take, in seconds.
TIMEOUT = 30

#: Reads one file of spec at a commit.
Reader = Callable[[str, str], bytes]


def raw(commit: str, name: str) -> bytes:
    """One script of spec at a commit, as the forge serves its bytes."""
    url = f"https://raw.githubusercontent.com/{SPEC}/{commit}/scripts/{name}"
    with urllib.request.urlopen(url, timeout=TIMEOUT) as answer:
        return answer.read()


def main_head(environ: Mapping[str, str] = os.environ) -> str:
    """The commit spec's main is at, asked with a token where one is set, so a
    shared runner's address does not spend the anonymous allowance."""
    headers = {"Accept": "application/vnd.github.sha"}
    token = environ.get("GH_TOKEN") or environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"https://api.github.com/repos/{SPEC}/commits/main", headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return answer.read().decode("ascii").strip()


def sync(commit: str, read: Reader = raw, here: pathlib.Path = HERE) -> list[str]:
    """Take every file at a commit and record it; the names that changed."""
    changed = []
    for name in FILES:
        data = read(commit, name)
        path = here / name
        if not path.is_file() or path.read_bytes() != data:
            changed.append(name)
        path.write_bytes(data)
    (here / "REVISION").write_text(commit + "\n", "utf-8")
    return changed


def differing(commit: str, read: Reader, here: pathlib.Path) -> list[str]:
    """The files of the copy that differ from spec at a commit."""
    return [
        name
        for name in FILES
        if not (here / name).is_file() or (here / name).read_bytes() != read(commit, name)
    ]


def check(head: str, read: Reader = raw, here: pathlib.Path = HERE) -> tuple[int, str]:
    """Whether the copy is spec at its recorded commit and at main's head."""
    pinned = (here / "REVISION").read_text("utf-8").strip()
    edited = differing(pinned, read, here)
    behind = differing(head, read, here)
    remedy = f"python -m lfdev.vendored_spec sync {head}"
    if edited:
        return 1, (
            f"the copy differs from spec {pinned[:7]}, the commit REVISION names, in "
            f"{', '.join(edited)}: it was edited here. Take it again: {remedy}"
        )
    if behind:
        return 1, (
            f"the copy is spec {pinned[:7]} and spec's main {head[:7]} differs in "
            f"{', '.join(behind)}. Take it: {remedy}"
        )
    return 0, f"the copy is spec {pinned[:7]}, and spec's main {head[:7]} holds the same files"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args[:1] == ["sync"] and len(args) == 2:
            changed = sync(args[1])
            print(f"took spec {args[1][:7]}: {', '.join(changed) or 'nothing changed'}")
            return 0
        if args == ["check"]:
            code, said = check(main_head())
            print(said if code == 0 else f"::error::{said}")
            return code
    except OSError as broken:  # a URLError is one
        print(f"::error::spec could not be read: {broken}")
        return 2
    print(__doc__.split("Usage:")[1].split("`check`")[0].rstrip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
