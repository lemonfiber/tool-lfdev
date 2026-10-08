"""`lfdev doc`: the repository and file a page is rendered from, and how far
behind `main` that is."""

from __future__ import annotations

import json
import unittest
import urllib.error

from lfdev import doc

REPO = "https://github.com/lemonfiber/website-docs.lemonfiber.app"
REVISION = "a49e418f7f61ed96035cfdc926a8cf8dc0a74f76"
PATH = "src/content/docs/advanced/remote-access.md"
TABLE = {"/advanced/remote-access/": {"repository": REPO, "path": PATH, "revision": REVISION}}


def fetched(table=TABLE, fails=False):
    def fetch(url):
        if fails:
            raise urllib.error.URLError("offline")
        fetch.asked = url
        return json.dumps(table)

    return fetch


def compared(ahead=0, files=(), fails=False):
    def get(path):
        get.asked = path
        if fails:
            raise urllib.error.URLError("rate limited")
        return {"ahead_by": ahead, "files": [{"filename": name} for name in files]}

    return get


class Located(unittest.TestCase):
    def test_a_page_on_a_site_with_or_without_its_scheme_or_slash(self):
        for url in (
            "https://docs.lemonfiber.app/advanced/remote-access/",
            "docs.lemonfiber.app/advanced/remote-access",
            "https://docs.lemonfiber.app/advanced/remote-access/?x=1#y",
        ):
            with self.subTest(url=url):
                self.assertEqual(doc.located(url), ("docs.lemonfiber.app", "/advanced/remote-access/"))
        self.assertEqual(doc.located("https://lemonfiber.app"), ("lemonfiber.app", "/"))

    def test_another_site_or_scheme_is_refused(self):
        for url in ("https://example.com/a/", "http://docs.lemonfiber.app/a/"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "is not a page on"):
                doc.located(url)


class Source(unittest.TestCase):
    def test_an_entry_it_reads(self):
        page = doc.source(TABLE, "/advanced/remote-access/")
        self.assertEqual((page.repository, page.path, page.revision), (REPO, PATH, REVISION))

    def test_entries_it_does_not(self):
        cases = {
            "no such route": (TABLE, "/nowhere/", "is not a page"),
            "not a table": ([], "/advanced/remote-access/", "is not a page"),
            "another forge": (
                {"/a/": {"repository": "https://example.com/o/r", "path": "a.md", "revision": REVISION}},
                "/a/",
                "does not read",
            ),
            "a branch for a revision": (
                {"/a/": {"repository": REPO, "path": "a.md", "revision": "main"}},
                "/a/",
                "does not read",
            ),
            "no path": ({"/a/": {"repository": REPO, "revision": REVISION}}, "/a/", "does not read"),
        }
        for why, (table, route, said) in cases.items():
            with self.subTest(why), self.assertRaisesRegex(LookupError, said):
                doc.source(table, route)


class Doc(unittest.TestCase):
    URL = "https://docs.lemonfiber.app/advanced/remote-access/"

    def test_where_the_page_comes_from_and_that_it_is_current(self):
        fetch, get = fetched(), compared()
        code, said = doc.doc(self.URL, fetch, get)
        self.assertEqual(code, 0)
        self.assertEqual(fetch.asked, "https://docs.lemonfiber.app/provenance.json")
        self.assertEqual(get.asked, f"repos/lemonfiber/website-docs.lemonfiber.app/compare/{REVISION}...main")
        self.assertIn(f"  path        {PATH}", said)
        self.assertIn("  revision    a49e418, current with main", said)
        self.assertIn(f"  edit        {REPO}/edit/main/{PATH}", said)

    def test_behind_main_and_whether_the_file_moved(self):
        for files, moved in (([PATH, "x"], "has changed since"), (["x"], "is unchanged since")):
            with self.subTest(moved=moved):
                _, said = doc.doc(self.URL, fetched(), compared(3, files))
                self.assertIn(f"3 commits behind main; the file {moved}", said)

    def test_a_comparison_that_failed_is_said(self):
        code, said = doc.doc(self.URL, fetched(), compared(fails=True))
        self.assertEqual(code, 0)
        self.assertIn("not compared with main: <urlopen error rate limited>", said)

    def test_what_could_not_be_answered(self):
        cases = {
            "another site": ("https://example.com/a/", fetched(), 2, "is not a page on"),
            "the site is down": (self.URL, fetched(fails=True), 2, "could not read docs.lemonfiber.app's"),
            "not JSON": (self.URL, lambda url: "<html>", 2, "Expecting value"),
            "not a page it names": (self.URL.replace("remote", "local"), fetched(), 1, "is not a page"),
        }
        for why, (url, fetch, code, said) in cases.items():
            with self.subTest(why):
                answered, told = doc.doc(url, fetch, compared())
                self.assertEqual(answered, code)
                self.assertIn(said, told)


if __name__ == "__main__":
    unittest.main()
