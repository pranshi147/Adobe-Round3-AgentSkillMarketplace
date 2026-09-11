"""Machine-readability detectors: MR-001 .. MR-009.

Question answered by this module:
    "Can a retrieval agent reliably reach the site's important pages and extract
     text from them?"

Every detector follows the same contract:

    CHECK -> RAW OBSERVATION -> EVIDENCE -> FALSE-POSITIVE GUARDS
          -> CONFIDENCE -> FINDING -> SEVERITY -> ACTION

Detectors never fabricate observations: each Evidence item is a measurement
taken from the fetched bytes. The prose that explains *why* an observation
matters comes from references/defect-registry.json, not from a model.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from evidencekit import textutil as tu                       # noqa: E402
from evidencekit.crawl import (                              # noqa: E402
    normalize_url, is_crawlable_candidate, is_key_page, same_site, path_importance)
from evidencekit.findings import (                           # noqa: E402
    Evidence, Finding, registry_action, severity_from_share)

SKILL = "machine-readability"

PAGINATION_RE = re.compile(r"([?&]page=|/page/\d+|[?&]p=\d+|[?&]offset=)", re.IGNORECASE)
LOW_TEXT_TEMPLATE_RE = re.compile(
    r"/(contact|locations?|gallery|media|press-kit|downloads?|thank-you|"
    r"subscribe|unsubscribe|legal|terms|privacy|cookies?)(/|$)", re.IGNORECASE)


def run(ctx) -> list:
    findings = []
    for fn in (mr001, mr002, mr003, mr004, mr005, mr006, mr007, mr008, mr009):
        try:
            findings.extend(fn(ctx))
        except Exception as exc:  # one broken detector must not kill the audit
            ctx.note(getattr(fn, "defect_id", fn.__name__), ctx.ev.root_url,
                     f"detector raised {type(exc).__name__}: {exc}",
                     reason="detector error; no finding emitted")
    return findings


# ---------------------------------------------------------------- MR-001
def mr001(ctx) -> list:
    ev = ctx.ev
    robots = ev.robots
    if not robots or not robots.present:
        return []
    spec = ctx.spec("MR-001")

    candidates = [ev.root_url]
    sitemap_set = set(ev.sitemap_entries)
    candidates += list(sitemap_set)
    for targets in ev.link_graph.values():
        candidates += list(targets)

    seen, blocked = set(), []
    for url in candidates:
        n = normalize_url(url)
        if not n or n in seen:
            continue
        seen.add(n)
        if not same_site(n, ev.root_url) or not is_crawlable_candidate(n):
            continue          # guard: utility paths and assets are excluded
        if robots.allowed(n, ctx.user_agent):
            continue
        rule = robots.blocking_rule(n, ctx.user_agent)
        blocked.append((n, rule[1] if rule else "Disallow", n in sitemap_set))
        if len(blocked) >= 40:
            break

    if not blocked:
        return []

    target_blocked = any(normalize_url(u) == normalize_url(ev.root_url) for u, _, _ in blocked)
    sitemap_blocked = any(flag for _, _, flag in blocked)
    severity = "critical" if target_blocked else ("high" if sitemap_blocked else "medium")

    evidence = [Evidence(
        url=ev.robots_url,
        observation="robots.txt publishes a Disallow rule that matches content URLs",
        measurement=f"{len(blocked)} discovered content URL(s) matched by rule: {blocked[0][1]}",
        excerpt=blocked[0][1],
    )]
    for url, rule, from_sitemap in blocked[:4]:
        evidence.append(Evidence(
            url=url,
            observation=("URL is listed in the sitemap but disallowed to our user-agent"
                         if from_sitemap else
                         "URL is linked internally but disallowed to our user-agent"),
            measurement=f"matched robots rule: {rule}",
        ))

    return [Finding(
        id="MR-001", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="verified", confidence=0.98,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[u for u, _, _ in blocked],
        measurements={"blocked_urls": len(blocked), "sitemap_listed_blocked": sum(
            1 for _, _, f in blocked if f)},
        effort=spec["effort"],
        core_page_affected=target_blocked,
        affected_share=1.0 if target_blocked else min(1.0, len(blocked) / max(1, len(seen))),
        suggested_action=registry_action(spec, example=blocked[0][0], rule=blocked[0][1]),
    )]


# ---------------------------------------------------------------- MR-002
def mr002(ctx) -> list:
    spec = ctx.spec("MR-002")
    pages = ctx.content_pages()
    if not pages:
        return []
    hits = []
    for p in pages:
        directives = p.robots_directives()
        if "noindex" not in directives and "none" not in directives:
            continue
        source = "X-Robots-Tag header" if "noindex" in (
            p.headers.get("x-robots-tag") or "").lower() else "meta robots tag"
        value = p.headers.get("x-robots-tag") if source.startswith("X-") else p.meta_get("robots", "googlebot")
        hits.append((p, source, value))
    if not hits:
        return []

    core_hit = any(ctx.is_core(p) or ctx.is_target(p) for p, _, _ in hits)
    share = len(hits) / len(pages)
    severity = "critical" if core_hit else ("high" if share >= 0.25 else "medium")

    evidence = [Evidence(
        url=p.final_url,
        observation=f"page excludes itself from indexing via {src}",
        measurement=f"{src} value: {val}",
    ) for p, src, val in hits[:6]]

    return [Finding(
        id="MR-002", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="verified", confidence=0.99,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _, _ in hits],
        measurements={"noindexed_pages": len(hits), "sampled_content_pages": len(pages),
                      "share": round(share, 2)},
        effort=spec["effort"], core_page_affected=core_hit, affected_share=share,
        suggested_action=registry_action(spec, example=hits[0][0].final_url),
    )]


# ---------------------------------------------------------------- MR-003
def mr003(ctx) -> list:
    spec = ctx.spec("MR-003")
    ev = ctx.ev
    broken = {}

    for fail in ev.fetch_failures:
        status = fail.get("status") or 0
        if status < 400 or status == 429:
            continue
        refs = sorted(ev.referrers.get(normalize_url(fail["url"]), []))
        broken[normalize_url(fail["url"])] = {"status": status, "referrers": refs[:3]}

    for fail in ctx.link_check_failures:
        status = fail.get("status") or 0
        if status < 400 or status == 429:
            continue          # guard: timeouts/rate limits are not "broken"
        broken[normalize_url(fail["url"])] = {
            "status": status, "referrers": fail.get("referrers", [])[:3]}

    broken = {u: d for u, d in broken.items() if d["referrers"]}
    if not broken:
        return []

    home = ctx.homepage()
    home_url = normalize_url(home.final_url) if home else ""
    from_home = any(home_url in d["referrers"] for d in broken.values())
    severity = "high" if (len(broken) >= 3 or from_home) else "medium"

    evidence = [Evidence(
        url=url,
        observation=f"internally linked destination returns HTTP {d['status']}",
        measurement="linked from: " + ", ".join(d["referrers"]),
    ) for url, d in list(broken.items())[:6]]

    return [Finding(
        id="MR-003", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="verified", confidence=0.97,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=list(broken),
        measurements={"broken_destinations": len(broken), "linked_from_homepage": from_home},
        effort=spec["effort"],
        core_page_affected=any(path_importance(u) >= 8 for u in broken),
        affected_share=min(1.0, len(broken) / max(1, len(ev.link_graph) or 1)),
        suggested_action=registry_action(spec, count=len(broken)),
    )]


# ---------------------------------------------------------------- MR-004
def mr004(ctx) -> list:
    spec = ctx.spec("MR-004")
    pages = [p for p in ctx.content_pages() if p.canonical]
    if not pages:
        return []

    evidence, severity_bits, affected = [], [], []
    failed_urls = {normalize_url(f["url"]) for f in ctx.ev.fetch_failures
                   if (f.get("status") or 0) >= 400}
    failed_urls |= {normalize_url(f["url"]) for f in ctx.link_check_failures
                    if (f.get("status") or 0) >= 400}

    host = urlparse(ctx.ev.root_url).netloc.lower().lstrip("www.")
    for p in pages:
        can = normalize_url(p.canonical)
        own = normalize_url(p.final_url)
        if not can or can == own:
            continue
        if PAGINATION_RE.search(p.final_url):
            continue                       # guard: paginated series
        if _differs_only_trivially(can, own):
            continue                       # guard: slash/scheme/www/tracking
        if can in failed_urls:
            evidence.append(Evidence(
                url=p.final_url,
                observation="rel=canonical points at a URL that does not resolve",
                measurement=f"canonical={p.canonical} returns an error status"))
            severity_bits.append("high")
            affected.append(p.final_url)
            continue
        can_host = urlparse(can).netloc.lower().lstrip("www.")
        if can_host and can_host != host:
            evidence.append(Evidence(
                url=p.final_url,
                observation="rel=canonical assigns this page's identity to another domain",
                measurement=f"page host={host}, canonical host={can_host}; "
                            f"legitimate for syndication — confirm this is intended"))
            severity_bits.append("low")
            affected.append(p.final_url)

    # Content collapse: dissimilar pages sharing one canonical target.
    groups: dict = {}
    for p in pages:
        can = normalize_url(p.canonical)
        if can:
            groups.setdefault(can, []).append(p)
    for can, members in groups.items():
        uniq = {normalize_url(m.final_url): m for m in members}
        if len(uniq) < 2:
            continue
        ms = list(uniq.values())
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                a, b = ms[i], ms[j]
                if a.words_main < 60 and b.words_main < 60:
                    continue
                sim = ctx.similarity(a, b)
                if sim >= 0.6:
                    continue               # guard: genuine duplicates are fine
                evidence.append(Evidence(
                    url=a.final_url,
                    observation="two pages with materially different content declare the same canonical URL",
                    measurement=f"other page={b.final_url}; shared canonical={can}; "
                                f"main-text similarity={sim:.2f}"))
                severity_bits.append("high")
                affected.extend([a.final_url, b.final_url])
                break

    if not evidence:
        return []
    severity = ("high" if "high" in severity_bits
                else "medium" if "medium" in severity_bits else "low")
    level = "verified" if "high" in severity_bits else "corroborated"

    return [Finding(
        id="MR-004", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence[:6], evidence_level=level, confidence=0.9,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=list(dict.fromkeys(affected)),
        measurements={"pages_with_canonical": len(pages), "conflicts": len(evidence)},
        effort=spec["effort"],
        core_page_affected=any(ctx.is_core(p) for p in pages
                               if p.final_url in affected),
        affected_share=len(set(affected)) / max(1, len(ctx.content_pages())),
        suggested_action=registry_action(spec),
    )]


def _differs_only_trivially(a: str, b: str) -> bool:
    def strip(u):
        p = urlparse(u)
        host = p.netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        return host + (p.path or "/").rstrip("/")
    return strip(a) == strip(b)


# ---------------------------------------------------------------- MR-005
def mr005(ctx) -> list:
    spec = ctx.spec("MR-005")
    pages = [p for p in ctx.content_pages() if not LOW_TEXT_TEMPLATE_RE.search(p.path)]
    if not pages:
        return []

    THRESHOLD = 120
    affected = []
    for p in pages:
        if p.words_main >= THRESHOLD:
            continue
        script_ratio = (p.script_bytes / p.html_bytes) if p.html_bytes else 0.0
        indicator = None
        if p.empty_app_root:
            indicator = f"empty application root element id=\"{p.app_root_id}\""
        elif script_ratio >= 0.4 and p.script_tags >= 3:
            indicator = f"script payload is {script_ratio:.0%} of the served document"
        if not indicator:
            continue                        # guard: low text alone is not a defect
        if tu.word_count(p.noscript_text) >= 40:
            ctx.note("MR-005", p.final_url,
                     "served HTML is a shell but a <noscript> fallback carries content",
                     f"main words={p.words_main}, noscript words={tu.word_count(p.noscript_text)}",
                     "fallback content exists; downgraded")
            continue                        # guard: usable fallback exists
        affected.append((p, indicator, script_ratio))

    if not affected:
        return []
    home = ctx.homepage()
    home_affected = any(p is home or ctx.is_target(p) for p, _, _ in affected)
    share = len(affected) / len(pages)

    if len(affected) == 1 and not home_affected:
        p, indicator, _ = affected[0]
        ctx.note("MR-005", p.final_url,
                 "served HTML carries little main-region text and shows a rendering indicator",
                 f"main words={p.words_main}; {indicator}",
                 "single non-core page; below the two-page confidence gate")
        return []

    severe_share = sum(1 for p, _, _ in affected if p.words_main < 80) / len(pages)
    if severe_share >= 0.8 and home_affected:
        severity = "critical"
    elif home_affected or share >= 0.4:
        severity = "high"
    else:
        severity = "medium"

    evidence = [Evidence(
        url=p.final_url,
        observation="served HTML contains almost no main-region text; content appears to be assembled client-side",
        measurement=f"main-region words in served HTML={p.words_main} "
                    f"(threshold {THRESHOLD}); {indicator}",
    ) for p, indicator, _ in affected[:6]]

    return [Finding(
        id="MR-005", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.86,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _, _ in affected],
        measurements={"pages_below_threshold": len(affected),
                      "sampled_content_pages": len(pages),
                      "share": round(share, 2),
                      "median_main_words": _median([p.words_main for p, _, _ in affected])},
        effort=spec["effort"], core_page_affected=home_affected, affected_share=share,
        suggested_action=registry_action(spec, example=affected[0][0].final_url),
    )]


def _median(values):
    if not values:
        return 0
    vs = sorted(values)
    mid = len(vs) // 2
    return vs[mid] if len(vs) % 2 else (vs[mid - 1] + vs[mid]) // 2


# ---------------------------------------------------------------- MR-006
def mr006(ctx) -> list:
    spec = ctx.spec("MR-006")
    shell_urls = {p.final_url for p in ctx.content_pages()
                  if p.words_main < 120 and (p.empty_app_root or
                                             (p.html_bytes and p.script_bytes / p.html_bytes >= 0.4))}
    pages = [p for p in ctx.content_pages() if p.final_url not in shell_urls]
    if not pages:
        return []

    affected = []
    for p in pages:
        if p.regions_unreliable:
            ctx.note("MR-006", p.final_url,
                     "main-content and navigation regions could not be separated on this page",
                     f"no semantic landmarks and no recognisable chrome classes; "
                     f"{len(p.links)} links",
                     "region separation unreliable; this page was excluded from the "
                     "boilerplate measurement rather than judged on a guess")
            continue
        total_words = p.words_all
        if total_words < 60:
            continue
        main_share = p.words_main / total_words if total_words else 0.0
        text_chars = len(p.text_main) + len(p.text_chrome)
        link_share = (p.link_text_chars / text_chars) if text_chars else 0.0
        n_links = len(p.links)
        if main_share < 0.25 and link_share > 0.5 and n_links > 60:
            affected.append((p, main_share, link_share, n_links))

    if not affected:
        return []
    if len(affected) == 1:
        p, ms, ls, n = affected[0]
        ctx.note("MR-006", p.final_url,
                 "page text is dominated by navigation and link labels",
                 f"main-region share={ms:.0%}, link-text share={ls:.0%}, {n} links",
                 "single page; one navigation-heavy index page is a normal site feature")
        return []
    share = len(affected) / len(pages)
    core = any(ctx.is_core(p) for p, _, _, _ in affected)
    severity = "high" if (share >= 0.4 or (core and len(affected) >= 2)) else "medium"

    evidence = [Evidence(
        url=p.final_url,
        observation="page text is dominated by navigation and link labels rather than content",
        measurement=f"main-region words={p.words_main} of {p.words_all} total "
                    f"({ms:.0%} main); link text={ls:.0%} of all text; {n} links",
    ) for p, ms, ls, n in affected[:6]]

    return [Finding(
        id="MR-006", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.82,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.final_url for p, _, _, _ in affected],
        measurements={"affected_pages": len(affected), "sampled_content_pages": len(pages),
                      "share": round(share, 2)},
        effort=spec["effort"], core_page_affected=core, affected_share=share,
        suggested_action=registry_action(spec, example=affected[0][0].final_url),
    )]


# ---------------------------------------------------------------- MR-007
def mr007(ctx) -> list:
    spec = ctx.spec("MR-007")
    pages = ctx.content_pages()
    if not pages:
        return []

    evidence, bits, affected = [], [], []

    missing_title = [p for p in pages if not p.title.strip()]
    for p in missing_title[:3]:
        evidence.append(Evidence(
            url=p.final_url,
            observation="page has no <title> element, so it carries no machine-readable label",
            measurement="title length = 0 characters"))
        affected.append(p.final_url)
        bits.append("high" if ctx.is_core(p) else "medium")

    by_title: dict = {}
    for p in pages:
        t = tu.normalize_ws(p.title).lower()
        if t:
            by_title.setdefault(t, []).append(p)
    for title, members in by_title.items():
        uniq = list({normalize_url(m.final_url): m for m in members}.values())
        if len(uniq) < 2:
            continue
        if any(PAGINATION_RE.search(m.final_url) for m in uniq):
            continue                              # guard: paginated series
        pair = None
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                if ctx.similarity(uniq[i], uniq[j]) < 0.8:   # guard: real duplicates -> FI-004
                    pair = (uniq[i], uniq[j], ctx.similarity(uniq[i], uniq[j]))
                    break
            if pair:
                break
        if not pair:
            continue
        a, b, sim = pair
        evidence.append(Evidence(
            url=a.final_url,
            observation="distinct pages with different content publish an identical title",
            measurement=f"title=\"{tu.truncate(a.title, 90)}\" also used by {b.final_url}; "
                        f"main-text similarity={sim:.2f}; {len(uniq)} URLs share it"))
        affected.extend(m.final_url for m in uniq)
        bits.append("high" if len(uniq) >= 3 else "medium")

    no_h1 = [p for p in pages if p.words_main >= 120 and not p.h1s]
    if no_h1:
        evidence.append(Evidence(
            url=no_h1[0].final_url,
            observation="content page has no H1 heading",
            measurement=f"{len(no_h1)} of {len(pages)} sampled content pages have no H1"))
        affected.extend(p.final_url for p in no_h1)
        bits.append("medium" if len(no_h1) >= 2 else "low")

    if not evidence:
        return []
    severity = "high" if "high" in bits else ("medium" if "medium" in bits else "low")
    core = any(ctx.is_core(p) for p in pages if p.final_url in set(affected))

    return [Finding(
        id="MR-007", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence[:6], evidence_level="verified", confidence=0.94,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=list(dict.fromkeys(affected)),
        measurements={"pages_without_title": len(missing_title),
                      "pages_without_h1": len(no_h1),
                      "duplicate_title_groups": sum(
                          1 for m in by_title.values() if len(m) > 1)},
        effort=spec["effort"], core_page_affected=core,
        affected_share=len(set(affected)) / max(1, len(pages)),
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- MR-008
def mr008(ctx) -> list:
    """Enumeration failure = no usable sitemap AND measurably weak internal discovery.

    A missing sitemap on a small, well-linked site is enumerable through links
    alone, so absence by itself is routed to a proactive opportunity rather than
    reported as a defect.
    """
    spec = ctx.spec("MR-008")
    ev = ctx.ev
    if ev.scope != "site":
        return []                                  # not checked in single-page scope
    if ev.sitemap_status not in ("absent", "unreachable", "invalid", "empty"):
        return _sitemap_coverage_note(ctx)

    weaknesses = _discovery_weaknesses(ctx)
    if not weaknesses:
        ctx.note("MR-008", ev.robots_url,
                 "no usable XML sitemap resolves for this site",
                 f"sitemap status={ev.sitemap_status}",
                 "internal linking is adequate, so enumeration does not depend on a "
                 "sitemap; raised as a proactive opportunity instead of a finding")
        return []

    attempts = ev.sitemap_attempts or [
        (ev.robots_url, "no Sitemap: directive in robots.txt and /sitemap.xml did not resolve")]
    evidence = [Evidence(
        url=url,
        observation="no usable XML sitemap could be retrieved at this location",
        measurement=outcome) for url, outcome in attempts[:3]]
    evidence.extend(weaknesses["evidence"])

    return [Finding(
        id="MR-008", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"],
        severity=weaknesses["severity"],
        evidence=evidence[:6], evidence_level="corroborated", confidence=0.82,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[ev.root_url] + weaknesses["urls"],
        measurements={"sitemap_status": ev.sitemap_status,
                      "homepage_internal_destinations": weaknesses["home_links"],
                      "unlinked_important_pages_at_depth_3_plus": len(weaknesses["urls"])},
        effort=spec["effort"], core_page_affected=True,
        affected_share=weaknesses["share"],
        suggested_action=registry_action(spec),
    )]


def _discovery_weaknesses(ctx):
    """Corroborating evidence that link-based enumeration is genuinely weak."""
    home = ctx.homepage()
    if home is None:
        return None
    home_targets = {normalize_url(l.href) for l in home.internal_links}
    buried = [p for p in ctx.content_pages()
              if p is not home
              and normalize_url(p.final_url) not in home_targets
              and is_key_page(p.final_url)
              and p.depth >= 3]
    evidence, urls = [], []
    if buried:
        for p in buried[:3]:
            evidence.append(Evidence(
                url=p.final_url,
                observation="an important page is neither listed in a sitemap nor linked "
                            "from the entry page",
                measurement=f"first reached at depth {p.depth}"))
            urls.append(p.final_url)
        return {"severity": "medium", "evidence": evidence, "urls": urls,
                "home_links": len(home_targets),
                "share": len(buried) / max(1, len(ctx.content_pages()))}
    if len(home_targets) < 5 and len(ctx.content_pages()) >= 5:
        evidence.append(Evidence(
            url=home.final_url,
            observation="the entry page exposes very few internal destinations, so a "
                        "link-following crawl has little to expand from",
            measurement=f"{len(home_targets)} distinct internal destination(s) on the homepage"))
        return {"severity": "low", "evidence": evidence, "urls": [],
                "home_links": len(home_targets), "share": 0.4}
    return None


def _sitemap_coverage_note(ctx) -> list:
    """A sitemap exists but covers little of the link graph: informational only."""
    ev = ctx.ev
    linked = set()
    for targets in ev.link_graph.values():
        linked |= {t for t in targets if is_crawlable_candidate(t)}
    if not linked:
        return []
    covered = len(linked & set(ev.sitemap_entries)) / len(linked)
    if covered >= 0.3:
        return []
    ctx.note("MR-008", ev.sitemap_urls[0] if ev.sitemap_urls else ev.robots_url,
             "the sitemap lists a small fraction of the internally linked URLs",
             f"{len(linked & set(ev.sitemap_entries))} of {len(linked)} linked URLs "
             f"listed ({covered:.0%})",
             "the pages are still reachable by following links, so low coverage alone "
             "is reported as an opportunity rather than a defect")
    return []


# ---------------------------------------------------------------- MR-009
def mr009(ctx) -> list:
    """Non-descriptive anchors whose destination is described nowhere in the sample.

    A "Read more" link sitting beside a descriptive link to the same page loses
    nothing, so only anchors whose destination has no descriptive label anywhere
    are counted.
    """
    spec = ctx.spec("MR-009")
    pages = ctx.content_pages()
    described: set = set()
    anchors: list = []
    for p in pages:
        for link in p.internal_links:
            if PAGINATION_RE.search(link.href):
                continue                              # guard: pagination controls
            label = link.label
            if label.strip().isdigit():
                continue
            target = normalize_url(link.href)
            if tu.is_nondescriptive_anchor(label):
                anchors.append((p.final_url, label, link.href, target, True))
            else:
                described.add(target)
                anchors.append((p.final_url, label, link.href, target, False))

    total = len(anchors)
    if total < 25:
        return []                                     # guard: too few links to judge
    weak = [a for a in anchors if a[4] and a[3] not in described]
    share = len(weak) / total
    if share < 0.3:
        return []
    severity = "medium" if share >= 0.45 else "low"

    deep = [p for p in pages if p.depth >= 3 and path_importance(p.final_url) >= 5]
    evidence = [Evidence(
        url=ctx.ev.root_url,
        observation="a large share of internal anchors carry no destination-describing "
                    "label, and their destinations are described nowhere else in the sample",
        measurement=f"{len(weak)} of {total} internal anchors ({share:.0%}) across "
                    f"{len(pages)} sampled pages")]
    for src, label, href, _t, _w in weak[:4]:
        evidence.append(Evidence(
            url=src,
            observation="internal link label does not describe its destination",
            measurement=f"anchor text=\"{tu.truncate(label, 60)}\" -> {href}"))

    return [Finding(
        id="MR-009", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence[:6], evidence_level="corroborated", confidence=0.8,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=list(dict.fromkeys(a[0] for a in weak)),
        measurements={"internal_anchors": total, "non_descriptive_unrecoverable": len(weak),
                      "share": round(share, 2),
                      "important_pages_at_depth_3_plus": len(deep)},
        effort=spec["effort"], core_page_affected=False, affected_share=share,
        suggested_action=registry_action(spec),
    )]
