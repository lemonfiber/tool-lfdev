#!/usr/bin/env python3
"""A repository's implementation status, one row per requirement — OPS-R74, OPS-R75.

Every repository a version is satisfied in keeps `status.toml` at its root, and
changes it in the pull request that changes what it says. One short row per
requirement the repository has worked on:

    requirement = [
      { id = "F8-R6", state = "done", evidence = ["crates/lemonfiber-plugin/src/refusing/recipes.rs", "crates/lemonfiber-plugin/src/refusing/recipes/tests.rs::a_flow_no_pair_declares_is_refused"], landed = "6409706" },
    ]

A repository whose rows would run past a thousand lines keeps them in a
`status/` directory instead, one `<feature>.toml` per feature in the same shape,
each holding only that feature's rows (`status/F8.toml`, `status/ARCH.toml`).
Keeping both a `status.toml` and a `status/` directory is refused.

`state` is `done`, `partial` or `open`. `evidence` names the code and the test
that hold the requirement, each as one of:

    path              a file or directory in this repository
    path::text        that file, which has to contain `text` (a test's name)
    repo:path         a file in another repository, checked where its checkout
                      is given with `--sibling`

`landed` is the commit that finished the requirement, for the case where no
commit cites it and none can: a merged commit cannot gain a trailer. It has to
be in this repository's history.

The release gate reads these files (`gate.py`), and so does the no-stubs gate.
This checks one of them against the specification and against the repository
it sits in:

  * the file has the shape above, and nothing else, and a file under `status/`
    holds only its own feature's rows;
  * every identifier is a requirement the specification defines, and none
    appears twice; a retired one only where a version locked it before it was
    retired, because what that version shipped is still a fact;
  * a `done` row names evidence, and every path it names exists, and every
    `::text` occurs in its file;
  * a `done` row no version locks is recorded like any other: work done ahead of
    its version is a fact, and `check_goal_coverage.py` already holds every
    accepted requirement to a version or to a declared wait;
  * a `landed` commit is in this repository's history.

`repos` names every repository whose tracker that is, read from every version
manifest's `satisfied_in`; `maturity.py` reads them together to derive what the
catalogue says of each feature.

Usage:
  status_check.py check --spec <spec root> [--repo-root .] [--sibling name=path ...]
  status_check.py repos --spec <spec root>

Exit 0 = every claim is backed; 1 = claims that are not, named; 2 = the question
could not be asked.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass

from integrity import elsewhere
from paths import within_cwd
from patterns import REQ_DEF, REQ_RETIRED_ROW

#: Where a repository keeps its tracker.
FILE = "status.toml"
#: Where a repository whose rows run past a thousand lines keeps one file per feature.
DIRECTORY = "status"

#: What a tracker split by feature, and a version manifest, are each kept as.
TOML = "*.toml"

#: Where the version manifests are, each naming its goals and its repositories.
VERSIONS = pathlib.Path("70-operations") / "versions"

#: The states a row may be in. Only the first counts towards a release.
STATES = ("done", "partial", "open")
DONE = STATES[0]

#: The keys a row may carry.
REQUIRED = ("id", "state")
OPTIONAL = ("evidence", "landed")

IDENTIFIER = re.compile(r"^[A-Z]+\d*-R\d+$")
SHA = re.compile(r"^[0-9a-f]{7,40}$")
# `repo:path`, and never `path::text`: one colon after a repository's name.
ELSEWHERE = re.compile(r"^([a-z0-9][a-z0-9.-]*):(?!:)(.+)$")


class Unreadable(Exception):
    """The tracker could not be read as one, so nothing in it can be judged."""


@dataclass(frozen=True)
class Row:
    """One requirement as one repository records it."""

    id: str
    state: str
    evidence: tuple[str, ...]
    landed: str | None
    repo: str

    @property
    def done(self) -> bool:
        return self.state == DONE


def table_faults(table: dict, here: str, seen: set[str]) -> list[str]:
    """What is wrong with one `[[requirement]]` table, noting its identifier as seen."""
    faults = [f"{here}: carries `{key}`, which is not one of {', '.join(REQUIRED + OPTIONAL)}"
              for key in table if key not in REQUIRED + OPTIONAL]
    faults += [f"{here}: has no `{key}`" for key in REQUIRED if key not in table]
    ident, state = table.get("id"), table.get("state")
    if ident is not None:
        faults += identifier_faults(ident, here, seen)
    if state is not None and state not in STATES:
        faults.append(f"{here}: `{state}` is not one of {', '.join(STATES)}")
    evidence = table.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(e, str) and e for e in evidence):
        faults.append(f"{here}: `evidence` has to be a list of paths")
    elif state == DONE and not evidence:
        faults.append(f"{here}: {ident} is done and names no evidence; name the code and "
                      "the test that hold it")
    landed = table.get("landed")
    if landed is not None and (not isinstance(landed, str) or not SHA.match(landed)):
        faults.append(f"{here}: `landed` has to be a commit's hexadecimal name")
    return faults


def identifier_faults(ident: object, here: str, seen: set[str]) -> list[str]:
    """Whether a row's identifier is one, and the first row to name it."""
    if not isinstance(ident, str) or not IDENTIFIER.match(ident):
        return [f"{here}: `{ident}` is not a requirement identifier"]
    if ident in seen:
        return [f"{here}: {ident} is recorded twice; one row says where a requirement stands"]
    seen.add(ident)
    return []


