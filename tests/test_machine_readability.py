"""Each detector is tested twice: once with a page that MUST trigger it, and
once with a very similar page that MUST NOT. The negative controls are the
point — a rule that cannot be shown to stay quiet is not a rule, it is noise.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import helpers  # noqa: E402
from helpers import context, ids, page  # noqa: E402

MR = helpers.load_detectors("machine-readability")
SITEMAP = ["/", "/about.html", "/pricing.html"]

HEALTHY = {
    "/": page("Precision hand tools for workshops — Northwind Tools"),
    "/about.html": page("How Northwind Tools was founded — Northwind Tools",
                        body="Northwind Tools is a manufacturer of calibrated torque "
                             "wrenches based in Pune, founded in 2011 by two service "
                             "engineers who were tired of sending workshop tools abroad "
                             "for recalibration every year. The company began as a single "
                             "calibration bench in a rented industrial unit and now runs a "
                             "small production line alongside the original service, with "
                             "twenty two people employed across production, the laboratory "
                             "and customer support in the same building."),
    "/pricing.html": page("Tool prices and calibration fees — Northwind Tools",
                          body="These are the prices for Northwind Tools products, and they "
                               "include the calibration certificate but exclude delivery. "
                               "The TW-200 click type torque wrench covers twenty to two "
                               "hundred and ten newton metres. Recalibration of a wrench "
                               "bought from us takes three working days in the laboratory, "
                               "and wrenches from other manufacturers take longer because "
                               "they need an additional adaptor set before measurement."),
}


class TestHealthySiteIsSilent(unittest.TestCase):
    def test_no_findings_on_clean_site(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertEqual(ids(MR.run(ctx)), set())


class TestMR001RobotsBlocking(unittest.TestCase):
    ROBOTS_BLOCKING = "User-agent: *\nDisallow: /guides/\n"
    ROBOTS_UTILITY = "User-agent: *\nDisallow: /cart\nDisallow: /checkout\n"
    LINKING = page("Guides index — Northwind Tools",
                   head_extra='<meta name="x" content="y">')

    def _pages(self):
        pages = dict(HEALTHY)
        pages["/"] = page("Precision hand tools for workshops — Northwind Tools",
                          body="Northwind Tools is a workshop tool manufacturer. Read the "
                               "<a href='/guides/torque.html'>torque guide for workshops</a> "
                               "for calibration advice about wrenches and fasteners used in "
                               "commercial garages every day of the working week.")
        return pages

    def test_fires_when_content_path_blocked(self):
        ctx = context(self._pages(), robots_text=self.ROBOTS_BLOCKING, sitemap=SITEMAP)
        findings = [f for f in MR.run(ctx) if f.id == "MR-001"]
        self.assertEqual(len(findings), 1)
        self.assertIn("Disallow: /guides/", findings[0].evidence_text())
        self.assertEqual(findings[0].evidence_level, "verified")

    def test_silent_when_only_utility_paths_blocked(self):
        ctx = context(self._pages(), robots_text=self.ROBOTS_UTILITY, sitemap=SITEMAP)
        self.assertNotIn("MR-001", ids(MR.run(ctx)))

    def test_severity_critical_when_target_blocked(self):
        ctx = context(HEALTHY, robots_text="User-agent: *\nDisallow: /\n", sitemap=SITEMAP)
        f = [f for f in MR.run(ctx) if f.id == "MR-001"][0]
        self.assertEqual(f.severity, "critical")


class TestMR002Noindex(unittest.TestCase):
    def test_fires_on_noindex_content_page(self):
        pages = dict(HEALTHY)
        pages["/pricing.html"] = page("Tool prices — Northwind Tools",
                                      head_extra='<meta name="robots" content="noindex">')
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("MR-002", ids(MR.run(ctx)))

    def test_silent_on_nofollow_or_noarchive(self):
        pages = dict(HEALTHY)
        pages["/pricing.html"] = page(
            "Tool prices — Northwind Tools",
            head_extra='<meta name="robots" content="nofollow, noarchive">')
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("MR-002", ids(MR.run(ctx)))

    def test_header_directive_detected(self):
        ctx = context(HEALTHY, sitemap=SITEMAP,
                      headers={"/pricing.html": {"content-type": "text/html",
                                                 "x-robots-tag": "noindex"}})
        self.assertIn("MR-002", ids(MR.run(ctx)))


class TestMR003BrokenLinks(unittest.TestCase):
    def test_fires_on_404_with_referrer(self):
        ctx = context(HEALTHY, sitemap=SITEMAP, link_check_failures=[
            {"url": helpers.HOST + "/gone.html", "status": 404,
             "referrers": [helpers.HOST + "/"]}])
        self.assertIn("MR-003", ids(MR.run(ctx)))

    def test_silent_on_rate_limit(self):
        ctx = context(HEALTHY, sitemap=SITEMAP, link_check_failures=[
            {"url": helpers.HOST + "/slow.html", "status": 429,
             "referrers": [helpers.HOST + "/"]}])
        self.assertNotIn("MR-003", ids(MR.run(ctx)))

    def test_silent_on_timeout_without_status(self):
        ctx = context(HEALTHY, sitemap=SITEMAP, link_check_failures=[
            {"url": helpers.HOST + "/slow.html", "status": 0, "error": "timeout",
             "referrers": [helpers.HOST + "/"]}])
        self.assertNotIn("MR-003", ids(MR.run(ctx)))


class TestMR004Canonical(unittest.TestCase):
    def test_fires_when_dissimilar_pages_share_canonical(self):
        pages = {
            "/": page("Home — Northwind Tools", canonical=helpers.HOST + "/"),
            "/a.html": page("Torque wrench calibration service — Northwind Tools",
                            canonical=helpers.HOST + "/"),
            "/b.html": page("Staff picnic photographs — Northwind Tools",
                            canonical=helpers.HOST + "/",
                            body="The warehouse team closed early on a Saturday and went "
                                 "out to the lake for cricket and food. Forty three people "
                                 "came along including eleven from the night shift who "
                                 "normally never meet the day crew at all during a week."),
        }
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("MR-004", ids(MR.run(ctx)))

    def test_silent_on_trivially_different_canonical(self):
        pages = {"/": page("Home — Northwind Tools",
                           canonical="http://www.example.test/")}
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("MR-004", ids(MR.run(ctx)))

    def test_silent_on_self_canonical(self):
        pages = {"/about.html": page("About — Northwind Tools",
                                     canonical=helpers.HOST + "/about.html")}
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("MR-004", ids(MR.run(ctx)))


SHELL = ('<html lang="en"><head><title>Store finder — Northwind Tools</title></head>'
         '<body><div id="root"></div><script>'
         + 'var padding_for_script_weight = "x";' * 40 +
         '</script></body></html>')


class TestMR005ClientSideRendering(unittest.TestCase):
    def test_fires_on_two_shell_pages(self):
        pages = dict(HEALTHY)
        pages["/store.html"] = SHELL
        pages["/finder.html"] = SHELL.replace("Store finder", "Branch finder")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("MR-005", ids(MR.run(ctx)))

    def test_single_non_core_shell_is_withheld_not_reported(self):
        pages = dict(HEALTHY)
        pages["/store.html"] = SHELL
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("MR-005", ids(MR.run(ctx)))
        self.assertTrue(any(n["defect_id"] == "MR-005" for n in ctx.needs_validation))

    def test_silent_when_script_heavy_page_still_serves_text(self):
        pages = dict(HEALTHY)
        pages["/app.html"] = page("Interactive tool selector — Northwind Tools",
                                  head_extra="<script>" + "var a=1;" * 400 + "</script>")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("MR-005", ids(MR.run(ctx)))

    def test_noscript_fallback_downgrades(self):
        shell_with_fallback = SHELL.replace(
            "<div id=\"root\"></div>",
            "<div id=\"root\"></div><noscript><p>" + "Fallback copy for readers. " * 12
            + "</p></noscript>")
        pages = dict(HEALTHY)
        pages["/store.html"] = shell_with_fallback
        pages["/finder.html"] = shell_with_fallback
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("MR-005", ids(MR.run(ctx)))


class TestMR006Boilerplate(unittest.TestCase):
    def _nav_heavy(self):
        nav = "".join(f'<a href="/cat-{i}.html">Category number {i} of tools</a>'
                      for i in range(70))
        return ('<html lang="en"><head><title>Everything — Northwind Tools</title></head>'
                f'<body><nav>{nav}</nav><main><h1>Everything</h1>'
                '<p>Browse the range below.</p></main></body></html>')

    def test_fires_when_nav_dominates(self):
        pages = dict(HEALTHY)
        pages["/all.html"] = self._nav_heavy()
        pages["/all2.html"] = self._nav_heavy().replace("Everything", "All tools")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("MR-006", ids(MR.run(ctx)))

    def test_silent_on_normal_page_with_navigation(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertNotIn("MR-006", ids(MR.run(ctx)))


class TestMR007PageIdentity(unittest.TestCase):
    def test_fires_on_duplicate_titles_with_different_content(self):
        pages = dict(HEALTHY)
        pages["/x.html"] = page("Shared title — Northwind Tools")
        pages["/y.html"] = page(
            "Shared title — Northwind Tools",
            body="Weekend opening hours change from the start of next month with stores "
                 "opening earlier on Saturday and closing earlier on Sunday. The schedule "
                 "is displayed at every entrance and on the shelf edge notices near the "
                 "checkouts for customers who plan collections in advance.")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("MR-007", ids(MR.run(ctx)))

    def test_silent_when_titles_unique(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertNotIn("MR-007", ids(MR.run(ctx)))

    def test_missing_title_fires(self):
        pages = dict(HEALTHY)
        pages["/x.html"] = page("").replace("<title></title>", "")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("MR-007", ids(MR.run(ctx)))


class TestMR008SitemapDowngrade(unittest.TestCase):
    """A missing sitemap alone is an opportunity, not a defect.

    It becomes a finding only when link-based enumeration is also measurably
    weak — important pages unlinked from the entry page and sitting deep, or an
    entry page that exposes almost no internal destinations.
    """

    def _buried_site(self):
        # homepage links only to /a.html; /pricing.html is reached at depth 3
        home = ('<html lang="en"><head><title>Home — Northwind Tools</title></head><body>'
                '<main><h1>Home</h1><p>Northwind Tools is a workshop tool manufacturer '
                'making calibrated torque wrenches for independent repair shops across '
                'the country every single working day.</p>'
                '<a href="/a.html">Workshop guides index</a>'
                '<a href="/b.html">Calibration laboratory</a>'
                '<a href="/c.html">Socket set range</a>'
                '<a href="/d.html">Delivery information</a>'
                '<a href="/e.html">Warranty terms</a></main></body></html>')
        pages = {"/": home}
        for slug in ("a", "b", "c", "d", "e"):
            pages[f"/{slug}.html"] = page(f"Section {slug} — Northwind Tools")
        pages["/pricing.html"] = page("Tool prices — Northwind Tools")
        return pages

    def test_absent_sitemap_alone_is_not_a_finding(self):
        ctx = context(HEALTHY)
        self.assertNotIn("MR-008", ids(MR.run(ctx)))

    def test_absent_sitemap_alone_is_recorded_as_an_opportunity(self):
        ctx = context(HEALTHY)
        MR.run(ctx)
        notes = [n for n in ctx.needs_validation if n["defect_id"] == "MR-008"]
        self.assertTrue(notes)
        self.assertIn("proactive", notes[0]["why_withheld"])

    def test_fires_when_absence_meets_buried_important_page(self):
        pages = self._buried_site()
        ctx = context(pages)
        for p in ctx.ev.pages:
            if p.path == "/pricing.html":
                p.depth = 3
        found = [f for f in MR.run(ctx) if f.id == "MR-008"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "medium")
        self.assertEqual(found[0].evidence_level, "corroborated")

    def test_fires_at_low_severity_when_entry_page_is_a_dead_end(self):
        thin = ('<html lang="en"><head><title>Home — Northwind Tools</title></head><body>'
                '<main><h1>Home</h1><p>Northwind Tools is a workshop tool manufacturer '
                'that makes calibrated torque wrenches for independent repair shops in '
                'every part of the country.</p>'
                '<a href="/a.html">The only internal link</a></main></body></html>')
        pages = {"/": thin}
        for slug in "abcde":
            pages[f"/{slug}.html"] = page(f"Page {slug} — Northwind Tools")
        ctx = context(pages)
        found = [f for f in MR.run(ctx) if f.id == "MR-008"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "low")

    def test_small_site_with_a_thin_entry_page_is_not_a_finding(self):
        """A three-page site is enumerable by definition; nothing to report."""
        thin = ('<html lang="en"><head><title>Home — Aditi Sharma</title></head><body>'
                '<main><h1>Home</h1><p>Aditi Sharma is a product designer working on '
                'data tools for research teams in universities and public bodies.</p>'
                '<a href="/work.html">Selected project work</a></main></body></html>')
        ctx = context({"/": thin,
                       "/work.html": page("Work — Aditi Sharma"),
                       "/contact.html": page("Contact — Aditi Sharma")})
        self.assertNotIn("MR-008", ids(MR.run(ctx)))

    def test_silent_when_sitemap_present_and_covering(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertNotIn("MR-008", ids(MR.run(ctx)))

    def test_low_sitemap_coverage_is_an_opportunity_not_a_finding(self):
        ctx = context(HEALTHY, sitemap=["/"])
        self.assertNotIn("MR-008", ids(MR.run(ctx)))

    def test_not_checked_in_page_scope(self):
        ctx = context(HEALTHY, scope="page")
        self.assertNotIn("MR-008", ids(MR.run(ctx)))
        self.assertFalse([n for n in ctx.needs_validation if n["defect_id"] == "MR-008"])


class TestMR009AnchorText(unittest.TestCase):
    def _weak_links_page(self, count=30, describe_elsewhere=False):
        links = "".join(f'<a href="/p-{i}.html">Click here</a>' for i in range(count))
        if describe_elsewhere:
            links += "".join(
                f'<a href="/p-{i}.html">Torque wrench guide number {i}</a>'
                for i in range(count))
        return ('<html lang="en"><head><title>Resources — Northwind Tools</title></head>'
                f'<body><main><h1>Resources</h1><p>Useful pages about calibration and '
                f'workshop practice are listed below for readers who want more detail on '
                f'torque and fasteners.</p>{links}</main></body></html>')

    def test_fires_on_stock_anchor_text(self):
        ctx = context({"/": self._weak_links_page()}, sitemap=SITEMAP)
        self.assertIn("MR-009", ids(MR.run(ctx)))

    def test_silent_when_the_destination_is_described_elsewhere(self):
        """A "Click here" beside a descriptive link to the same page loses nothing."""
        ctx = context({"/": self._weak_links_page(describe_elsewhere=True)},
                      sitemap=SITEMAP)
        self.assertNotIn("MR-009", ids(MR.run(ctx)))

    def test_silent_on_descriptive_anchors(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertNotIn("MR-009", ids(MR.run(ctx)))

    def test_silent_below_minimum_anchor_count(self):
        ctx = context({"/": self._weak_links_page(count=20)}, sitemap=SITEMAP)
        self.assertNotIn("MR-009", ids(MR.run(ctx)))


if __name__ == "__main__":
    unittest.main()
