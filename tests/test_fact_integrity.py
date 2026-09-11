import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import helpers  # noqa: E402
from helpers import context, ids, page  # noqa: E402
from test_machine_readability import HEALTHY, SITEMAP  # noqa: E402

FI = helpers.load_detectors("fact-integrity")

ORG_LD = ('<script type="application/ld+json">{"@context":"https://schema.org",'
          '"@type":"Organization","name":"Northwind Tools","description":'
          '"Northwind Tools manufactures calibrated torque wrenches and precision hand '
          'tools for independent vehicle repair workshops across India since 2011."}'
          '</script>')

LONG_BODY = (
    "Orders placed before two in the afternoon on a working day are dispatched the same "
    "day from the nearest fulfilment centre that holds the item in stock. Orders placed "
    "after that cutoff, or on a Sunday or a public holiday, are dispatched on the next "
    "working day instead. Delivery to metropolitan addresses normally takes two working "
    "days from dispatch and delivery to other addresses takes three to five working days "
    "depending on the courier network serving that particular pin code. Bulky items such "
    "as furniture and large appliances are moved by a separate freight partner and are "
    "scheduled by telephone before delivery, because somebody must be present to accept "
    "the consignment and check it for transit damage before signing for it. If nobody "
    "is available at the agreed time the consignment returns to the depot and a second "
    "attempt is scheduled at no extra charge to the customer who placed the original "
    "order. A third attempt is charged at the standard freight rate for that route.")

LONG_BODY_ALT = (
    "Three new service counters opened this month across the larger stores, and they "
    "handle returns, exchanges and warranty claims in a single queue instead of sending "
    "people between two separate desks as they did before the change was made. Staff on "
    "the new counters can process a warranty claim from beginning to end, including "
    "printing the replacement authorisation, which previously required a supervisor to "
    "sign the paperwork in a back office away from the shop floor. Early figures suggest "
    "that the average wait has fallen by about a third since the counters opened, though "
    "the sample is small and covers only the first few weeks of operation in three "
    "buildings. We plan to extend the same layout to the remaining stores through the "
    "current quarter, starting with the branches that report the longest queues on a "
    "weekend afternoon when families tend to visit together.")


def healthy_with(**extra):
    pages = dict(HEALTHY)
    pages["/"] = page("Precision hand tools for workshops — Northwind Tools",
                      head_extra=ORG_LD)
    pages.update(extra)
    return pages


class TestHealthySiteIsSilent(unittest.TestCase):
    def test_no_findings_on_clean_site(self):
        ctx = context(healthy_with(), sitemap=SITEMAP)
        self.assertEqual(ids(FI.run(ctx)), set())


class TestFI001EntityNames(unittest.TestCase):
    def test_fires_on_unrelated_names(self):
        conflicting = ('<script type="application/ld+json">{"@type":"Organization",'
                       '"name":"Apex Commerce Pvt Ltd"}</script>')
        pages = {"/": page("Shop everything — Zenith Retail", head_extra=conflicting,
                           site_name="Zenith Retail")}
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("FI-001", ids(FI.run(ctx)))

    def test_silent_on_legal_suffix_variant(self):
        variant = ('<script type="application/ld+json">{"@type":"Organization",'
                   '"name":"Northwind Tools Pvt. Ltd."}</script>')
        pages = {"/": page("Workshop tools — Northwind Tools", head_extra=variant)}
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-001", ids(FI.run(ctx)))

    def test_silent_on_containment_variant(self):
        variant = ('<script type="application/ld+json">{"@type":"Organization",'
                   '"name":"Northwind Tools and Calibration"}</script>')
        pages = {"/": page("Workshop tools — Northwind Tools", head_extra=variant)}
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-001", ids(FI.run(ctx)))