def shape(data: dict, where: str) -> list[str]:
    """What is wrong with the file's shape, before anything it says is read."""
    faults = [f"{where}: `{key}` is not something a tracker holds; only "
              "`[[requirement]]` tables are" for key in data if key != "requirement"]
    tables = data.get("requirement", [])
    if not isinstance(tables, list):
        return [*faults, f"{where}: `requirement` has to be an array of tables"]
    seen: set[str] = set()
    for number, table in enumerate(tables, start=1):
        here = f"{where}, requirement {number}"
        if isinstance(table, dict):
            faults += table_faults(table, here, seen)
        else:
            faults.append(f"{here}: is not a table")
    return faults


def parse(text: str, where: str, repo: str) -> list[Row] | None:
    """The rows a tracker's text holds, or None for the milestone shape.

    A tracker in the milestone shape the binary kept before this one is read as
    none: `gate.py` reads that one through its Markdown rendering. Anything else
    that does not parse is refused rather than read as empty, because a tracker
    nobody could read reports success about nothing.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as broken:
        raise Unreadable(f"{where}: {broken}") from broken
    if "milestone" in data:
        return None
    faults = shape(data, where)
    if faults:
        raise Unreadable("\n".join(faults))
    return [
        Row(t["id"], t["state"], tuple(t.get("evidence", [])), t.get("landed"), repo)
        for t in data.get("requirement", [])
    ]


def read(path: pathlib.Path, repo: str) -> list[Row] | None:
    """The rows of one tracker file on disk, or None where there is none."""
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as broken:
        raise Unreadable(f"{path}: {broken}") from broken
    return parse(text, str(path), repo)


def family(ident: str) -> str:
    """The feature or namespace a requirement belongs to: `F8` for `F8-R6`."""
    return ident.partition("-R")[0]


def gathered(files: list[tuple[str, str]], repo: str) -> list[Row]:
    """The rows of a `status/` directory, each file holding its own feature's only.

    `files` is each file's name and text. A row in the wrong file, and a
    requirement in two, are refused: the split is by feature so that a row is
    found where its identifier says it is.
    """
    rows: list[Row] = []
    seen: dict[str, str] = {}
    faults = []
    for name, text in sorted(files):
        where = f"{DIRECTORY}/{name}"
        for row in parse(text, where, repo) or []:
            if family(row.id) != pathlib.Path(name).stem:
                faults.append(f"{where}: {row.id} belongs in {DIRECTORY}/{family(row.id)}.toml")
            if row.id in seen:
                faults.append(f"{where}: {row.id} is also recorded in {seen[row.id]}")
            seen[row.id] = where
            rows.append(row)
    if faults:
        raise Unreadable("\n".join(faults))
    return rows


def load(root: pathlib.Path, repo: str) -> list[Row] | None:
    """A repository's tracker from its checkout: `status.toml`, or `status/`.

    None where it keeps neither, or keeps the milestone shape.
    """
    single, split = root / FILE, root / DIRECTORY
    if single.is_file() and split.is_dir():
        raise Unreadable(f"{repo} keeps both {FILE} and {DIRECTORY}/; keep one")
    if split.is_dir():
        files = sorted(split.glob(TOML))
        try:
            return gathered([(f.name, f.read_text(encoding="utf-8")) for f in files], repo)
        except UnicodeDecodeError as broken:
            raise Unreadable(f"{repo}: {broken}") from broken
    return read(single, repo)


def requirements(spec: pathlib.Path) -> tuple[set[str], set[str]]:
    """Every requirement the specification defines, and those it has retired."""
    defined: set[str] = set()
    retired: set[str] = set()
    for doc in spec.rglob("*.md"):
        if elsewhere(doc, spec):
            continue
        text = doc.read_text(encoding="utf-8")
        defined.update(REQ_DEF.findall(text))
        retired.update(REQ_RETIRED_ROW.findall(text))
    return defined, retired


def manifests(spec: pathlib.Path) -> list[dict]:
    """Every version manifest, read, the template apart."""
    return [tomllib.loads(path.read_text(encoding="utf-8"))
            for path in sorted((spec / VERSIONS).glob(TOML)) if path.stem != "TEMPLATE"]


def locked(spec: pathlib.Path) -> set[str]:
    """Every requirement some version manifest locks."""
    return {goal for data in manifests(spec) for goal in data.get("goals", [])}


def searched(spec: pathlib.Path) -> list[str]:
    """Every repository some version is satisfied in, which is every tracker."""
    return sorted({repo for data in manifests(spec)
                   for repo in data.get("satisfied_in", data.get("repos", []))})


def reachable(root: pathlib.Path, sha: str) -> bool:
    """Whether the repository at `root` holds that commit in its history."""
    done = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "HEAD"],
                          capture_output=True, check=False)
    return done.returncode == 0


def located(entry: str, root: pathlib.Path,
            siblings: dict[str, pathlib.Path]) -> tuple[pathlib.Path | None, str | None]:
    """The file an evidence entry names and the text it promises, or no file
    where it names another repository whose checkout was not given."""
    if match := ELSEWHERE.match(entry):
        name, entry = match.groups()
        if name not in siblings:
            return None, None
        root = siblings[name]
    path, _, text = entry.partition("::")
    return root / path, text or None


def evidence_faults(row: Row, where: str, root: pathlib.Path,
                    siblings: dict[str, pathlib.Path]) -> list[str]:
    """Each evidence entry that names something that is not there."""
    faults = []
    for entry in row.evidence:
        path, text = located(entry, root, siblings)
        if path is None:
            continue
        if not path.exists():
            faults.append(f"{where}: {row.id} names `{entry}` as evidence and there "
                          "is no such path")
        elif text is not None and (path.is_dir()
                                   or text not in path.read_text(encoding="utf-8",
                                                                 errors="ignore")):
            faults.append(f"{where}: {row.id} names `{entry}` as evidence and the "
                          f"file does not contain `{text}`")
    return faults


def check(rows: list[Row], where: str, spec: pathlib.Path, root: pathlib.Path,
          siblings: dict[str, pathlib.Path]) -> list[str]:
    """Every claim in one tracker that the specification or the tree does not back."""
    defined, retired = requirements(spec)
    carried = locked(spec)
    faults = []
    for row in rows:
        if row.id not in defined:
            faults.append(f"{where}: {row.id} is defined nowhere in the specification")
            continue
        if row.id in retired and row.id not in carried:
            faults.append(f"{where}: {row.id} is withdrawn or superseded and no version "
                          "locked it, so nothing was built against it")
        faults += evidence_faults(row, where, root, siblings)
        if row.landed and not reachable(root, row.landed):
            faults.append(f"{where}: {row.id} names `{row.landed}` as where it landed, "
                          "and this repository's history has no such commit")
    return faults


def pairs(specs: list[str], flag: str) -> dict[str, pathlib.Path]:
    """`name=path` arguments as a mapping, refusing one that is not or that
    leaves the working directory."""
    found = {}
    for spec in specs:
        name, sep, raw = spec.partition("=")
        if not sep or not name or not raw:
            raise Unreadable(f"{flag} wants name=path, got {spec!r}")
        found[name] = within_cwd(raw)
    return found


def report(faults: list[str], ok: str) -> int:
    for fault in faults:
        print(f"::error::{fault}")
    if faults:
        print(f"\nstatus-check: {len(faults)} claim(s) nothing backs.")
        return 1
    print(f"status-check: {ok}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("check")
    one.add_argument("--spec", required=True)
    one.add_argument("--repo-root", default=".")
    one.add_argument("--sibling", action="append", default=[], metavar="name=path")
    names = commands.add_parser("repos")
    names.add_argument("--spec", required=True)
    args = parser.parse_args()

    spec = within_cwd(args.spec)
    if not (spec / VERSIONS).is_dir():
        print(f"::error::no version manifests under {spec}")
        return 2
    try:
        if args.command == "repos":
            print("\n".join(searched(spec)))
            return 0
        root = within_cwd(args.repo_root)
        rows = load(root, root.name)
        if rows is None:
            print(f"status-check: no tracker in this shape under {args.repo_root} — nothing to check")
            return 0
        siblings = pairs(args.sibling, "--sibling")
        return report(check(rows, f"{root.name}'s tracker", spec, root, siblings),
                      f"every row of the tracker under {args.repo_root} is backed.")
    except Unreadable as refused:
        for line in str(refused).splitlines():
            print(f"::error::{line}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
