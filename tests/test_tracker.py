"""Tracker rows, written as every lemonfiber tracker writes them."""

from __future__ import annotations

import pathlib
import tempfile
import tomllib
import unittest

from lfdev import tracker

EXISTING = """# a tracker

requirement = [
  { id = "A1-R1", state = "open", evidence = [] },
  { id = "A1-R2", state = "done", evidence = ["src/a.rs"] },
]
"""


class Row(unittest.TestCase):
    def test_a_row_as_one_line(self):
        self.assertEqual(
            tracker.row("A1-R1", "done", ["src/a.rs", 'src/b.rs::says "hi"'], "abc1234"),
            '  { id = "A1-R1", state = "done", evidence = ["src/a.rs", "src/b.rs::says \\"hi\\""], landed = "abc1234" },',
        )
        self.assertEqual(
            tracker.row("A1-R1", "open", [], None), '  { id = "A1-R1", state = "open", evidence = [] },'
        )

    def test_refused(self):
        with self.assertRaisesRegex(ValueError, "not a state"):
            tracker.row("A1-R1", "finished", [], None)
        with self.assertRaisesRegex(ValueError, "names its evidence"):
            tracker.row("A1-R1", "done", [], None)


class WithRow(unittest.TestCase):
    def test_replaces_the_requirements_row(self):
        line = tracker.row("A1-R1", "done", ["src/a.rs"], None)
        after = tracker.with_row(EXISTING, "A1-R1", line)
        rows = tomllib.loads(after)["requirement"]
        self.assertEqual([r["state"] for r in rows], ["done", "done"])
        self.assertTrue(after.startswith("# a tracker"))

    def test_adds_a_row_before_the_array_closes(self):
        after = tracker.with_row(EXISTING, "A1-R3", tracker.row("A1-R3", "partial", [], None))
        self.assertEqual([r["id"] for r in tomllib.loads(after)["requirement"]], ["A1-R1", "A1-R2", "A1-R3"])

    def test_begins_a_tracker(self):
        after = tracker.with_row("", "A1-R1", tracker.row("A1-R1", "open", [], None))
        self.assertTrue(after.startswith(tracker.HEADER))
        self.assertEqual(tomllib.loads(after)["requirement"][0]["id"], "A1-R1")

    def test_a_tracker_with_no_array(self):
        with self.assertRaisesRegex(ValueError, "no `requirement"):
            tracker.with_row("# only a comment\n", "A1-R1", "x")

    def test_an_identifier_that_is_a_prefix_of_another(self):
        text = EXISTING.replace("A1-R2", "A1-R10")
        after = tracker.with_row(text, "A1-R1", tracker.row("A1-R1", "partial", [], None))
        states = {r["id"]: r["state"] for r in tomllib.loads(after)["requirement"]}
        self.assertEqual(states, {"A1-R1": "partial", "A1-R10": "done"})


class PathFor(unittest.TestCase):
    def test_the_file_or_the_features_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertEqual(tracker.path_for(root, "F8-R6"), root / "status.toml")
            (root / "status").mkdir()
            self.assertEqual(tracker.path_for(root, "F8-R6"), root / "status" / "F8.toml")
            self.assertEqual(tracker.family("ARCH-R12"), "ARCH")


if __name__ == "__main__":
    unittest.main()
