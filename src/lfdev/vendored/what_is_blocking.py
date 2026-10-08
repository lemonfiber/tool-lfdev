#!/usr/bin/env python3
"""Say what a `BLOCKED` pull request is blocked on, including what never reported.

Usage: what_is_blocking.py <owner/repo> [<number> ...]
       what_is_blocking.py --org <owner>

GitHub will tell you a pull request is blocked. It will not reliably tell you by
what. A required check that failed is on the page with a link to its log; a
required check that *never reported* is on no page at all — the merge box says
"Required statuses must pass" and the check list simply does not mention it.
There is nothing to click, because nothing ran.

That is not a corner case. A workflow with a `paths:` filter that does not match,
a job whose `needs:` dependency failed, a reusable workflow the caller granted
too few permissions to, a third-party app having an outage: all four block a pull
request forever and all four look identical, which is to say they look like
nothing at all. On 2026-09-13 every open pull request in this organisation sat on
a missing `SonarCloud Code Analysis` and a missing `gate / gate`, and finding
that out took reading branch protection and the check list side by side by hand.

So that is what this does. It reads what branch protection requires — the status
contexts and the rules that are not contexts at all — against what the head
commit actually carries, and names the difference.

Against the head *commit*, not the pull request. `gh pr checks` reads a rollup
that lags, and branch protection is evaluated against the commit; asking the
pull request instead is how this reported twenty of twenty satisfied while a
check was still running.

Where it and GitHub disagree it says so rather than quietly contradicting the
merge box, and where every required context is missing it says that once, with
the reason, instead of once per context.

Two halves, split the way `dco_check.py` splits: `_gh` shells out and everything
above it is handed what `gh` said and decides. The decisions are the part worth
testing, and a suite that had to stand up a repository and a branch protection
rule to reach them would be testing GitHub.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# What a reported check's state means for the merge.
#
# `SKIPPED` and `NEUTRAL` are deliberately neither: GitHub does not treat them as
# failures, and this does not claim they are passes. A skipped required check is
# worth a maintainer's eye — it is how a gate goes quiet without going red — so it
# is named rather than folded into either column.
PASSED = frozenset({"SUCCESS"})
FAILED = frozenset({"FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"})
WAITING = frozenset({"PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED"})
QUIET = frozenset({"SKIPPED", "NEUTRAL", "CANCELLED", "STALE"})

# The order findings are printed in, worst first. `missing` leads because it is
# the one with nowhere to look.
ORDER = ("missing", "failing", "quiet", "waiting", "passed")

# Branch protection is not only a list of checks, and the rest of it blocks just
# as hard while appearing in no check list at all.
#
# Each entry maps a protection setting to the question that decides whether it is
# what is holding this pull request, and to the sentence a maintainer can act on.
# `required_signatures` is here because it is the trap that costs the most time:
# an unsigned commit blocks a pull request with every check green and nothing
# anywhere naming the cause.
RULES = (
    (
        "strict",
        "behind",
        "the branch must be up to date with its base — rebase it and push",
    ),
    (
        "signatures",
        "unsigned",
        "every commit must be signed — re-sign and force-push",
    ),
    (
        "conversation",
        "unresolved",
        "every review conversation must be resolved",
    ),
    (
        "reviews",
        "unapproved",
        "an approving review is required",
    ),
)


# How loudly each state speaks, for deciding which of two reports under one name
# is the one to show. Built once: it never changes, and a dict comprehension per
# call was doing the same work for every check on every pull request.
#
# `PASSED` is in here, and leaving it out was a bug. Everything absent took the
# default rank, which is `WAITING`'s — so a success and a run still going tied,
# and a tie is decided by whichever the forge happened to list first. A re-run
# then reads as the old pass: `lemonfiber-companion#123` reported twenty of
# twenty satisfied while `mutation testing` was `in_progress` on the head commit,
# and this script contradicted a `BLOCKED` merge box on the strength of it.
#
# Ranked last rather than merely distinct: a pass is the only state that says
# nothing more is coming, so anything else reported under the same name is news.
RANK = {
    **dict.fromkeys(FAILED, 0),
    **dict.fromkeys(WAITING, 1),
    **dict.fromkeys(QUIET, 2),
    **dict.fromkeys(PASSED, 3),
}


def blocking(required: list[str], reported: dict[str, str]) -> dict[str, list[str]]:
    """Sort every required context by what it is doing.

    `required` is what branch protection insists on; `reported` maps a check name
    to its state. A context in the first and not the second is `missing` — the
    whole reason this exists. A check that reported and is not required is not
    this function's business: it cannot block the merge, so it is not returned.

    An unrecognised state counts as `waiting` rather than as a pass. A new state
    GitHub adds should read as "not finished" until somebody looks, because the
    alternative is a gate that quietly widens every time the forge does.
    """
    found: dict[str, list[str]] = {key: [] for key in ORDER}
    for context in required:
        state = reported.get(context)
        if state is None:
            found["missing"].append(context)
        elif state in PASSED:
            found["passed"].append(context)
        elif state in FAILED:
            found["failing"].append(context)
        elif state in QUIET:
            found["quiet"].append(context)
        else:
            found["waiting"].append(context)
    return found


def unmet(protection: dict[str, bool], state: dict[str, bool]) -> list[str]:
    """The protection rules holding this pull request that are not checks.

    `protection` says which rules the branch turns on; `state` says which of the
    corresponding conditions this pull request is currently failing. A rule that
    is off, or on and satisfied, is not returned.

    Separate from `blocking` because these are a different kind of answer: a
    failing check has a log, and none of these has anything at all. Reporting
    "every required context is satisfied" while one of them holds the merge is
    the same wrong answer GitHub's own merge box gives.
    """
    unread = set(state.get("unread") or ())
    said: list[str] = []
    for setting, condition, sentence in RULES:
        if not protection.get(setting):
            continue
        if condition in unread:
            # The one answer this must never give about a rule that is on. Two
            # of the four are read with a second `gh` call, and a call that
            # failed used to be indistinguishable from a rule that was met —
            # so a rate limit or a token missing a scope made the report say
            # every required context is satisfied, about a question it had not
            # managed to ask.
            said.append(
                f"the {setting} rule is on and could not be read here, "
                "so it is unproven rather than satisfied"
            )
        elif state.get(condition):
            said.append(sentence)
    return said


def why_nothing_ran(found: dict[str, list[str]], conclusions: list[str]) -> str | None:
    """Where every required check is missing, the reason they all are.

    Twenty contexts reported as missing, one line each, is twenty statements of
    one fact — and the fact is not about the contexts. Nothing ran. What is worth
    saying is why, and `startup_failure` is the answer that has no other symptom:
    a workflow that could not start produces no check run, no log, and no entry on
    the pull request. On 2026-09-13 every workflow on three branches failed to
    start inside one minute, and each pull request read as twenty missing checks.

    Only where *everything* is missing. A single missing context among reported
    ones is a different question — a `paths:` filter, a failed `needs:` — and this
    would be the wrong answer to it.
    """
    if not found["missing"] or any(found[key] for key in ORDER if key != "missing"):
        return None
    if "startup_failure" in conclusions:
        return (
            "no required check reported because the workflows did not start "
            "(startup_failure). A run that fails to start leaves no check, no log "
            "and nothing on the pull request. Re-running is usually refused; push "
            "the branch again"
        )
    if not conclusions:
        # True, and also what a branch pushed a moment ago looks like. Saying only
        # the first half sends somebody hunting a broken trigger while the runs
        # they are waiting for are still being scheduled.
        return (
            "no required check reported, and no workflow run has finished for this "
            "commit — which is also how a branch pushed moments ago reads. Look "
            "again before treating it as a broken trigger"
        )
    return "no required check reported yet; the runs that exist have not produced them"


def disagrees(found: dict[str, list[str]], rules: list[str], forge: str) -> str | None:
    """Where this script and GitHub have reached different conclusions.

    GitHub's `mergeStateStatus` is the answer that actually decides the merge,
    and this script is a second opinion about the same evidence. Where the two
    agree, saying so adds nothing. Where they do not, one of them is reading
    something stale — and printing "every required context is satisfied" over the
    top of a `BLOCKED` merge box sends somebody looking for a failure that is not
    there, which is the shape of unhelpfulness this was written against.

    So it says both, and says which to believe. GitHub decides. It is also
    usually the one that has not caught up: closing and reopening the pull
    request forces it to, at the price of starting every workflow again.
    """
    # `waiting` counts. A check still running is a pull request GitHub is right
    # to be blocking, and calling that a disagreement would make this cry wolf on
    # every pull request between the push and the last check — which is most of
    # them, most of the time.
    clear = not rules and not any(
        found[key] for key in ("missing", "failing", "waiting")
    )
    if clear and forge not in ("CLEAN", "HAS_HOOKS", "UNSTABLE", "UNKNOWN", ""):
        return (
            f"every required context is satisfied here, but GitHub says {forge}. "
            "GitHub decides, and it is usually the one that has not recomputed — "
            "closing and reopening the pull request forces it, at the price of "
            "starting every workflow again"
        )
    return None


def verdict(found: dict[str, list[str]], rules: list[str] | None = None) -> str:
    """One line saying whether anything is wrong, and where to look if so."""
    if found["missing"]:
        return (
            "blocked on a check that never reported, which appears nowhere in the "
            "pull request's own check list"
        )
    if found["failing"]:
        return "blocked on a check that failed; its log is on the pull request"
    if rules:
        return "every required context is satisfied; a branch protection rule holds it"
    if found["waiting"]:
        return "nothing is wrong; checks are still running"
    return "every required context is satisfied"


def lines(
    repo: str,
    number: int,
    found: dict[str, list[str]],
    rules: list[str] | None = None,
    nothing_ran: str | None = None,
    split: str | None = None,
) -> list[str]:
    """The report, worst first, with the empty categories left out."""
    if split:
        return [f"{repo}#{number}: {split}"]
    if nothing_ran:
        out = [f"{repo}#{number}: {nothing_ran}"]
        out.extend(f"  {'RULE':>8}: {said}" for said in rules or [])
        out.append(f"  {'missing':>8}: {len(found['missing'])} required contexts, all of them")
        return out
    out = [f"{repo}#{number}: {verdict(found, rules)}"]
    for key in ORDER:
        if key == "passed" or not found[key]:
            continue
        for context in found[key]:
            out.append(f"  {key.upper():>8}: {context}")
    for said in rules or []:
        out.append(f"  {'RULE':>8}: {said}")
    passed = len(found["passed"])
    if passed:
        out.append(f"  {'passed':>8}: {passed}")
    return out


# What a repository and a branch are allowed to be called, checked before either
# reaches `gh`.
#
# Nothing here goes through a shell, so this is not shell injection — it is
# argument injection, which needs no shell. `gh` reads an argument beginning with
# `-` as an option, so a "repository" called `--template` is not a repository
# this fails to find; it is a flag, silently changing what the command does. The
# repository name arrives from the command line and is interpolated into an API
# path besides, where `..` would walk out of it.
#
# Refused rather than escaped. There is no legitimate repository or branch this
# turns away: GitHub allows neither a leading dash nor `..` in either.
_SAFE = re.compile(r"\A[0-9A-Za-z][0-9A-Za-z._/-]{0,254}\Z")
_NAME = re.compile(r"\A[0-9A-Za-z][0-9A-Za-z._-]{0,99}\Z")
_BRANCH = re.compile(r"\A[0-9A-Za-z][0-9A-Za-z._/-]{0,254}\Z")


def safe(value: str) -> str:
    """`value`, or a refusal — applied where it is put into a `gh` argument.

    `look` already turns away a repository or branch that is not one, with a
    sentence a reader can act on, and that is the right place for the message.
    It is the wrong place for the guarantee: it leaves every later caller of the
    helpers below to remember, and it leaves the check far enough from the
    `subprocess` call that a taint analyser cannot see the two connected —
    SonarCloud raised `S8705` here twice for exactly that reason, and was right
    to, because "some caller checks this" is not a property of this function.

    So the values are checked where they are used. Raised rather than returned
    empty: reaching here with an unchecked name is a mistake in this file, not a
    repository somebody cannot read, and the two should not look alike.
    """
    if not _SAFE.match(value):
        raise ValueError(f"refusing to pass {value!r} to gh: not a name or a number")
    return value


def named(repo: str) -> bool:
    """Whether `repo` is `owner/name` and both halves are what they claim."""
    owner, slash, name = repo.partition("/")
    return bool(slash) and bool(_NAME.match(owner)) and bool(_NAME.match(name))


def branched(base: str) -> bool:
    """Whether `base` is a branch name, and not a path walking out of one."""
    return bool(_BRANCH.match(base)) and ".." not in base


def _gh(*args: str) -> str:
    """What `gh` said, or an empty string where it would not answer.

    Empty rather than raised: a repository with no branch protection is a real
    answer to "what is required here", and so is a token that cannot read it.
    Both are reported by the caller as "nothing required", which is true of what
    this was able to see and is said plainly rather than implied.

    No shell, and never one: the arguments are passed as a list, and the two that
    come from outside this script are checked against `named` and `branched`
    before they arrive here.
    """
    done = subprocess.run(
        ("gh", *args), capture_output=True, text=True, check=False, timeout=60
    )
    return done.stdout if done.returncode == 0 else ""


def _protection_of(repo: str, base: str) -> dict:
    """The whole branch protection object for `base`, read once.

    Once, because the two questions asked of it — which contexts are required,
    and which of the other rules are on — are two reads of the same document.
    """
    said = _gh("api", f"repos/{safe(repo)}/branches/{safe(base)}/protection")
    return json.loads(said) if said.strip() else {}


def required_in(protection: dict) -> list[str]:
    """The contexts branch protection insists on."""
    return list((protection.get("required_status_checks") or {}).get("contexts") or [])


def rules_in(protection: dict) -> dict[str, bool]:
    """Which of the non-check rules are turned on."""
    checks = protection.get("required_status_checks") or {}
    reviews = protection.get("required_pull_request_reviews") or {}
    return {
        "strict": bool(checks.get("strict")),
        "signatures": bool((protection.get("required_signatures") or {}).get("enabled")),
        "conversation": bool(
            (protection.get("required_conversation_resolution") or {}).get("enabled")
        ),
        "reviews": (reviews.get("required_approving_review_count") or 0) > 0,
    }


# The `gh pr view --json` fields `_state` asks for. Named here so the suite can
# hand them back to `gh` and check it accepts them.
#
# It has to. `_gh` answers an unreadable repository with an empty string on
# purpose, so one bad repository does not end the run for the others — which
# means a field name `gh` rejects also comes back empty, and the rule it feeds
# silently never fires. `reviewThreads` was exactly that: a plausible name, not a
# real one, and every conversation-resolution block would have gone unreported
# with the script saying nothing was wrong.
FIELDS = ("mergeStateStatus", "reviewDecision")


def _state(repo: str, number: int) -> dict[str, bool]:
    """Which of those conditions this pull request is currently failing.

    `mergeStateStatus` answers "behind" directly. The rest are asked separately
    rather than inferred from `BLOCKED`, which is the single word this whole
    script exists because GitHub gives instead of a reason.
    """
    said = _gh("pr", "view", "-R", safe(repo), safe(str(number)), "--json", ",".join(FIELDS))
    if not said.strip():
        return {}
    pr = json.loads(said)
    unsigned, unresolved = _unsigned(repo, number), _unresolved(repo, number)
    return {
        "forge": pr.get("mergeStateStatus") or "",
        "behind": pr.get("mergeStateStatus") == "BEHIND",
        "unsigned": bool(unsigned),
        "unresolved": bool(unresolved),
        "unapproved": pr.get("reviewDecision") not in ("APPROVED", None, ""),
        # The two that can come back unreadable, named so the report can say so.
        # Reporting them as satisfied is the one answer this script must never
        # give, because it is the answer the merge box already gives.
        "unread": [
            condition
            for condition, answer in (("unsigned", unsigned), ("unresolved", unresolved))
            if answer is None
        ],
    }


# Review threads and their resolution are not on `gh pr view`, only on GraphQL.
THREADS = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) { nodes { isResolved } }
    }
  }
}
"""


