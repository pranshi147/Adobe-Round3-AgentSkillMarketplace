"""Off-site corroboration: bounded, opt-outable, and honest about its limits.

What this module does
---------------------
It fetches **only URLs the audited site itself declares or owns**: the external
references in its own markup (`sameAs`, `identifier`, `rel=me`, `rel=author`,
`rel=publisher`, cross-domain `rel=alternate`), and the other common form of its
own hostname (www <-> apex). That is enough to answer four evidenced questions:

  * do the references this site offers for corroboration actually resolve?
  * does the destination recognisably concern this brand?
  * does it reference this domain back, confirming both sides describe one entity?
  * does a reference to the brand's other hostname form reach this site at all?

Together these are the site's **off-site discoverability surface**: the routes
by which something published elsewhere leads back here, and the independent
records against which a claim about this brand could be checked.

What this module deliberately does NOT do
-----------------------------------------
  * No web search, no search-engine API, no key required.
  * No crawling of third parties the site did not name.
  * No inference from absence. A site that declares no external references is
    not failing anything; the audit records that no probe was possible and, at
    most, raises a proactive opportunity. The audit never concludes that a brand
    is undiscoverable on the web — it has not looked at the web, only at what
    the site publishes and at that site's own hostnames.
  * No claim about whether any AI product has indexed, used or ignored the site.

Degradation
-----------
If the network is unavailable, disabled with `--external off`, or a probe
times out, the probe is recorded as `not_checked` with the reason. Detectors
only ever reason over probes that actually returned an HTTP status, so a
sandbox with no egress produces zero external findings rather than a failed
audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import textutil as tu
from .htmlparse import parse_html

# Statuses that mean "the platform refused an automated client", which says
# nothing about whether the profile exists.
REFUSAL_STATUSES = {401, 403, 405, 406, 429, 451}


@dataclass
class Probe:
    url: str
    source: str
    kind: str = "reference"            # reference | hostname
    status: int = 0
    error: str = ""
    checked: bool = False
    title: str = ""
    site_name: str = ""
    text_sample: str = ""
    description: str = ""              # an independent description of the brand
    links_back: bool = False           # does it reference the audited domain?
    final_url: str = ""
    canonical: str = ""
    reason_not_checked: str = ""

    @property
    def resolved(self) -> bool:
        return self.checked and 200 <= self.status < 300

    @property
    def broken(self) -> bool:
        return self.checked and self.status >= 400 and self.status not in REFUSAL_STATUSES

    @property
    def readable(self) -> bool:
        return self.resolved and bool(self.title or self.site_name or self.text_sample)

    @property
    def consolidates_to(self) -> str:
        """Where this hostname says its content really lives."""
        return self.canonical or self.final_url

    def to_dict(self) -> dict:
        d = {"url": self.url, "declared_in": self.source, "kind": self.kind,
             "checked": self.checked, "status": self.status or None}
        if self.kind == "reference" and self.checked:
            d["links_back"] = self.links_back
            d["carries_description"] = bool(self.description)
        if self.title:
            d["title"] = tu.truncate(self.title, 120)
        if self.reason_not_checked:
            d["not_checked_because"] = self.reason_not_checked
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class ExternalEvidence:
    """Everything the off-site pass observed, including why it observed nothing."""
    mode: str = "auto"                  # auto | off
    performed: bool = False
    declared: list = field(default_factory=list)     # [(url, source)]
    probes: list = field(default_factory=list)       # [Probe] — declared references
    host_probes: list = field(default_factory=list)  # [Probe] — hostname variants
    limitations: list = field(default_factory=list)

    @property
    def checked_probes(self) -> list:
        return [p for p in self.probes if p.checked]

    @property
    def resolved_references(self) -> list:
        return [p for p in self.probes if p.readable]

    @property
    def independent_descriptions(self) -> list:
        return [p for p in self.probes if p.readable and p.description]

    def summary(self) -> dict:
        return {
            "mode": self.mode,
            "performed": self.performed,
            "declared_identifiers": len(self.declared),
            "probes_attempted": len(self.probes),
            "probes_completed": len(self.checked_probes),
            "references_resolved": len(self.resolved_references),
            "references_linking_back": sum(1 for p in self.resolved_references
                                           if p.links_back),
            "independent_descriptions_found": len(self.independent_descriptions),
            "hostname_variants_probed": len(self.host_probes),
            "probes": [p.to_dict() for p in self.probes],
            "hostname_probes": [p.to_dict() for p in self.host_probes],
            "scope_note": (
                "Only URLs the site itself declares (sameAs, identifier, rel=me, "
                "rel=author, rel=publisher, cross-domain rel=alternate) and the other "
                "common form of its own hostname were requested. No search engine, "
                "directory or third-party source the site did not name was consulted. "
                "No conclusion is drawn from the absence of external references, and no "
                "claim is made about how discoverable this brand is on the web at "
                "large — the audit has not looked at the web at large."),
        }


def collect(fetcher, declared: list, limit: int = 6, mode: str = "auto",
            origin: str = "", host_limit: int = 2) -> ExternalEvidence:
    """Probe the site's off-site discoverability surface, read-only and bounded.

    Two request groups, both inside the audit's single shared deadline and both
    subject to robots.txt on the destination host:

      * up to `limit` external references the site declares about itself;
      * up to `host_limit` alternate forms of the site's own hostname.
    """
    ev = ExternalEvidence(mode=mode, declared=list(declared))

    if mode == "off":
        ev.limitations.append(
            "Off-site discoverability probing was disabled (--external off); no external "
            "URL and no hostname variant was requested, so no off-site finding can be "
            "reported.")
        return ev

    audited_host = _bare_host(origin)

    for url, source in declared[:limit]:
        ev.probes.append(_probe(fetcher, url, source, "reference", audited_host))

    for variant in _hostname_variants(origin)[:host_limit]:
        ev.host_probes.append(
            _probe(fetcher, variant, "the other common form of this site's hostname",
                   "hostname", audited_host))

    ev.performed = True
    if not declared:
        ev.limitations.append(
            "The site declares no external references in its markup, so there was nothing "
            "to corroborate against. This is not treated as a defect: many legitimate "
            "sites have no external record worth declaring.")
    if len(declared) > limit:
        ev.limitations.append(
            f"{len(declared)} external references were declared; the first {limit} were "
            f"probed to stay inside the request budget.")
    unchecked = [p for p in ev.probes if not p.checked]
    if unchecked:
        ev.limitations.append(
            f"{len(unchecked)} of {len(ev.probes)} external probes could not be completed "
            f"(network unavailable, non-HTTP reference, robots.txt, or budget exhausted); "
            f"no off-site finding is reported for those URLs.")
    return ev


def _probe(fetcher, url: str, source: str, kind: str, audited_host: str) -> Probe:
    """One bounded, read-only request. Never raises; records why if it cannot run."""
    probe = Probe(url=url, source=source, kind=kind)
    if urlparse(url).scheme not in ("http", "https"):
        probe.reason_not_checked = "reference is not an http(s) URL"
        return probe
    if fetcher.out_of_time():
        probe.reason_not_checked = "audit time budget exhausted before this probe"
        return probe

    res = fetcher.fetch(url)
    if getattr(res, "blocked_by_robots", False):
        probe.reason_not_checked = "robots.txt on the destination host disallows this URL"
        return probe
    if res.error and not res.status:
        probe.error = res.error
        probe.reason_not_checked = f"external request failed: {res.error}"
        return probe

    probe.checked = True
    probe.status = res.status
    probe.final_url = res.final_url or url
    if res.body and "html" in (res.content_type or "text/html"):
        doc = parse_html(url, res.body, res.headers, status=res.status,
                         final_url=probe.final_url)
        probe.title = doc.title
        probe.site_name = doc.meta_get("og:site_name", "application-name")
        probe.text_sample = tu.truncate(doc.text_main or doc.text_chrome, 1200)
        probe.canonical = doc.canonical
        description = doc.meta_get("description", "og:description")
        if tu.word_count(description) >= 8:
            probe.description = tu.truncate(description, 300)
        probe.links_back = _references_host(doc, audited_host)
    return probe


def _bare_host(url: str) -> str:
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _hostname_variants(origin: str) -> list:
    from .entity import hostname_variants
    return hostname_variants(origin) if origin else []


def _references_host(doc, audited_host: str) -> bool:
    """Does this page point back at the audited domain, in a link or in text?"""
    if not audited_host:
        return False
    for link in doc.links:
        if _bare_host(link.href) == audited_host:
            return True
    haystack = f"{doc.text_main} {doc.text_chrome}".lower()
    return audited_host in haystack


def mentions_brand(probe: Probe, names: list) -> bool:
    """Does the retrieved profile recognisably concern one of these brand names?

    Checks the destination's title, site name, visible text and its own URL path,
    using the same compatibility rules as on-site name comparison.
    """
    haystacks = [probe.title, probe.site_name, probe.text_sample,
                 re.sub(r"[^A-Za-z0-9]+", " ", urlparse(probe.url).path or "")]
    for norm_name, _raw, _count in names:
        if not norm_name:
            continue
        for hay in haystacks:
            if not hay:
                continue
            hay_norm = tu.normalize_entity_name(hay)
            if not hay_norm:
                continue
            if norm_name in hay_norm:
                return True
            if tu.names_compatible(norm_name, hay_norm) and len(hay_norm.split()) <= 6:
                return True
            squashed = norm_name.replace(" ", "")
            if squashed and squashed in hay_norm.replace(" ", ""):
                return True
    return False
