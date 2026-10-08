"""`lfdev doctor`, against a git and a `gh` that answer as told."""

from __future__ import annotations

import unittest
from unittest import mock

from lfdev import doctor

READY = {
    ("git", "config", "--get", "core.hooksPath"): (0, ".githooks"),
    ("git", "config", "--get", "user.name"): (0, "A Person"),
    ("git", "config", "--get", "user.email"): (0, "a@example.org"),
    ("git", "config", "--get", "commit.gpgsign"): (0, "true"),
    ("git", "config", "--get", "user.signingkey"): (0, "~/.ssh/id.pub"),
    ("gh", "auth", "status"): (0, ""),
}


def runner(answers):
    return lambda args: answers.get(tuple(args), (1, ""))


class Doctor(unittest.TestCase):
    def test_a_clone_set_up_to_commit(self):
        code, said = doctor.report(doctor.checks(runner(READY)))
        self.assertEqual(code, 0)
        self.assertEqual(said.count("ok  "), 4)

    def test_a_new_clone_is_told_what_to_run(self):
        code, said = doctor.report(doctor.checks(runner({})))
        self.assertEqual(code, 1)
        self.assertIn("FIX  hooks on  ->  git config core.hooksPath .githooks", said)
        self.assertIn("FIX  gh authenticated  ->  gh auth login", said)

    def test_signing_needs_both_the_switch_and_a_key(self):
        half = {**READY, ("git", "config", "--get", "user.signingkey"): (1, "")}
        found = {c.name: c.ok for c in doctor.checks(runner(half))}
        self.assertFalse(found["commits signed"])


class Run(unittest.TestCase):
    def test_a_program_and_its_output(self):
        done = mock.Mock(returncode=0, stdout=" true\n")
        with mock.patch("subprocess.run", return_value=done):
            self.assertEqual(doctor.run(["git", "config", "--get", "x"]), (0, "true"))

    def test_a_program_that_is_not_installed(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(doctor.run(["gh"]), (127, ""))


if __name__ == "__main__":
    unittest.main()