def _unresolved(repo: str, number: int) -> bool | None:
    """Whether any review conversation is still open, or nothing where unreadable.

    A `--jq` over a list prints `[]` on a successful call with nothing in it, so
    empty output is `gh` having failed rather than an answer. The two used to be
    one: a rate limit, an expired token or a scope the token lacks each produced
    `False` here, the rule was dropped from the report, and the run said every
    required context was satisfied with nothing hinting that it had not asked.
    """
    owner, name = repo.split("/", 1)
    said = _gh(
        "api", "graphql",
        "-f", f"query={THREADS}",
        "-F", f"owner={safe(owner)}", "-F", f"repo={safe(name)}", "-F", f"number={safe(str(number))}",
        "--jq", "[.data.repository.pullRequest.reviewThreads.nodes[].isResolved]",
    )
    if not said.strip():
        return None
    return any(not resolved for resolved in json.loads(said))


def _unsigned(repo: str, number: int) -> list[str] | None:
    """Commits with no verified signature, or nothing where that could not be read.

    The rule this repository is most often blocked by and the one no check list
    names, so losing it silently is the worst of the four to lose.
    """
    said = _gh(
        "api",
        f"repos/{safe(repo)}/pulls/{safe(str(number))}/commits",
        "--jq",
        "[.[] | select(.commit.verification.verified | not) | .sha[0:8]]",
    )
    if not said.strip():
        return None
    return json.loads(said)


