"""The forge, read through its REST API with the person's own credentials
(REPO-R75, REPO-R77).

The token is `GH_TOKEN` or `GITHUB_TOKEN` where one is set, and otherwise what
`gh auth token` prints, so the tool acts as whoever is signed in to `gh`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from lfdev import __version__

#: The organisation every repository the tool works on belongs to.
ORG = "lemonfiber"
#: How the tool names itself to every address it reads. A site behind a CDN
#: refuses the default `Python-urllib` name.
USER_AGENT = f"lfdev/{__version__}"
#: A repository's address on the forge, as `git remote get-url` gives it.
REMOTE = re.compile(r"github\.com[:/](?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?$")
#: One POST to the forge: its path and body, then the JSON it answers with.
Poster = Callable[[str, Mapping[str, Any]], Any]
#: The REST API's root.
API = "https://api.github.com"
#: How long a request may take before it is given up, in seconds.
TIMEOUT = 30


def ending(ask: Callable[[Sequence[str]], tuple[int, str]], root: pathlib.Path, cites: str) -> str:
    """The lines a pull request's body ends with.

    A squash merge writes the title and body to `main` as the commit, so the body
    carries the citation and the sign-off that commit needs (GOV-R62). The
    sign-off names the identity `git commit -s` signs with, which is git's
    committer identity in that clone.
    """
    code, said = ask(["git", "-C", str(root), "var", "GIT_COMMITTER_IDENT"])
    who = said.rsplit(" ", 2)[0] if code == 0 and said.count(" ") >= 2 else ""
    return f"Spec: {cites}" + (f"\n\nSigned-off-by: {who}" if who else "")


class Unauthenticated(Exception):
    """No token: nothing in the environment, and `gh` signed in to nothing."""


def token(environ: Mapping[str, str] = os.environ) -> str:
    """The person's token."""
    found = environ.get("GH_TOKEN") or environ.get("GITHUB_TOKEN")
    if found:
        return found
    try:
        done = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        done = None
    if done is None or done.returncode != 0 or not done.stdout.strip():
        raise Unauthenticated("no token: set GH_TOKEN, or sign in with `gh auth login`")
    return done.stdout.strip()


def _request(path: str, auth: str, body: Mapping[str, Any] | None = None) -> Any:
    request = urllib.request.Request(
        f"{API}/{path.lstrip('/')}",
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {auth}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return json.load(answer)


def get(path: str, auth: str) -> Any:
    """One GET against the REST API, as JSON."""
    return _request(path, auth)


def post(path: str, auth: str, body: Mapping[str, Any]) -> Any:
    """One POST against the REST API, with a JSON body, as JSON."""
    return _request(path, auth, body)
