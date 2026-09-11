import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import helpers  # noqa: E402
from helpers import context, ids, page  # noqa: E402
from test_machine_readability import HEALTHY, SITEMAP  # noqa: E402

AX = helpers.load_detectors("arrival-experience")

PICNIC = ("Every winter the warehouse team closes early on a Saturday and heads out to the "
          "lake for an afternoon of cricket, food and an argument about who packed the ice. "
          "This year forty three people came along, including eleven from the night shift "
          "who normally never meet the day crew at all. The cricket was won by the returns "
          "desk, which nobody expected, and the cooking was handled by a rotating group of "
          "volunteers who started before sunrise on the day.")

LONG_POLICY = (
    "Orders placed before two in the afternoon on a working day are dispatched the same "
    "day from the nearest fulfilment centre that holds the item in stock at that moment. "
    "Orders placed after that cutoff, or on a Sunday or a public holiday, are dispatched "
    "on the next working day instead of the same evening. Delivery to metropolitan "
    "addresses normally takes two working days from dispatch, and delivery to other "
    "addresses takes three to five working days depending on the courier network serving "
    "that particular pin code. Bulky items such as furniture and large appliances are "
    "moved by a separate freight partner and are scheduled by telephone before delivery, "
    "because somebody must be present to accept the consignment and check it for transit "
    "damage before signing the paperwork. If nobody is available at the agreed time the "
    "consignment returns to the depot and a second attempt is scheduled at no extra "
    "charge to the customer who placed the original order for the goods.")

NO_DEFINITION = ("Welcome. Thousands of products across kitchen, home, tools and outdoor. "
                 "Free delivery on orders above four hundred and ninety nine rupees. Shop "
                 "by category, save your favourites, and check back often. Members get "
                 "early access to seasonal price drops before they go live for everybody.")