class TestFI002EntityIdentity(unittest.TestCase):
    def test_fires_when_no_markup_and_no_about_page(self):
        pages = {"/": page("Shop everything — Zenith Retail", nav=False,
                           site_name="Zenith Retail")}
        ctx = context(pages, sitemap=["/"])
        self.assertIn("FI-002", ids(FI.run(ctx)))

    def test_silent_when_about_page_exists(self):
        pages = {"/": page("Shop everything — Zenith Retail", site_name="Zenith Retail")}
        ctx = context(pages, sitemap=["/", "/about.html"])
        self.assertNotIn("FI-002", ids(FI.run(ctx)))

    def test_silent_when_organization_markup_exists(self):
        pages = {"/": page("Shop everything — Northwind Tools", nav=False,
                           head_extra=ORG_LD)}
        ctx = context(pages, sitemap=["/"])
        self.assertNotIn("FI-002", ids(FI.run(ctx)))


PRODUCT_LD = ('<script type="application/ld+json">{"@type":"Product",'
              '"name":"Vortex 600W blender","offers":{"@type":"Offer","price":"%s",'
              '"priceCurrency":"INR"}}</script>')
PRODUCT_BODY = ("The Vortex 600W blender costs ₹%s and comes with a one and a half litre "
                "jar, a pulse setting and a two year warranty on the motor unit itself. "
                "The blades are stainless steel and the jar is dishwasher safe on the top "
                "rack of a domestic machine.")


class TestFI003StructuredDataContradiction(unittest.TestCase):
    def test_fires_when_price_differs(self):
        pages = healthy_with(**{"/blender.html": page(
            "Vortex 600W blender — Northwind Tools", h1="Vortex 600W blender",
            head_extra=PRODUCT_LD % "999", body=PRODUCT_BODY % "1,299")})
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("FI-003", ids(FI.run(ctx)))

    def test_silent_when_price_matches(self):
        pages = healthy_with(**{"/blender.html": page(
            "Vortex 600W blender — Northwind Tools", h1="Vortex 600W blender",
            head_extra=PRODUCT_LD % "1299.00", body=PRODUCT_BODY % "1,299")})
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-003", ids(FI.run(ctx)))

    def test_silent_when_no_visible_price_to_contradict(self):
        pages = healthy_with(**{"/blender.html": page(
            "Vortex 600W blender — Northwind Tools", h1="Vortex 600W blender",
            head_extra=PRODUCT_LD % "999")})
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-003", ids(FI.run(ctx)))

    def test_fires_on_availability_contradiction(self):
        ld = ('<script type="application/ld+json">{"@type":"Product",'
              '"name":"Vortex 600W blender","offers":{"@type":"Offer",'
              '"availability":"https://schema.org/InStock"}}</script>')
        body = ("The Vortex 600W blender is out of stock at every warehouse and we cannot "
                "give a restock date yet. Customers who need a blender this week should "
                "look at the alternatives listed further down this page instead of "
                "waiting for this particular model to return to the shelves.")
        pages = healthy_with(**{"/blender.html": page(
            "Vortex 600W blender — Northwind Tools", h1="Vortex 600W blender",
            head_extra=ld, body=body)})
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("FI-003", ids(FI.run(ctx)))


class TestFI004DuplicateContent(unittest.TestCase):
    def test_fires_on_unconsolidated_duplicates(self):
        pages = healthy_with(**{
            "/shipping.html": page("Shipping policy — Northwind Tools", body=LONG_BODY,
                                   canonical=helpers.HOST + "/shipping.html"),
            "/delivery.html": page("Delivery policy — Northwind Tools", body=LONG_BODY,
                                   canonical=helpers.HOST + "/delivery.html"),
        })
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("FI-004", ids(FI.run(ctx)))

    def test_silent_when_canonical_consolidates(self):
        pages = healthy_with(**{
            "/shipping.html": page("Shipping policy — Northwind Tools", body=LONG_BODY,
                                   canonical=helpers.HOST + "/shipping.html"),
            "/delivery.html": page("Delivery policy — Northwind Tools", body=LONG_BODY,
                                   canonical=helpers.HOST + "/shipping.html"),
        })
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-004", ids(FI.run(ctx)))

    def test_silent_on_different_content(self):
        ctx = context(healthy_with(), sitemap=SITEMAP)
        self.assertNotIn("FI-004", ids(FI.run(ctx)))


TIMELY_BODY = ("The latest stock arrives every week and the current price list is shown "
               "below for every product we hold in the warehouse today. Members get early "
               "access to seasonal reductions before they are published for everyone else, "
               "and the selection rotates on a Monday morning without exception.")


