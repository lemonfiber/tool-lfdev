"""The board and the work to pick up, as the frontpage computes them."""

from __future__ import annotations

import unittest

from lfdev import work
from tests.fixture import board


class Cards(unittest.TestCase):
    def test_every_feature_with_its_facets(self):
        a1, b1 = work.cards(board())
        self.assertEqual(
            (a1.id, a1.versions, a1.repos, a1.open_goals, a1.claims),
            ("A1", ("0.1.0",), ("lemonfiber",), 0, 0),
        )
        self.assertEqual((b1.repos, b1.open_goals, b1.claims), (("lemonfiber", "sdk-ts"), 4, 1))

    def test_feature_of_a_requirement(self):
        self.assertEqual(work.feature_of("F8-R6"), "F8")
        self.assertEqual(work.feature_of("F8"), "F8")


class Matches(unittest.TestCase):
    def test_each_filter_as_the_frontpage_reads_it(self):
        a1, b1 = work.cards(board())
        cases = [
            ({}, True, True),
            ({"version": "0.1.0"}, True, False),
            ({"area": "B"}, False, True),
            ({"audience": "both"}, False, True),
            ({"repo": "sdk-ts"}, False, True),
            ({"maturity": "shipped"}, True, False),
            ({"status": "draft"}, False, False),
            ({"claimed": "yes"}, False, True),
            ({"claimed": "no"}, True, False),
            ({"label": "ux"}, True, False),
            ({"q": "a1"}, True, False),
            ({"q": "form"}, False, True),
        ]
        for filters, first, second in cases:
            with self.subTest(filters=filters):
                self.assertEqual((work.matches(a1, filters), work.matches(b1, filters)), (first, second))


class Pick(unittest.TestCase):
    def test_the_first_two_versions_taking_work(self):
        self.assertEqual([v["version"] for v in work.taking_work(board())], ["0.3.0", "0.4.0"])

    def test_unmet_unclaimed_goals_with_where_they_stand(self):
        found = work.pickable(board())
        self.assertEqual([g.id for g in found], ["B1-R1", "GOV-R1", "B1-R3"])
        b1, gov, _ = found
        self.assertEqual((b1.repos, b1.area, b1.text), (("lemonfiber",), "B", "The tool MUST run a form."))
        self.assertEqual((gov.repos, gov.area, gov.text), ((), None, None))

    def test_filtered_by_version_area_and_repository(self):
        found = work.pickable(board())
        ids = lambda f: [g.id for g in found if work.pick_matches(g, f)]  # noqa: E731
        self.assertEqual(ids({"version": "0.4.0"}), ["B1-R3"])
        self.assertEqual(ids({"area": "B"}), ["B1-R1", "B1-R3"])
        self.assertEqual(ids({"repo": "lemonfiber"}), ["B1-R1"])
        self.assertEqual(ids({}), ["B1-R1", "GOV-R1", "B1-R3"])


if __name__ == "__main__":
    unittest.main()
