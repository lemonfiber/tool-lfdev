"""The forge, read through its REST API with the person's own credentials
(REPO-R75, REPO-R77).

The token is `GH_TOKEN` or `GITHUB_TOKEN` where one is set, and otherwise what
`gh auth token` prints, so the tool acts as whoever is signed in to `gh`.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from collections.abc import Mapping
from typing import Any

#: The REST API's root.
API = "https://api.github.com"
#: How long a request may take before it is given up, in seconds.
TIMEOUT = 30


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


def get(path: str, auth: str) -> Any:
    """One GET against the REST API, as JSON."""
    request = urllib.request.Request(
        f"{API}/{path.lstrip('/')}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {auth}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return json.load(answer)