# A check run says `status` until it is over and `conclusion` after; a commit
# status says `state`. Both are lowercase and neither vocabulary is the one the
# columns above are written in, so each is translated once, here.
_CONCLUSION = {
    "success": "SUCCESS",
    "failure": "FAILURE",
    "timed_out": "TIMED_OUT",
    "action_required": "ACTION_REQUIRED",
    "startup_failure": "STARTUP_FAILURE",
    "cancelled": "CANCELLED",
    "neutral": "NEUTRAL",
    "skipped": "SKIPPED",
    "stale": "STALE",
}
_STATUS = {"queued": "QUEUED", "in_progress": "IN_PROGRESS", "waiting": "WAITING"}
_COMMIT_STATE = {
    "success": "SUCCESS",
    "failure": "FAILURE",
    "error": "FAILURE",
    "pending": "PENDING",
}


def reading(runs: list[dict], statuses: list[dict]) -> dict[str, str]:
    """One state per check name, from what the head commit actually carries.

    The most recent report under a name wins, because that is the one the forge
    is holding the merge against. Where two share a timestamp the worse of them
    does, since showing the pass and hiding the failure beside it is how this
    tool would become the thing it exists to catch.

    An unrecognised `conclusion` keeps its own name rather than being mapped to
    anything: `blocking` reads a state it does not know as unfinished, and that
    is the right reading for a word GitHub added after this was written.
    """
    latest: dict[str, tuple[str, str]] = {}
    for run in runs:
        conclusion = run.get("conclusion")
        state = (
            _CONCLUSION.get(conclusion, (conclusion or "").upper())
            if conclusion
            else _STATUS.get(run.get("status", ""), "PENDING")
        )
        _keep(latest, run.get("name", ""), state,
              run.get("completed_at") or run.get("started_at") or "")
    for status in statuses:
        _keep(latest, status.get("context", ""),
              _COMMIT_STATE.get(status.get("state", ""), "PENDING"),
              status.get("created_at") or "")
    return {name: state for name, (_, state) in latest.items()}


