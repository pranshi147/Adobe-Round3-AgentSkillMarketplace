"""Fact-integrity detectors: FI-001 .. FI-007.

Question answered by this module:
    "If a retrieval agent does find the information, will it understand and trust the
     *correct* fact, and can it attribute and date that fact?"

These detectors compare independent assertions the site makes about itself —
markup versus visible text, one identity surface versus another, wording
versus timestamps — and report only where those assertions actually conflict
or where a claim cannot be dated or attributed at all.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from evidencekit import entity, textutil as tu               # noqa: E402
from evidencekit.crawl import normalize_url, is_crawlable_candidate  # noqa: E402
from evidencekit.findings import (                           # noqa: E402
    Evidence, Finding, registry_action)

SKILL = "fact-integrity"

BYLINE_RE = re.compile(r"\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z\.]+){0,2})\b")
EDITORIAL_PATH_RE = re.compile(r"/(blog|news|articles?|insights?|stories|press|"
                               r"resources|guides?)(/|$)", re.IGNORECASE)
ARCHIVE_PATH_RE = re.compile(r"/(archive|changelog|releases?|history|20\d{2})(/|$)",
                             re.IGNORECASE)
ABOUT_PATH_RE = re.compile(r"/(about|about-us|company|who-we-are|our-story|"
                           r"corporate|overview)(/|$|\.)", re.IGNORECASE)
ENTITY_TYPES = entity.ENTITY_TYPES


def run(ctx) -> list:
    findings = []
    for fn in (fi001, fi002, fi003, fi004, fi005, fi006, fi007):
        try:
            findings.extend(fn(ctx))
        except Exception as exc:
            ctx.note(fn.__name__, ctx.ev.root_url,
                     f"detector raised {type(exc).__name__}: {exc}",
                     reason="detector error; no finding emitted")
    return findings


# ---------------------------------------------------------------- helpers
# Entity-name evidence is shared with the external-evidence skill so both
# reason over exactly the same set of published names.
_entity_nodes = entity.entity_nodes


def _name_candidates(ctx) -> list:
    return entity.name_candidates(ctx)


# ---------------------------------------------------------------- FI-001
def fi001(ctx) -> list:
    spec = ctx.spec("FI-001")
    cands = _name_candidates(ctx)
    if len(cands) < 2:
        return []

    by_source: dict = {}
    for src, raw, url, core in cands:
        norm = tu.normalize_entity_name(raw)
        if not norm or len(norm) < 2:
            continue
        by_source.setdefault(src, {}).setdefault(norm, (raw, url, core))
    if len(by_source) < 2:
        return []                       # guard: needs 2+ independent source types

    flat = []
    for src, names in by_source.items():
        for norm, (raw, url, core) in names.items():
            flat.append((src, norm, raw, url, core))

    conflicts = []
    for i in range(len(flat)):
        for j in range(i + 1, len(flat)):
            a, b = flat[i], flat[j]
            if a[0] == b[0]:
                continue                # same source type disagreeing is not enough
            if tu.names_compatible(a[1], b[1]):
                continue                # guard: containment / acronym / overlap
            conflicts.append((a, b))
    if not conflicts:
        return []

    sources_involved = {c[0][0] for c in conflicts} | {c[1][0] for c in conflicts}
    core_conflict = any(c[0][4] and c[1][4] for c in conflicts)
    severity = "high" if (core_conflict or len(sources_involved) >= 3) else "medium"

    evidence, seen = [], set()
    for a, b in conflicts[:3]:
        for src, norm, raw, url, _core in (a, b):
            key = (src, norm)
            if key in seen:
                continue
            seen.add(key)
            evidence.append(Evidence(
                url=url,
                observation=f"brand name asserted by {src}",
                measurement=f"value=\"{tu.truncate(raw, 80)}\" (normalised: \"{norm}\")"))

    return [Finding(
        id="FI-001", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence[:6], evidence_level="corroborated", confidence=0.85,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=list(dict.fromkeys(e.url for e in evidence)),
        measurements={"identity_sources": len(by_source),
                      "conflicting_pairs": len(conflicts),
                      "distinct_normalised_names": len({f[1] for f in flat})},
        effort=spec["effort"], core_page_affected=core_conflict,
        affected_share=0.6, suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- FI-002
def fi002(ctx) -> list:
    spec = ctx.spec("FI-002")
    pages = ctx.content_pages()
    home = ctx.homepage()
    if not pages or home is None:
        return []                      # guard: sample never reached the site root

    has_entity_markup = any(_entity_nodes(p) for p in pages)
    has_microdata = any(t.lower() in ENTITY_TYPES for p in pages for t in p.microdata_types)
    if has_entity_markup or has_microdata:
        return []

    known_urls = {normalize_url(p.final_url) for p in ctx.ev.pages}
    known_urls |= set(ctx.ev.sitemap_entries)
    for targets in ctx.ev.link_graph.values():
        known_urls |= set(targets)
    about = [u for u in known_urls if u and ABOUT_PATH_RE.search(urlparse(u).path or "")]
    if about:
        return []                      # guard: an about page satisfies identity

    return [Finding(
        id="FI-002", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity="medium",
        evidence=[
            Evidence(url=home.final_url,
                     observation="no Organization/LocalBusiness/WebSite structured data found",
                     measurement=f"0 entity nodes across {len(pages)} sampled pages; "
                                 f"JSON-LD types seen: "
                                 f"{sorted({t for p in pages for t in p.jsonld_types()}) or 'none'}"),
            Evidence(url=ctx.ev.root_url,
                     observation="no about/company page found in the sitemap or internal link graph",
                     measurement=f"{len(known_urls)} known URLs checked against "
                                 f"about|company|who-we-are|our-story patterns"),
        ],
        evidence_level="verified", confidence=0.9,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[ctx.ev.root_url],
        measurements={"sampled_pages": len(pages), "entity_nodes": 0, "about_pages": 0},
        effort=spec["effort"], core_page_affected=True, affected_share=1.0,
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- FI-003
def fi003(ctx) -> list:
    spec = ctx.spec("FI-003")
    pages = ctx.content_pages()
    mismatches, pages_with_markup = [], 0

    for p in pages:
        products = p.jsonld_nodes_of("Product", "Offer", "AggregateOffer",
                                     "Service", "Event", "Course")
        if not products:
            continue
        pages_with_markup += 1
        visible_prices = set(tu.find_prices(p.text_main))
        page_tokens = ctx.tokens(p) | tu.content_tokens(p.title) | tu.content_tokens(
            " ".join(p.h1s))
        low_text = " ".join([p.text_main, p.title, " ".join(p.h1s)]).lower()

        for node in products:
            declared, offer_node = _declared_price(node)
            if declared is not None and visible_prices:
                if _price_in_range(node, offer_node, declared, visible_prices):
                    continue                       # guard: from/range pricing
                if declared not in visible_prices:
                    mismatches.append((p, "price", declared,
                                       ", ".join(sorted(visible_prices)[:3])))
                    continue
            name = node.get("name")
            if isinstance(name, str) and name.strip():
                nt = tu.content_tokens(name)
                # Guard: an expanded product title in markup is not a contradiction.
                if len(nt) >= 2 and tu.overlap_ratio(nt, page_tokens) < 0.25:
                    mismatches.append((p, "name", tu.truncate(name, 70),
                                       tu.truncate(p.h1s[0] if p.h1s else p.title, 70)))
            avail = _availability(node, offer_node)
            if avail:
                claims_out = "out of stock" in low_text or "sold out" in low_text
                if avail == "instock" and claims_out:
                    mismatches.append((p, "availability", "InStock",
                                       "page text states the item is out of stock"))
                elif avail == "outofstock" and "in stock" in low_text and not claims_out:
                    mismatches.append((p, "availability", "OutOfStock",
                                       "page text states the item is in stock"))

    if not mismatches or not pages_with_markup:
        return []

    affected_pages = {m[0].final_url for m in mismatches}
    share = len(affected_pages) / pages_with_markup
    material = any(m[1] in ("price", "availability") and ctx.is_core(m[0]) for m in mismatches)
    severity = "high" if (share >= 0.4 or material) else "medium"

    evidence = [Evidence(
        url=p.final_url,
        observation=f"JSON-LD {field} does not match the visible page",
        measurement=f"structured value=\"{declared}\"; visible value(s)=\"{visible}\"",
    ) for p, field, declared, visible in mismatches[:6]]

    fields = sorted({m[1] for m in mismatches})
    return [Finding(
        id="FI-003", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.88,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=sorted(affected_pages),
        measurements={"pages_with_product_markup": pages_with_markup,
                      "pages_with_mismatch": len(affected_pages),
                      "share": round(share, 2), "fields": fields},
        effort=spec["effort"], core_page_affected=material, affected_share=share,
        suggested_action=registry_action(spec, field="/".join(fields),
                                         example=sorted(affected_pages)[0]),
    )]


def _declared_price(node):
    offers = node.get("offers")
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict):
        price = offers.get("price", offers.get("lowPrice"))
        if price is not None:
            return tu.normalize_number(price), offers
    price = node.get("price", node.get("lowPrice"))
    if price is not None:
        return tu.normalize_number(price), node
    return None, offers if isinstance(offers, dict) else None


def _price_in_range(node, offer_node, declared, visible_prices) -> bool:
    src = offer_node if isinstance(offer_node, dict) else node
    if not (src.get("lowPrice") or src.get("highPrice")):
        return False
    try:
        nums = sorted(float(v) for v in visible_prices)
        d = float(declared)
    except (TypeError, ValueError):
        return False
    return bool(nums) and nums[0] <= d <= nums[-1]


def _availability(node, offer_node):
    src = offer_node if isinstance(offer_node, dict) else node
    val = src.get("availability") if isinstance(src, dict) else None
    if not isinstance(val, str):
        return None
    v = val.rsplit("/", 1)[-1].lower()
    if "instock" in v:
        return "instock"
    if "outofstock" in v or "soldout" in v:
        return "outofstock"
    return None


# ---------------------------------------------------------------- FI-004
def fi004(ctx) -> list:
    spec = ctx.spec("FI-004")
    pages = [p for p in ctx.content_pages() if p.words_main >= 150]
    if len(pages) < 2:
        return []
    return _fi004(ctx, spec, pages)


def _fi004(ctx, spec, pages) -> list:
    pairs = []
    for i in range(len(pages)):
        for j in range(i + 1, len(pages)):
            a, b = pages[i], pages[j]
            ua, ub = normalize_url(a.final_url), normalize_url(b.final_url)
            if ua == ub:
                continue
            if re.search(r"([?&]page=|/page/\d+)", ua + ub):
                continue                        # guard: paginated variants
            if _variant_pair(ua, ub):
                continue                        # guard: version/locale variants
            ca = normalize_url(a.canonical) if a.canonical else ua
            cb = normalize_url(b.canonical) if b.canonical else ub
            if ca == cb:
                continue                        # guard: already consolidated
            sim = ctx.similarity(a, b)
            if sim >= 0.9:
                pairs.append((a, b, sim, ca, cb))
    if not pairs:
        return []

    core = any(ctx.is_core(a) or ctx.is_core(b) for a, b, _, _, _ in pairs)
    severity = "high" if (len(pairs) >= 3 or core) else "medium"
    evidence = [Evidence(
        url=a.final_url,
        observation="a second URL serves near-identical content without consolidation",
        measurement=f"duplicate of {b.final_url}; main-text similarity={sim:.2f}; "
                    f"canonicals: {ca} vs {cb}",
    ) for a, b, sim, ca, cb in pairs[:5]]

    return [Finding(
        id="FI-004", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="verified", confidence=0.93,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=list(dict.fromkeys(
            [p.final_url for pair in pairs for p in (pair[0], pair[1])])),
        measurements={"duplicate_pairs": len(pairs), "compared_pages": len(pages)},
        effort=spec["effort"], core_page_affected=core,
        affected_share=len({p.final_url for pair in pairs for p in (pair[0], pair[1])})
        / max(1, len(ctx.content_pages())),
        suggested_action=registry_action(spec),
    )]


VERSION_SEG_RE = re.compile(r"/(v?\d+(?:\.\d+)*|latest|stable|next|current)(/|$)",
                            re.IGNORECASE)
LOCALE_SEG_RE = re.compile(r"/([a-z]{2}(?:[-_][a-z]{2})?)(/|$)", re.IGNORECASE)


def _variant_pair(a: str, b: str) -> bool:
    """True when two URLs differ only by a version or locale path segment.

    Versioned documentation and translated pages are near-identical by design;
    reporting them as unconsolidated duplicates is a false positive.
    """
    for pattern in (VERSION_SEG_RE, LOCALE_SEG_RE):
        stripped_a = pattern.sub("/", a, count=1)
        stripped_b = pattern.sub("/", b, count=1)
        if stripped_a == stripped_b and (stripped_a != a or stripped_b != b):
            return True
    return False


# ---------------------------------------------------------------- FI-005
def fi005(ctx) -> list:
    spec = ctx.spec("FI-005")
    pages = ctx.content_pages()
    if not pages:
        return []

    no_date, weak_date, volatile_hits = [], [], 0
    for p in pages:
        markers = tu.has_any(p.text_main, tu.TIME_SENSITIVE_PHRASES)
        year_now = str(ctx.today.year) in p.text_main
        if not markers and not year_now:
            continue                      # guard: evergreen pages never fire
        if page_dates(p):
            continue
        volatile = tu.has_any(p.text_main, tu.VOLATILE_PHRASES)
        if volatile:
            volatile_hits += 1
        entry = (p, (markers or [f"references {ctx.today.year}"])[0], bool(volatile))
        if p.headers.get("last-modified"):
            weak_date.append(entry)       # guard: HTTP header is a weak signal
        else:
            no_date.append(entry)

    core_hit = any(ctx.is_core(p) for p, _, _ in no_date)
    if len(no_date) < 2 and not core_hit:
        for p, marker, _ in no_date + weak_date:
            ctx.note("FI-005", p.final_url,
                     "timeliness language present with no machine-readable date",
                     f"phrase=\"{marker}\"",
                     "single non-core page; below the two-page confidence gate")
        return []

    share_volatile = volatile_hits / len(pages)
    # High severity requires a commercial claim that visibly carries a value a
    # reader could act on — a price on the page — not merely volatile wording.
    priced = any(tu.find_prices(p.text_main) for p, _m, vol in no_date if vol)
    if not no_date:
        severity = "low"
        group = weak_date
    elif share_volatile >= 0.3 and priced:
        severity = "high"
        group = no_date
    else:
        severity = "medium"
        group = no_date

    evidence = [Evidence(
        url=p.final_url,
        observation="page asserts current information but exposes no date signal",
        measurement=f"timeliness phrase=\"{marker}\"; no JSON-LD date, no <time datetime>, "
                    f"no parseable visible date"
                    + ("; volatile commercial claim present" if vol else ""),
    ) for p, marker, vol in group[:6]]

    return [Finding(
        id="FI-005", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="verified", confidence=0.91,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _, _ in group],
        measurements={"pages_without_date_signal": len(no_date),
                      "pages_with_only_http_last_modified": len(weak_date),
                      "sampled_content_pages": len(pages),
                      "volatile_claim_pages": volatile_hits},
        effort=spec["effort"], core_page_affected=core_hit,
        affected_share=len(group) / len(pages),
        suggested_action=registry_action(spec),
    )]


def page_dates(page) -> list:
    """All date signals available on a page, in markup or visible text."""
    out = []
    for node in page.jsonld:
        for key in ("dateModified", "datePublished", "uploadDate", "dateCreated"):
            val = node.get(key)
            if isinstance(val, str):
                d = tu.parse_datetime_attr(val)
                if d:
                    out.append((d, f"JSON-LD {key}"))
    for attr, text in page.time_elements:
        d = tu.parse_datetime_attr(attr) or (tu.find_dates(text)[0]
                                             if tu.find_dates(text) else None)
        if d:
            out.append((d, "<time> element"))
    for key in ("article:modified_time", "article:published_time", "date",
                "dc.date", "last-modified"):
        val = page.meta.get(key)
        if val:
            d = tu.parse_datetime_attr(val)
            if d:
                out.append((d, f"meta {key}"))
    for d in tu.find_dates(page.text_main):
        out.append((d, "visible text"))
    return out


# ---------------------------------------------------------------- FI-006
def fi006(ctx) -> list:
    spec = ctx.spec("FI-006")
    stale = []
    for p in ctx.content_pages():
        if ARCHIVE_PATH_RE.search(p.path) or EDITORIAL_PATH_RE.search(p.path):
            continue                       # guard: dated/archival templates
        dates = page_dates(p)
        if not dates:
            continue
        newest, source = max(dates, key=lambda t: t[0])
        age_months = (ctx.today.year - newest.year) * 12 + (ctx.today.month - newest.month)
        if age_months <= 24:
            continue
        claims = tu.has_any(p.text_main, ("latest", "current", "currently",
                                          "up to date", "up-to-date", "today",
                                          "newest", "as of"))
        newer_years = [y for y in tu.find_years(p.text_main) if y > newest.year]
        if not claims and not newer_years:
            continue                       # guard: an old date alone is fine
        reason = (f"page text says \"{claims[0]}\"" if claims
                  else f"page text references {max(newer_years)}")
        stale.append((p, newest, source, age_months, reason))

    if not stale:
        return []
    core = any(ctx.is_core(p) for p, _, _, _, _ in stale)
    severity = "high" if core else "medium"
    evidence = [Evidence(
        url=p.final_url,
        observation="page claims current information but its newest date signal is old",
        measurement=f"newest date={newest.isoformat()} (from {source}), "
                    f"{age} months old; {reason}",
    ) for p, newest, source, age, reason in stale[:6]]

    return [Finding(
        id="FI-006", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.87,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _, _, _, _ in stale],
        measurements={"stale_pages": len(stale),
                      "oldest_months": max(s[3] for s in stale)},
        effort=spec["effort"], core_page_affected=core,
        affected_share=len(stale) / max(1, len(ctx.content_pages())),
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- FI-007
def fi007(ctx) -> list:
    spec = ctx.spec("FI-007")
    unattributed, text_only = [], []
    for p in ctx.content_pages():
        if not _is_editorial(p):
            continue
        has_struct = _has_structured_attribution(p)
        byline = BYLINE_RE.search(p.text_main[:1200])
        if has_struct:
            continue
        if byline:
            text_only.append((p, byline.group(0)))
        else:
            unattributed.append(p)

    if len(unattributed) >= 2:
        evidence = [Evidence(
            url=p.final_url,
            observation="editorial page carries no author, publisher or byline",
            measurement="no JSON-LD author/publisher, no meta author, no visible byline; "
                        f"main-region words={p.words_main}",
        ) for p in unattributed[:6]]
        return [Finding(
            id="FI-007", detector=spec["detector"], title=spec["title"], category=SKILL,
            stage=spec["stage"], failure_mode=spec["failure_mode"], severity="medium",
            evidence=evidence, evidence_level="verified", confidence=0.92,
            impact=spec["impact"], mechanism=spec["mechanism"],
            affected_urls=[p.final_url for p in unattributed],
            measurements={"unattributed_editorial_pages": len(unattributed)},
            effort=spec["effort"], core_page_affected=False,
            affected_share=len(unattributed) / max(1, len(ctx.content_pages())),
            suggested_action=registry_action(spec),
        )]

    if len(text_only) >= 2:
        evidence = [Evidence(
            url=p.final_url,
            observation="attribution appears in the visible text but not in structured data",
            measurement=f"visible byline=\"{tu.truncate(byline, 60)}\"; "
                        f"no author/publisher in JSON-LD or meta",
        ) for p, byline in text_only[:6]]
        return [Finding(
            id="FI-007", detector=spec["detector"],
            title="Editorial attribution is not machine-readable",
            category=SKILL, stage=spec["stage"], failure_mode=spec["failure_mode"],
            severity="low", evidence=evidence, evidence_level="verified", confidence=0.9,
            impact=spec["impact"], mechanism=spec["mechanism"],
            affected_urls=[p.final_url for p, _ in text_only],
            measurements={"text_only_attribution_pages": len(text_only)},
            effort=spec["effort"], core_page_affected=False,
            affected_share=len(text_only) / max(1, len(ctx.content_pages())),
            suggested_action=registry_action(spec),
        )]
    return []


def _is_editorial(page) -> bool:
    if page.jsonld_nodes_of("Article", "BlogPosting", "NewsArticle", "Report"):
        return True
    if EDITORIAL_PATH_RE.search(page.path) and page.words_main >= 150:
        return True
    return page.words_main >= 300 and bool(page_dates(page))


def _has_structured_attribution(page) -> bool:
    if page.meta_get("author", "article:author"):
        return True
    for node in page.jsonld:
        for key in ("author", "publisher", "creator"):
            val = node.get(key)
            if isinstance(val, dict) and val.get("name"):
                return True
            if isinstance(val, str) and val.strip():
                return True
            if isinstance(val, list) and val:
                return True
    return False
