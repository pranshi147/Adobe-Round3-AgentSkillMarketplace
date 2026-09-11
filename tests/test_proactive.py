"""Proactive opportunities.

Two properties matter and neither was directly tested before this pass:

  * each generator fires from a real observation, not from a template;
  * each is suppressed when the corresponding defect already fired, so the
    report never suggests adding a thing it just reported as broken.

An empty opportunities section on a well-built site is the correct outcome, not
a sign the generators are dead — the last test here pins that down.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import helpers  # noqa: E402
from helpers import context, page  # noqa: E402
from evidencekit.external import ExternalEvidence  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "orch_proactive",
    ROOT / "skills" / "evidence-path-orchestrator" / "scripts" / "proactive.py")
proactive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proactive)

ORG_NO_SAMEAS = ('<script type="application/ld+json">{"@type":"Organization",'
                 '"name":"Northwind Tools","url":"%s/","description":'
                 '"Northwind Tools manufactures calibrated torque wrenches for '
                 'independent vehicle repair workshops across India since 2011."}'
                 '</script>' % helpers.HOST)

ORG_WITH_SAMEAS = ORG_NO_SAMEAS.replace(
    '"description":', '"sameAs":["https://profile.test/nw"],"description":')


class _Fired:
    """Minimal stand-in for a Finding: generators only read `.id`."""

    def __init__(self, defect_id):
        self.id = defect_id


def ids(ops):
    return {op["title"] for op in ops}


def titles_containing(ops, needle):
    return [op for op in ops if needle.lower() in op["title"].lower()]


class TestOpportunityShape(unittest.TestCase):
    def setUp(self):
        self.ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_NO_SAMEAS)})
        self.ops = proactive.generate(self.ctx, [])

    def test_ids_are_sequential(self):
        self.assertEqual([op["id"] for op in self.ops],
                         [f"PO-{i:03d}" for i in range(1, len(self.ops) + 1)])

    def test_every_opportunity_is_actionable(self):
        for op in self.ops:
            action = op["suggested_action"]
            self.assertTrue(op["observation"], op["title"])
            self.assertTrue(action["summary"], op["title"])
            self.assertTrue(action["implementation"], op["title"])
            self.assertTrue(action["why_it_works"], op["title"])
            self.assertTrue(action["verification"], op["title"])

    def test_opportunities_never_claim_a_defect(self):
        for op in self.ops:
            self.assertIn(op["priority"], ("P2", "P3"), op["title"])
            self.assertIn("stage", op)


class TestAbsenceBecomesAnOpportunityNotAFinding(unittest.TestCase):
    def test_no_declared_identifiers_yields_an_opportunity(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_NO_SAMEAS)})
        ops = proactive.generate(ctx, [])
        self.assertTrue(titles_containing(ops, "external identifiers"))

    def test_that_opportunity_says_it_does_not_apply_without_a_real_record(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_NO_SAMEAS)})
        op = titles_containing(proactive.generate(ctx, []), "external identifiers")[0]
        steps = " ".join(op["suggested_action"]["implementation"]).lower()
        self.assertIn("do not create", steps)

    def test_declared_identifiers_suppress_it(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_WITH_SAMEAS)})
        ctx.external = ExternalEvidence(mode="auto")
        ctx.external.declared = [("https://profile.test/nw", "sameAs")]
        self.assertFalse(titles_containing(proactive.generate(ctx, []),
                                           "external identifiers"))

    def test_missing_sitemap_yields_an_opportunity(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_NO_SAMEAS)})
        self.assertTrue(titles_containing(proactive.generate(ctx, []), "sitemap"))

    def test_sitemap_opportunity_is_suppressed_when_MR_008_fired(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_NO_SAMEAS)})
        ops = proactive.generate(ctx, [_Fired("MR-008")])
        self.assertFalse([op for op in ops if op["title"] == "Publish an XML sitemap"])

    def test_present_sitemap_yields_no_sitemap_absence_opportunity(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_NO_SAMEAS)},
                      sitemap=["/"])
        self.assertFalse([op for op in proactive.generate(ctx, [])
                          if op["title"] == "Publish an XML sitemap"])


class TestSuppressionByFiredDefect(unittest.TestCase):
    """The report must never suggest adding a thing it just called broken."""

    def test_sameas_suggestion_suppressed_when_entity_identity_missing(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_NO_SAMEAS)})
        ops = proactive.generate(ctx, [_Fired("FI-002")])
        self.assertFalse(titles_containing(ops, "sameAs"))

    def test_entity_description_suggestion_suppressed_when_AX_002_fired(self):
        org = ('<script type="application/ld+json">{"@type":"Organization",'
               '"name":"Northwind Tools"}</script>')
        ctx = context({"/": page("Home — Northwind Tools", head_extra=org)})
        ops = proactive.generate(ctx, [_Fired("AX-002")])
        self.assertFalse(titles_containing(ops, "brand fact block"))

    def test_product_markup_suggestion_suppressed_when_FI_003_fired(self):
        priced = page("Wrench — Northwind Tools",
                      body="The TW-200 wrench costs ₹4,999 and includes a certificate "
                           "recording the measured deviation at three points on the scale.")
        pages = {"/": page("Home — Northwind Tools", head_extra=ORG_WITH_SAMEAS),
                 "/a.html": priced, "/b.html": priced.replace("TW-200", "TW-050")}
        ctx = context(pages, sitemap=["/"])
        self.assertTrue(titles_containing(proactive.generate(ctx, []), "commercial facts"))
        self.assertFalse(titles_containing(
            proactive.generate(ctx, [_Fired("FI-003")]), "commercial facts"))

    def test_passage_structure_suggestion_suppressed_when_extraction_already_broken(self):
        long_body = "The calibration laboratory keeps reference transducers under contract. " * 60
        flat = ('<html lang="en"><head><title>Guide — Northwind Tools</title></head><body>'
                f'<main><h1>Guide</h1><p>{long_body}</p></main></body></html>')
        ctx = context({"/": flat, "/b.html": flat.replace("Guide", "Manual")},
                      sitemap=["/"])
        self.assertTrue(titles_containing(proactive.generate(ctx, []), "labelled sections"))
        self.assertFalse(titles_containing(
            proactive.generate(ctx, [_Fired("MR-005")]), "labelled sections"))


class TestObservationDriven(unittest.TestCase):
    def test_faq_markup_suggested_only_where_question_content_exists(self):
        qa = page("Questions — Northwind Tools",
                  body="What is a torque wrench? It is a tool that measures applied "
                       "force. How do I calibrate one? Send it to a laboratory. "
                       "Can I do it myself? Not reliably without a reference transducer.")
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_WITH_SAMEAS),
                       "/faq.html": qa}, sitemap=["/"])
        self.assertTrue(titles_containing(proactive.generate(ctx, []), "FAQPage"))

    def test_faq_markup_not_suggested_on_ordinary_prose(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_WITH_SAMEAS)},
                      sitemap=["/"])
        self.assertFalse(titles_containing(proactive.generate(ctx, []), "FAQPage"))

    def test_lastmod_suggested_only_when_the_sitemap_lacks_dates(self):
        pages = {"/": page("Home — Northwind Tools", head_extra=ORG_WITH_SAMEAS)}
        without = context(pages, sitemap=["/", "/a.html"], sitemap_lastmod_count=0)
        with_dates = context(pages, sitemap=["/", "/a.html"], sitemap_lastmod_count=2)
        self.assertTrue(titles_containing(proactive.generate(without, []), "lastmod"))
        self.assertFalse(titles_containing(proactive.generate(with_dates, []), "lastmod"))


class TestWellBuiltSiteNeedsNothing(unittest.TestCase):
    """An empty opportunities section is a correct outcome, not a dead generator."""

    def test_a_site_that_already_does_everything_gets_no_suggestions(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_WITH_SAMEAS)},
                      sitemap=["/"], sitemap_lastmod_count=5)
        ctx.external = ExternalEvidence(mode="auto")
        ctx.external.declared = [("https://profile.test/nw", "sameAs")]
        self.assertEqual(proactive.generate(ctx, []), [])

    def test_but_the_same_site_missing_one_thing_gets_exactly_that_suggestion(self):
        ctx = context({"/": page("Home — Northwind Tools", head_extra=ORG_NO_SAMEAS)},
                      sitemap=["/"], sitemap_lastmod_count=5)
        ctx.external = ExternalEvidence(mode="auto")
        ctx.external.declared = []
        ops = proactive.generate(ctx, [])
        self.assertEqual(len(ops), 2)
        self.assertTrue(titles_containing(ops, "sameAs"))
        self.assertTrue(titles_containing(ops, "external identifiers"))


if __name__ == "__main__":
    unittest.main()
