"""The forge, read with the person's own token."""

from __future__ import annotations

import io
import json
import pathlib
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


class Post(unittest.TestCase):
    def test_one_request_with_a_json_body(self):
        answer = mock.MagicMock()
        answer.__enter__.return_value = io.BytesIO(json.dumps({"number": 7}).encode())
        with mock.patch("urllib.request.urlopen", return_value=answer) as opened:
            self.assertEqual(forge.post("repos/x/y/pulls", "t", {"title": "a"}), {"number": 7})
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"title": "a"})
        self.assertEqual(request.get_header("Authorization"), "Bearer t")


if __name__ == "__main__":
    unittest.main()


class Ending(unittest.TestCase):
    def test_the_citation_then_the_committer_s_sign_off(self):
        asked = []

        def ask(args):
            asked.append(args)
            return 0, "Ana Lima <ana@example.org> 1760000000 +0200"

        said = forge.ending(ask, pathlib.Path("/work/spec"), "GOV-R40")
        self.assertEqual(said, "Spec: GOV-R40\n\nSigned-off-by: Ana Lima <ana@example.org>")
        self.assertEqual(asked, [["git", "-C", "/work/spec", "var", "GIT_COMMITTER_IDENT"]])

    def test_no_identity_leaves_the_citation_alone(self):
        for answer in ((1, ""), (0, "nobody")):
            with self.subTest(answer):
                self.assertEqual(
                    forge.ending(lambda _, said=answer: said, pathlib.Path("."), "B1-R1"), "Spec: B1-R1"
                )
