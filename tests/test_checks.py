"""`lfdev checks`: what it reads, and the ten minutes it waits between reads."""

from __future__ import annotations

import datetime
import json
import pathlib
import tempfile
import unittest

from lfdev import checks

T0 = datetime.datetime(2026, 10, 8, 12, 0, tzinfo=datetime.UTC)
RUNS = {
    "check_runs": [
        {"name": "tests", "status": "completed", "conclusion": "success"},
        {"name": "hygiene / lines", "status": "in_progress", "conclusion": None},
    ]
}


class Forge:
    """Answers as the REST API would, counting what it was asked."""

    def __init__(self, runs=RUNS):
        self.asked = []
        self.runs = runs

    def __call__(self, path):
        self.asked.append(path)
        if path.endswith("check-runs?per_page=100"):
            return self.runs
        return {"head": {"sha": "abc"}}


class Target(unittest.TestCase):
    def test_a_repository_in_the_org_or_named_with_its_owner(self):
        self.assertEqual(checks.parse_target("spec#695"), ("lemonfiber/spec", 695))
        self.assertEqual(checks.parse_target("other/repo#1"), ("other/repo", 1))

    def test_anything_else(self):
        with self.assertRaisesRegex(ValueError, "not owner/repo#number"):
            checks.parse_target("spec 695")


class Floor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = pathlib.Path(self.tmp.name, "lfdev", "checks.json")

    def test_reads_the_head_commits_check_runs(self):
        forge = Forge()
        found, wait = checks.checks("lemonfiber/spec", 1, forge, T0, self.path)
        self.assertIsNone(wait)
        self.assertEqual(
            forge.asked,
            ["repos/lemonfiber/spec/pulls/1", "repos/lemonfiber/spec/commits/abc/check-runs?per_page=100"],
        )
        self.assertEqual([c["name"] for c in found], ["hygiene / lines", "tests"])
        self.assertEqual(found[0]["conclusion"], "")

    def test_a_second_read_within_ten_minutes_is_not_made(self):
        forge = Forge()
        checks.checks("lemonfiber/spec", 1, forge, T0, self.path)
        later = T0 + datetime.timedelta(minutes=4)
        found, wait = checks.checks("lemonfiber/spec", 1, forge, later, self.path)
        self.assertEqual(len(forge.asked), 2, "no new request")
        self.assertEqual(wait, datetime.timedelta(minutes=6))
        self.assertEqual(len(found), 2)

    def test_after_ten_minutes_or_for_another_pull_request_it_reads(self):
        forge = Forge()
        checks.checks("lemonfiber/spec", 1, forge, T0, self.path)
        checks.checks("lemonfiber/spec", 2, forge, T0, self.path)
        checks.checks("lemonfiber/spec", 1, forge, T0 + checks.FLOOR, self.path)
        self.assertEqual(len(forge.asked), 6)

    def test_an_unreadable_record_is_no_record(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{", "utf-8")
        _, wait = checks.checks("lemonfiber/spec", 1, Forge(), T0, self.path)
        self.assertIsNone(wait)
        self.assertIn("lemonfiber/spec#1", json.loads(self.path.read_text("utf-8")))


class Cache(unittest.TestCase):
    def test_under_the_users_cache_directory(self):
        self.assertEqual(checks.cache_file({"XDG_CACHE_HOME": "/c"}), pathlib.Path("/c/lfdev/checks.json"))
        self.assertEqual(checks.cache_file({}).parts[-2:], ("lfdev", "checks.json"))


class View(unittest.TestCase):
    def test_one_word_for_the_whole(self):
        done = {"status": "completed"}
        self.assertEqual(checks.verdict([{**done, "conclusion": "success"}]), "passing")
        self.assertEqual(checks.verdict([{**done, "conclusion": "failure"}]), "failing")
        self.assertEqual(checks.verdict([{"status": "queued", "conclusion": ""}]), "pending")

    def test_what_it_prints(self):
        found = [
            {"name": "tests", "status": "completed", "conclusion": "success"},
            {"name": "lint", "status": "queued", "conclusion": ""},
        ]
        said = checks.view("lemonfiber/spec#1", found, None)
        self.assertIn("lemonfiber/spec#1: pending (2 checks, read now)", said)
        self.assertIn("  queued      lint", said)
        later = checks.view("x#1", found, datetime.timedelta(minutes=5, seconds=30))
        self.assertIn("another read in 6 min", later)


if __name__ == "__main__":
    unittest.main()
