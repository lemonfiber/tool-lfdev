"""`lfdev status`: write the row, have spec check it, commit it, or take it back."""

from __future__ import annotations

import pathlib
import tempfile
import tomllib
import unittest

from lfdev import spec_scripts, status

ROW = status.Asked("A1-R1", "done", ["src/a.rs"], None, None)


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        (base / "spec" / "10-functional").mkdir(parents=True)
        self.root = base / "repo"
        self.root.mkdir()
        self.ran = []
        self.where = []
        self.answers = {
            "rev-parse --show-toplevel": (0, str(self.root)),
            "rev-parse --abbrev-ref HEAD": (0, "feat/x"),
        }

    def ask(self, args):
        return self.answers.get(" ".join(args[1:]), (1, ""))

    def runner(self, check=0, add=0, commit=0):
        def run(args, cwd=None):
            self.ran.append(args)
            self.where.append(cwd)
            if args[1] == str(spec_scripts.VENDORED / "status_check.py"):
                return check
            return add if "add" in args else commit

        return run

    def tracker(self):
        return tomllib.loads((self.root / "status.toml").read_text("utf-8"))["requirement"]


class Record(Repo):
    def test_writes_checks_and_commits(self):
        code, said = status.record(ROW, self.ask, self.runner())
        self.assertEqual(code, 0)
        self.assertEqual(said, "A1-R1 is done in status.toml, committed")
        self.assertEqual(self.tracker()[0]["evidence"], ["src/a.rs"])
        check, add, commit = self.ran
        self.assertEqual(check[2:], ["check", "--spec", "spec", "--repo-root", "repo"])
        self.assertEqual(self.where, [self.root.parent.resolve(), self.root, self.root])
        self.assertEqual(add[-1], "status.toml")
        self.assertIn("-S", commit)
        self.assertIn("-s", commit)
        self.assertIn("Spec: A1-R1", commit)

    def test_a_refused_row_is_taken_back(self):
        code, said = status.record(ROW, self.ask, self.runner(check=1))
        self.assertEqual(code, 1)
        self.assertIn("left as it was", said)
        self.assertFalse((self.root / "status.toml").exists(), "a tracker it began is removed")
        (self.root / "status.toml").write_text("requirement = [\n]\n", "utf-8")
        status.record(ROW, self.ask, self.runner(check=1))
        self.assertEqual((self.root / "status.toml").read_text("utf-8"), "requirement = [\n]\n")

    def test_git_not_committing_is_said(self):
        for kind in ({"add": 1}, {"commit": 1}):
            with self.subTest(kind=kind):
                code, said = status.record(ROW, self.ask, self.runner(**kind))
                self.assertEqual(code, 1)
                self.assertIn("git did not commit it", said)

    def test_refused_before_anything_is_written(self):
        cases = {
            "outside a repository": (
                {"rev-parse --show-toplevel": (128, "")},
                ROW,
                "not inside a git repository",
            ),
            "on main": ({"rev-parse --abbrev-ref HEAD": (0, "main")}, ROW, "make a branch"),
            "done without evidence": (
                {},
                status.Asked("A1-R1", "done", [], None, None),
                "names its evidence",
            ),
            "no spec": ({}, status.Asked("A1-R1", "open", [], None, "/nowhere"), "no checkout of spec"),
        }
        for why, (answers, asked, said) in cases.items():
            with self.subTest(why):
                self.answers.update(answers)
                code, told = status.record(asked, self.ask, self.runner())
                self.assertEqual(code, 2)
                self.assertIn(said, told)
                self.assertEqual(self.ran, [])
                self.setUp()

    def test_a_tracker_that_does_not_parse_after_the_edit(self):
        (self.root / "status.toml").write_text('requirement = [\n  { id = "A1-R2", state =\n]\n', "utf-8")
        code, _ = status.record(ROW, self.ask, self.runner())
        self.assertEqual(code, 2)
        self.assertEqual(self.ran, [])


if __name__ == "__main__":
    unittest.main()
