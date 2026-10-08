"""The committed command table is the parser's, and is rewritten from it."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import runpy
import tempfile
import unittest
from unittest import mock

from lfdev import cli, commands


class Table(unittest.TestCase):
    def test_every_command_with_its_purpose_in_the_parsers_order(self):
        rows = commands.table()
        self.assertEqual(rows[0], {"name": "doctor", "purpose": "check this clone is set up to commit"})
        self.assertIn(
            {"name": "claim", "purpose": "claim a requirement with a draft pull request here"}, rows
        )
        self.assertEqual(len(rows), len({r["name"] for r in rows}))

    def test_the_committed_file_is_the_parsers(self):
        committed = commands.FILE.read_text("utf-8")
        self.assertEqual(
            committed,
            commands.written(commands.table(cli.parser())),
            "run `python -m lfdev.commands` and commit commands.json",
        )
        self.assertEqual(json.loads(committed)["generated_by"], "python -m lfdev.commands")


class Writing(unittest.TestCase):
    def test_main_rewrites_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp, "commands.json")
            with mock.patch.object(commands, "FILE", target), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(commands.main(), 0)
            self.assertEqual(json.loads(target.read_text("utf-8"))["commands"], commands.table())

    def test_python_dash_m_runs_it(self):
        with (
            mock.patch.object(pathlib.Path, "write_text") as wrote,
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as ran,
        ):
            runpy.run_module("lfdev.commands", run_name="__main__")
        self.assertEqual(ran.exception.code, 0)
        wrote.assert_called_once()


if __name__ == "__main__":
    unittest.main()
