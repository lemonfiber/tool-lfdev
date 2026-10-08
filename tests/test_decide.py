"""`lfdev decide`: a row under today's date in spec's decision log, committed."""

from __future__ import annotations

import datetime
import pathlib
import tempfile
import unittest

from lfdev import decide

TODAY = datetime.date(2026, 10, 8)
HEAD = "| Decision | Where it lives |\n|---|---|\n"
LOG = (
    "# Decision log\n\n## How a decision is recorded\n\nProse.\n\n"
    f"## 2026-09-29\n\n{HEAD}| Old | [A1](a1.md) |\n\n"
    f"## 2026-10-07\n\n{HEAD}| Newer | [A2](a2.md) |\n\n"
    "## Requirements\n\n| ID | Requirement |\n|----|-------------|\n| **GOV-R49** | Text |\n"
)


class WithRow(unittest.TestCase):
    def test_a_new_day_goes_after_the_last_earlier_one(self):
        after = decide.with_row(LOG, TODAY, "| New | x |")
        self.assertIn(
            f"| Newer | [A2](a2.md) |\n\n## 2026-10-08\n\n{HEAD}| New | x |\n\n## Requirements", after
        )

    def test_a_day_between_two_goes_between_them(self):
        after = decide.with_row(LOG, datetime.date(2026, 10, 1), "| Mid | x |")
        self.assertIn(f"| Old | [A1](a1.md) |\n\n## 2026-10-01\n\n{HEAD}| Mid | x |\n\n## 2026-10-07", after)

    def test_a_day_before_every_other_goes_first(self):
        after = decide.with_row(LOG, datetime.date(2026, 1, 1), "| First | x |")
        self.assertIn(f"Prose.\n\n## 2026-01-01\n\n{HEAD}| First | x |\n\n## 2026-09-29", after)

    def test_an_existing_day_gains_a_row_under_its_last(self):
        after = decide.with_row(LOG, datetime.date(2026, 10, 7), "| Also | x |")
        self.assertIn("| Newer | [A2](a2.md) |\n| Also | x |\n\n## Requirements", after)
        self.assertEqual(after.count("## 2026-10-07"), 1)

    def test_a_day_with_no_table_gains_one(self):
        log = "## 2026-10-08\n\n## Requirements\n"
        after = decide.with_row(log, TODAY, "| Row | x |")
        self.assertEqual(after, f"## 2026-10-08\n\n{HEAD}| Row | x |\n\n## Requirements\n")

    def test_the_last_day_of_the_file(self):
        log = f"## 2026-10-08\n\n{HEAD}| A | x |"
        self.assertEqual(decide.with_row(log, TODAY, "| B | x |"), f"{log}\n| B | x |")

    def test_a_log_with_no_dated_heading_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no dated heading"):
            decide.with_row("# Decision log\n", TODAY, "| A | x |")


class Cell(unittest.TestCase):
    def test_pipes_are_escaped_and_ends_trimmed(self):
        self.assertEqual(decide.cell("  a | b "), r"a \| b")

    def test_empty_or_several_lines_are_refused(self):
        for text in ("", "  ", "one\ntwo"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "one line"):
                decide.cell(text)


class Record(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.log = self.root / decide.LOG
        self.log.parent.mkdir(parents=True)
        self.log.write_text(LOG, "utf-8")
        self.ran = []
        self.answers = {
            "rev-parse --show-toplevel": (0, str(self.root)),
            "rev-parse --abbrev-ref HEAD": (0, "docs/decision"),
        }

    def ask(self, args):
        return self.answers.get(" ".join(args[1:]), (1, ""))

    def runner(self, add=0, commit=0):
        def run(args, cwd=None):
            self.ran.append((args, cwd))
            return add if "add" in args else commit

        return run

    def record(self, decision="Do it", where="[A1](a1.md)", **kind):
        return decide.record(decision, where, self.ask, self.runner(**kind), TODAY)

    def test_writes_and_commits(self):
        code, said = self.record()
        self.assertEqual(
            (code, said), (0, "recorded under 2026-10-08 in 50-governance/decision-log.md, committed")
        )
        self.assertIn("## 2026-10-08\n\n" + HEAD + "| Do it | [A1](a1.md) |\n", self.log.read_text("utf-8"))
        (add, add_cwd), (commit, commit_cwd) = self.ran
        self.assertEqual(add[-1], "50-governance/decision-log.md")
        self.assertEqual((add_cwd, commit_cwd), (self.root, self.root))
        for flag in ("-S", "-s", "docs(decisions): a decision of 2026-10-08", "Spec: GOV-R49"):
            self.assertIn(flag, commit)

    def test_git_not_committing_is_said(self):
        for kind in ({"add": 1}, {"commit": 1}):
            with self.subTest(kind=kind):
                code, said = self.record(**kind)
                self.assertEqual(code, 1)
                self.assertIn("git did not commit it", said)

    def test_refused_before_anything_is_written(self):
        cases = {
            "outside a repository": (
                {"rev-parse --show-toplevel": (128, "")},
                {},
                "not inside a git repository",
            ),
            "not spec": (
                {"rev-parse --show-toplevel": (0, str(self.root / "elsewhere"))},
                {},
                "checkout of spec",
            ),
            "on main": ({"rev-parse --abbrev-ref HEAD": (0, "main")}, {}, "make a branch"),
            "two lines": ({}, {"decision": "a\nb"}, "one line"),
        }
        for why, (answers, given, said) in cases.items():
            with self.subTest(why):
                self.answers.update(answers)
                code, told = self.record(**given)
                self.assertEqual(code, 2)
                self.assertIn(said, told)
                self.assertEqual(self.ran, [])
                self.assertEqual(self.log.read_text("utf-8"), LOG)
                self.setUp()


if __name__ == "__main__":
    unittest.main()
