#!/usr/bin/env python3
"""Spec-side integrity checks. Run in CI on the spec repo itself (GOV-R11).

Verifies:
  - every cited requirement/ADR identifier resolves to a definition
  - no requirement ID is defined twice (IDs are permanent and unique, GOV-R8)
  - every internal Markdown link resolves to a real file
  - a document's `**Status:**` line says what its front matter says
  - the counts this repository's own prose states match what it contains
  - each version manifest's stated goal count matches the goals it locks
  - each Draft proposal is in the shape the RFC process gives, with no identifier

Exit 0 = clean, 1 = problems found.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sys
import tomllib

import metafm
from catalogue import FEATURES_README
from catalogue import areas as area_names
from patterns import ADR_CITE, ADR_FILE, REQ_DEF
from patterns import CITE as REQ_CITE

ROOT = pathlib.Path(__file__).resolve().parent.parent

REGISTRY = pathlib.Path("30-repos/repos.toml")
VERSIONS = pathlib.Path("70-operations/versions")

LINK = re.compile(r"\[[^\]]*\]\((?!https?://|mailto:)([^)#]+)(?:#[^)]*)?\)")

#: The two places a document states its status: the front matter a tool reads,
#: and the bold line under the title a person reads. The first `**Status:**` line
#: is the one compared, as `spec_check.py` reads it, because a document may quote
#: another status further down.
FRONTMATTER_STATUS = re.compile(r"^status:\s*(\S+)", re.MULTILINE)
HEADER_STATUS = re.compile(r"^\*\*Status:\*\*\s*(\w+)", re.MULTILINE)

#: The words both silence refusals carry. A governed sentence that has gone is a
#: different fault from a number that is wrong, and only the second is repaired by
#: `--write` — so the two are told apart here rather than answered with one
#: sentence that is right about one of them.
UNCOMPARED = "so nothing was compared"


#: Directories under the root that hold no document of this repository's own.
#:
#: `checkouts/` is other repositories, cloned here on purpose — `.gitignore` says
#: so, `execute-version` puts nine of them there, and the release gates are meant
#: to be runnable from a checkout the same way. Read as this repository's prose,
#: every relative link in a tracker cloned there resolves against the wrong tree
#: and the whole of it reports as broken, which is `just integrity` failing for a
#: reason that is not about anything in this repository.
# Directories under the root that hold somebody else's text. `checkouts` is the
# other repositories this one reads, `vendor` and `node_modules` are copies a
# tool fetched, and `dist` is a rendered one. A dot-directory is whatever a tool
# put there — an agent's worktree, a cache, a virtualenv — and the worktree is
# the one that bites: it is a second clone of this repository, so every
# requirement in it is defined a second time and the gate reports the entire spec
# as duplicated, on a machine where nothing is wrong.
ELSEWHERE = ("checkouts", "vendor", "node_modules", "dist")


def elsewhere(path, root=None):
    """Whether a path sits under something this repository did not write.

    Relative to the root, because a clone can live anywhere: a checkout under
    `~/.local/src` has a dot in its absolute path and every file in it would be
    skipped, which is the same gate going quiet for the opposite reason.

    The root is an argument so that a check reading a tree it was pointed at asks
    this the same way. It is the one answer to which files are ours, and a second
    spelling of it is how one gate comes to walk a directory another skips.

    Neither side is resolved. The path is one this root's own walk produced, so it
    is already under it as written — and resolving would follow a symlink out of
    the tree, which is a containment question `write_counts` asks for itself and
    answers differently.
    """
    return any(
        part in ELSEWHERE or part.startswith(".")
        for part in path.relative_to(root if root is not None else ROOT).parts
    )


def md_files():
    return [p for p in ROOT.rglob("*.md") if not elsewhere(p)]


def defined_reqs():
    defined = collections.Counter()
    for p in md_files():
        for m in REQ_DEF.findall(p.read_text(encoding="utf-8")):
            defined[m] += 1
    return defined


def defined_adrs():
    dec = ROOT / "00-overview" / "decisions"
    adrs = set()
    if dec.is_dir():
        for f in dec.iterdir():
            m = ADR_FILE.match(f.name)
            if m:
                adrs.add(int(m.group(1)))
    return adrs


def undefined_citations(defset, adrs):
    problems = []
    for p in md_files():
        text = p.read_text(encoding="utf-8")
        # Only report the first stray citation per file; the rest is noise.
        for rid in REQ_CITE.findall(text):
            if rid not in defset:
                problems.append(f"{p.relative_to(ROOT)}: cites undefined {rid}")
                break
        for a in ADR_CITE.findall(text):
            if int(a) not in adrs:
                problems.append(f"{p.relative_to(ROOT)}: cites undefined ADR-{a}")
                break
    return problems


def check_ids():
    defined = defined_reqs()
    problems = [f"duplicate requirement id defined {n}x: {i}"
                for i, n in sorted(defined.items()) if n > 1]
    problems += undefined_citations(set(defined), defined_adrs())
    return problems


def check_links():
    problems = []
    for p in md_files():
        for target in LINK.findall(p.read_text(encoding="utf-8")):
            target = target.strip()
            if not target or target.startswith(".docs/") or "/.docs/" in target:
                continue  # repo-local .docs live in cli, not here
            resolved = (p.parent / target).resolve()
            if not resolved.exists():
                problems.append(f"{p.relative_to(ROOT)}: broken link -> {target}")
    return problems


#: Where Draft proposals are opened, one file each (GOV-R40).
PROPOSALS = pathlib.Path("10-functional/proposals")
#: The two files there that describe the shape rather than propose anything.
PROPOSAL_SHAPES = ("README.md", "TEMPLATE.md")
#: A proposal's file name: lower-case letters, digits and hyphens.
PROPOSAL_FILE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.md$")
PROPOSAL_KINDS = ("proposal", "gap")
PROPOSAL_FIELDS = ("kind", "area", "title", "amends", "status")
#: A feature's identifier, which an `amends` may name.
FEATURE = re.compile(r"^[A-Z]\d+$")
#: A statement of behaviour: a bullet using one of RFC 2119's keywords.
STATEMENT = re.compile(r"^- .*\b(MUST|SHOULD|MAY)\b", re.MULTILINE)


def section(text: str, heading: str) -> str:
    """The text under a `## heading`, to the next one, read line by line."""
    lines = text.splitlines()
    try:
        start = next(n for n, line in enumerate(lines) if line.rstrip() == f"## {heading}")
    except StopIteration:
        return ""
    end = next((n for n in range(start + 1, len(lines)) if lines[n].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1:end]).strip()


def amendable(name: str) -> bool:
    """Whether `amends` names a feature the catalogue holds or a page that exists."""
    if FEATURE.match(name):
        return any((ROOT / "10-functional" / "features").glob(f"*/{name.lower()}-*.md"))
    return (ROOT / name).is_file() and not elsewhere(ROOT / name)


def field_faults(front: dict, areas: set[str]) -> list[str]:
    """What is wrong with a proposal's front matter."""
    faults = []
    unknown = sorted(set(front) - set(PROPOSAL_FIELDS))
    if unknown:
        faults.append(f"carries fields the shape does not: {', '.join(unknown)}")
    if front.get("kind") not in PROPOSAL_KINDS:
        faults.append(f"has kind {front.get('kind')!r}; it is one of {', '.join(PROPOSAL_KINDS)}")
    if front.get("area") not in areas:
        faults.append(f"names area {front.get('area')!r}, which the catalogue does not hold")
    if not front.get("title"):
        faults.append("has no title")
    if front.get("status") != "draft":
        faults.append(f"has status {front.get('status')!r}; a proposal is draft until approved")
    amends = front.get("amends")
    if amends and not amendable(amends):
        faults.append(f"amends {amends!r}, which is neither a feature nor a page here")
    return faults


