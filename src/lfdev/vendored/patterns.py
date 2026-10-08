"""What every gate in this directory is looking for, written once.

These scripts read the same things out of the same prose: a requirement defined
in a table, a requirement cited somewhere, an ADR filename, a `Spec:` trailer.
Each had written its own pattern for it — the definition four times, the citation
four times, the trailer four times in two spellings — and two of them had already
drifted apart.

That matters more here than it would elsewhere, because these scripts are the
gates. Two of them reading *nearly* the same pattern is how one comes to accept
what the other refuses, and neither is wrong on its own terms. `status_lint`
building a ceiling from citations while `integrity` checked definitions is
exactly that, and it composed correctly only by accident.

Importing across scripts works under the invocation CI uses: CPython puts a
script's own directory on `sys.path`, so `python3 .spec-canonical/scripts/x.py`
finds this from any working directory.
"""

import re

# A requirement, defined: the table row that brings it into being.
REQ_DEF = re.compile(r"^\|\s*\*\*([A-Z]+\d*-R\d+)\*\*\s*\|", re.MULTILINE)

# The same row, keeping the text as well, for the gates that read what it says.
REQ_DEF_ROW = re.compile(r"^\|\s*\*\*([A-Z]+\d*-R\d+)\*\*\s*\|([^|]*)\|", re.MULTILINE)

# A row kept only to retire a number: withdrawn or superseded in place.
#
# The row stays so the number is never reused, and its body says that instead of
# stating a requirement. It is a headstone, not a requirement, and OPS-R30 forbids
# one being a goal — so a gate that counts it as live is asking for something no
# manifest is permitted to give. `check_goal_coverage` did exactly that and held
# five debts nothing could ever discharge; `check_stageable` did the mirror of it
# and would have accepted a withdrawn identifier as a goal, under a docstring
# naming OPS-R30 as the rule it enforces.
REQ_RETIRED_ROW = re.compile(
    r"^\|\s*\*\*([A-Z]+\d*-R\d+)\*\*\s*\|\s*\*(?:Withdrawn|Superseded)\b",
    re.MULTILINE,
)

# A requirement, cited: a mention of one anywhere in prose.
CITE = re.compile(r"\b([A-Z]+\d*-R\d+)\b")

# A citation of either kind, for the gates that check both.
#
# The requirement half is `CITE`'s, deliberately. One of the two copies this
# replaces bounded the prefix at four characters and the number at four digits,
# which is true of every identifier today and is a rule nobody wrote down.
CITE_ANY = re.compile(r"\b([A-Z]+\d*-R\d+|ADR-\d{3,4})\b")

# A range of requirements, as a tracker writes one: `B1-R2..R7`.
RANGE = re.compile(r"\b([A-Z]+\d*)-R(\d+)\.\.(?:[A-Z]+\d*-)?R?(\d+)\b")

# An ADR, by its filename.
ADR_FILE = re.compile(r"^0*(\d{3,4})-.*\.md$")

# An ADR, cited.
ADR_CITE = re.compile(r"\bADR-(\d{3,4})\b")

# What a tracker row names where the work landed without a trailer to cite it.
#
# A commit cannot gain a `Spec:` trailer after it is merged, so a goal finished by
# somebody who wrote one trailer for a change closing several requirements has no
# way to be cited afterwards — and a later commit citing it without advancing it is
# exactly the unauditable claim the gate exists to refuse. This is the way out, and
# it is deliberately a **commit** rather than a pull request: a sha can be checked
# against the repository itself, offline, and `git show` is the audit.
LANDED = re.compile(r"landed in `([0-9a-f]{7,40})`")

# The trailer a commit or a pull request cites the specification with.
SPEC_TRAILER = re.compile(r"^[ \t]*Spec:[ \t]*(\S.*)$", re.MULTILINE | re.IGNORECASE)

# A version, as the manifests and the tracker write one.
VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def ordered(version: str) -> tuple[int, ...]:
    """A version as the numbers it is, which is not the order its name sorts in.

    As text `0.10.0` sorts below `0.2.0`, and four scripts spelled this key for
    themselves. One of them spelled it twice and used the other ordering in
    between: `check_order` recorded which version first locks a feature by
    walking the manifests in *name* order and then ranked those versions
    numerically, so six features were recorded as shipping several versions later
    than they do — `B2` in `0.15.0` where it is in `0.8.0`, `D1` in `0.12.0` where
    it is in `0.4.0`.

    Nothing went red for it, because the inversions it hid happened to fall in
    released versions, which are reported as history rather than as faults. The
    next one would not.
    """
    return tuple(int(part) for part in version.split("."))

# A pre-release identifier, as OPS-R61 lets a tag carry one: dot-separated
# alphanumeric segments, appended to a version that is otherwise this one.
#
# Kept apart from `VERSION` rather than folded into it, and the separation is the
# rule. Four gates match a version to decide whether they may act on it, and every
# one of them is about the release — staging it, transitioning it, naming the
# manifest it lives in. A pattern that accepted `0.15.0-pre.1` everywhere would let
# a pre-release be staged, be recorded as released, and name a manifest of its own,
# which is the whole of what OPS-R60 says must not happen.
#
# `rc` is refused by name. ARCH-R43 gives "the first release candidate" a meaning
# about the product's life — the moment `schema_version` stops changing in place —
# and a tag that called itself one would fire that by accident.
PRERELEASE_ID = re.compile(r"^(?!rc\d*(?:\.|$))[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*$")

# Every state a version manifest may be in, in the order OPS-R32 puts them.
#
# Ordered rather than a set, because three comments write this chain out for a
# reader and `test_release_states.py` holds them to it — which needs to know
# what comes after what, not merely what is allowed.
STATES = ("planned", "staged", "in_progress", "releasable", "released", "yanked")

# The states meaning "this is the version being worked on".
#
# Three gates asked this question and each spelled the answer itself: the PR
# classifier looking for the manifest to classify against, the staging check
# refusing a second version in flight, and `execute-version` refusing to execute
# one that is not. A state added to the middle of the lifecycle would have had
# to be remembered in three places in two languages, and the one that gets
# forgotten is whichever is not being edited that day.
IN_FLIGHT = ("staged", "in_progress", "releasable")

# A git ref that is safe to hand to a command is deliberately *not* here.
# `commit_lint` and `dco_check` each validate their arguments against one before
# reaching a subprocess, and the analysis that checks such a call cannot follow a
# pattern imported from elsewhere — so importing it reported both guarded calls
# as unguarded. A validation is worth keeping where the thing it validates is.
