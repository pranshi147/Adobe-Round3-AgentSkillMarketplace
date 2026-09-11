"""Helpers for building audit evidence in memory.

Detector tests must be able to state a page's exact HTML and assert exactly
what the detector does with it, with no network involved. `build_evidence`
constructs the same SiteEvidence object the crawler would produce.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from evidencekit.context import AuditContext                  # noqa: E402
from evidencekit.crawl import SiteEvidence, normalize_url     # noqa: E402
from evidencekit.fetch import DEFAULT_UA, RobotsInfo          # noqa: E402
from evidencekit.findings import load_registry                # noqa: E402
from evidencekit.htmlparse import parse_html                  # noqa: E402

HOST = "http://example.test"
REGISTRY = load_registry()


def build_evidence(pages: dict, root: str = HOST + "/", robots_text: str | None = None,
                   sitemap: list | None = None, scope: str = "site",
                   headers: dict | None = None, statuses: dict | None = None,
                   sitemap_status: str = "ok", failures: list | None = None,
                   sitemap_lastmod_count: int = 99) -> SiteEvidence:
    """pages: {url_or_path: html}. The first entry is treated as depth 0."""
    ev = SiteEvidence(root_url=normalize_url(root), scope=scope, started_at=0.0,
                      finished_at=1.0)
    ev.robots_url = HOST + "/robots.txt"
    ev.robots = (RobotsInfo(HOST, 200, robots_text, present=True) if robots_text
                 else RobotsInfo(HOST, 404, present=False))
    ev.sitemap_entries = [normalize_url(_abs(u)) for u in (sitemap or [])]
    ev.sitemap_status = sitemap_status if sitemap else "absent"
    ev.sitemap_urls = [HOST + "/sitemap.xml"] if sitemap else []
    ev.sitemap_lastmod_count = sitemap_lastmod_count
    ev.fetch_failures = list(failures or [])

    for idx, (url, html) in enumerate(pages.items()):
        full = _abs(url)
        doc = parse_html(full, html, (headers or {}).get(url, {"content-type": "text/html"}),
                         status=(statuses or {}).get(url, 200), final_url=full)
        doc.depth = 0 if idx == 0 else 1
        doc.source = "seed" if idx == 0 else "link"
        ev.pages.append(doc)

    for doc in ev.pages:
        src = normalize_url(doc.final_url)
        targets = set()
        for link in doc.internal_links:
            t = normalize_url(link.href)
            if t:
                targets.add(t)
                ev.referrers.setdefault(t, set()).add(src)
        ev.link_graph[src] = targets
    return ev


def _abs(url: str) -> str:
    if url.startswith("http"):
        return url
    return HOST + ("" if url.startswith("/") else "/") + url


def context(pages: dict, **kwargs) -> AuditContext:
    link_failures = kwargs.pop("link_check_failures", None)
    ev = build_evidence(pages, **kwargs)
    return AuditContext(ev, REGISTRY, user_agent=DEFAULT_UA,
                        link_check_failures=link_failures)


# -- reusable page bodies -------------------------------------------------
def page(title="A clear and specific page title about tools", h1=None, body=None,
         head_extra="", nav=True, canonical=None, main_links=3, lang="en",
         site_name="Northwind Tools"):
    """A page that is healthy by construction; tests mutate one thing at a time."""
    h1 = h1 or title.split(" — ")[0]
    body = body or (
        "Northwind Tools is a workshop tool manufacturer that makes calibrated torque "
        "wrenches for independent repair shops. Every wrench is calibrated against a "
        "reference transducer before it leaves the factory, and each unit ships with a "
        "certificate recording the measured deviation at three separate test points on "
        "the scale. The catalogue covers click type wrenches from five to two hundred "
        "and ten newton metres, socket sets in metric and imperial sizes, and the "
        "calibration service that keeps those tools accurate after a year of workshop "
        "use in a busy commercial garage environment with several working bays.")
    links = "".join(
        f'<a href="/related-{i}.html">Detailed guide number {i} for workshops</a> '
        for i in range(1, main_links + 1))
    nav_html = ('<nav><a href="/about.html">About Northwind Tools</a>'
                '<a href="/pricing.html">Tool pricing and calibration fees</a></nav>'
                if nav else "")
    can = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    site = f'<meta property="og:site_name" content="{site_name}">' if site_name else ""
    return (f'<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8">'
            f'<title>{title}</title>{site}{can}{head_extra}</head><body>{nav_html}'
            f'<main><h1>{h1}</h1><p>{body}</p><h2>Details</h2><p>{links}</p></main>'
            f'<footer><p>© 2026 {site_name}</p></footer></body></html>')


def load_detectors(skill: str):
    """Import a skill's detector module the way the orchestrator does."""
    import importlib.util
    path = ROOT / "skills" / skill / "scripts" / "detectors.py"
    spec = importlib.util.spec_from_file_location(
        f"test_{skill.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ids(findings) -> set:
    return {f.id for f in findings}