def body_faults(kind: str | None, amends: str | None, text: str) -> list[str]:
    """What is wrong with what a proposal or a gap says."""
    faults = []
    if REQ_DEF.search(text):
        faults.append("defines an identifier; identifiers are allocated on approval (GOV-R41)")
    if kind == "proposal" and not STATEMENT.search(section(text, "Proposed behaviour")):
        faults.append("has no statement under ## Proposed behaviour using MUST, SHOULD or MAY")
    if kind == "gap" and not amends:
        faults.append("is a gap and names no feature or page that is silent (amends)")
    if kind == "gap" and not section(text, "What the specification does not say"):
        faults.append("says nothing under ## What the specification does not say")
    return faults


def proposal_faults(path: pathlib.Path, areas: set[str]) -> list[str]:
    """What is wrong with one proposal file, each fault a sentence."""
    text = path.read_text(encoding="utf-8")
    front = metafm.parse(text)
    if front is None:
        return ["has no front matter; copy TEMPLATE.md"]
    named = [] if PROPOSAL_FILE.match(path.name) else [
        "is not named with lower-case letters, digits and hyphens"]
    return named + field_faults(front, areas) + body_faults(front.get("kind"), front.get("amends"), text)


def check_proposals():
    """Every Draft proposal that is not in the shape the RFC process gives."""
    directory = ROOT / PROPOSALS
    if not directory.is_dir():
        return []
    catalogue = ROOT / FEATURES_README
    areas = set(area_names(catalogue.read_text(encoding="utf-8"))) if catalogue.is_file() else set()
    problems = []
    for path in sorted(directory.iterdir()):
        if path.name in PROPOSAL_SHAPES or path.is_dir():
            continue
        if path.suffix != ".md":
            problems.append(f"{path.relative_to(ROOT)}: is not a proposal; only Markdown files belong here")
            continue
        problems += [f"{path.relative_to(ROOT)} {fault}" for fault in proposal_faults(path, areas)]
    return problems


