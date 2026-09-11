"""Off-site discoverability tests.

The most important assertions here are the negative ones: absence of external
presence must never become a finding, an unreachable network must never fail
the audit, and a site that declares nothing must be treated as fine.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import helpers  # noqa: E402
from helpers import context, ids, page  # noqa: E402
from evidencekit import entity, external  # noqa: E402
from evidencekit.external import ExternalEvidence, Probe  # noqa: E402

EX = helpers.load_detectors("external-evidence")

ORG = ('<script type="application/ld+json">{"@context":"https://schema.org",'
       '"@type":"Organization","name":"Northwind Tools","url":"%s/",'
       '"sameAs":%s}</script>')


def site(same_as="[]", name="Northwind Tools", extra_org_fields=""):
    org = ('<script type="application/ld+json">{"@type":"Organization","name":"%s",'
           '"url":"%s/"%s,"sameAs":%s}</script>'
           % (name, helpers.HOST, extra_org_fields, same_as))
    return {"/": page(f"Workshop tools — {name}", head_extra=org, site_name=name)}


def with_probes(ctx, probes, performed=True, mode="auto", declared=None):
    ev = ExternalEvidence(mode=mode)
    ev.performed = performed
    ev.declared = declared if declared is not None else [(p.url, "sameAs") for p in probes]
    ev.probes = probes
    ctx.external = ev
    return ctx


def probe(url, status=200, checked=True, title="", text="", site_name="",
          links_back=False, description="", kind="reference", final_url="",
          canonical=""):
    return Probe(url=url, source="sameAs in entity markup", kind=kind, status=status,
                 checked=checked, title=title, text_sample=text, site_name=site_name,
                 links_back=links_back, description=description,
                 final_url=final_url or url, canonical=canonical)


def with_hosts(ctx, host_probes, performed=True):
    ev = ctx.external if ctx.external.performed else ExternalEvidence(mode="auto")
    ev.performed = performed
    ev.host_probes = host_probes
    ctx.external = ev
    return ctx


class TestAbsenceIsNeverAFailure(unittest.TestCase):
    def test_no_declared_identifiers_produces_no_findings(self):
        ctx = context(site())
        ctx.external = external.collect(_NoNetworkFetcher(), [], mode="auto")
        self.assertEqual(ids(EX.run(ctx)), set())

    def test_no_declared_identifiers_is_recorded_as_a_non_defect(self):
        ev = external.collect(_NoNetworkFetcher(), [], mode="auto")
        self.assertTrue(ev.performed)
        self.assertIn("not treated as a defect", " ".join(ev.limitations))

    def test_external_findings_need_a_completed_probe(self):
        ctx = with_probes(context(site()), [], performed=False, mode="off")
        self.assertEqual(ids(EX.run(ctx)), set())


class TestGracefulDegradation(unittest.TestCase):
    def test_mode_off_makes_no_requests(self):
        fetcher = _CountingFetcher()
        ev = external.collect(fetcher, [("https://profile.test/x", "sameAs")], mode="off")
        self.assertEqual(fetcher.calls, 0)
        self.assertFalse(ev.performed)
        self.assertIn("disabled", " ".join(ev.limitations))

    def test_network_failure_is_a_limitation_not_a_finding(self):
        ev = external.collect(_NoNetworkFetcher(),
                              [("https://profile.test/x", "sameAs")], mode="auto")
        self.assertEqual(len(ev.checked_probes), 0)
        self.assertTrue(any("could not be completed" in l for l in ev.limitations))
        ctx = context(site())
        ctx.external = ev
        self.assertEqual(ids(EX.run(ctx)), set())

    def test_probe_limit_is_respected_and_reported(self):
        declared = [(f"https://profile.test/{i}", "sameAs") for i in range(9)]
        ev = external.collect(_OkFetcher(), declared, limit=3, mode="auto")
        self.assertEqual(len(ev.probes), 3)
        self.assertTrue(any("first 3 were probed" in l for l in ev.limitations))

    def test_summary_states_the_scope_boundary(self):
        summary = external.collect(_OkFetcher(), [], mode="auto").summary()
        self.assertIn("No search engine", summary["scope_note"])


class TestEX001Unreachable(unittest.TestCase):
    def test_fires_on_a_dead_declared_profile(self):
        ctx = with_probes(context(site()), [probe("https://profile.test/gone", status=404)])
        self.assertIn("EX-001", ids(EX.run(ctx)))

    def test_platform_refusal_is_not_a_dead_profile(self):
        for status in (401, 403, 405, 429, 451):
            ctx = with_probes(context(site()),
                              [probe("https://profile.test/x", status=status)])
            self.assertNotIn("EX-001", ids(EX.run(ctx)), f"status {status}")

    def test_working_profile_is_silent(self):
        ctx = with_probes(context(site()),
                          [probe("https://profile.test/x", title="Northwind Tools")])
        self.assertNotIn("EX-001", ids(EX.run(ctx)))


class TestEX002Corroboration(unittest.TestCase):
    def test_fires_when_the_profile_never_names_the_brand(self):
        ctx = with_probes(context(site()), [
            probe("https://profile.test/a", title="Riverbend Cycling Club",
                  text="The club meets on Sunday mornings at the north gate."),
            probe("https://profile.test/b", title="Unrelated directory listing",
                  text="A page about something else entirely."),
        ])
        self.assertIn("EX-002", ids(EX.run(ctx)))

    def test_silent_when_the_title_names_the_brand(self):
        ctx = with_probes(context(site()),
                          [probe("https://profile.test/a", title="Northwind Tools | Profile")])
        self.assertNotIn("EX-002", ids(EX.run(ctx)))

    def test_silent_when_the_brand_appears_only_in_the_url_path(self):
        ctx = with_probes(context(site()),
                          [probe("https://profile.test/company/northwind-tools",
                                 title="Profile", text="Some platform boilerplate.")])
        self.assertNotIn("EX-002", ids(EX.run(ctx)))

    def test_legal_suffix_variant_still_corroborates(self):
        ctx = with_probes(context(site()),
                          [probe("https://profile.test/a", title="Northwind Tools Pvt. Ltd.")])
        self.assertNotIn("EX-002", ids(EX.run(ctx)))

    def test_unreadable_destination_is_not_a_failure_to_corroborate(self):
        ctx = with_probes(context(site()), [probe("https://profile.test/a")])  # no text
        self.assertNotIn("EX-002", ids(EX.run(ctx)))


class TestEX003Ambiguity(unittest.TestCase):
    def test_fires_on_common_word_name_with_no_disambiguators(self):
        pages = {"/": page("Bright Harbor — home",
                           head_extra='<meta property="og:site_name" content="Bright Harbor">',
                           site_name="Bright Harbor")}
        ctx = context(pages)
        self.assertIn("EX-003", ids(EX.run(ctx)))

    def test_one_disambiguator_of_any_kind_suppresses_it(self):
        for field in ('"foundingDate":"2011"', '"legalName":"Bright Harbor Pvt Ltd"',
                      '"sameAs":["https://profile.test/bh"]', '"areaServed":"India"'):
            org = ('<script type="application/ld+json">{"@type":"Organization",'
                   '"name":"Bright Harbor",%s}</script>' % field)
            ctx = context({"/": page("Bright Harbor — home", head_extra=org,
                                     site_name="Bright Harbor")})
            self.assertNotIn("EX-003", ids(EX.run(ctx)), field)

    def test_distinctive_name_never_fires(self):
        ctx = context(site(name="Northwind Tools"))
        self.assertNotIn("EX-003", ids(EX.run(ctx)))

    def test_ambiguity_scoring_is_about_the_name_only(self):
        self.assertTrue(entity.name_is_ambiguous("bright harbor")[0])
        self.assertTrue(entity.name_is_ambiguous("arc")[0])
        self.assertFalse(entity.name_is_ambiguous("northwind tools")[0])
        self.assertFalse(entity.name_is_ambiguous("zyllex")[0])


class TestEX004DomainBridge(unittest.TestCase):
    def test_fires_when_domain_and_brand_are_unrelated_and_unbridged(self):
        org = ('<script type="application/ld+json">{"@type":"Organization",'
               '"name":"Northwind Tools"}</script>')
        ctx = context({"/": page("Workshop tools — Northwind Tools", head_extra=org)})
        self.assertIn("EX-004", ids(EX.run(ctx)))

    def test_entity_url_is_the_bridge_and_suppresses_it(self):
        ctx = context(site())
        self.assertNotIn("EX-004", ids(EX.run(ctx)))

    def test_matching_domain_never_fires(self):
        org = ('<script type="application/ld+json">{"@type":"Organization",'
               '"name":"Example"}</script>')
        ctx = context({"/": page("Home — Example", head_extra=org, site_name="Example")})
        self.assertNotIn("EX-004", ids(EX.run(ctx)))

    def test_domain_label_handles_suffixes_and_ip_hosts(self):
        self.assertEqual(entity.domain_label("https://www.example.co.uk/x"), "example")
        self.assertEqual(entity.domain_label("https://shop.example.com/x"), "example")
        self.assertEqual(entity.domain_label("http://127.0.0.1:8080/x"), "")


class TestDeclaredIdentifierCollection(unittest.TestCase):
    def test_only_site_declared_urls_are_collected(self):
        ctx = context(site(same_as='["https://profile.test/a","https://profile.test/b"]'))
        declared = entity.declared_entity_urls(ctx)
        self.assertEqual([u for u, _s in declared],
                         ["https://profile.test/a", "https://profile.test/b"])

    def test_ordinary_page_links_are_not_treated_as_identifiers(self):
        ctx = context({"/": page("Home — Northwind Tools",
                                 head_extra='<script type="application/ld+json">'
                                            '{"@type":"Organization","name":"Northwind Tools"}'
                                            '</script>')})
        self.assertEqual(entity.declared_entity_urls(ctx), [])


class TestOffSiteDiscoverabilitySurface(unittest.TestCase):
    """The six scenarios an off-site capability has to get right."""

    def test_strong_external_discoverability_is_silent(self):
        """Resolving, brand-naming, mutually-linked references: nothing to report."""
        ctx = with_probes(context(site(same_as='["https://profile.test/nw"]')), [
            probe("https://profile.test/nw", title="Northwind Tools",
                  text="Northwind Tools makes calibrated torque wrenches.",
                  links_back=True, description="Northwind Tools manufactures calibrated "
                                               "torque wrenches for repair workshops."),
            probe("https://registry.test/northwind", title="Northwind Tools — register entry",
                  text="Northwind Tools, incorporated 2011.", links_back=True,
                  description="Registry entry for Northwind Tools, a tool manufacturer."),
        ])
        with_hosts(ctx, [probe("https://www.example.test/", kind="hostname",
                               final_url="http://example.test/")])
        self.assertEqual(ids(EX.run(ctx)), set())

    def test_missing_external_references_is_never_a_defect(self):
        ctx = context(site())
        ctx.external = external.collect(_NoNetworkFetcher(), [], mode="auto")
        self.assertEqual(ids(EX.run(ctx)), set())
        self.assertIn("not treated as a defect", " ".join(ctx.external.limitations))

    def test_conflicting_entity_identity_is_reported(self):
        """An external record that resolves but describes a different entity."""
        ctx = with_probes(context(site()), [
            probe("https://profile.test/a", title="Riverbend Cycling Club",
                  text="The club meets on Sunday mornings.", links_back=True),
            probe("https://profile.test/b", title="Halden Freight Services",
                  text="Pallet delivery across the region.", links_back=True),
        ])
        self.assertIn("EX-002", ids(EX.run(ctx)))

    def test_unreachable_external_reference_is_reported(self):
        ctx = with_probes(context(site()), [probe("https://profile.test/gone", status=404)])
        found = [f for f in EX.run(ctx) if f.id == "EX-001"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].evidence_level, "verified")

    def test_consistent_independent_sources_are_silent(self):
        """Different platforms, same entity, all pointing home."""
        ctx = with_probes(context(site()), [
            probe("https://a.test/northwind-tools", title="Northwind Tools",
                  links_back=True, description="Calibrated torque wrenches from Pune."),
            probe("https://b.test/company/northwind", title="Northwind Tools Pvt. Ltd.",
                  links_back=True, description="Tool manufacturer serving repair workshops."),
            probe("https://c.test/nw", title="Northwind Tools profile",
                  links_back=True, description="Workshop tools and calibration services."),
        ])
        self.assertEqual(ids(EX.run(ctx)), set())

    def test_no_finding_is_produced_from_absence_alone(self):
        """False-positive control: nothing declared, nothing resolved, nothing claimed."""
        ctx = with_probes(context(site()), [], performed=True, declared=[])
        findings = EX.run(ctx)
        self.assertEqual([f.id for f in findings], [])


class TestEX005CanonicalDomain(unittest.TestCase):
    def test_fires_when_the_other_hostname_serves_a_separate_site(self):
        ctx = with_hosts(with_probes(context(site()), []), [
            probe("https://www.example.test/", kind="hostname", status=200,
                  final_url="https://www.example.test/", title="Something else")])
        found = [f for f in EX.run(ctx) if f.id == "EX-005"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "medium")

    def test_silent_when_the_variant_redirects_home(self):
        ctx = with_hosts(with_probes(context(site()), []), [
            probe("https://www.example.test/", kind="hostname", status=200,
                  final_url="http://example.test/")])
        self.assertNotIn("EX-005", ids(EX.run(ctx)))

    def test_silent_when_the_variant_canonicalises_home(self):
        ctx = with_hosts(with_probes(context(site()), []), [
            probe("https://www.example.test/", kind="hostname", status=200,
                  final_url="https://www.example.test/",
                  canonical="http://example.test/")])
        self.assertNotIn("EX-005", ids(EX.run(ctx)))

    def test_silent_when_the_variant_does_not_resolve(self):
        """Serving only one hostname form is normal and correct."""
        for status in (0, 404, 500):
            ctx = with_hosts(with_probes(context(site()), []), [
                probe("https://www.example.test/", kind="hostname", status=status,
                      checked=bool(status))])
            self.assertNotIn("EX-005", ids(EX.run(ctx)), f"status {status}")

    def test_no_variant_exists_for_an_ip_host(self):
        from evidencekit.entity import hostname_variants
        self.assertEqual(hostname_variants("http://127.0.0.1:8080/"), [])


class TestEX006Reciprocity(unittest.TestCase):
    def test_fires_when_two_references_never_point_back(self):
        ctx = with_probes(context(site()), [
            probe("https://a.test/northwind", title="Northwind Tools", links_back=False),
            probe("https://b.test/northwind", title="Northwind Tools", links_back=False),
        ])
        found = [f for f in EX.run(ctx) if f.id == "EX-006"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "low")

    def test_a_single_one_way_reference_is_not_enough(self):
        ctx = with_probes(context(site()), [
            probe("https://a.test/northwind", title="Northwind Tools", links_back=False),
            probe("https://b.test/northwind", title="Northwind Tools", links_back=True),
        ])
        self.assertNotIn("EX-006", ids(EX.run(ctx)))

    def test_unreadable_references_do_not_count_as_one_way(self):
        ctx = with_probes(context(site()), [
            probe("https://a.test/x"), probe("https://b.test/x")])   # no title/text
        self.assertNotIn("EX-006", ids(EX.run(ctx)))

    def test_back_reference_detection_accepts_a_link_or_bare_domain(self):
        from evidencekit.external import _references_host
        from evidencekit.htmlparse import parse_html
        linked = parse_html("https://a.test/p",
                            '<main><a href="https://example.test/">site</a></main>')
        in_text = parse_html("https://a.test/p", "<main><p>See example.test for more.</p></main>")
        neither = parse_html("https://a.test/p", "<main><p>No reference at all.</p></main>")
        self.assertTrue(_references_host(linked, "example.test"))
        self.assertTrue(_references_host(in_text, "example.test"))
        self.assertFalse(_references_host(neither, "example.test"))


class TestReferenceCollectionBreadth(unittest.TestCase):
    def test_standard_link_rels_count_as_declared_references(self):
        head = ('<link rel="me" href="https://a.test/nw">'
                '<link rel="publisher" href="https://b.test/nw">')
        ctx = context({"/": page("Home — Northwind Tools", head_extra=head)})
        urls = [u for u, _s in entity.declared_entity_urls(ctx)]
        self.assertIn("https://a.test/nw", urls)
        self.assertIn("https://b.test/nw", urls)

    def test_same_site_alternate_is_not_an_external_reference(self):
        head = f'<link rel="alternate" href="{helpers.HOST}/feed.xml">'
        ctx = context({"/": page("Home — Northwind Tools", head_extra=head)})
        self.assertEqual(entity.declared_entity_urls(ctx), [])

    def test_probe_budget_covers_references_and_hostnames_separately(self):
        declared = [(f"https://p{i}.test/", "sameAs") for i in range(9)]
        ev = external.collect(_OkFetcher(), declared, limit=6, mode="auto",
                              origin="https://example.test/", host_limit=2)
        self.assertEqual(len(ev.probes), 6)
        self.assertLessEqual(len(ev.host_probes), 2)
        self.assertLessEqual(len(ev.probes) + len(ev.host_probes), 8)

    def test_mode_off_probes_no_hostname_variant_either(self):
        fetcher = _CountingFetcher()
        ev = external.collect(fetcher, [("https://p.test/", "sameAs")], mode="off",
                              origin="https://example.test/")
        self.assertEqual(fetcher.calls, 0)
        self.assertEqual(ev.host_probes, [])


class _NoNetworkFetcher:
    user_agent = "test"

    def out_of_time(self):
        return False

    def fetch(self, url, **kwargs):
        from evidencekit.fetch import FetchResult
        return FetchResult(url=url, error="network error: sandbox has no egress")


class _CountingFetcher(_NoNetworkFetcher):
    def __init__(self):
        self.calls = 0

    def fetch(self, url, **kwargs):
        self.calls += 1
        return super().fetch(url)


class _OkFetcher(_NoNetworkFetcher):
    def fetch(self, url, **kwargs):
        from evidencekit.fetch import FetchResult
        return FetchResult(url=url, final_url=url, status=200,
                           headers={"content-type": "text/html"},
                           body="<html><head><title>Northwind Tools</title></head></html>")


if __name__ == "__main__":
    unittest.main()
