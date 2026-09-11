import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from evidencekit.htmlparse import (  # noqa: E402
    context_gate_signals, has_cta, parse_html)

BASE = "http://example.test/page.html"


class TestIdentityExtraction(unittest.TestCase):
    def test_title_meta_canonical_lang(self):
        doc = parse_html(BASE, '<html lang="en-IN"><head><title>A title</title>'
                               '<meta name="description" content="D">'
                               '<meta property="og:site_name" content="Brand">'
                               '<link rel="canonical" href="/canon.html">'
                               '</head><body><main><p>hello</p></main></body></html>')
        self.assertEqual(doc.title, "A title")
        self.assertEqual(doc.meta_get("description"), "D")
        self.assertEqual(doc.meta_get("og:site_name"), "Brand")
        self.assertEqual(doc.canonical, "http://example.test/canon.html")
        self.assertEqual(doc.lang, "en-in")

    def test_robots_directives_from_markup_and_header(self):
        doc = parse_html(BASE, '<head><meta name="robots" content="noindex, follow"></head>',
                         headers={"X-Robots-Tag": "noarchive"})
        self.assertIn("noindex", doc.robots_directives())
        self.assertIn("noarchive", doc.robots_directives())

    def test_headings_collected_with_levels(self):
        doc = parse_html(BASE, "<main><h1>One</h1><h2>Two</h2><h2>Three</h2></main>")
        self.assertEqual(doc.h1s, ["One"])
        self.assertEqual([t for lvl, t in doc.headings if lvl == 2], ["Two", "Three"])


class TestRegionsAndText(unittest.TestCase):
    HTML = ('<body><nav><a href="/a.html">Nav link</a></nav>'
            '<main><p>Main body content here for the reader.</p>'
            '<a href="/b.html">Body link</a></main>'
            '<footer><a href="/c.html">Footer link</a></footer></body>')

    def test_main_text_excludes_chrome(self):
        doc = parse_html(BASE, self.HTML)
        self.assertIn("Main body content", doc.text_main)
        self.assertNotIn("Nav link", doc.text_main)
        self.assertIn("Nav link", doc.text_chrome)

    def test_link_regions(self):
        doc = parse_html(BASE, self.HTML)
        regions = {l.text: l.region for l in doc.links}
        self.assertEqual(regions["Nav link"], "nav")
        self.assertEqual(regions["Body link"], "main")
        self.assertEqual(regions["Footer link"], "footer")

    def test_class_based_chrome_detection(self):
        doc = parse_html(BASE, '<div class="site-navbar"><a href="/x.html">X</a></div>'
                               '<main><p>text</p></main>')
        self.assertEqual(doc.links[0].region, "nav")

    def test_internal_vs_external_links(self):
        doc = parse_html(BASE, '<main><a href="/in.html">in</a>'
                               '<a href="https://other.test/out">out</a></main>')
        self.assertEqual([l.internal for l in doc.links], [True, False])

    def test_non_http_links_dropped(self):
        doc = parse_html(BASE, '<main><a href="mailto:a@b.c">mail</a>'
                               '<a href="#top">top</a><a href="javascript:x()">js</a></main>')
        self.assertEqual(doc.links, [])

    def test_script_and_style_text_excluded(self):
        doc = parse_html(BASE, '<main><p>real</p></main>'
                               '<script>var hidden = "secret";</script>'
                               '<style>.x{color:red}</style>')
        self.assertNotIn("secret", doc.text_main)
        self.assertNotIn("color", doc.text_main)


class TestStructuredData(unittest.TestCase):
    def test_jsonld_graph_flattened(self):
        doc = parse_html(BASE, '<script type="application/ld+json">'
                               '{"@graph":[{"@type":"Organization","name":"N"},'
                               '{"@type":"WebSite","name":"W"}]}</script>')
        self.assertEqual(sorted(doc.jsonld_types()), ["Organization", "WebSite"])

    def test_malformed_jsonld_recorded_not_swallowed(self):
        doc = parse_html(BASE, '<script type="application/ld+json">{oops}</script>')
        self.assertEqual(doc.jsonld, [])
        self.assertEqual(len(doc.jsonld_errors), 1)

    def test_nodes_of_type_lookup(self):
        doc = parse_html(BASE, '<script type="application/ld+json">'
                               '{"@type":["Product","Thing"],"name":"P"}</script>')
        self.assertEqual(len(doc.jsonld_nodes_of("product")), 1)

    def test_microdata_types_detected(self):
        doc = parse_html(BASE, '<div itemscope itemtype="https://schema.org/Organization">'
                               '</div>')
        self.assertEqual(doc.microdata_types, ["Organization"])


class TestRenderingSignals(unittest.TestCase):
    def test_empty_app_root_detected(self):
        doc = parse_html(BASE, '<body><div id="root"></div>'
                               '<script>var a=1;</script></body>')
        self.assertTrue(doc.empty_app_root)

    def test_populated_app_root_not_flagged(self):
        doc = parse_html(BASE, '<body><div id="root"><main><p>'
                               + "Real server rendered content that a fetcher can read. " * 3
                               + '</p></main></div></body>')
        self.assertFalse(doc.empty_app_root)

    def test_noscript_captured_separately(self):
        doc = parse_html(BASE, '<body><noscript>fallback copy</noscript>'
                               '<main><p>x</p></main></body>')
        self.assertIn("fallback copy", doc.noscript_text)
        self.assertNotIn("fallback", doc.text_main)


class TestInteractionSignals(unittest.TestCase):
    def test_location_gate_detected(self):
        doc = parse_html(BASE, '<main><p>Select your city to continue</p>'
                               '<select name="city"><option>Delhi</option></select></main>')
        signals = context_gate_signals(doc)
        self.assertTrue(any("city" in s.lower() for s in signals))

    def test_language_switcher_is_not_a_context_gate(self):
        doc = parse_html(BASE, '<main><select name="language">'
                               '<option>English</option></select></main>')
        self.assertEqual(context_gate_signals(doc), [])

    def test_cta_detected_in_main_region(self):
        doc = parse_html(BASE, '<main><button>Book a demo</button></main>')
        self.assertTrue(has_cta(doc))

    def test_repeated_blocks_recorded(self):
        html = "<main>" + '<p>The same repeated sentence appears here.</p>' * 3 + "</main>"
        doc = parse_html(BASE, html)
        self.assertEqual(doc.blocks.count("The same repeated sentence appears here."), 3)


class TestRobustness(unittest.TestCase):
    def test_unclosed_tags_do_not_raise(self):
        doc = parse_html(BASE, "<main><p>one<p>two<div><span>three</main>")
        self.assertIn("one", doc.text_main)

    def test_empty_document(self):
        doc = parse_html(BASE, "")
        self.assertEqual(doc.title, "")
        self.assertEqual(doc.words_main, 0)


if __name__ == "__main__":
    unittest.main()
