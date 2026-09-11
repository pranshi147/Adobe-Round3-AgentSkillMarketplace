"""Bounded evidence collection.

This is *not* a recursive spider. It performs a deliberately small,
stratified sample so that:

  * runtime stays well inside the 5-minute budget,
  * the audited site is never hammered,
  * the sample covers the page templates that matter for AI citation
    (entity/about pages, product/service pages, pricing, help, editorial).

Scope rules:
  - single-page mode: the target URL plus site-level resources
    (robots.txt, sitemap, canonical target) only.
  - site mode: homepage + sitemap URLs + one/two-hop internal links,
    stratified by URL template, capped by page and time budgets.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

from . import htmlparse
from .fetch import Fetcher, RobotsInfo

TRACKING_PARAMS = re.compile(
    r"^(utm_|gclid$|fbclid$|mc_cid$|mc_eid$|ref$|referrer$|igshid$|"
    r"msclkid$|yclid$|_ga$|s_kwcid$)", re.IGNORECASE)

SLUG_RE = re.compile(r"^[0-9]+$|^[0-9a-f]{8,}$|^.{25,}$|\d{3,}")

UTILITY_PATH_RE = re.compile(
    r"/(cart|checkout|basket|login|signin|sign-in|signup|register|account|"
    r"my-?account|admin|wp-admin|wp-login|search|api|graphql|cdn-cgi|"
    r"logout|password|order|orders|payment|wishlist|preferences|settings|"
    r"session|auth)(/|$|\?)", re.IGNORECASE)

IMPORTANT_PATH_HINTS = (
    ("about", 10), ("company", 9), ("who-we-are", 9), ("our-story", 8),
    ("pricing", 9), ("plans", 8), ("price", 7),
    ("product", 8), ("products", 8), ("services", 8), ("service", 7),
    ("solutions", 7), ("features", 7), ("platform", 6),
    ("contact", 7), ("locations", 6), ("store", 5),
    ("faq", 7), ("help", 6), ("support", 6), ("docs", 6), ("documentation", 6),
    ("blog", 5), ("news", 5), ("press", 5), ("resources", 4), ("guides", 5),
    ("case-stud", 5), ("customers", 4), ("team", 4), ("careers", 2),
)

# Paths that answer the questions people ask about a brand. Used where a rule
# needs "an important page" as a category rather than as a decayed score —
# deep editorial content is expected to be deep and is deliberately excluded.
KEY_PAGE_RE = re.compile(
    r"/(about|about-us|company|who-we-are|our-story|pricing|prices|plans|"
    r"product|products|service|services|solutions|contact|contact-us|"
    r"support|help|faq|faqs|docs|documentation)(/|$|\.)", re.IGNORECASE)


def is_key_page(url: str) -> bool:
    """True for pages a visitor or an agent is likely to be looking for by name."""
    return bool(KEY_PAGE_RE.search(urlparse(url).path or ""))


ASSET_EXT_RE = re.compile(
    r"\.(?:jpg|jpeg|png|gif|webp|avif|svg|ico|css|js|mjs|json|xml|pdf|zip|"
    r"gz|mp4|mp3|webm|woff2?|ttf|eot|dmg|exe|csv|xlsx?|docx?|pptx?)$",
    re.IGNORECASE)


def normalize_url(url: str, base: str = "") -> str:
    """Canonical comparison form: no fragment, no tracking params, no dup slash."""
    if not url:
        return ""
    if base:
        url = urljoin(base, url)
    try:
        p = urlparse(url.strip())
    except ValueError:
        return ""
    if p.scheme not in ("http", "https"):
        return ""
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    if (scheme == "http" and netloc.endswith(":80")):
        netloc = netloc[:-3]
    if (scheme == "https" and netloc.endswith(":443")):
        netloc = netloc[:-4]
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    if not path:
        path = "/"
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                       if not TRACKING_PARAMS.match(k)])
    return urlunparse((scheme, netloc, path, "", query, ""))


def same_site(url: str, root: str) -> bool:
    a, b = urlparse(url).netloc.lower(), urlparse(root).netloc.lower()
    if not a or not b:
        return False
    a = a[4:] if a.startswith("www.") else a
    b = b[4:] if b.startswith("www.") else b
    return a == b


def url_template(url: str) -> str:
    """Collapse a URL to its structural template, e.g. /blog/{slug}."""
    p = urlparse(url)
    parts = [seg for seg in (p.path or "/").split("/") if seg]
    out = []
    for seg in parts:
        out.append("{slug}" if SLUG_RE.search(seg) else seg.lower())
    return "/" + "/".join(out) if out else "/"


def path_importance(url: str) -> int:
    path = (urlparse(url).path or "/").lower()
    if path in ("", "/"):
        return 12
    score = 0
    for hint, weight in IMPORTANT_PATH_HINTS:
        if hint in path:
            score = max(score, weight)
    depth = len([s for s in path.split("/") if s])
    return max(0, score - max(0, depth - 2))


def is_crawlable_candidate(url: str) -> bool:
    if ASSET_EXT_RE.search(urlparse(url).path or ""):
        return False
    if UTILITY_PATH_RE.search(url):
        return False
    return True


@dataclass
class SiteEvidence:
    root_url: str
    scope: str = "site"                     # site | page
    started_at: float = 0.0
    finished_at: float = 0.0
    pages: list = field(default_factory=list)          # [PageDoc]
    robots: RobotsInfo | None = None
    robots_url: str = ""
    sitemap_urls: list = field(default_factory=list)   # discovered sitemap files
    sitemap_attempts: list = field(default_factory=list)  # [(url, outcome)]
    sitemap_entries: list = field(default_factory=list)  # URLs listed in sitemaps
    sitemap_status: str = "absent"          # absent | ok | unreachable | empty | invalid
    sitemap_lastmod_count: int = 0
    blocked_urls: list = field(default_factory=list)   # [(url, rule)]
    fetch_failures: list = field(default_factory=list)  # [(url, status, error, referrers)]
    link_graph: dict = field(default_factory=dict)     # url -> set(url)
    referrers: dict = field(default_factory=dict)      # url -> set(url)
    limitations: list = field(default_factory=list)
    requests_made: int = 0

    @property
    def host(self) -> str:
        return urlparse(self.root_url).netloc.lower()

    @property
    def html_pages(self) -> list:
        return [p for p in self.pages if p.status and 200 <= p.status < 300 and p.is_html]

    @property
    def duration(self) -> float:
        return (self.finished_at or time.time()) - self.started_at

    def page_by_url(self, url: str):
        n = normalize_url(url)
        for p in self.pages:
            if normalize_url(p.final_url) == n or normalize_url(p.url) == n:
                return p
        return None

    def content_pages(self) -> list:
        """HTML pages that are plausibly informational (not utility screens)."""
        return [p for p in self.html_pages if is_crawlable_candidate(p.final_url)]


def count_lastmod(xml_text: str) -> int:
    return len(re.findall(r"<lastmod>", xml_text or "", re.IGNORECASE))


def parse_sitemap(xml_text: str, base: str) -> tuple:
    """Return (child_sitemaps, page_urls). Tolerates namespaces and junk."""
    children, pages = [], []
    if not xml_text or not xml_text.lstrip().startswith("<"):
        return children, pages
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        # fall back to a permissive scan
        for m in re.finditer(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text, re.IGNORECASE):
            pages.append(urljoin(base, m.group(1)))
        return children, pages
    tag = root.tag.split("}")[-1].lower()
    for el in root.iter():
        name = el.tag.split("}")[-1].lower()
        if name != "loc" or not (el.text or "").strip():
            continue
        loc = urljoin(base, el.text.strip())
        parent = "sitemap" if tag == "sitemapindex" else "url"
        (children if parent == "sitemap" else pages).append(loc)
    return children, pages


class Crawler:
    def __init__(self, fetcher: Fetcher, max_pages: int = 20,
                 max_depth: int = 2, max_sitemaps: int = 3,
                 log=lambda *a, **k: None):
        self.f = fetcher
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.max_sitemaps = max_sitemaps
        self.log = log

    # ------------------------------------------------------------------
    def run(self, target_url: str, scope: str = "site") -> SiteEvidence:
        target = normalize_url(target_url)
        ev = SiteEvidence(root_url=target, scope=scope, started_at=time.time())
        origin = "{0}://{1}".format(*urlparse(target)[:2])
        ev.robots_url = origin + "/robots.txt"
        ev.robots = self.f.robots_for(target)
        if ev.robots.unknown:
            ev.limitations.append(
                f"robots.txt at {ev.robots_url} returned status {ev.robots.status or 'n/a'} "
                f"({ev.robots.error or 'unreadable'}); crawl restricted to the supplied URL.")
        if ev.robots.crawl_delay:
            self.f.min_interval = max(self.f.min_interval, min(ev.robots.crawl_delay, 2.0))

        seeds = [(target, 0, "seed")]
        if scope == "site":
            self._collect_sitemaps(ev, origin)
        else:
            ev.sitemap_status = "not-checked"

        self._fetch_pages(ev, seeds)

        if scope == "site" and not ev.robots.unknown:
            queue = self._build_queue(ev, target)
            self._fetch_pages(ev, queue)

        ev.finished_at = time.time()
        ev.requests_made = self.f.requests_made
        return ev

    # ------------------------------------------------------------------
    def _collect_sitemaps(self, ev: SiteEvidence, origin: str):
        candidates = list(dict.fromkeys(
            (ev.robots.sitemaps if ev.robots else []) + [origin + "/sitemap.xml"]))
        seen_status = []
        for sm_url in candidates[: self.max_sitemaps]:
            if self.f.out_of_time():
                break
            res = self.f.fetch(sm_url)
            if not res.ok or not res.body.strip():
                seen_status.append("unreachable")
                ev.sitemap_attempts.append(
                    (sm_url, f"HTTP {res.status or 'n/a'}{': ' + res.error if res.error else ''}"))
                continue
            children, pages = parse_sitemap(res.body, sm_url)
            if not children and not pages:
                seen_status.append("invalid")
                ev.sitemap_attempts.append(
                    (sm_url, f"HTTP {res.status} but no <loc> entries could be parsed"))
                continue
            ev.sitemap_attempts.append((sm_url, f"HTTP {res.status}, {len(pages)} URL(s) listed"))
            ev.sitemap_lastmod_count += count_lastmod(res.body)
            ev.sitemap_urls.append(sm_url)
            ev.sitemap_entries.extend(pages)
            for child in children[: self.max_sitemaps]:
                if self.f.out_of_time():
                    break
                cres = self.f.fetch(child)
                if cres.ok:
                    _, cpages = parse_sitemap(cres.body, child)
                    ev.sitemap_lastmod_count += count_lastmod(cres.body)
                    if cpages:
                        ev.sitemap_urls.append(child)
                        ev.sitemap_entries.extend(cpages)
            seen_status.append("ok")
        ev.sitemap_entries = list(dict.fromkeys(
            normalize_url(u) for u in ev.sitemap_entries if normalize_url(u)))
        if "ok" in seen_status:
            ev.sitemap_status = "empty" if not ev.sitemap_entries else "ok"
        elif "invalid" in seen_status:
            ev.sitemap_status = "invalid"
        elif seen_status:
            ev.sitemap_status = "unreachable"
        else:
            ev.sitemap_status = "absent"

    # ------------------------------------------------------------------
    def _build_queue(self, ev: SiteEvidence, target: str) -> list:
        """Stratified selection of the next pages to sample."""
        home = ev.pages[0] if ev.pages else None
        candidates: "OrderedDict[str, tuple]" = OrderedDict()

        def add(url, depth, source):
            n = normalize_url(url)
            if not n or n == target or n in candidates:
                return
            if not same_site(n, target) or not is_crawlable_candidate(n):
                return
            candidates[n] = (depth, source)

        if home is not None:
            for link in home.internal_links:
                add(link.href, 1, "link")
        for u in ev.sitemap_entries:
            add(u, 1, "sitemap")

        buckets: dict = defaultdict(list)
        for url, (depth, source) in candidates.items():
            buckets[url_template(url)].append((url, depth, source))

        # Order templates: importance of their most important member first.
        ordered = sorted(
            buckets.items(),
            key=lambda kv: (-max(path_importance(u) for u, _, _ in kv[1]), kv[0]))

        per_bucket = 3 if len(ordered) > 4 else 6
        queue: list = []
        round_idx = 0
        while len(queue) < self.max_pages - len(ev.pages) and round_idx < per_bucket:
            added_any = False
            for _tmpl, items in ordered:
                if round_idx >= len(items):
                    continue
                items_sorted = sorted(items, key=lambda t: -path_importance(t[0]))
                url, depth, source = items_sorted[round_idx]
                queue.append((url, depth, source))
                added_any = True
                if len(queue) >= self.max_pages - len(ev.pages):
                    break
            if not added_any:
                break
            round_idx += 1
        return queue

    # ------------------------------------------------------------------
    def _fetch_pages(self, ev: SiteEvidence, queue: list):
        for url, depth, source in queue:
            if len(ev.pages) >= self.max_pages:
                ev.limitations.append(
                    f"page budget of {self.max_pages} reached; sample truncated.")
                break
            if self.f.out_of_time():
                ev.limitations.append("time budget reached; sample truncated.")
                break
            n = normalize_url(url)
            if ev.page_by_url(n):
                continue
            robots = self.f.robots_for(n)
            if not robots.allowed(n, self.f.user_agent):
                rule = robots.blocking_rule(n, self.f.user_agent)
                ev.blocked_urls.append((n, rule[1] if rule else "Disallow"))
                continue
            res = self.f.fetch(n)
            if res.blocked_by_robots:
                rule = robots.blocking_rule(n, self.f.user_agent)
                ev.blocked_urls.append((n, rule[1] if rule else "Disallow"))
                continue
            doc = self._to_doc(res, depth, source)
            ev.pages.append(doc)
            if not res.ok:
                ev.fetch_failures.append({
                    "url": n, "status": res.status, "error": res.error,
                    "source": source,
                })
            self._record_links(ev, doc)

    def _to_doc(self, res, depth, source):
        doc = htmlparse.parse_html(res.url, res.body or "", res.headers,
                                   status=res.status, final_url=res.final_url or res.url)
        doc.depth = depth
        doc.source = source
        doc.redirect_chain = res.redirect_chain
        doc.fetch_error = res.error
        return doc

    def _record_links(self, ev: SiteEvidence, doc):
        src = normalize_url(doc.final_url)
        targets = set()
        for link in doc.internal_links:
            t = normalize_url(link.href)
            if t:
                targets.add(t)
                ev.referrers.setdefault(t, set()).add(src)
        ev.link_graph[src] = targets


def check_links(fetcher: Fetcher, ev: SiteEvidence, limit: int = 10) -> list:
    """Verify a bounded sample of internally-linked URLs we have not fetched.

    Returns a list of dicts for URLs that failed, each carrying the referring
    page so the finding can point at a concrete, fixable location.
    """
    already = {normalize_url(p.final_url) for p in ev.pages}
    already |= {normalize_url(p.url) for p in ev.pages}
    seen: "OrderedDict[str, set]" = OrderedDict()
    for src, targets in ev.link_graph.items():
        for t in targets:
            if t in already or not is_crawlable_candidate(t):
                continue
            seen.setdefault(t, set()).add(src)

    # Prefer links that appear on more than one page, then important paths.
    ordered = sorted(seen.items(), key=lambda kv: (-len(kv[1]), -path_importance(kv[0])))
    failures = []
    checked = 0
    for url, srcs in ordered:
        if checked >= limit or fetcher.out_of_time():
            break
        robots = fetcher.robots_for(url)
        if not robots.allowed(url, fetcher.user_agent):
            continue
        res = fetcher.fetch(url, method="GET")
        checked += 1
        if res.status >= 400 or (res.error and not res.status):
            failures.append({
                "url": url, "status": res.status, "error": res.error,
                "referrers": sorted(srcs)[:3],
            })
    return failures
