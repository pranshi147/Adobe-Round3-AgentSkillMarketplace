"""AuditContext — the single object every detector receives.

It carries the collected evidence, the defect registry, memoised text
measurements, and the `needs_validation` sink where indicative-only signals
go instead of becoming findings.
"""

from __future__ import annotations

import datetime as _dt
from urllib.parse import urlparse

from . import textutil as tu
from .crawl import SiteEvidence, normalize_url, path_importance, is_crawlable_candidate
from .external import ExternalEvidence
from .fetch import DEFAULT_UA
from .htmlparse import parse_html, rendering_classification


class AuditContext:
    def __init__(self, evidence: SiteEvidence, registry: dict,
                 user_agent: str = DEFAULT_UA, link_check_failures: list | None = None):
        self.ev = evidence
        self.registry = registry
        self.user_agent = user_agent
        self.link_check_failures = link_check_failures or []
        self.today = _dt.date.today()
        self.needs_validation: list = []
        self.external = ExternalEvidence(mode="off")
        # Optional rendered-HTML snapshots supplied by the caller (url -> html).
        # The auditor never renders anything itself; see rendering_of().
        self.rendered_evidence: dict = {}
        self._shingles: dict = {}
        self._tokens: dict = {}
        self._rendered_docs: dict = {}

    # -- registry ---------------------------------------------------------
    def spec(self, defect_id: str) -> dict:
        return self.registry[defect_id]

    # -- page sets --------------------------------------------------------
    def content_pages(self) -> list:
        return self.ev.content_pages()

    def substantive_pages(self, min_words: int = 120) -> list:
        return [p for p in self.content_pages() if p.words_main >= min_words]

    def homepage(self):
        for p in self.ev.pages:
            if p.depth == 0 or (urlparse(p.final_url).path or "/") in ("", "/"):
                return p
        return self.ev.pages[0] if self.ev.pages else None

    def is_core(self, page) -> bool:
        """Homepage, about/company, or a primary product/service/pricing page."""
        if page is None:
            return False
        if page.depth == 0:
            return True
        if (urlparse(page.final_url).path or "/") in ("", "/"):
            return True
        return path_importance(page.final_url) >= 8

    def is_target(self, page) -> bool:
        return normalize_url(page.final_url) == normalize_url(self.ev.root_url)

    # -- memoised text measurements ---------------------------------------
    def shingles(self, page) -> set:
        key = id(page)
        if key not in self._shingles:
            self._shingles[key] = tu.shingles(page.text_main)
        return self._shingles[key]

    def tokens(self, page) -> set:
        key = id(page)
        if key not in self._tokens:
            self._tokens[key] = tu.content_tokens(page.text_main)
        return self._tokens[key]

    def similarity(self, a, b) -> float:
        return tu.jaccard(self.shingles(a), self.shingles(b))

    # -- rendering ---------------------------------------------------------
    def rendering_of(self, page) -> str:
        """How this page's content reaches a reader.

        Returns one of:
          server_rendered        substantive text is in the served HTML
          server_rendered_thin   little text served, and no rendering indicator
          likely_client_rendered served HTML shows client-assembly signatures —
                                 NOT a claim that a browser was run to confirm it
          interaction_required   the text is served but gated behind a control
          verified_after_render  a caller-supplied rendered snapshot confirms the
                                 content appears only after client-side rendering
        """
        base = rendering_classification(page)
        rendered = self.rendered_doc(page)
        if rendered is None:
            return base
        if base in ("likely_client_rendered", "server_rendered_thin") \
                and rendered.words_main >= max(120, 3 * max(1, page.words_main)):
            return "verified_after_render"
        return base

    def rendered_doc(self, page):
        """Parsed caller-supplied rendered snapshot for this page, if any."""
        key = normalize_url(page.final_url)
        if key not in self.rendered_evidence:
            return None
        if key not in self._rendered_docs:
            self._rendered_docs[key] = parse_html(page.final_url,
                                                  self.rendered_evidence[key],
                                                  final_url=page.final_url)
        return self._rendered_docs[key]

    @property
    def rendering_verification(self) -> str:
        if self.rendered_evidence:
            return (f"caller-supplied rendered snapshots for "
                    f"{len(self.rendered_evidence)} URL(s); all other pages judged "
                    f"from served HTML only")
        return "not performed — no browser engine was used; all pages judged from served HTML"

    # -- indicative sink ---------------------------------------------------
    def note(self, defect_id: str, url: str, observation: str,
             measurement: str = "", reason: str = ""):
        """Record a signal that is real but not strong enough to be a finding."""
        self.needs_validation.append({
            "defect_id": defect_id,
            "detector": self.registry.get(defect_id, {}).get("detector", defect_id),
            "url": url,
            "observation": observation,
            "measurement": measurement,
            "why_withheld": reason or "single indicative signal; below confidence gate",
        })

    # -- brand tokens ------------------------------------------------------
    def brand_tokens(self) -> set:
        """Tokens that name the site itself (used to strip brand from titles)."""
        toks: set = set()
        host = urlparse(self.ev.root_url).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        label = host.split(":")[0].split(".")[0]
        if label:
            toks.add(label)
        home = self.homepage()
        if home is not None:
            site_name = home.meta_get("og:site_name", "application-name")
            for t in tu.words(site_name):
                toks.add(t)
        return {t for t in toks if len(t) > 1}


def is_utility(url: str) -> bool:
    return not is_crawlable_candidate(url)
