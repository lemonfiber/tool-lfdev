"""`lfdev decide "<decision>" --where "<link>"`: record a decision the
maintainer made, as a row under today's date in spec's decision log (GOV-R49).

It runs in a checkout of spec, on a branch. The row goes under today's heading,
which it adds in date order where the log has none yet, and it is committed,
signed, with the `Spec:` line and a sign-off (REPO-R77). It will not commit to
`main`.
"""

from __future__ import annotations

import datetime
import pathlib
import re

from lfdev.spec_scripts import Runner
from lfdev.status import DEFAULT, Asker

#: The log, from the root of a checkout of spec.
LOG = pathlib.Path("50-governance/decision-log.md")
#: The requirement the log serves.
REQUIREMENT = "GOV-R49"
#: A day's heading.
DAY = re.compile(r"^## (\d{4}-\d{2}-\d{2})$")
#: The head of a day's table.
TABLE = ("| Decision | Where it lives |", "|---|---|")


def cell(text: str) -> str:
    """Text as one table cell: on one line, its pipes escaped."""
    flat = text.strip()
    if not flat or "\n" in flat:
        raise ValueError("a decision and where it lives are each one line of text")
    return flat.replace("|", r"\|")


def with_row(log: str, day: datetime.date, row: str) -> str:
    """The log with the row added under the day's heading."""
    lines = log.split("\n")
    stamp = day.isoformat()
    headings = [(at, line) for at, line in enumerate(lines) if line.startswith("## ")]
    days = [(at, found.group(1)) for at, line in headings if (found := DAY.match(line))]
    if not days:
        raise ValueError(f"{LOG} has no dated heading to put the row beside")
    following = {at: next((h for h, _ in headings if h > at), len(lines)) for at, _ in days}
    same = next((at for at, found in days if found == stamp), None)
    if same is not None:
        end = following[same]
        last = max((at for at in range(same, end) if lines[at].startswith("|")), default=None)
        if last is None:
            lines[same + 1 : same + 1] = ["", *TABLE, row]
        else:
            lines.insert(last + 1, row)
        return "\n".join(lines)
    before = [at for at, found in days if found < stamp]
    place = following[before[-1]] if before else days[0][0]
    lines[place:place] = [f"## {stamp}", "", *TABLE, row, ""]
    return "\n".join(lines)


def record(
    decision: str,
    where: str,
    ask: Asker,
    run: Runner,
    today: datetime.date,
) -> tuple[int, str]:
    """Write and commit one row; the exit code and what to say."""
    code, top = ask(["git", "rev-parse", "--show-toplevel"])
    if code != 0:
        return 2, "not inside a git repository"
    root = pathlib.Path(top)
    path = root / LOG
    if not path.is_file():
        return 2, f"no {LOG} here: run this in a checkout of spec"
    _, branch = ask(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == DEFAULT:
        return 2, f"on {DEFAULT}: make a branch for the change first (git switch -c <name>)"
    try:
        row = f"| {cell(decision)} | {cell(where)} |"
        after = with_row(path.read_text("utf-8"), today, row)
    except ValueError as refused:
        return 2, str(refused)
    path.write_text(after, "utf-8")
    relative = str(LOG)
    committed = run(["git", "add", "--", relative], root)
    if committed == 0:
        message = ["-m", f"docs(decisions): a decision of {today.isoformat()}", "-m", f"Spec: {REQUIREMENT}"]
        committed = run(["git", "commit", "-S", "-s", *message, "--", relative], root)
    if committed != 0:
        return committed, f"{relative} is written, and git did not commit it"
    return 0, f"recorded under {today.isoformat()} in {relative}, committed"
