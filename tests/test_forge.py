"""The forge, read with the person's own token."""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from lfdev import forge


class Token(unittest.TestCase):
    def test_from_the_environment_first(self):
        self.assertEqual(forge.token({"GH_TOKEN": "a", "GITHUB_TOKEN": "b"}), "a")
        self.assertEqual(forge.token({"GITHUB_TOKEN": "b"}), "b")

    def test_from_gh_otherwise(self):
        done = mock.Mock(returncode=0, stdout="t0ken\n")
        with mock.patch("subprocess.run", return_value=done):
            self.assertEqual(forge.token({}), "t0ken")

    def test_none_anywhere(self):
        signed_out = mock.Mock(returncode=1, stdout="")
        for effect in ({"return_value": signed_out}, {"side_effect": FileNotFoundError}):
            with (
                self.subTest(effect=effect),
                mock.patch("subprocess.run", **effect),
                self.assertRaisesRegex(forge.Unauthenticated, "gh auth login"),
            ):
                forge.token({})


class Get(unittest.TestCase):
    def test_one_request_with_the_token(self):
        answer = mock.MagicMock()
        answer.__enter__.return_value = io.BytesIO(json.dumps({"ok": True}).encode())
        with mock.patch("urllib.request.urlopen", return_value=answer) as opened:
            self.assertEqual(forge.get("/repos/x/y", "t"), {"ok": True})
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/x/y")
        self.assertEqual(request.get_header("Authorization"), "Bearer t")


if __name__ == "__main__":
    unittest.main()