def check_statuses():
    """Every document whose two statuses disagree, named with both.

    The citation gates read the front matter, so a document accepted there
    and still headed *Draft* is citable while it tells a reader it is not, and
    one headed *Accepted* over a draft front matter tells them the opposite.
    Accepting a document means changing both lines.
    """
    problems = []
    for p in md_files():
        text = p.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        head, _, _ = text[len("---\n"):].partition("\n---\n")
        front = FRONTMATTER_STATUS.search(head)
        header = HEADER_STATUS.search(text)
        if not front or not header:
            continue
        if front.group(1).lower() != header.group(1).lower():
            problems.append(
                f"{p.relative_to(ROOT)}: front matter says status {front.group(1)} "
                f"and the **Status:** line says {header.group(1)}"
            )
    return problems


#: Prose that states a number about this repository, and how to count the real
#: one. The documentation site guards its own transcriptions of these; nothing
#: guarded the spec's own, so its README drifted to a feature count nine short
#: and an ADR count five short.
def counted() -> tuple[dict, list[str]]:
    """What the tree actually holds, as {pattern: (actual, what)}, and any faults.

    Split out from `stated_counts` so that reporting a wrong number and writing
    the right one read the same table. A second copy of it is how a `--write`
    mode comes to disagree with the check that follows it.
    """
    features = ROOT / "10-functional" / "features"
    index = features / "index.json"

    # A tree with no feature catalogue states no counts about one. Reporting a
    # missing index here would be this check complaining that it has nothing to
    # do, which is noise rather than a finding.
    if not features.is_dir():
        return {}, []
    if not index.is_file():
        return {}, [
            (
                f"{index.relative_to(ROOT)} is missing, so the counts this "
                "repository states about its catalogue cannot be checked"
            )
        ]

    counts = json.loads(index.read_text(encoding="utf-8"))["counts"]
    features = int(counts["features"])
    adrs = len([p for p in (ROOT / "00-overview" / "decisions").glob("*.md")
                if ADR_FILE.match(p.name)])

    return {
        r"(\d+)-feature catalogue": (features, "features"),
        r"(\d+) ADRs": (adrs, "architecture decision records"),
    }, []


def stated_counts() -> list[str]:
    """Numbers the repository states about itself that no longer match it.

    Each pattern matches one sentence in the whole tree, which makes finding
    none of them indistinguishable from finding all of them right. Rephrase
    either — `the 81 feature catalogue`, `25 architecture decision records` —
    and this returns nothing, `integrity.py` prints `clean`, and the number goes
    back to being ungoverned by the check written to govern it.

    So the sentences are counted as well as compared. `check_services` refuses
    the same silence in the same words a directory over, and the reason it gives
    is the general one: a checker that finds no prose to compare passes in
    exactly the case where the format changed under it.
    """
    expected, faults = counted()
    seen = dict.fromkeys(expected, 0)
    for path in md_files():
        text = path.read_text(encoding="utf-8")
        for pattern, (actual, what) in expected.items():
            for found in re.finditer(pattern, text):
                seen[pattern] += 1
                stated = int(found.group(1))
                if stated != actual:
                    line = text[: found.start()].count("\n") + 1
                    faults.append(
                        f"{path.relative_to(ROOT)}:{line}: says {stated} "
                        f"{what} where this repository has {actual}"
                    )
    faults += [
        f"no sentence states a count of {expected[pattern][1]} in the shape "
        f"{pattern!r}, so nothing was compared — either the prose moved or this "
        f"check did. `--write` cannot repair this one: it rewrites a number "
        f"inside a sentence it can find. Put the sentence back in that shape, or "
        f"move the pattern in `counted()` to the shape the prose now uses"
        for pattern, found in seen.items()
        if not found
    ]
    return faults


