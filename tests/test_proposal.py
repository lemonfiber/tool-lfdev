"""`lfdev propose` and `lfdev gap`: a proposal in the RFC process's shape,
refused before anything is written when it is not, and opened as a pull
request when it is."""

from __future__ import annotations

import pathlib
import tempfile
import unittest
import urllib.error

from lfdev import proposal
from tests.fixture import board


def the_board():
    data = board()
    data["areas"] = [{"id": "A"}, {"id": "B"}]
    return data


def asked(**given):
    fields = {
        "kind": "proposal",
        "area": "B",
        "title": "Scheduled scans",
        "problem": "Libraries go stale.",
        "statements": ["The tool MUST scan nightly.", "It SHOULD say when."],
        "rationale": "# Not a heading\nBecause.",
    }
    fields.update(given)
    return proposal.Asked(**fields)


class Shape(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / "50-governance").mkdir()
        (self.root / "50-governance" / "rules.md").write_text("# Rules\n", "utf-8")

    def test_a_proposal_in_shape_has_no_faults_and_reads_as_the_template(self):
        self.assertEqual(proposal.faults(asked(amends="B1"), the_board(), self.root), [])
        self.assertEqual(proposal.faults(asked(amends="50-governance/rules.md"), the_board(), self.root), [])
        text = proposal.text(asked(amends="B1"))
        self.assertTrue(
            text.startswith(
                "---\nkind: proposal\narea: B\ntitle: Scheduled scans\namends: B1\nstatus: draft\n---\n"
            )
        )
        self.assertIn("## Proposed behaviour\n\n- The tool MUST scan nightly.\n- It SHOULD say when.\n", text)
        self.assertIn("## Rationale\n\n\\# Not a heading\nBecause.", text)

    def test_empty_prose_says_so(self):
        text = proposal.text(asked(problem="", rationale=""))
        self.assertIn("## Problem\n\n(none given)", text)
        self.assertNotIn("amends:", text)

    def test_a_gap(self):
        gap = proposal.Asked("gap", "B", "Silence on scans", "B1", missing="When scans run.")
        self.assertEqual(proposal.faults(gap, the_board(), self.root), [])
        self.assertIn("## What the specification does not say\n\nWhen scans run.\n", proposal.text(gap))

    def test_faults(self):
        cases = {
            "an unknown area": (asked(area="Z"), "area 'Z' is not one"),
            "a title on two lines": (asked(title="a\nb"), "the title is one line"),
            "a title of punctuation": (asked(title="!!!"), "the title is one line"),
            "an unknown feature": (asked(amends="Z9"), "amends 'Z9'"),
            "a page outside": (asked(amends="../outside.md"), "amends '../outside.md'"),
            "no statement": (asked(statements=[]), "at least one"),
            "a statement without a keyword": (asked(statements=["It scans."]), "MUST, SHOULD or MAY"),
            "a gap naming nothing": (proposal.Asked("gap", "B", "Silence", missing="x"), "a gap names"),
            "a gap saying nothing": (proposal.Asked("gap", "B", "Silence", "B1"), "a gap names"),
            "a requirement row": (asked(problem="| **B1-R9** | x |"), "carries a requirement row"),
        }
        for why, (given, said) in cases.items():
            with self.subTest(why):
                self.assertIn(said, "; ".join(proposal.faults(given, the_board(), self.root)))


