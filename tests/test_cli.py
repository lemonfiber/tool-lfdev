"""The command line: its version, and its help when asked for nothing."""

from __future__ import annotations

import contextlib
import io
import runpy
import unittest
from unittest import mock

from lfdev import __version__, cli


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


if __name__ == "__main__":
    unittest.main()
