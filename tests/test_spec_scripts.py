"""Running spec's scripts from the copy, and finding a checkout of spec."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

from lfdev import spec_scripts


class Script(unittest.TestCase):
    def test_runs_the_copy_with_this_python(self):
        seen = []
        code = spec_scripts.script(
            "status_check.py", "check", cwd=pathlib.Path("/w"), runner=lambda a, c: seen.append((a, c)) or 3
        )
        self.assertEqual(code, 3)
        script = str(spec_scripts.VENDORED / "status_check.py")
        self.assertEqual(seen, [([sys.executable, script, "check"], pathlib.Path("/w"))])

    def test_run_passes_the_exit_code_through(self):
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=4)) as ran:
            self.assertEqual(spec_scripts.run(["x"]), 4)
        self.assertIsNone(ran.call_args.kwargs["cwd"])


class SpecRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        (self.base / "spec" / "10-functional").mkdir(parents=True)
        (self.base / "repo").mkdir()

    def test_beside_this_repository(self):
        self.assertEqual(spec_scripts.spec_root(None, self.base / "repo", {}), self.base / "spec")

    def test_named_or_from_the_variable(self):
        spec = str(self.base / "spec")
        self.assertEqual(spec_scripts.spec_root(spec, pathlib.Path("/x/y"), {}), self.base / "spec")
        self.assertEqual(
            spec_scripts.spec_root(None, pathlib.Path("/x/y"), {spec_scripts.SPEC_VARIABLE: spec}),
            self.base / "spec",
        )

    def test_none_to_be_found(self):
        with self.assertRaisesRegex(FileNotFoundError, "clone https://github.com/lemonfiber/spec"):
            spec_scripts.spec_root(None, pathlib.Path("/nowhere/repo"), {})


if __name__ == "__main__":
    unittest.main()