class TestFI005Freshness(unittest.TestCase):
    def test_fires_when_timeliness_claimed_without_date(self):
        pages = healthy_with(**{
            "/news-a.html": page("Store news one — Northwind Tools", body=TIMELY_BODY),
            "/news-b.html": page("Store news two — Northwind Tools", body=TIMELY_BODY),
        })
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("FI-005", ids(FI.run(ctx)))

    def test_silent_when_time_element_present(self):
        dated = TIMELY_BODY + ' Updated <time datetime="2026-08-14">14 August 2026</time>.'
        pages = healthy_with(**{
            "/news-a.html": page("Store news one — Northwind Tools", body=dated),
            "/news-b.html": page("Store news two — Northwind Tools", body=dated),
        })
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-005", ids(FI.run(ctx)))

    def test_evergreen_pages_never_fire(self):
        ctx = context(healthy_with(), sitemap=SITEMAP)
        self.assertNotIn("FI-005", ids(FI.run(ctx)))

    def test_single_non_core_page_is_withheld(self):
        pages = healthy_with(**{
            "/news-a.html": page("Store news one — Northwind Tools", body=TIMELY_BODY)})
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-005", ids(FI.run(ctx)))
        self.assertTrue(any(n["defect_id"] == "FI-005" for n in ctx.needs_validation))


class TestFI006StaleCurrency(unittest.TestCase):
    def test_fires_on_old_date_with_currency_claim(self):
        old = ('<script type="application/ld+json">{"@type":"WebPage",'
               '"dateModified":"2021-01-05"}</script>')
        body = ("This is the current price list and the latest specification for every "
                "wrench we sell, including the calibration fee for tools bought elsewhere "
                "and brought to our laboratory for measurement before a certificate is "
                "issued to the workshop that owns them.")
        pages = healthy_with(**{"/prices-old.html": page(
            "Current prices — Northwind Tools", head_extra=old, body=body)})
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("FI-006", ids(FI.run(ctx)))

    def test_silent_on_recent_date(self):
        recent = ('<script type="application/ld+json">{"@type":"WebPage",'
                  '"dateModified":"%s"}</script>' % dt.date.today().isoformat())
        body = "This is the current price list and the latest specification for wrenches."
        pages = healthy_with(**{"/prices-new.html": page(
            "Current prices — Northwind Tools", head_extra=recent, body=body)})
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-006", ids(FI.run(ctx)))

    def test_silent_on_old_date_without_currency_claim(self):
        old = ('<script type="application/ld+json">{"@type":"WebPage",'
               '"dateModified":"2021-01-05"}</script>')
        pages = healthy_with(**{"/history.html": page(
            "Company history — Northwind Tools", head_extra=old)})
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-006", ids(FI.run(ctx)))


class TestFI007Attribution(unittest.TestCase):
    def test_fires_on_unattributed_editorial_pages(self):
        pages = healthy_with(**{
            "/blog/one.html": page("Store news one — Northwind Tools", body=LONG_BODY),
            "/blog/two.html": page("Store news two — Northwind Tools", body=LONG_BODY_ALT),
        })
        ctx = context(pages, sitemap=SITEMAP)
        self.assertIn("FI-007", ids(FI.run(ctx)))

    def test_silent_when_author_declared(self):
        author = ('<script type="application/ld+json">{"@type":"BlogPosting",'
                  '"author":{"@type":"Person","name":"Meera Ranganathan"},'
                  '"publisher":{"@type":"Organization","name":"Northwind Tools"}}</script>')
        pages = healthy_with(**{
            "/blog/one.html": page("Store news one — Northwind Tools", body=LONG_BODY,
                                   head_extra=author),
            "/blog/two.html": page("Store news two — Northwind Tools", body=LONG_BODY_ALT,
                                   head_extra=author),
        })
        ctx = context(pages, sitemap=SITEMAP)
        self.assertNotIn("FI-007", ids(FI.run(ctx)))

    def test_product_pages_are_not_editorial(self):
        ctx = context(healthy_with(), sitemap=SITEMAP)
        self.assertNotIn("FI-007", ids(FI.run(ctx)))


if __name__ == "__main__":
    unittest.main()