def _keep(latest: dict, name: str, state: str, when: str) -> None:
    """Record `state` for `name` where it is the one worth reporting."""
    if not name:
        return
    seen = latest.get(name)
    if seen is None or when > seen[0] or (when == seen[0] and _worse(state, seen[1])):
        latest[name] = (when, state)


def _reported(repo: str, number: int) -> dict[str, str]:
    """Every check the head commit carries, by name.

    Read from the commit rather than from `gh pr checks`. They are not the same
    answer: `gh pr checks` reads a rollup that lags, and on
    `lemonfiber-companion#123` it reported `mutation testing` as the success of a
    previous run while the commit carried one still in progress — so this script
    called twenty of twenty satisfied and contradicted a `BLOCKED` merge box.
    Branch protection is evaluated against the commit, so the commit is what this
    asks.
    """
    sha = _head(repo, number)
    if not sha:
        return {}
    runs = _gh(
        "api", f"repos/{safe(repo)}/commits/{safe(sha)}/check-runs?per_page=100",
        "--paginate", "--jq",
        "[.check_runs[]|{name,conclusion,status,completed_at,started_at}]",
    )
    statuses = _gh(
        "api", f"repos/{safe(repo)}/commits/{safe(sha)}/status",
        "--jq", "[.statuses[]|{context,state,created_at}]",
    )
    return reading(
        json.loads(runs) if runs.strip() else [],
        json.loads(statuses) if statuses.strip() else [],
    )