class Propose(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / proposal.PROPOSALS).mkdir(parents=True)
        self.ran = []
        self.posted = []
        self.answers = {
            "rev-parse --show-toplevel": (0, str(self.root)),
            "remote get-url origin": (0, "git@github.com:lemonfiber/spec.git"),
        }

    def ask(self, args):
        return self.answers.get(" ".join(args[1:]), (1, ""))

    def runner(self, failing=None):
        def run(args, cwd=None):
            self.ran.append(args)
            return 1 if failing and args[1] == failing else 0

        return run

    def poster(self, fails=False):
        def post(path, body):
            self.posted.append((path, body))
            if fails:
                raise urllib.error.URLError("refused")
            return {"html_url": "https://github.com/lemonfiber/spec/pull/99"}

        return post

    def propose(self, given=None, failing=None, fails=False):
        return proposal.propose(
            given or asked(), the_board(), self.ask, self.runner(failing), self.poster(fails)
        )

    def test_writes_commits_pushes_and_opens_it(self):
        self.assertEqual(self.propose(), (0, "opened https://github.com/lemonfiber/spec/pull/99"))
        written = self.root / proposal.PROPOSALS / "scheduled-scans.md"
        self.assertIn("kind: proposal", written.read_text("utf-8"))
        _, switch, add, commit, push = self.ran
        self.assertEqual(switch[2:], ["-c", "proposal/scheduled-scans", "origin/main"])
        self.assertEqual(add[-1], "10-functional/proposals/scheduled-scans.md")
        for part in ("-S", "-s", "docs(proposal): Scheduled scans", "Spec: GOV-R40"):
            self.assertIn(part, commit)
        self.assertEqual(push[-1], "proposal/scheduled-scans")
        ((path, body),) = self.posted
        self.assertEqual(path, "repos/lemonfiber/spec/pulls")
        self.assertEqual(
            (body["title"], body["head"]), ("Proposal: Scheduled scans", "proposal/scheduled-scans")
        )
        self.assertTrue(body["maintainer_can_modify"])
        self.assertIn("Spec: GOV-R40", body["body"])

    def test_from_a_fork_the_head_names_its_owner(self):
        self.answers["remote get-url origin"] = (0, "https://github.com/ana/spec.git")
        gap = proposal.Asked("gap", "B", "Silence on scans", "B1", missing="When scans run.")
        self.propose(gap)
        ((_, body),) = self.posted
        self.assertEqual(
            (body["head"], body["title"]), ("ana:proposal/silence-on-scans", "Gap: Silence on scans")
        )

    def test_a_step_that_fails_is_said(self):
        cases = {
            "fetch": "nothing is written",
            "switch": "nothing is written",
            "add": "did not succeed",
            "commit": "did not succeed",
            "push": "did not succeed",
        }
        for step, said in cases.items():
            with self.subTest(step):
                self.setUp()
                code, told = self.propose(failing=step)
                self.assertEqual(code, 1)
                self.assertIn(said, told)
                self.assertEqual(self.posted, [])

    def test_a_pull_request_the_forge_refused_is_said(self):
        code, said = self.propose(fails=True)
        self.assertEqual(code, 1)
        self.assertIn("proposal/scheduled-scans is pushed, and the pull request was not opened", said)

    def test_refused_before_anything_runs(self):
        (self.root / proposal.PROPOSALS / "taken.md").write_text("x", "utf-8")
        cases = {
            "outside a repository": (
                {"rev-parse --show-toplevel": (128, "")},
                asked(),
                "not inside a git repository",
            ),
            "no origin": ({"remote get-url origin": (2, "")}, asked(), "origin is not a repository"),
            "out of shape": ({}, asked(area="Z"), "area 'Z'"),
            "a file that exists": ({}, asked(title="Taken"), "already exists"),
        }
        for why, (answers, given, said) in cases.items():
            with self.subTest(why):
                self.ran.clear()
                self.answers.update(answers)
                code, told = self.propose(given)
                self.assertEqual(code, 2)
                self.assertIn(said, told)
                self.assertEqual((self.ran, self.posted), ([], []))
                self.answers.update(
                    {
                        "rev-parse --show-toplevel": (0, str(self.root)),
                        "remote get-url origin": (0, "git@github.com:lemonfiber/spec.git"),
                    }
                )

    def test_not_a_checkout_of_spec(self):
        self.answers["rev-parse --show-toplevel"] = (0, str(self.root / "elsewhere"))
        self.assertEqual(self.propose()[0], 2)
        self.assertIn("checkout of spec", self.propose()[1])


if __name__ == "__main__":
    unittest.main()
