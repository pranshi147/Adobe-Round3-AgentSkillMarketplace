import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidencekit import textutil as tu  # noqa: E402


class TestNormalisation(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(tu.normalize_ws("  a\n\t b  "), "a b")

    def test_content_tokens_drop_stopwords(self):
        self.assertEqual(tu.content_tokens("The torque of the wrench"),
                         {"torque", "wrench"})

    def test_jaccard_bounds(self):
        self.assertEqual(tu.jaccard(set(), set()), 1.0)
        self.assertEqual(tu.jaccard({"a"}, set()), 0.0)
        self.assertAlmostEqual(tu.jaccard({"a", "b"}, {"b", "c"}), 1 / 3)

    def test_shingles_of_short_text(self):
        self.assertEqual(tu.shingles("one two", 6), {"one two"})


class TestEntityNames(unittest.TestCase):
    def test_legal_suffixes_stripped(self):
        self.assertEqual(tu.normalize_entity_name("Apex Commerce Pvt. Ltd."),
                         "apex commerce")

    def test_containment_is_compatible(self):
        self.assertTrue(tu.names_compatible("acme", "acme technologies"))

    def test_acronym_is_compatible(self):
        self.assertTrue(tu.names_compatible("bmc", "big mountain corp"))

    def test_unrelated_names_conflict(self):
        self.assertFalse(tu.names_compatible("zenith retail", "apex commerce"))

    def test_accents_normalised(self):
        self.assertEqual(tu.normalize_entity_name("Café Zürich"), "cafe zurich")


class TestDatesAndPrices(unittest.TestCase):
    def test_iso_date(self):
        self.assertIn(dt.date(2026, 3, 4), tu.find_dates("published 2026-03-04"))

    def test_text_dates_both_orders(self):
        self.assertIn(dt.date(2026, 3, 12), tu.find_dates("12 March 2026"))
        self.assertIn(dt.date(2026, 3, 12), tu.find_dates("March 12, 2026"))

    def test_ambiguous_numeric_date_rejected(self):
        self.assertEqual(tu.find_dates("03/04/2026"), [])

    def test_unambiguous_numeric_date_accepted(self):
        self.assertIn(dt.date(2026, 4, 23), tu.find_dates("23/04/2026"))

    def test_impossible_date_rejected(self):
        self.assertEqual(tu.find_dates("2026-02-31"), [])

    def test_prices_normalised_across_currencies(self):
        self.assertEqual(tu.find_prices("costs ₹4,999 or $59.00"), ["4999", "59"])

    def test_number_normalisation(self):
        self.assertEqual(tu.normalize_number("4999.00"), "4999")
        self.assertEqual(tu.normalize_number("1,299"), "1299")
        self.assertIsNone(tu.normalize_number("not-a-price"))


class TestAnchorsAndSentences(unittest.TestCase):
    def test_stock_anchors_are_nondescriptive(self):
        for text in ("Click here", "read more", ">", "", "  Learn More  "):
            self.assertTrue(tu.is_nondescriptive_anchor(text), text)

    def test_real_anchors_are_descriptive(self):
        self.assertFalse(tu.is_nondescriptive_anchor("TW-200 wrench specification"))

    def test_definitional_sentence_detected(self):
        self.assertTrue(tu.looks_definitional("Northwind Tools is a manufacturer."))
        self.assertTrue(tu.looks_definitional("We provide calibration services."))

    def test_slogan_is_not_definitional(self):
        self.assertFalse(tu.looks_definitional("Better tools. Better work."))

    def test_sentence_split(self):
        self.assertEqual(len(tu.sentences("One thing. Two things! Three?")), 3)


if __name__ == "__main__":
    unittest.main()
