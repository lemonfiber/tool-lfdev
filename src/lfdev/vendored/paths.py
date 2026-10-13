#!/usr/bin/env python3
"""Where a path handed to a gate on its command line is allowed to point.

Every gate here is run by a workflow with paths a step assembled, and a gate that
will read any file it is pointed at is a way to read any file. So each path from
a command line is resolved and refused if it leaves the working directory, in
one place, so that two gates cannot disagree about what is inside it.

A job that holds a secret reads and writes repository and artifact files through
`plain_read`, `plain_write` and `plain_files`, which never follow a link: a file
somebody else put there could otherwise point the job at its own credentials.
"""

from __future__ import annotations

import errno
import os
import pathlib
import re
import stat


def within_cwd(raw: str) -> pathlib.Path:
    """Resolve a CLI-supplied path, refusing anything outside the working tree."""
    path = pathlib.Path(raw).resolve()
    if not path.is_relative_to(pathlib.Path.cwd().resolve()):
        print(f"::error::path escapes the working directory: {raw}")
        raise SystemExit(2)
    return path


class NotPlain(ValueError):
    """A path that is not a plain file under its root: a link, a hard link, a device, a
    directory where a file was asked for, or a name that leaves the root."""


#: One segment of a path a workflow hands on: a plain name, never `.` or `..`.
_SEGMENT = re.compile(r"\A(?!\.\.?\Z)[A-Za-z0-9_@+.-]{1,255}\Z")


def _segments(relative: str) -> list[str]:
    parts = [] if relative == "." else relative.split("/")
    if not parts:
        raise NotPlain("the working directory itself is not a file")
    if any(not _SEGMENT.match(part) for part in parts):
        raise NotPlain(f"{relative!r} is not a plain relative path")
    return parts


def _directories(root: pathlib.Path, parts: list[str], make: bool) -> pathlib.Path:
    """The directory `parts` lie in under `root`, every step of it a real directory."""
    here = root
    for part in parts:
        here = here / part
        try:
            held = os.lstat(here)
        except FileNotFoundError:
            if not make:
                raise
            os.mkdir(here, 0o755)
            held = os.lstat(here)
        if not stat.S_ISDIR(held.st_mode):
            raise NotPlain(f"{here.relative_to(root)} is not a plain directory")
    return here


def plain_relative(raw: str) -> str:
    """A path from a command line as a plain path under the working directory.

    It must resolve, through `within_cwd`, to exactly the path it names: one that
    leaves the working directory or passes through a link on the way is refused, and
    the plain readers and writers below refuse a link at its last step.
    """
    cwd = pathlib.Path.cwd().resolve()
    resolved = within_cwd(raw).relative_to(cwd).as_posix()
    given = pathlib.Path(raw)
    named = (given.relative_to(cwd) if given.is_absolute() else given).as_posix()
    if os.path.islink(cwd / named):
        raise NotPlain(f"{raw} is a link")
    if os.path.normpath(named) != resolved:
        raise NotPlain(f"{raw} passes through a link")
    if resolved != ".":
        _segments(resolved)
    return resolved


def plain_directory(raw: str, make: bool = False) -> pathlib.Path:
    """A directory from a command line, every step of it under the working directory a
    real directory and none of them a link; made where `make` asks and it is missing."""
    relative = plain_relative(raw)
    cwd = pathlib.Path.cwd().resolve()
    return cwd if relative == "." else _directories(cwd, relative.split("/"), make)


def plain_read(root: pathlib.Path, relative: str, limit: int) -> bytes:
    """A plain file's bytes, at most `limit` of them, never through a link.

    Every directory on the way is checked with `lstat`, and the file is opened with
    `O_NOFOLLOW` and refused unless it is a regular file with one link, so nothing
    a repository or an artifact holds can point this at a file outside it.
    """
    parts = _segments(relative)
    where = _directories(root, parts[:-1], make=False) / parts[-1]
    try:
        handle = os.open(where, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as why:
        if why.errno == errno.ELOOP:
            raise NotPlain(f"{relative} is a link") from None
        raise
    held = os.fstat(handle)
    if not stat.S_ISREG(held.st_mode) or held.st_nlink != 1:
        os.close(handle)
        raise NotPlain(f"{relative} is not a plain file")
    with os.fdopen(handle, "rb") as opened:
        body = opened.read(limit + 1)
    if len(body) > limit:
        raise NotPlain(f"{relative} is larger than {limit} bytes")
    return body


def plain_write(root: pathlib.Path, relative: str, body: bytes) -> None:
    """Write a plain file, replacing a plain file there and refusing anything else."""
    parts = _segments(relative)
    where = _directories(root, parts[:-1], make=True) / parts[-1]
    try:
        held = os.lstat(where)
    except FileNotFoundError:
        held = None
    if held is not None:
        if not stat.S_ISREG(held.st_mode) or held.st_nlink != 1:
            raise NotPlain(f"{relative} is not a plain file to replace")
        os.unlink(where)
    handle = os.open(where, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(handle, "wb") as written:
        written.write(body)


def plain_files(root: pathlib.Path) -> tuple[list[str], list[str]]:
    """Every plain file under `root`, and every entry that is anything else, as paths
    relative to it; nothing is followed, and a directory that is a link is not entered."""
    plain, other = [], []
    for here, directories, files in os.walk(root, followlinks=False):
        base = pathlib.Path(here)
        for name in sorted(files) + [one for one in directories if os.path.islink(base / one)]:
            held = os.lstat(base / name)
            relative = (base / name).relative_to(root).as_posix()
            if stat.S_ISREG(held.st_mode) and held.st_nlink == 1:
                plain.append(relative)
            else:
                other.append(relative)
    return sorted(plain), sorted(other)