def _head(repo: str, number: int) -> str:
    said = _gh(
        "pr", "view", "-R", safe(repo), safe(str(number)),
        "--json", "headRefOid", "--jq", ".headRefOid",
    )
    return said.strip()


def _worse(state: str, than: str) -> bool:
    """Whether `state` is the one a maintainer needs to hear about."""
    return RANK.get(state, 1) < RANK.get(than, 1)


def _conclusions(repo: str, branch: str, sha: str) -> list[str]:
    """How this commit's workflow runs ended — not this branch's.

    A branch keeps its old runs, and every push leaves another set. Reading them
    all means a `startup_failure` from two pushes ago answers for a commit whose
    runs are queued and fine, which is the same mistake `no_open_codeql_alert.py`
    was making about analyses: the ref keeps answering after the commit it
    describes has been replaced. `lemonfiber-companion#121` was told to push
    again on the strength of a run belonging to a commit it had already replaced.

    Only asked when nothing reported, because that is the only case it answers.
    """
    said = _gh(
        "run", "list", "-R", safe(repo), "--branch", safe(branch), "--limit", "40",
        "--json", "headSha,conclusion", "--jq",
        f'[.[]|select(.headSha == "{safe(sha)}")|.conclusion]',
    )
    return [c for c in (json.loads(said) if said.strip() else []) if c]