class TestHealthySiteIsSilent(unittest.TestCase):
    def test_no_findings_on_clean_site(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertEqual(ids(AX.run(ctx)), set())


class TestAX001IntentMismatch(unittest.TestCase):
    def test_fires_when_title_promises_absent_subject(self):
        pages = dict(HEALTHY)
        pages["/wholesale.html"] = page(
            "Wholesale stainless steel fasteners bulk supply — Northwind Tools",
            h1="Our staff picnic in pictures", body=PICNIC)
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("AX-001", ids(AX.run(ctx)))

    def test_silent_when_title_and_body_agree(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertNotIn("AX-001", ids(AX.run(ctx)))

    def test_brand_tokens_do_not_create_a_mismatch(self):
        pages = dict(HEALTHY)
        pages["/x.html"] = page("Northwind Tools Northwind Tools — Northwind Tools",
                                h1="Calibration laboratory")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("AX-001", ids(AX.run(ctx)))

    def test_thin_pages_excluded(self):
        html = ('<html lang="en"><head><title>Bulk fastener supply for industry</title>'
                '</head><body><main><h1>Picnic</h1><p>Short note.</p></main></body></html>')
        ctx = context({"/": html}, sitemap=SITEMAP)
        self.assertNotIn("AX-001", ids(AX.run(ctx)))


class TestAX002OrientationGap(unittest.TestCase):
    def test_fires_on_core_page_without_definitional_sentence(self):
        ctx = context({"/": page("Shop everything — Zenith Retail", body=NO_DEFINITION,
                                 site_name="Zenith Retail")}, sitemap=SITEMAP)
        self.assertIn("AX-002", ids(AX.run(ctx)))

    def test_silent_when_definition_present(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertNotIn("AX-002", ids(AX.run(ctx)))

    def test_listing_templates_excluded(self):
        pages = dict(HEALTHY)
        pages["/blog/index.html"] = page("Blog — Northwind Tools", body=NO_DEFINITION)
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("AX-002", ids(AX.run(ctx)))

    def test_definition_only_in_meta_is_low_severity(self):
        desc = ('<meta name="description" content="Zenith Retail is a general retailer '
                'selling kitchen, home and outdoor products across India.">')
        ctx = context({"/": page("Shop everything — Zenith Retail", body=NO_DEFINITION,
                                 head_extra=desc, site_name="Zenith Retail")},
                      sitemap=SITEMAP)
        found = [f for f in AX.run(ctx) if f.id == "AX-002"]
        self.assertEqual(found[0].severity, "low")


class TestAX003DeadEnds(unittest.TestCase):
    def _dead_page(self, title):
        return page(title, main_links=0, body=LONG_POLICY)

    def test_fires_when_most_content_pages_are_dead_ends(self):
        pages = {"/": self._dead_page("Shipping — Northwind Tools"),
                 "/a.html": self._dead_page("Returns — Northwind Tools"),
                 "/b.html": self._dead_page("Warranty — Northwind Tools")}
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("AX-003", ids(AX.run(ctx)))

    def test_isolated_dead_end_is_withheld(self):
        pages = dict(HEALTHY)
        pages["/a.html"] = page("Shipping policy — Northwind Tools", body=LONG_POLICY,
                                main_links=0)
        for slug, title in (("b", "Returns policy"), ("c", "Warranty terms"),
                            ("d", "Installation notes")):
            pages[f"/{slug}.html"] = page(f"{title} — Northwind Tools",
                                          body=f"{title} are described here. " + LONG_POLICY)
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("AX-003", ids(AX.run(ctx)))
        self.assertTrue(any(n["defect_id"] == "AX-003" for n in ctx.needs_validation))

    def test_silent_when_pages_link_onward(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertNotIn("AX-003", ids(AX.run(ctx)))


CITY_PICKER = ('<html lang="en"><head><title>Delivery availability — Zenith Retail</title>'
               '</head><body><main><h1>Delivery availability</h1>'
               '<p>Select your city to see delivery slots and stock.</p>'
               '<label>Choose your city</label>'
               '<select name="city"><option>Delhi NCR</option><option>Mumbai</option>'
               '<option>Pune</option></select><button>Set location</button>'
               '<p>Availability and prices vary by location.</p></main></body></html>')


class TestAX004ContextDependency(unittest.TestCase):
    def test_fires_when_content_is_gated(self):
        ctx = context({"/": CITY_PICKER}, sitemap=SITEMAP)
        self.assertIn("AX-004", ids(AX.run(ctx)))

    def test_silent_when_default_content_is_served(self):
        rich = CITY_PICKER.replace(
            "<p>Availability and prices vary by location.</p>",
            "<p>Availability and prices vary by location. " + LONG_POLICY + "</p>")
        ctx = context({"/": rich}, sitemap=SITEMAP)
        self.assertNotIn("AX-004", ids(AX.run(ctx)))
        self.assertTrue(any(n["defect_id"] == "AX-004" for n in ctx.needs_validation))

    def test_language_switcher_is_not_a_gate(self):
        html = ('<html lang="en"><head><title>Home — Zenith Retail</title></head><body>'
                '<main><h1>Home</h1><select name="language"><option>English</option>'
                '<option>हिन्दी</option></select><p>Short welcome copy.</p></main></body>')
        ctx = context({"/": html}, sitemap=SITEMAP)
        self.assertNotIn("AX-004", ids(AX.run(ctx)))


class TestAX005PromotionalInterference(unittest.TestCase):
    def _promo_page(self, title="Weekly picks — Zenith Retail", path_ok=True):
        block = '<div class="promo-banner"><p>Members save an extra five percent today</p></div>'
        return ('<html lang="en"><head><title>' + title + '</title></head><body><main>'
                '<h1>Weekly picks from the kitchen range</h1>'
                '<p>Our buyers choose a small number of kitchen products each week based on '
                'what sold well in the previous fortnight and what suppliers delivered into '
                'the warehouse during that period.</p>' + block +
                '<p>Items in the weekly selection keep their normal warranty and their normal '
                'return window, so choosing from this list does not change any of the rights '
                'a customer has when buying from us in a store or online.</p>' + block +
                '<p>Stock levels on selected items are limited to whatever the warehouse '
                'holds when the selection goes live, and we do not restock a selected item '
                'in the middle of the week if it sells out early.</p>' + block +
                '</main></body></html>')

    def test_fires_on_repeated_promotional_blocks(self):
        ctx = context({"/": self._promo_page()}, sitemap=SITEMAP)
        self.assertIn("AX-005", ids(AX.run(ctx)))

    def test_silent_on_campaign_landing_pages(self):
        ctx = context({"/offers/weekly.html": self._promo_page("Weekly sale offers")},
                      sitemap=SITEMAP)
        self.assertNotIn("AX-005", ids(AX.run(ctx)))

    def test_silent_on_ordinary_content_pages(self):
        ctx = context(HEALTHY, sitemap=SITEMAP)
        self.assertNotIn("AX-005", ids(AX.run(ctx)))


ACCORDION_TEMPLATE = (
    '<html lang="en"><head><title>{title}</title></head><body><main>'
    '<h1>{h1}</h1><p>Details are below.</p>'
    '<div class="accordion-content"><p>{body}</p></div></main></body></html>')

DETAIL = ("The wrench covers twenty to two hundred and ten newton metres and ships with "
          "a calibration certificate recording the measured deviation at three points. ")


class TestAX006InteractionGatedContent(unittest.TestCase):
    def _gated(self, title, h1="Specifications"):
        return ACCORDION_TEMPLATE.format(title=title, h1=h1, body=DETAIL * 12)

    def test_fires_when_substance_sits_behind_interaction(self):
        pages = dict(HEALTHY)
        pages["/spec-a.html"] = self._gated("Specifications A — Northwind Tools")
        pages["/spec-b.html"] = self._gated("Specifications B — Northwind Tools")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("AX-006", ids(AX.run(ctx)))

    def test_silent_when_the_visible_answer_is_already_substantive(self):
        """Progressive disclosure on top of a real answer is good practice."""
        html = ('<html lang="en"><head><title>Specifications — Northwind Tools</title>'
                '</head><body><main><h1>Specifications</h1><p>' + DETAIL * 10 + '</p>'
                '<div class="accordion-content"><p>' + DETAIL * 20 +
                '</p></div></main></body></html>')
        pages = dict(HEALTHY)
        pages["/spec-a.html"] = html
        pages["/spec-b.html"] = html.replace("Specifications", "Materials")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("AX-006", ids(AX.run(ctx)))

    def test_cookie_and_nav_containers_are_not_gated_content(self):
        html = ('<html lang="en"><head><title>Home — Northwind Tools</title></head><body>'
                '<main><h1>Home</h1><p>Short intro copy for the reader.</p>'
                '<div class="cookie-consent" hidden><p>' + DETAIL * 12 + '</p></div>'
                '<div class="nav-drawer" aria-hidden="true"><p>' + DETAIL * 12 +
                '</p></div></main></body></html>')
        ctx = context({"/": html, "/b.html": html}, sitemap=SITEMAP)
        self.assertNotIn("AX-006", ids(AX.run(ctx)))

    def test_small_collapsed_extra_does_not_fire(self):
        html = ('<html lang="en"><head><title>Guide — Northwind Tools</title></head><body>'
                '<main><h1>Guide</h1><p>' + DETAIL * 3 + '</p>'
                '<details><summary>More</summary><p>One short extra note.</p></details>'
                '</main></body></html>')
        ctx = context({"/": html, "/b.html": html}, sitemap=SITEMAP)
        self.assertNotIn("AX-006", ids(AX.run(ctx)))

    def test_isolated_non_core_instance_is_withheld(self):
        pages = dict(HEALTHY)
        pages["/spec-a.html"] = self._gated("Specifications A — Northwind Tools")
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("AX-006", ids(AX.run(ctx)))
        self.assertTrue(any(n["defect_id"] == "AX-006" for n in ctx.needs_validation))


class TestAX007ImportantPagesBuried(unittest.TestCase):
    def _site(self, home_links=("/section.html",)):
        links = "".join(f'<a href="{h}">Section index page for readers</a>'
                        for h in home_links)
        home = ('<html lang="en"><head><title>Home — Northwind Tools</title></head><body>'
                '<main><h1>Home</h1><p>Northwind Tools is a workshop tool manufacturer '
                'making calibrated torque wrenches for independent repair shops in every '
                'part of the country.</p>' + links + '</main></body></html>')
        return {"/": home,
                "/section.html": page("Section — Northwind Tools"),
                "/pricing.html": page("Tool prices — Northwind Tools")}

    def _at_depth(self, ctx, path, depth):
        for p in ctx.ev.pages:
            if p.path == path:
                p.depth = depth

    def test_fires_when_an_important_page_is_unlinked_and_deep(self):
        ctx = context(self._site(), sitemap=["/"])
        self._at_depth(ctx, "/pricing.html", 3)
        found = [f for f in AX.run(ctx) if f.id == "AX-007"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "medium")

    def test_downgraded_to_low_when_a_sitemap_lists_the_page(self):
        ctx = context(self._site(), sitemap=["/", "/pricing.html"])
        self._at_depth(ctx, "/pricing.html", 3)
        found = [f for f in AX.run(ctx) if f.id == "AX-007"]
        self.assertEqual(found[0].severity, "low")

    def test_silent_when_the_homepage_links_to_it(self):
        ctx = context(self._site(home_links=("/section.html", "/pricing.html")),
                      sitemap=["/"])
        self._at_depth(ctx, "/pricing.html", 3)
        self.assertNotIn("AX-007", ids(AX.run(ctx)))

    def test_silent_for_ordinary_deep_content(self):
        pages = self._site()
        pages.pop("/pricing.html")
        pages["/blog/a-long-post.html"] = page("A long post — Northwind Tools")
        ctx = context(pages, sitemap=["/"])
        self._at_depth(ctx, "/blog/a-long-post.html", 4)
        self.assertNotIn("AX-007", ids(AX.run(ctx)))

    def test_silent_when_important_pages_are_shallow(self):
        ctx = context(self._site(), sitemap=["/"])
        self.assertNotIn("AX-007", ids(AX.run(ctx)))


if __name__ == "__main__":
    unittest.main()