def write_counts() -> list[str]:
    """Rewrite every stated count to what the tree holds. Returns what changed.

    The number is replaced inside the sentence that carries it, so the prose
    keeps its own voice — `80-feature catalogue` stays that phrase, with a
    different number in it.

    This exists because the check alone was not enough. Three of these needed a
    person on one afternoon: the ADR count twice, in two pull requests that then
    conflicted with each other, and the feature count once at 68 against 77.
    Each time the fix was to count files by hand and type the answer in.
    """
    expected, faults = counted()
    if faults:
        return faults
    changed = []
    for path in md_files():
        text = original = path.read_text(encoding="utf-8")
        for pattern, (actual, what) in expected.items():
            def replace(found, actual=actual, what=what, path=path):
                stated = int(found.group(1))
                if stated == actual:
                    return found.group(0)
                changed.append(
                    f"{path.relative_to(ROOT)}: {stated} -> {actual} {what}"
                )
                return found.group(0).replace(found.group(1), str(actual), 1)

            text = re.sub(pattern, replace, text)
        if text == original:
            continue
        # Only ever write inside the tree that was counted. `md_files()` yields
        # from `ROOT.rglob`, so this holds today — asserting it means a symlink
        # out of the tree, or a future caller passing a path from somewhere
        # else, cannot make it stop holding quietly.
        inside = path.resolve()
        if not inside.is_relative_to(ROOT.resolve()):
            changed.append(f"{path}: outside the spec tree, not rewritten")
            continue
        inside.write_text(text, encoding="utf-8")
    return changed


#: A version manifest's comment saying how many goals it locks.
#:
#: The number is kept out of the replacement so `--write` can put a different one
#: in the same sentence, the way `write_counts` does for the prose counts.
GOAL_COUNT = re.compile(r"^(#\s*)(\d+)(\s+goals\b)", re.MULTILINE)


def manifests() -> list[pathlib.Path]:
    """Every version manifest, the template excluded.

    The template is a file whose job is to be read as an example, so a number
    written into it documents the shape rather than claiming anything.
    """
    return [
        path
        for path in sorted((ROOT / VERSIONS).glob("*.toml"))
        if path.name != "TEMPLATE.toml"
    ]


def goal_counts() -> list[tuple[pathlib.Path, str, int, int]]:
    """Every stated goal count against the goals its manifest actually locks.

    A version states this in a comment and answers it in `goals`, so the two can
    disagree — and nothing downstream reads the comment, because `index.json`
    publishes the real number per version. That is what lets a stale one survive a
    whole release: it is prose in a data file, and the only reader is a person.

    The comparison is per match rather than per file, so a manifest stating the
    number twice is held to both.
    """
    found = []
    for path in manifests():
        text = path.read_text(encoding="utf-8")
        locked = len(tomllib.loads(text).get("goals", []))
        for match in GOAL_COUNT.finditer(text):
            line = text[: match.start()].count("\n") + 1
            found.append((path, f"{line}", int(match.group(2)), locked))
    return found


def stated_goal_counts() -> list[str]:
    """Version manifests whose stated goal count is not the number they lock.

    A manifest stating none is left alone — three of them state none, and asking
    for the sentence would be this check demanding prose rather than checking it.
    What is refused is a tree that has manifests and states the count in none of
    them: a pattern matching nowhere and a set of numbers that are all right print
    the same nothing, and the number this governs is one an editor retypes.
    """
    present = manifests()
    if not present:
        return []

    stated_anywhere = goal_counts()
    faults = [
        f"{path.relative_to(ROOT)}:{line}: says {stated} goals where this "
        f"version locks {locked}"
        for path, line, stated, locked in stated_anywhere
        if stated != locked
    ]
    if not stated_anywhere:
        faults.append(
            f"no manifest of the {len(present)} under {VERSIONS} states how many "
            f"goals it locks in the shape {GOAL_COUNT.pattern!r}, so nothing was "
            f"compared — either the comment moved or this check did. `--write` "
            f"cannot repair this one: it rewrites a number inside a comment it can "
            f"find. Put the comment back in that shape, or move `GOAL_COUNT` to "
            f"the shape the manifests now use"
        )
    return faults


def write_goal_counts() -> list[str]:
    """Rewrite each stated goal count to what its manifest locks. Returns changes.

    The number is replaced inside the comment that carries it, so a manifest
    explaining its own scope keeps its wording and gains the right figure.
    """
    changed = []
    for path in manifests():
        text = original = path.read_text(encoding="utf-8")
        locked = len(tomllib.loads(text).get("goals", []))

        def replace(match, locked=locked, path=path):
            if int(match.group(2)) == locked:
                return match.group(0)
            changed.append(
                f"{path.relative_to(ROOT)}: {match.group(2)} -> {locked} goals"
            )
            return f"{match.group(1)}{locked}{match.group(3)}"

        text = GOAL_COUNT.sub(replace, text)
        if text != original:
            path.write_text(text, encoding="utf-8")
    return changed


