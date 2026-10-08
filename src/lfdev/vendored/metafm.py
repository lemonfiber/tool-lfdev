#!/usr/bin/env python3
"""Minimal parser for the controlled frontmatter on feature docs.

Handles the only shapes the feature frontmatter uses — a leading ``---`` block of
flat ``key: value`` pairs, with bare / single-quoted / double-quoted scalars and
``[a, b]`` flow lists. Deliberately not a general YAML parser, so the scripts
carry no third-party dependency.
"""
import pathlib


def _scalar(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def parse(text: str):
    """Return the frontmatter as a dict, or None if there is no block."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    data = {}
    for line in text[4:end].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            data[key] = [_scalar(x) for x in inner.split(",")] if inner else []
        else:
            data[key] = _scalar(raw)
    return data


def load(path) -> dict:
    return parse(pathlib.Path(path).read_text(encoding="utf-8"))
