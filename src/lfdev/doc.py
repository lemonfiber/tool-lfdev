"""`lfdev doc <url>`: where a page on one of the organisation's sites comes
from, so a fix goes to the file that is rendered rather than to the site.

Each site publishes `provenance.json`, every route it renders against the
repository, path and revision it came from. This reads it for the page's site,
says which repository and file own the page, and asks the forge how far that
revision is behind the repository's `main` and whether the file has changed
since: a page rendered from an old revision may already be fixed.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: The sites that publish their provenance; no other address is fetched.
SITES = ("docs.lemonfiber.app", "contribute.lemonfiber.app", "lemonfiber.app")
#: Where a site publishes it, from its root.
PROVENANCE = "provenance.json"
#: A repository's address on the forge.
REPOSITORY = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)$")
#: A revision, as provenance names it.
REVISION = re.compile(r"^[0-9a-f]{7,40}$")
#: The branch a page is edited on.
BRANCH = "main"

#: Reads the text at a URL.
Fetcher = Callable[[str], str]
#: One GET against the forge's REST API.
Getter = Callable[[str], Any]


@dataclass(frozen=True)
class Source:
    """Where one page comes from."""

    route: str
    repository: str
    path: str
    revision: str


def located(url: str) -> tuple[str, str]:
    """A page's site and its route as provenance keys it, or why not."""
    parts = urllib.parse.urlsplit(url if "://" in url else f"https://{url}")
    if parts.scheme != "https" or parts.hostname not in SITES:
        raise ValueError(f"{url} is not a page on {', '.join(SITES)}")
    route = parts.path or "/"
    return parts.hostname, route if route.endswith("/") else f"{route}/"


def source(table: Any, route: str) -> Source:
    """The page's entry in its site's provenance, or why not."""
    entry = table.get(route) if isinstance(table, dict) else None
    if not isinstance(entry, dict):
        raise LookupError(f"{route} is not a page the site's {PROVENANCE} names")
    found = Source(route, *(str(entry.get(key, "")) for key in ("repository", "path", "revision")))
    if not REPOSITORY.match(found.repository) or not REVISION.match(found.revision) or not found.path:
        raise LookupError(f"{route} has an entry in {PROVENANCE} this does not read: {entry}")
    return found


def drift(page: Source, get: Getter) -> str:
    """How far the page's revision is behind `main`, and whether its file moved."""
    owner, repo = REPOSITORY.match(page.repository).groups()
    compared = get(f"repos/{owner}/{repo}/compare/{page.revision}...{BRANCH}")
    behind = int(compared.get("ahead_by", 0))
    if behind == 0:
        return f"current with {BRANCH}"
    files = [entry.get("filename") for entry in compared.get("files", [])]
    moved = "has changed since" if page.path in files else "is unchanged since"
    return f"{behind} commits behind {BRANCH}; the file {moved}"


def view(page: Source, site: str, said: str) -> str:
    """What `lfdev doc` prints."""
    return "\n".join(
        [
            f"https://{site}{page.route}",
            f"  repository  {page.repository}",
            f"  path        {page.path}",
            f"  revision    {page.revision[:7]}, {said}",
            f"  edit        {page.repository}/edit/{BRANCH}/{page.path}",
        ]
    )


def doc(url: str, fetch: Fetcher, get: Getter) -> tuple[int, str]:
    """Where one page comes from; the exit code and what to say."""
    try:
        site, route = located(url)
        table = json.loads(fetch(f"https://{site}/{PROVENANCE}"))
        page = source(table, route)
    except ValueError as refused:  # a JSONDecodeError is a ValueError
        return 2, str(refused)
    except LookupError as missing:
        return 1, str(missing)
    except urllib.error.URLError as broken:
        return 2, f"could not read {site}'s {PROVENANCE}: {broken}"
    try:
        said = drift(page, get)
    except urllib.error.URLError as broken:
        said = f"not compared with {BRANCH}: {broken}"
    return 0, view(page, site, said)
