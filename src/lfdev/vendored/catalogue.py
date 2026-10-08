#!/usr/bin/env python3
"""Where the feature catalogue lives, and how to read it — read once.

Three scripts had each written down where feature docs are and what shape their
frontmatter must hold: the board generator globbed for them, the frontmatter
check globbed for them again and re-read the schema beside it, and anything else
wanting a feature's `maturity` would have made a third copy.

That is the `patterns.py` lesson applied to the catalogue rather than to prose.
A gate and a generator disagreeing about which files *are* the catalogue is how
one comes to pass on a set the other refuses — and the failure is silent in the
direction that matters, because a reader finding nothing reports nothing wrong.

So the glob and the schema have one home, and `features()` is the only answer to
"what does the catalogue hold".
"""
from __future__ import annotations

import glob
import json
import pathlib

import metafm

#: Every feature doc, by the layout `check_order.py` and the board both assume:
#: one directory per area, one file per feature.
FEATURE_DOCS = "10-functional/features/[a-n]-*/*.md"

#: The controlled frontmatter's schema — the source of every enum below.
SCHEMA_PATH = "10-functional/features/_meta/feature.schema.json"


def schema() -> dict:
    """The frontmatter schema, read on call rather than at import.

    At import it would bind to whatever directory the interpreter started in,
    which is the wrong answer for anything that changes working directory — a
    test suite, most obviously, but also any caller reaching this from a
    checkout it did not start in.
    """
    return json.loads(pathlib.Path(SCHEMA_PATH).read_text(encoding="utf-8"))


def enum(name: str) -> set[str]:
    """The allowed values of one frontmatter key, from the schema itself."""
    return set(schema()["properties"][name]["enum"])


def id_pattern() -> str:
    """The regex a feature id must match, as the schema states it."""
    return schema()["properties"]["id"]["pattern"]


def features() -> dict[str, dict]:
    """Every feature the catalogue holds, keyed by id.

    A doc with no frontmatter, or none carrying an `id`, is not a feature — it is
    a README or a meta page sitting in the same tree, and `check_frontmatter.py`
    is what complains about a real one that lost its block.
    """
    found: dict[str, dict] = {}
    for path in sorted(glob.glob(FEATURE_DOCS)):
        front = metafm.load(path)
        if front and "id" in front:
            front["path"] = path
            found[front["id"]] = front
    return found
