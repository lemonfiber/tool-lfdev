"""`lfdev goals`: rewrite a manifest's goals, commit, push, open the pull request."""

from __future__ import annotations

import pathlib
import tempfile
import tomllib
import unittest
import urllib.error

from lfdev import goals

MANIFEST = (
    "# Why this version.\n"
    'version = "0.18.0"\n'
    'status  = "{status}"\n'
    'repos   = ["lemonfiber"]\n'
    "goals   = [\n"
    '    "A1-R1",\n'
    '    "A1-R2",\n'
    "]\n"
    "\n"
    "# After the goals.\n"
)


def asked(add=(), remove=(), version="0.18.0"):
    return goals.Asked(version, list(add), list(remove))


class Changed(unittest.TestCase):
    def test_adds_at_the_end_and_removes_in_place(self):
        self.assertEqual(
            goals.changed(["A1-R1", "A1-R2"], asked(["B2-R1", "B2-R1"], ["A1-R1"])),
            ["A1-R2", "B2-R1"],
        )

    def test_refusals(self):
        cases = {
            "nothing asked": (asked(), "name a goal"),
            "not an identifier": (asked(["A1"]), "is not a requirement identifier"),
            "already there": (asked(["A1-R1"]), "already promises A1-R1"),
            "not there": (asked(remove=["B2-R1"]), "does not promise B2-R1"),
        }
        for why, (given, said) in cases.items():
            with self.subTest(why), self.assertRaisesRegex(ValueError, said):
                goals.changed(["A1-R1"], given)


class WithGoals(unittest.TestCase):
    def test_a_multi_line_list_is_rewritten_in_place(self):
        text = MANIFEST.format(status="planned")
        after = goals.with_goals(text, ["A1-R2", "B2-R1"])
        self.assertIn('goals   = [\n    "A1-R2",\n    "B2-R1",\n]\n\n# After the goals.\n', after)
        self.assertTrue(after.startswith("# Why this version.\n"))

    def test_an_inline_list_keeps_its_comment(self):
        after = goals.with_goals('goals = ["A1-R1"]   # locked\nx = 1\n', ["A1-R1", "B2-R1"])
        self.assertEqual(after, 'goals = [\n    "A1-R1",\n    "B2-R1",\n]   # locked\nx = 1\n')

    def test_no_goals_and_an_unclosed_list_are_refused(self):
        for text, said in (
            ('version = "1"\n', "no goals list"),
            ('goals = [\n  "A1-R1",\n', "does not close"),
        ):
            with self.subTest(said=said), self.assertRaisesRegex(ValueError, said):
                goals.with_goals(text, [])


class Edited(unittest.TestCase):
    def test_locked_past_planned(self):
        for status, locked in (("planned", False), ("staged", True), ("released", True)):
            with self.subTest(status=status):
                after, frozen = goals.edited(MANIFEST.format(status=status), asked(["B2-R1"]))
                self.assertEqual(frozen, locked)
                self.assertEqual(tomllib.loads(after)["goals"], ["A1-R1", "A1-R2", "B2-R1"])

    def test_a_rewrite_that_moves_anything_else_is_refused(self):
        # The list closes on its last goal's line, so the first `]` at the start
        # of a line is the next list's, which the rewrite would take with it.
        text = 'goals = [\n  "A1-R1"]\nother = [\n]\n'
        with self.assertRaisesRegex(ValueError, "more than the goals"):
            goals.edited(text, asked(["B2-R1"]))


class Describe(unittest.TestCase):
    def test_names_each_change_and_the_label(self):
        body = goals.describe(asked(["B2-R1"], ["A1-R1"]), locked=True)
        self.assertIn("- adds `B2-R1`\n- removes `A1-R1`", body)
        self.assertIn("carries `goals-change`", body)
        self.assertNotIn("goals-change", goals.describe(asked(["B2-R1"]), locked=False))


