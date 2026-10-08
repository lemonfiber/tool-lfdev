"""The command line: its version, and its help when asked for nothing."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import runpy
import tempfile
import unittest
from unittest import mock

from lfdev import __version__, checks, cli, doctor, forge, snapshot
from tests.fixture import board


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            code = cli.main(argv)
        except SystemExit as stopped:
            code = int(stopped.code or 0)
    return code, out.getvalue()


class CommandLine(unittest.TestCase):
    def test_it_names_its_version(self):
        self.assertEqual(run(["--version"]), (0, f"lfdev {__version__}\n"))

    def test_asked_for_nothing_it_prints_its_help(self):
        code, said = run([])
        self.assertEqual(code, 0)
        self.assertIn("usage: lfdev", said)

    def test_python_dash_m_runs_the_same_command(self):
        out = io.StringIO()
        with (
            mock.patch("sys.argv", ["lfdev"]),
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit) as ran,
        ):
            runpy.run_module("lfdev", run_name="__main__")
        self.assertEqual(ran.exception.code, 0)
        self.assertIn("usage: lfdev", out.getvalue())


class Commands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(self.tmp.name, "board.json")
        path.write_text(json.dumps(board()), "utf-8")
        patch = mock.patch.dict(os.environ, {snapshot.SOURCE_VARIABLE: str(path)})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_board_by_maturity_filtered(self):
        code, said = run(["board", "--area", "B"])
        self.assertEqual(code, 0)
        self.assertIn("read at 2026-10-08T00:00:00Z · spec at aaaaaaa", said)
        self.assertIn("1 of 2 features", said)
        self.assertIn("building (1)\n  B1     Forms  [area B, 4 open, 1 claimed]", said)
        self.assertIn("shipped (0)", said)

    def test_board_refuses_a_claimed_value_it_does_not_know(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run(["board", "--claimed", "maybe"])[0], 2)

    def test_next_lists_unclaimed_goals_by_version(self):
        code, said = run(["next"])
        self.assertEqual(code, 0)
        self.assertIn("3 goals nobody has claimed", said)
        self.assertIn(
            "0.3.0\n  B1-R1      open      lemonfiber\n             The tool MUST run a form.", said
        )
        self.assertIn("  GOV-R1     unknown   no tracker yet", said)
        self.assertIn("0.4.0\n  B1-R3", said)

    def test_next_filtered(self):
        self.assertIn("1 goals", run(["next", "--repo", "lemonfiber"])[1])

    def test_a_snapshot_that_cannot_be_read(self):
        err = io.StringIO()
        with (
            mock.patch.dict(os.environ, {snapshot.SOURCE_VARIABLE: "/nowhere.json"}),
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(run(["board"])[0], 2)
        self.assertIn("lfdev: the board snapshot at /nowhere.json could not be read", err.getvalue())

    def test_checks_read_and_shown(self):
        found = [{"name": "tests", "status": "completed", "conclusion": "failure"}]
        with (
            mock.patch.object(forge, "token", return_value="t"),
            mock.patch.object(checks, "checks", return_value=(found, None)) as read,
        ):
            code, said = run(["checks", "spec#9"])
        self.assertEqual(code, 1, "a failing check fails the command")
        self.assertIn("lemonfiber/spec#9: failing", said)
        get = read.call_args.args[2]
        with mock.patch.object(forge, "get", return_value={"ok": 1}) as fetched:
            self.assertEqual(get("repos/x"), {"ok": 1})
        fetched.assert_called_once_with("repos/x", "t")

    def test_checks_passing(self):
        found = [{"name": "tests", "status": "completed", "conclusion": "success"}]
        with (
            mock.patch.object(forge, "token", return_value="t"),
            mock.patch.object(checks, "checks", return_value=(found, None)),
        ):
            self.assertEqual(run(["checks", "spec#9"])[0], 0)

    def test_checks_refused(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(run(["checks", "not a target"])[0], 2)
        self.assertIn("lfdev: 'not a target' is not", err.getvalue())

    def test_doctor(self):
        with mock.patch.object(doctor, "run", return_value=(1, "")):
            code, said = run(["doctor"])
        self.assertEqual(code, 1)
        self.assertIn("FIX  hooks on", said)


if __name__ == "__main__":
    unittest.main()
