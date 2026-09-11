"""Arrival-experience detectors: AX-001 .. AX-005.

Question answered by this module:
    "If a retrieval-oriented research agent sends someone to this page, does the destination
     confirm the implied answer and offer a logical next step?"

This is deliberately not a general UX audit. Every check here is about the
specific situation of an AI-referred visitor: no browsing context, a
half-answered question, and a page that must confirm the promise in seconds.
Subjective visual judgements are out of scope; only measurable structural
properties of the served page are used.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from evidencekit import textutil as tu                       # noqa: E402
from evidencekit.crawl import is_key_page, normalize_url  # noqa: E402
from evidencekit.htmlparse import context_gate_signals, has_cta  # noqa: E402
from evidencekit.findings import Evidence, Finding, registry_action  # noqa: E402

SKILL = "arrival-experience"

LISTING_PATH_RE = re.compile(
    r"/(blog|news|articles?|category|categories|collections?|tag|tags|"
    r"search|shop|products?)(/|$)", re.IGNORECASE)
CAMPAIGN_PATH_RE = re.compile(r"/(offers?|deals?|sale|promo|campaign|lp|landing)(/|$)",
                              re.IGNORECASE)
CAMPAIGN_TITLE_RE = re.compile(r"\b(sale|offer|deal|discount|% off|coupon)\b", re.IGNORECASE)


def run(ctx) -> list:
    findings = []
    for fn in (ax001, ax002, ax003, ax004, ax005, ax006, ax007):
        try:
            findings.extend(fn(ctx))
        except Exception as exc:
            ctx.note(fn.__name__, ctx.ev.root_url,
                     f"detector raised {type(exc).__name__}: {exc}",
                     reason="detector error; no finding emitted")
    return findings


# ---------------------------------------------------------------- AX-001
def ax001(ctx) -> list:
    spec = ctx.spec("AX-001")
    brand = ctx.brand_tokens()
    mismatches = []
    for p in ctx.content_pages():
        if p.words_main < 80:
            continue                       # guard: absence of content, not mismatch
        if not p.title.strip() or not p.h1s:
            continue
        title_tokens = tu.content_tokens(p.title) - brand
        if len(title_tokens) < 3:
            continue                       # guard: too short to measure
        h1_tokens = tu.content_tokens(p.h1s[0])
        body_tokens = ctx.tokens(p)
        h1_overlap = tu.jaccard(title_tokens, h1_tokens)
        body_cover = tu.overlap_ratio(title_tokens, body_tokens)
        if h1_overlap < 0.2 and body_cover < 0.3:
            missing = sorted(title_tokens - body_tokens)[:6]
            mismatches.append((p, h1_overlap, body_cover, missing))

    if not mismatches:
        return []
    core = any(ctx.is_core(p) for p, _, _, _ in mismatches)
    severity = "high" if core else "medium"
    evidence = [Evidence(
        url=p.final_url,
        observation="the page title promises a subject that the heading and body do not cover",
        measurement=f"title=\"{tu.truncate(p.title, 70)}\"; h1=\"{tu.truncate(p.h1s[0], 70)}\"; "
                    f"title/H1 token overlap={ho:.2f}; title terms present in body={bc:.0%}; "
                    f"absent title terms: {', '.join(missing) or 'n/a'}",
    ) for p, ho, bc, missing in mismatches[:5]]

    return [Finding(
        id="AX-001", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.8,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _, _, _ in mismatches],
        measurements={"mismatched_pages": len(mismatches),
                      "sampled_content_pages": len(ctx.content_pages())},
        effort=spec["effort"], core_page_affected=core,
        affected_share=len(mismatches) / max(1, len(ctx.content_pages())),
        suggested_action=registry_action(spec, example=mismatches[0][0].final_url),
    )]


# ---------------------------------------------------------------- AX-002
def ax002(ctx) -> list:
    spec = ctx.spec("AX-002")
    gaps, meta_only = [], []
    for p in ctx.content_pages():
        if not ctx.is_core(p):
            continue                       # guard: core entity pages only
        if LISTING_PATH_RE.search(p.path):
            continue
        if p.words_main < 40:
            continue                       # guard: MR-005 territory
        opening = " ".join(tu.words(p.text_main)[:120])
        opening_text = _first_words(p.text_main, 120)
        if any(tu.looks_definitional(s) for s in tu.sentences(opening_text)):
            continue
        if p.lang and not p.lang.startswith("en"):
            if p.meta_get("description"):
                continue                   # guard: non-English page with a description
        desc = p.meta_get("description", "og:description") or _markup_description(p)
        if desc and any(tu.looks_definitional(s) for s in tu.sentences(desc)):
            meta_only.append((p, desc))
        else:
            gaps.append((p, opening_text))
        del opening

    if not gaps and not meta_only:
        return []
    if gaps:
        severity, group = "medium", gaps
        evidence = [Evidence(
            url=p.final_url,
            observation="the opening content contains no plain statement of what this is",
            measurement=f"first {tu.word_count(opening)} served words contain no definitional "
                        f"sentence pattern; opening text: \"{tu.truncate(opening, 160)}\"",
        ) for p, opening in group[:4]]
    else:
        severity, group = "low", meta_only
        evidence = [Evidence(
            url=p.final_url,
            observation="the entity is defined only in the meta description, not in page content",
            measurement=f"meta description=\"{tu.truncate(desc, 120)}\"; "
                        f"no definitional sentence in the first 120 served words",
        ) for p, desc in group[:4]]

    return [Finding(
        id="AX-002", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.78,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _ in group],
        measurements={"core_pages_without_definition": len(gaps),
                      "definition_only_in_meta": len(meta_only)},
        effort=spec["effort"], core_page_affected=True,
        affected_share=len(group) / max(1, len(ctx.content_pages())),
        suggested_action=registry_action(spec, example=group[0][0].final_url),
    )]


def _markup_description(page) -> str:
    """A substantive `description` in the page's own structured data."""
    for node in page.jsonld:
        desc = node.get("description")
        if isinstance(desc, str) and tu.word_count(desc) >= 12:
            return desc
    return ""


