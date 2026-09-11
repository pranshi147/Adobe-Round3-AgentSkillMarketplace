"""Dynamic-content handling.

The auditor never runs a browser. These tests pin down the distinction it must
keep: content missing from server HTML, content that *looks* client-rendered,
content gated behind interaction, and content actually verified after rendering
using a snapshot the caller supplied.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import helpers  # noqa: E402
from helpers import context, ids, page  # noqa: E402
from evidencekit.crawl import normalize_url  # noqa: E402
from evidencekit.htmlparse import parse_html, rendering_classification  # noqa: E402

MR = helpers.load_detectors("machine-readability")

SHELL = ('<html lang="en"><head><title>Store finder — Northwind Tools</title></head>'
         '<body><div id="root"></div><script>'
         + 'var padding_for_script_weight = "x";' * 40 +
         '</script></body></html>')

ACCORDION = ('<html lang="en"><head><title>Specifications — Northwind Tools</title></head>'
             '<body><main><h1>Specifications</h1><p>See details below.</p>'
             '<div class="accordion-content"><p>'
             + "The wrench covers twenty to two hundred and ten newton metres. " * 12
             + '</p></div></main></body></html>')

RENDERED = ('<html lang="en"><head><title>Store finder — Northwind Tools</title></head>'
            '<body><div id="root"><main><h1>Store finder</h1><p>'
            + "Northwind Tools has service counters in eleven cities. " * 30
            + '</p></main></div></body></html>')


class TestClassification(unittest.TestCase):
    def test_server_rendered(self):
        doc = parse_html("http://a.test/", page(
            "Home — Northwind Tools",
            body="Northwind Tools is a workshop tool manufacturer. "
                 + "Every wrench is calibrated against a reference transducer. " * 20))
        self.assertEqual(rendering_classification(doc), "server_rendered")

    def test_likely_client_rendered_is_an_inference_not_a_verification(self):
        doc = parse_html("http://a.test/", SHELL)
        self.assertEqual(rendering_classification(doc), "likely_client_rendered")

    def test_interaction_required_is_distinct_from_client_rendered(self):
        doc = parse_html("http://a.test/", ACCORDION)
        self.assertEqual(rendering_classification(doc), "interaction_required")

    def test_thin_page_without_indicators_is_not_called_client_rendered(self):
        doc = parse_html("http://a.test/",
                         "<html><head><title>Contact</title></head><body><main>"
                         "<h1>Contact</h1><p>Call us on the number below.</p>"
                         "</main></body></html>")
        self.assertEqual(rendering_classification(doc), "server_rendered_thin")

    def test_cookie_banner_text_is_not_counted_as_hidden_content(self):
        html = ('<main><h1>T</h1><p>Visible copy.</p>'
                '<div class="cookie-consent" hidden><p>'
                + "We use cookies to improve your experience. " * 20 + '</p></div></main>')
        doc = parse_html("http://a.test/", html)
        self.assertEqual(doc.words_hidden, 0)


class TestHonestRenderingClaims(unittest.TestCase):
    def test_default_context_states_rendering_was_not_performed(self):
        ctx = context({"/": page("Home — Northwind Tools")}, sitemap=["/"])
        self.assertIn("not performed", ctx.rendering_verification)
        self.assertIn("no browser engine", ctx.rendering_verification)

    def test_supplied_snapshot_upgrades_the_claim_for_that_url_only(self):
        ctx = context({"/": SHELL, "/other.html": SHELL}, sitemap=["/"])
        ctx.rendered_evidence = {normalize_url(helpers.HOST + "/"): RENDERED}
        pages = {p.path: p for p in ctx.ev.pages}
        self.assertEqual(ctx.rendering_of(pages["/"]), "verified_after_render")
        self.assertEqual(ctx.rendering_of(pages["/other.html"]), "likely_client_rendered")
        self.assertIn("caller-supplied", ctx.rendering_verification)

    def test_snapshot_that_adds_nothing_does_not_upgrade_the_claim(self):
        ctx = context({"/": SHELL}, sitemap=["/"])
        ctx.rendered_evidence = {normalize_url(helpers.HOST + "/"): SHELL}
        self.assertEqual(ctx.rendering_of(ctx.ev.pages[0]), "likely_client_rendered")

    def test_mr005_evidence_describes_served_html_not_rendered_state(self):
        ctx = context({"/": SHELL, "/b.html": SHELL.replace("Store", "Branch")},
                      sitemap=["/"])
        found = [f for f in MR.run(ctx) if f.id == "MR-005"]
        self.assertTrue(found)
        blob = found[0].evidence_text().lower()
        self.assertIn("served html", blob)
        for overclaim in ("rendered page", "after rendering", "in the browser"):
            self.assertNotIn(overclaim, blob)


class TestInteractionIsNotRenderingFailure(unittest.TestCase):
    def test_accordion_page_is_not_reported_as_a_rendering_gap(self):
        ctx = context({"/": page("Home — Northwind Tools"),
                       "/a.html": ACCORDION,
                       "/b.html": ACCORDION.replace("Specifications", "Materials")},
                      sitemap=["/"])
        self.assertNotIn("MR-005", ids(MR.run(ctx)))

    def test_hidden_words_are_measured_separately_from_visible_words(self):
        doc = parse_html("http://a.test/", ACCORDION)
        self.assertGreater(doc.words_hidden, 60)
        self.assertLess(doc.words_visible_main, 120)
        self.assertEqual(doc.words_main, doc.words_visible_main + doc.words_hidden)


if __name__ == "__main__":
    unittest.main()
