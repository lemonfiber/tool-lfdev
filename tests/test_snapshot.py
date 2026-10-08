"""Reading the board snapshot, and refusing one this tool cannot read."""

from __future__ import annotations

import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from lfdev import snapshot
from tests.fixture import board


class Parse(unittest.TestCase):
    def test_a_snapshot_in_the_format_read_here(self):
        self.assertEqual(snapshot.parse(json.dumps(board()))["format"], 1)

    def test_refused_when_not_json_not_an_object_or_another_format(self):
        for text, said in (("{", "not JSON"), ("[]", "not an object"), ('{"format": 2}', "format 2")):
            with self.subTest(text=text), self.assertRaisesRegex(snapshot.Unreadable, said):
                snapshot.parse(text)


class Load(unittest.TestCase):
    def test_from_a_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp, "board.json")
            path.write_text(json.dumps(board()), "utf-8")
            self.assertEqual(snapshot.load(str(path))["generated_at"], "2026-10-08T00:00:00Z")

    def test_a_path_that_is_not_there(self):
        with self.assertRaisesRegex(snapshot.Unreadable, "could not be read"):
            snapshot.load("/nowhere/board.json")

    def test_from_an_https_address(self):
        answer = mock.MagicMock()
        answer.__enter__.return_value = io.BytesIO(json.dumps(board()).encode())
        with mock.patch("urllib.request.urlopen", return_value=answer) as opened:
            self.assertEqual(snapshot.load(snapshot.BOARD_URL)["format"], 1)
        opened.assert_called_once_with(snapshot.BOARD_URL, timeout=snapshot.TIMEOUT)

    def test_an_address_that_is_not_https(self):
        with self.assertRaisesRegex(snapshot.Unreadable, "not an https address"):
            snapshot.load("http://example.org/board.json")


class Source(unittest.TestCase):
    def test_the_variable_or_the_published_address(self):
        self.assertEqual(snapshot.source({snapshot.SOURCE_VARIABLE: "b.json"}), "b.json")
        self.assertEqual(snapshot.source({}), snapshot.BOARD_URL)


if __name__ == "__main__":
    unittest.main()