def _first_words(text: str, n: int) -> str:
    parts = text.split()
    return " ".join(parts[:n])


# ---------------------------------------------------------------- AX-003
def ax003(ctx) -> list:
    spec = ctx.spec("AX-003")
    pages = [p for p in ctx.content_pages() if p.words_main >= 150]
    if len(pages) < 2:
        return []
    dead = []
    for p in pages:
        if p.regions_unreliable:
            ctx.note("AX-003", p.final_url,
                     "in-body links could not be separated from navigation on this page",
                     f"no semantic landmarks and no recognisable chrome classes; "
                     f"{len(p.links)} links",
                     "region separation unreliable; excluded from the dead-end measurement")
            continue
        in_body = {l.href for l in p.main_internal_links}
        if len(in_body) >= 3:
            continue
        if has_cta(p) and len(in_body) >= 1:
            continue                       # guard: a clear next action counts
        dead.append((p, len(in_body)))
    if not dead:
        return []
    share = len(dead) / len(pages)
    if share < 0.3:
        for p, n in dead:
            ctx.note("AX-003", p.final_url,
                     "content page offers no in-body route onward",
                     f"main-region internal links={n}",
                     "isolated case; below the 30% share gate")
        return []

    evidence = [Evidence(
        url=p.final_url,
        observation="substantial content page has no contextual links to a next step",
        measurement=f"main-region internal links={n} (excluding nav/header/footer); "
                    f"main-region words={p.words_main}",
    ) for p, n in dead[:5]]

    return [Finding(
        id="AX-003", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity="medium",
        evidence=evidence, evidence_level="corroborated", confidence=0.79,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _ in dead],
        measurements={"dead_end_pages": len(dead), "measured_pages": len(pages),
                      "share": round(share, 2)},
        effort=spec["effort"],
        core_page_affected=any(ctx.is_core(p) for p, _ in dead),
        affected_share=share, suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- AX-004
def ax004(ctx) -> list:
    spec = ctx.spec("AX-004")
    gated = []
    for p in ctx.content_pages():
        signals = context_gate_signals(p)
        if not signals:
            continue
        if p.words_main >= 150:
            ctx.note("AX-004", p.final_url,
                     "context selector present but substantive default content is served",
                     f"main-region words={p.words_main}; control: {tu.truncate(signals[0], 80)}",
                     "default content exists; not a retrieval gap")
            continue                       # guard: default content is served
        gated.append((p, signals[0]))

    if not gated:
        return []
    core = any(ctx.is_core(p) for p, _ in gated)
    severity = "high" if core else "medium"
    evidence = [Evidence(
        url=p.final_url,
        observation="page content appears to depend on a user context the fetcher cannot supply",
        measurement=f"context control found: \"{tu.truncate(sig, 90)}\"; "
                    f"served main-region words={p.words_main}",
    ) for p, sig in gated[:5]]

    return [Finding(
        id="AX-004", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.81,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _ in gated],
        measurements={"context_gated_pages": len(gated),
                      "sampled_content_pages": len(ctx.content_pages())},
        effort=spec["effort"], core_page_affected=core,
        affected_share=len(gated) / max(1, len(ctx.content_pages())),
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- AX-005
def ax005(ctx) -> list:
    spec = ctx.spec("AX-005")
    hits = []
    for p in ctx.content_pages():
        if p.words_main < 120 or p.regions_unreliable:
            continue                       # guard: shell pages belong to MR-005, and
            # promotional share is meaningless where regions cannot be separated
        if CAMPAIGN_PATH_RE.search(p.path) or CAMPAIGN_TITLE_RE.search(p.title or ""):
            continue                       # guard: promotional pages by design
        promo_share = len(p.text_promo) / len(p.text_main) if p.text_main else 0.0
        counts = Counter(b for b in p.blocks if tu.word_count(b) >= 5)
        repeated = [(b, c) for b, c in counts.items() if c >= 3]
        if promo_share >= 0.25 or repeated:
            hits.append((p, promo_share, repeated))

    strong = [h for h in hits if h[1] >= 0.4 or h[2]]
    if not strong:
        for p, share, _ in hits:
            ctx.note("AX-005", p.final_url,
                     "promotional blocks occupy a noticeable share of the page text",
                     f"promotional share of main text={share:.0%}",
                     "below the 40% reporting threshold and no repeated blocks")
        return []

    share = len(strong) / max(1, len(ctx.content_pages()))
    severity = "medium" if (share >= 0.3 or any(h[1] >= 0.4 for h in strong)) else "low"
    evidence = []
    for p, promo_share, repeated in strong[:5]:
        if repeated:
            block, count = repeated[0]
            evidence.append(Evidence(
                url=p.final_url,
                observation="an identical text block is emitted several times on the same page",
                measurement=f"block repeated {count}× : \"{tu.truncate(block, 90)}\"; "
                            f"promotional share of main text={promo_share:.0%}"))
        else:
            evidence.append(Evidence(
                url=p.final_url,
                observation="promotional containers hold a large share of the page's own text",
                measurement=f"promotional characters={len(p.text_promo)} of "
                            f"{len(p.text_main)} main-region characters "
                            f"({promo_share:.0%})"))

    return [Finding(
        id="AX-005", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.76,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _, _ in strong],
        measurements={"affected_pages": len(strong),
                      "max_promotional_share": round(max(h[1] for h in strong), 2),
                      "pages_with_repeated_blocks": sum(1 for h in strong if h[2])},
        effort=spec["effort"],
        core_page_affected=any(ctx.is_core(p) for p, _, _ in strong),
        affected_share=share, suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- AX-006
def ax006(ctx) -> list:
    """Substance hidden behind interaction while the visible page stays thin."""
    spec = ctx.spec("AX-006")
    shell_urls = {p.final_url for p in ctx.content_pages()
                  if ctx.rendering_of(p) == "likely_client_rendered"}
    gated = []
    for p in ctx.content_pages():
        if p.final_url in shell_urls:
            continue                       # guard: MR-005 territory, nothing was served
        visible = p.words_visible_main
        hidden = p.words_hidden
        if visible >= 120:
            continue                       # guard: progressive disclosure over a real answer
        if hidden < 60 or hidden < 2 * max(1, visible):
            continue                       # guard: a collapsed extra is not a gate
        gated.append((p, visible, hidden))

    if not gated:
        return []
    core = any(ctx.is_core(p) for p, _, _ in gated)
    if len(gated) == 1 and not core:
        p, visible, hidden = gated[0]
        ctx.note("AX-006", p.final_url,
                 "page substance sits inside collapsed containers",
                 f"visible main words={visible}, hidden words={hidden}",
                 "single non-core page; below the two-page confidence gate")
        return []

    severity = "high" if core else "medium"
    evidence = [Evidence(
        url=p.final_url,
        observation="the page's substance is only reachable by interacting with it",
        measurement=f"always-visible main words={visible}; words inside collapsed "
                    f"containers={hidden}; container(s): "
                    f"{', '.join(p.hidden_containers[:2])}",
    ) for p, visible, hidden in gated[:5]]

    return [Finding(
        id="AX-006", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.8,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _, _ in gated],
        measurements={"interaction_gated_pages": len(gated),
                      "sampled_content_pages": len(ctx.content_pages()),
                      "max_hidden_words": max(h for _, _, h in gated)},
        effort=spec["effort"], core_page_affected=core,
        affected_share=len(gated) / max(1, len(ctx.content_pages())),
        suggested_action=registry_action(spec, example=gated[0][0].final_url),
    )]


# ---------------------------------------------------------------- AX-007
def ax007(ctx) -> list:
    """Important pages that the entry page never links to and that sit deep."""
    spec = ctx.spec("AX-007")
    home = ctx.homepage()
    if home is None:
        return []
    home_targets = {normalize_url(l.href) for l in home.internal_links}
    sitemap = set(ctx.ev.sitemap_entries)

    buried = []
    for p in ctx.content_pages():
        url = normalize_url(p.final_url)
        if url in home_targets or p is home:
            continue                       # guard: linked from the entry page in any region
        if not is_key_page(p.final_url):
            continue                       # guard: recognised key paths only; deep
            # editorial content is expected to be deep and never fires this rule
        if p.depth < 3:
            continue
        buried.append((p, url in sitemap))

    if not buried:
        return []
    all_in_sitemap = all(in_sitemap for _p, in_sitemap in buried)
    severity = "low" if all_in_sitemap else "medium"
    evidence = [Evidence(
        url=p.final_url,
        observation="an important page is not linked from the entry page and sits deep in the site",
        measurement=f"first reached at depth {p.depth}; homepage links to "
                    f"{len(home_targets)} internal URL(s), none of them this one; "
                    f"{'listed' if in_sitemap else 'not listed'} in a sitemap",
    ) for p, in_sitemap in buried[:5]]

    return [Finding(
        id="AX-007", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="verified", confidence=0.9,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _ in buried],
        measurements={"buried_important_pages": len(buried),
                      "homepage_internal_links": len(home_targets),
                      "all_listed_in_sitemap": all_in_sitemap},
        effort=spec["effort"],
        core_page_affected=any(ctx.is_core(p) for p, _ in buried),
        affected_share=len(buried) / max(1, len(ctx.content_pages())),
        suggested_action=registry_action(spec),
    )]
