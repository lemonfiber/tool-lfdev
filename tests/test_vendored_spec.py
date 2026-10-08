"""The copy of spec's scripts: taken at a commit, and held to it and to main."""

from __future__ import annotations

import contextlib
import io
import pathlib
import runpy
import tempfile
import unittest
import urllib.error
from unittest import mock

from lfdev import vendored_spec as vendored


class Spec:
    """Serves each file at a commit, as the forge would, counting the asks."""

    def __init__(self, commits):
        self.commits = commits

    def __call__(self, commit, name):
        return self.commits[commit].get(name, f"# {name} at {commit}\n".encode())


SPEC = Spec({"aaa": {}, "bbb": {"patterns.py": b"# moved\n"}})


class Copy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.here = pathlib.Path(self.tmp.name)

    def test_sync_takes_every_file_and_records_the_commit(self):
        self.assertEqual(vendored.sync("aaa", SPEC, self.here), list(vendored.FILES))
        self.assertEqual((self.here / "REVISION").read_text("utf-8"), "aaa\n")
        self.assertEqual((self.here / "paths.py").read_bytes(), b"# paths.py at aaa\n")
        self.assertEqual(vendored.sync("aaa", SPEC, self.here), [], "taken again, nothing changes")

    def test_a_copy_that_is_main(self):
        vendored.sync("aaa", SPEC, self.here)
        same = Spec({"aaa": {}, "ccc": {n: f"# {n} at aaa\n".encode() for n in vendored.FILES}})
        code, said = vendored.check("ccc", same, self.here)
        self.assertEqual(code, 0)
        self.assertIn("the copy is spec aaa, and spec's main ccc holds the same files", said)

    def test_a_copy_behind_main(self):
        vendored.sync("aaa", SPEC, self.here)
        code, said = vendored.check("bbb", SPEC, self.here)
        self.assertEqual(code, 1)
        self.assertIn("differs in status_check.py", said)
        self.assertIn("python -m lfdev.vendored_spec sync bbb", said)

    def test_a_copy_edited_here(self):
        vendored.sync("aaa", SPEC, self.here)
        (self.here / "metafm.py").write_bytes(b"# changed by hand\n")
        code, said = vendored.check("aaa", SPEC, self.here)
        self.assertEqual(code, 1)
        self.assertIn("it was edited here", said)
        self.assertIn("metafm.py", said)

    def test_a_file_missing_from_the_copy(self):
        vendored.sync("aaa", SPEC, self.here)
        (self.here / "paths.py").unlink()
        self.assertEqual(vendored.check("aaa", SPEC, self.here)[0], 1)


class Forge(unittest.TestCase):
    def answer(self, body):
        opened = mock.MagicMock()
        opened.__enter__.return_value = io.BytesIO(body)
        return opened

    def test_a_file_at_a_commit(self):
        with mock.patch("urllib.request.urlopen", return_value=self.answer(b"x")) as got:
            self.assertEqual(vendored.raw("abc", "paths.py"), b"x")
        self.assertEqual(
            got.call_args.args[0],
            "https://raw.githubusercontent.com/lemonfiber/spec/abc/scripts/paths.py",
        )

    def test_mains_head_with_a_token_where_one_is_set(self):
        with mock.patch("urllib.request.urlopen", return_value=self.answer(b"abc\n")) as got:
            self.assertEqual(vendored.main_head({"GITHUB_TOKEN": "t"}), "abc")
        self.assertEqual(got.call_args.args[0].get_header("Authorization"), "Bearer t")
        with mock.patch("urllib.request.urlopen", return_value=self.answer(b"abc")) as got:
            vendored.main_head({})
        self.assertIsNone(got.call_args.args[0].get_header("Authorization"))


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = vendored.main(argv)
    return code, out.getvalue()


class Main(unittest.TestCase):
    def test_sync(self):
        with mock.patch.object(vendored, "sync", return_value=["paths.py"]):
            self.assertEqual(run(["sync", "abcdef12"]), (0, "took spec abcdef1: paths.py\n"))
        with mock.patch.object(vendored, "sync", return_value=[]):
            self.assertIn("nothing changed", run(["sync", "abc"])[1])

    def test_check(self):
        with (
            mock.patch.object(vendored, "main_head", return_value="abc"),
            mock.patch.object(vendored, "check", return_value=(1, "behind")),
        ):
            self.assertEqual(run(["check"]), (1, "::error::behind\n"))
        with (
            mock.patch.object(vendored, "main_head", return_value="abc"),
            mock.patch.object(vendored, "check", return_value=(0, "current")),
        ):
            self.assertEqual(run(["check"]), (0, "current\n"))

    def test_spec_that_cannot_be_read(self):
        with mock.patch.object(vendored, "main_head", side_effect=urllib.error.URLError("down")):
            code, said = run(["check"])
        self.assertEqual(code, 2)
        self.assertIn("::error::spec could not be read", said)

    def test_anything_else_prints_the_usage(self):
        code, said = run(["sync"])
        self.assertEqual(code, 2)
        self.assertIn("python -m lfdev.vendored_spec sync <commit>", said)

    def test_run_as_a_module(self):
        with (
            mock.patch("sys.argv", ["vendored_spec", "sync"]),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as ran,
        ):
            runpy.run_module("lfdev.vendored_spec", run_name="__main__")
        self.assertEqual(ran.exception.code, 2)

    def test_the_copy_in_this_package_is_whole(self):
        self.assertTrue(all((vendored.HERE / name).is_file() for name in vendored.FILES))
        self.assertRegex(vendored.REVISION.read_text("utf-8"), r"^[0-9a-f]{40}\n$")


if __name__ == "__main__":
    unittest.main()
