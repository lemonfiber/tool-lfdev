"""`lfdev claim`: refuse what the board says is taken or full, then branch,
commit, push and open the draft."""

from __future__ import annotations

import unittest
import urllib.error

from lfdev import claim
from tests.fixture import board


def with_repo(counted, cap=3):
    data = board()
    data["claims"] = {"cap": cap, "stale_days": 14}
    data["repos"] = [{"name": "lemonfiber", "counted_pulls": counted}]
    data["requirements"].append({"id": "B1-R2", "text": "Claimed."})
    return data


class Claimable(unittest.TestCase):
    def test_an_open_requirement_in_a_repository_under_the_cap(self):
        found = claim.claimable(with_repo(1), "B1-R1", "lemonfiber")
        self.assertEqual(
            (found.ident, found.repo, found.text), ("B1-R1", "lemonfiber", "The tool MUST run a form.")
        )

    def test_a_bots_pull_request_claims_nothing(self):
        data = with_repo(1)
        data["pulls"].append({"repo": "lemonfiber", "number": 8, "cites": ["B1-R1"], "bot": True})
        self.assertEqual(claim.claimable(data, "B1-R1", "lemonfiber").ident, "B1-R1")

    def test_a_repository_the_board_did_not_count_is_not_refused(self):
        self.assertEqual(claim.claimable(with_repo(None), "B1-R1", "lemonfiber").ident, "B1-R1")
        self.assertEqual(claim.claimable(board(), "B1-R1", "sdk-ts").repo, "sdk-ts")

    def test_refusals(self):
        data = with_repo(3)
        data["versions"][2]["goals"].append({"id": "A1-R1", "claims": [{"repo": "sdk-ts", "number": 4}]})
        cases = {
            "not an identifier": ("B1", "is not a requirement identifier"),
            "not defined": ("Z9-R9", "defines no requirement Z9-R9"),
            "cited by an open pull request": ("B1-R2", "already claimed by lemonfiber#7"),
            "claimed on a goal": ("A1-R1", "already claimed by sdk-ts#4"),
            "the repository is full": ("B1-R1", "already holds 3 open pull requests"),
        }
        for why, (ident, said) in cases.items():
            with self.subTest(why), self.assertRaisesRegex(ValueError, said):
                claim.claimable(data, ident, "lemonfiber")


class Claim(unittest.TestCase):
    def setUp(self):
        self.ran = []
        self.posted = []
        self.answers = {
            "rev-parse --show-toplevel": (0, "/work/lemonfiber"),
            "remote get-url origin": (0, "git@github.com:lemonfiber/lemonfiber.git"),
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
            return {"html_url": "https://github.com/lemonfiber/lemonfiber/pull/9"}

        return post

    def claim(self, ident="B1-R1", failing=None, fails=False):
        return claim.claim(ident, with_repo(1), self.ask, self.runner(failing), self.poster(fails))

    def test_branches_commits_pushes_and_opens_a_draft(self):
        self.assertEqual(self.claim(), (0, "claimed B1-R1: https://github.com/lemonfiber/lemonfiber/pull/9"))
        _, switch, commit, push = self.ran
        self.assertEqual(switch[2:], ["-c", "claim/b1-r1", "origin/main"])
        for part in ("--allow-empty", "-S", "-s", "chore(claim): B1-R1", "Spec: B1-R1"):
            self.assertIn(part, commit)
        self.assertEqual(push[-1], "claim/b1-r1")
        ((path, body),) = self.posted
        self.assertEqual(path, "repos/lemonfiber/lemonfiber/pulls")
        self.assertTrue(body["draft"])
        self.assertIn("Spec: B1-R1", body["body"])
        self.assertIn("The tool MUST run a form.", body["body"])

    def test_https_remotes_are_read_too(self):
        self.answers["remote get-url origin"] = (0, "https://github.com/lemonfiber/sdk-ts")
        self.assertEqual(claim.this_repository(self.ask), "sdk-ts")

    def test_a_step_that_fails_stops_the_claim(self):
        for step in ("fetch", "switch", "commit", "push"):
            with self.subTest(step):
                self.setUp()
                code, said = self.claim(failing=step)
                self.assertEqual(code, 1)
                self.assertIn("is not claimed", said)
                self.assertEqual(self.posted, [])

    def test_a_draft_the_forge_refused_is_said(self):
        code, said = self.claim(fails=True)
        self.assertEqual(code, 1)
        self.assertIn("claim/b1-r1 is pushed, and the draft pull request was not opened", said)

    def test_refused_before_anything_runs(self):
        cases = {
            "outside a repository": (
                {"rev-parse --show-toplevel": (128, "")},
                "B1-R1",
                "not inside a git repository",
            ),
            "another organisation": (
                {"remote get-url origin": (0, "git@github.com:someone/fork.git")},
                "B1-R1",
                "origin is not a lemonfiber repository",
            ),
            "no origin": (
                {"remote get-url origin": (2, "")},
                "B1-R1",
                "origin is not a lemonfiber repository",
            ),
            "already claimed": ({}, "B1-R2", "already claimed"),
        }
        for why, (answers, ident, said) in cases.items():
            with self.subTest(why):
                self.setUp()
                self.answers.update(answers)
                code, told = self.claim(ident)
                self.assertEqual(code, 2)
                self.assertIn(said, told)
                self.assertEqual((self.ran, self.posted), ([], []))


if __name__ == "__main__":
    unittest.main()
