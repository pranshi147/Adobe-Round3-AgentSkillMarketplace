import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from evidencekit.crawl import (  # noqa: E402
    count_lastmod, is_crawlable_candidate, normalize_url, parse_sitemap,
    path_importance, same_site, url_template)
from evidencekit.fetch import DEFAULT_UA, FetchResult, Fetcher, RobotsInfo  # noqa: E402


class TestUrlNormalisation(unittest.TestCase):
    def test_fragment_and_tracking_removed(self):
        self.assertEqual(
            normalize_url("http://a.test/p?utm_source=x&id=7#frag"),
            "http://a.test/p?id=7")

    def test_trailing_slash_and_case(self):
        self.assertEqual(normalize_url("HTTP://A.TEST/path/"), "http://a.test/path")

    def test_default_ports_dropped(self):
        self.assertEqual(normalize_url("http://a.test:80/x"), "http://a.test/x")

    def test_relative_resolved_against_base(self):
        self.assertEqual(normalize_url("/b.html", "http://a.test/dir/a.html"),
                         "http://a.test/b.html")

    def test_non_http_scheme_rejected(self):
        self.assertEqual(normalize_url("ftp://a.test/x"), "")

    def test_same_site_ignores_www(self):
        self.assertTrue(same_site("http://www.a.test/x", "http://a.test/"))
        self.assertFalse(same_site("http://b.test/x", "http://a.test/"))


class TestTemplatesAndImportance(unittest.TestCase):
    def test_slug_collapsed(self):
        self.assertEqual(url_template("http://a.test/blog/2026-my-long-post-name-here"),
                         "/blog/{slug}")

    def test_stable_segments_kept(self):
        self.assertEqual(url_template("http://a.test/about"), "/about")

    def test_homepage_is_most_important(self):
        self.assertGreater(path_importance("http://a.test/"),
                           path_importance("http://a.test/about"))

    def test_depth_penalty(self):
        self.assertGreater(path_importance("http://a.test/about"),
                           path_importance("http://a.test/x/y/z/about"))

    def test_assets_and_utility_excluded(self):
        self.assertFalse(is_crawlable_candidate("http://a.test/app.js"))
        self.assertFalse(is_crawlable_candidate("http://a.test/checkout"))
        self.assertFalse(is_crawlable_candidate("http://a.test/my-account/orders"))
        self.assertTrue(is_crawlable_candidate("http://a.test/pricing"))


class TestSitemap(unittest.TestCase):
    URLSET = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>http://a.test/one</loc><lastmod>2026-01-02</lastmod></url>
      <url><loc>/two</loc></url>
    </urlset>"""

    INDEX = """<?xml version="1.0"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>http://a.test/sm1.xml</loc></sitemap>
    </sitemapindex>"""

    def test_urlset_parsed_and_relative_resolved(self):
        children, pages = parse_sitemap(self.URLSET, "http://a.test/sitemap.xml")
        self.assertEqual(children, [])
        self.assertEqual(pages, ["http://a.test/one", "http://a.test/two"])

    def test_sitemap_index_returns_children(self):
        children, pages = parse_sitemap(self.INDEX, "http://a.test/sitemap.xml")
        self.assertEqual(children, ["http://a.test/sm1.xml"])
        self.assertEqual(pages, [])

    def test_malformed_xml_falls_back_to_scan(self):
        broken = "<urlset><url><loc>http://a.test/x</loc></url>"
        _, pages = parse_sitemap(broken, "http://a.test/sitemap.xml")
        self.assertEqual(pages, ["http://a.test/x"])

    def test_html_is_not_a_sitemap(self):
        children, pages = parse_sitemap("<html><body>nope</body></html>",
                                        "http://a.test/sitemap.xml")
        self.assertEqual((children, pages), ([], []))

    def test_lastmod_counted(self):
        self.assertEqual(count_lastmod(self.URLSET), 1)


class TestRobots(unittest.TestCase):
    TEXT = ("User-agent: *\n"
            "Disallow: /guides/\n"
            "Disallow: /cart\n"
            "Crawl-delay: 1\n"
            "Sitemap: http://a.test/sitemap.xml\n")

    def setUp(self):
        self.robots = RobotsInfo("http://a.test", 200, self.TEXT, present=True)

    def test_disallowed_path_blocked(self):
        self.assertFalse(self.robots.allowed("http://a.test/guides/x", DEFAULT_UA))

    def test_other_paths_allowed(self):
        self.assertTrue(self.robots.allowed("http://a.test/pricing", DEFAULT_UA))

    def test_blocking_rule_reported_verbatim(self):
        rule = self.robots.blocking_rule("http://a.test/guides/x", DEFAULT_UA)
        self.assertEqual(rule[1], "Disallow: /guides/")

    def test_sitemap_and_crawl_delay_parsed(self):
        self.assertEqual(self.robots.sitemaps, ["http://a.test/sitemap.xml"])
        self.assertEqual(self.robots.crawl_delay, 1.0)

    def test_missing_robots_allows_everything(self):
        absent = RobotsInfo.from_fetch("http://a.test",
                                       FetchResult(url="r", status=404))
        self.assertFalse(absent.present)
        self.assertTrue(absent.allowed("http://a.test/anything", DEFAULT_UA))

    def test_server_error_marked_unknown(self):
        info = RobotsInfo.from_fetch("http://a.test", FetchResult(url="r", status=503))
        self.assertTrue(info.unknown)


class TestFetcherSafety(unittest.TestCase):
    def test_write_methods_refused(self):
        f = Fetcher()
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            with self.assertRaises(ValueError):
                f.fetch("http://a.test/", method=method)

    def test_unsupported_scheme_returns_error_not_exception(self):
        res = Fetcher().fetch("file:///etc/passwd")
        self.assertFalse(res.ok)
        self.assertIn("unsupported scheme", res.error)


if __name__ == "__main__":
    unittest.main()