class Propose(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.manifest = self.root / goals.VERSIONS / "0.18.0.toml"
        self.manifest.parent.mkdir(parents=True)
        self.status("staged")
        self.ran = []
        self.posted = []
        self.answers = {
            "rev-parse --show-toplevel": (0, str(self.root)),
            "rev-parse --abbrev-ref HEAD": (0, "goals/0.18.0"),
        }

    def status(self, status):
        self.manifest.write_text(MANIFEST.format(status=status), "utf-8")

    def ask(self, args):
        return self.answers.get(" ".join(args[1:]), (1, ""))

    def runner(self, add=0, commit=0, push=0):
        def run(args, cwd=None):
            self.ran.append(args)
            return {"add": add, "commit": commit, "push": push}[args[1]]

        return run

    def poster(self, fails=()):
        def post(path, body):
            self.posted.append((path, body))
            if path.rsplit("/", 1)[-1] in fails:
                raise urllib.error.URLError("refused")
            return {"number": 12, "html_url": "https://github.com/lemonfiber/spec/pull/12"}

        return post

    def propose(self, given=None, fails=(), **kind):
        return goals.propose(given or asked(["B2-R1"]), self.ask, self.runner(**kind), self.poster(fails))

    def test_a_locked_version_opens_a_labelled_pull_request(self):
        code, said = self.propose()
        self.assertEqual(
            (code, said), (0, "opened https://github.com/lemonfiber/spec/pull/12, labelled goals-change")
        )
        add, commit, push = self.ran
        self.assertEqual(add[-1], "70-operations/versions/0.18.0.toml")
        for part in ("-S", "-s", "chore(goals): what 0.18.0 promises", "Spec: OPS-R30, OPS-R31"):
            self.assertIn(part, commit)
        self.assertEqual(push[1:], ["push", "--set-upstream", "origin", "goals/0.18.0"])
        (pulls, body), (labels, label) = self.posted
        self.assertEqual(pulls, "repos/lemonfiber/spec/pulls")
        self.assertEqual((body["head"], body["base"]), ("goals/0.18.0", "main"))
        self.assertEqual(
            (labels, label), ("repos/lemonfiber/spec/issues/12/labels", {"labels": ["goals-change"]})
        )
        self.assertIn('"B2-R1"', self.manifest.read_text("utf-8"))

    def test_a_planned_version_is_not_labelled(self):
        self.status("planned")
        self.assertEqual(self.propose(), (0, "opened https://github.com/lemonfiber/spec/pull/12"))
        self.assertEqual(len(self.posted), 1)

    def test_what_did_not_happen_is_said(self):
        cases = {
            "add": ({"add": 1}, (), "git did not commit it"),
            "commit": ({"commit": 1}, (), "git did not commit it"),
            "push": ({"push": 1}, (), "git did not push it"),
            "pull": ({}, ("pulls",), "the pull request was not opened"),
            "label": ({}, ("labels",), "it is not labelled goals-change"),
        }
        for why, (kind, fails, said) in cases.items():
            with self.subTest(why):
                code, told = self.propose(fails=fails, **kind)
                self.assertEqual(code, 1)
                self.assertIn(said, told)
                self.setUp()

    def test_refused_before_anything_is_written(self):
        cases = {
            "not a version": ({}, asked(["B2-R1"], version="../x"), "is not a version"),
            "outside a repository": (
                {"rev-parse --show-toplevel": (128, "")},
                None,
                "not inside a git repository",
            ),
            "no manifest": ({}, asked(["B2-R1"], version="9.9.9"), "run this in a checkout of spec"),
            "on main": ({"rev-parse --abbrev-ref HEAD": (0, "main")}, None, "make a branch"),
            "already promised": ({}, asked(["A1-R1"]), "already promises"),
        }
        for why, (answers, given, said) in cases.items():
            with self.subTest(why):
                self.answers.update(answers)
                code, told = self.propose(given)
                self.assertEqual(code, 2)
                self.assertIn(said, told)
                self.assertEqual((self.ran, self.posted), ([], []))
                self.assertEqual(self.manifest.read_text("utf-8"), MANIFEST.format(status="staged"))
                self.setUp()


if __name__ == "__main__":
    unittest.main()