def _branch_of(repo: str, number: int) -> str:
    said = _gh(
        "pr", "view", "-R", safe(repo), safe(str(number)), "--json", "headRefName", "--jq", ".headRefName"
    )
    return said.strip()


def _open_prs(repo: str) -> list[int]:
    said = _gh("pr", "list", "-R", safe(repo), "--state", "open", "--json", "number")
    return [pr["number"] for pr in (json.loads(said) if said.strip() else [])]


def _repos(org: str) -> list[str]:
    said = _gh("repo", "list", safe(org), "--limit", "100", "--json", "nameWithOwner")
    return [r["nameWithOwner"] for r in (json.loads(said) if said.strip() else [])]


def _base(repo: str, number: int) -> str:
    said = _gh(
        "pr", "view", "-R", safe(repo), safe(str(number)), "--json", "baseRefName", "--jq", ".baseRefName"
    )
    return said.strip() or "main"


def look(repo: str, number: int) -> list[str]:
    """Read one pull request and report it."""
    if not named(repo):
        return [f"{repo}: not a repository name — expected owner/name"]
    base = _base(repo, number)
    if not branched(base):
        return [f"{repo}#{number}: base branch {base!r} is not a branch name"]
    protection = _protection_of(repo, base)
    required = required_in(protection)
    state = _state(repo, number)
    rules = unmet(rules_in(protection), state) if protection else []
    if not required and not rules:
        return [f"{repo}#{number}: nothing required, or branch protection is unreadable here"]
    found = blocking(required, _reported(repo, number))
    nothing_ran = None
    if found["missing"] and not any(found[key] for key in ORDER if key != "missing"):
        branch, sha = _branch_of(repo, number), _head(repo, number)
        if branched(branch) and sha:
            nothing_ran = why_nothing_ran(found, _conclusions(repo, branch, sha))
    split = disagrees(found, rules, str(state.get("forge", "")))
    return lines(repo, number, found, rules, nothing_ran, split)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="owner/repo, or the owner when --org is given")
    parser.add_argument("numbers", nargs="*", type=int, help="pull requests; default all open")
    parser.add_argument("--org", action="store_true", help="read every repository in the org")
    args = parser.parse_args(argv)

    if args.org:
        if not _NAME.match(args.target):
            print(f"{args.target}: not an organisation name")
            return 1
        pairs = [(repo, n) for repo in _repos(args.target) for n in _open_prs(repo)]
    elif args.numbers:
        pairs = [(args.target, n) for n in args.numbers]
    else:
        pairs = [(args.target, n) for n in _open_prs(args.target)]

    for repo, number in pairs:
        print("\n".join(look(repo, number)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