def check_manifest_repos():
    """Every repository a version manifest names resolves to one in the registry.

    `repos` says which streams a version cuts and `satisfied_in` says where the
    goal gate reads citations, and both are acted on: `manifest_repos.py` writes
    them out and `execute-version` clones the union. A name that resolves to
    nothing is a clone that fails at release, or a search that finds no commits
    and reports the goals unmet for a reason that is not about the work.

    `0.1.0` carried `media-stack` where every other manifest says
    `lemonfiber-media-stack`, which is the name the repository actually has.
    Nothing read the two lists against each other.
    """
    manifests = [
        m for m in sorted((ROOT / VERSIONS).glob("*.toml")) if m.name != "TEMPLATE.toml"
    ]

    # A tree with no manifests has nothing to check, which is the shape the
    # suite builds. A tree with manifests and no registry is a different fact
    # and says so rather than raising.
    if not manifests:
        return []

    known, unreadable = registered(len(manifests))

    if unreadable:
        return [unreadable]

    return [
        f"{manifest.relative_to(ROOT)}: {said}, which is not a repository in {REGISTRY}"
        for manifest in manifests
        for said, name in repositories_named(
            tomllib.loads(manifest.read_text(encoding="utf-8"))
        )
        if name not in known
    ]


def registered(wanted):
    """The repositories the registry knows, or why it could name none.

    Two answers rather than an empty set, because an empty set compares equal to a
    registry that holds nothing and to one that is not there at all — and against
    either, every name in every manifest would be reported as unknown, which reads
    as fifty broken manifests rather than one missing file.
    """
    registry = ROOT / REGISTRY

    if not registry.is_file():
        return set(), (
            f"{REGISTRY}: not found, and {wanted} manifest(s) name "
            "repositories that have to resolve to one"
        )

    read = tomllib.loads(registry.read_text(encoding="utf-8"))
    known = {repo["name"] for repo in read.get("repo", [])}

    if not known:
        return set(), f"{REGISTRY}: no repository was read, so nothing can be checked against it"

    return known, None


def repositories_named(data):
    """Every repository one manifest names, said the way that manifest says it.

    Three keys rather than two: a pin is keyed by repository as well, and `0.1.0`
    had the short name in both places. A pin that names nothing records which commit
    of no repository the release carried.
    """
    for field in ("repos", "satisfied_in"):
        for name in data.get(field, []):
            yield f"{field} names {name!r}", name

    for name in data.get("pins", {}):
        yield f"pins {name!r}", name


def main() -> int:
    if "--write" in sys.argv[1:]:
        changed = write_counts() + write_goal_counts()
        for line in changed:
            print(line)
        print(f"\n{len(changed)} stated count(s) rewritten.")
        # Asked again afterwards, because a repair that repaired nothing and a
        # tree that needed none print the same line. `0 stated count(s)
        # rewritten` is what a pattern matching nowhere produces, and it reads
        # as the numbers having been right all along.
        remaining = stated_counts() + stated_goal_counts()
        for fault in remaining:
            print(f"::error::{fault}")
        return 1 if remaining else 0

    counts = stated_counts() + stated_goal_counts()
    problems = []
    # De-dup the "cites undefined" one-per-file noise into unique messages.
    seen = set()
    for msg in (
        check_ids()
        + check_links()
        + check_statuses()
        + counts
        + check_manifest_repos()
        + check_proposals()
    ):
        if msg not in seen:
            seen.add(msg)
            problems.append(msg)
    if problems:
        for m in problems:
            print(f"::error::{m}")
        # The fix for a wrong count is never to type the right one: the tree is
        # the source of it and `--write` reads the tree. Said once at the end
        # rather than on each line, the way `check_services.py` says it — the
        # refusals above name the sentences, and this names what to do about
        # every one of them at once.
        #
        # Only where a number is wrong. A governed sentence that has gone
        # missing is not repaired by `--write`, and sending somebody there would
        # be sending them to a command that reports repairing nothing.
        if [one for one in counts if UNCOMPARED not in one]:
            print(
                "::error::this repository is the source of these numbers; run "
                "`just counts` (`integrity.py --write`) rather than editing the "
                "prose. A count nobody generated is a count that drifts again."
            )
        print(f"\n{len(problems)} integrity problem(s).")
        return 1
    print("spec integrity: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
