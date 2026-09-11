"""Off-site discoverability detectors: EX-001 .. EX-006.

Question answered by this module:
    "Can this entity be corroborated and told apart from others *outside* the
     four walls of its own site?"

Two of these detectors are computed entirely from what the site publishes
(EX-003, EX-004) and always run. Four require the bounded, read-only probe of
the references the site itself declares and its own hostname variants (EX-001,
EX-002, EX-005, EX-006); when that probe did not run — network unavailable,
`--external off`, or budget exhausted — they report nothing and the reason is
carried in the report's limitations.

Together they cover the site's off-site discoverability surface: do the routes
back to this site resolve (EX-001, EX-005), do the records at the other end
concern this entity (EX-002), do they agree in both directions (EX-006), and is
the entity distinguishable at all (EX-003, EX-004).

Three things this module refuses to do, by construction:

  * It never treats "no external presence found" as a defect. The absence of a
    Wikipedia entry, social profile or directory listing is not a failure, and
    plenty of legitimate sites have none. Absence produces, at most, a proactive
    opportunity.
  * It never searches the web or contacts a third party the site did not name.
  * It never claims that any AI product does or does not use this site. Every
    finding is a specific, evidenced retrieval or trust risk.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from evidencekit import entity, textutil as tu                # noqa: E402
from evidencekit.external import mentions_brand               # noqa: E402
from evidencekit.findings import Evidence, Finding, registry_action  # noqa: E402

SKILL = "external-evidence"


def run(ctx) -> list:
    findings = []
    for fn in (ex001, ex002, ex003, ex004, ex005, ex006):
        try:
            findings.extend(fn(ctx))
        except Exception as exc:
            ctx.note(fn.__name__, ctx.ev.root_url,
                     f"detector raised {type(exc).__name__}: {exc}",
                     reason="detector error; no finding emitted")
    return findings


# ---------------------------------------------------------------- EX-001
def ex001(ctx) -> list:
    spec = ctx.spec("EX-001")
    ext = ctx.external
    if not ext.performed:
        return []                       # probe never ran; absence proves nothing
    broken = [p for p in ext.probes if p.broken]
    if not broken:
        return []

    evidence = [Evidence(
        url=p.url,
        observation="an external identifier declared by this site does not resolve",
        measurement=f"HTTP {p.status}; declared via {p.source}",
    ) for p in broken[:5]]

    return [Finding(
        id="EX-001", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity="medium",
        evidence=evidence, evidence_level="verified", confidence=0.95,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.url for p in broken],
        measurements={"declared_identifiers": len(ext.declared),
                      "probes_completed": len(ext.checked_probes),
                      "unreachable": len(broken)},
        effort=spec["effort"], core_page_affected=True,
        affected_share=len(broken) / max(1, len(ext.checked_probes)),
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- EX-002
def ex002(ctx) -> list:
    spec = ctx.spec("EX-002")
    ext = ctx.external
    if not ext.performed:
        return []
    names = entity.published_names(ctx)
    if not names:
        return []                       # nothing to corroborate against

    uncorroborated = []
    for probe in ext.probes:
        if not probe.readable:
            continue                    # guard: unreadable ≠ uncorroborated
        if not mentions_brand(probe, names):
            uncorroborated.append(probe)
    if not uncorroborated:
        return []

    severity = "medium" if len(uncorroborated) >= 2 else "low"
    searched = ", ".join(f"\"{raw}\"" for _n, raw, _c in names[:3])
    evidence = [Evidence(
        url=p.url,
        observation="a declared external identifier resolves but does not name this brand",
        measurement=f"retrieved title=\"{tu.truncate(p.title or p.site_name, 90)}\"; "
                    f"no compatible form of {searched} found in its title, site name, "
                    f"visible text or URL path",
    ) for p in uncorroborated[:5]]

    return [Finding(
        id="EX-002", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="corroborated", confidence=0.78,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.url for p in uncorroborated],
        measurements={"probes_readable": sum(1 for p in ext.probes if p.readable),
                      "without_brand_mention": len(uncorroborated),
                      "brand_names_searched": [raw for _n, raw, _c in names[:3]]},
        effort=spec["effort"], core_page_affected=False,
        affected_share=len(uncorroborated) / max(
            1, sum(1 for p in ext.probes if p.readable)),
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- EX-003
def ex003(ctx) -> list:
    """Offline: an ambiguous name published with nothing to distinguish it."""
    spec = ctx.spec("EX-003")
    primary = entity.primary_name(ctx)
    if not primary:
        return []                       # the site names itself nowhere: FI-001/FI-002
    norm, raw, _count = primary
    ambiguous, reason = entity.name_is_ambiguous(norm)
    if not ambiguous:
        return []

    found = entity.disambiguators(ctx)
    strong = {k: v for k, v in found.items() if k != "definitional_sentence"}
    if strong:
        return []                       # guard: one disambiguator of any kind suffices

    severity = "low" if "definitional_sentence" in found else "medium"
    checked = ", ".join(entity.DISAMBIGUATOR_FIELDS[:8]) + ", …"
    home = ctx.homepage()
    url = home.final_url if home else ctx.ev.root_url

    return [Finding(
        id="EX-003", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=[
            Evidence(url=url,
                     observation="the published brand name is built from ordinary words",
                     measurement=f"name=\"{raw}\"; {reason}"),
            Evidence(url=ctx.ev.root_url,
                     observation="no disambiguating assertion was found anywhere in the sample",
                     measurement=f"checked entity markup for {checked} across "
                                 f"{len(ctx.content_pages())} sampled page(s); "
                                 f"found: {', '.join(sorted(found)) or 'none'}"),
        ],
        evidence_level="corroborated", confidence=0.75,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[ctx.ev.root_url],
        measurements={"brand_name": raw, "disambiguators_found": sorted(found)},
        effort=spec["effort"], core_page_affected=True, affected_share=0.5,
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- EX-004
def ex004(ctx) -> list:
    """Offline: domain label and brand name unrelated, with no bridging assertion."""
    spec = ctx.spec("EX-004")
    primary = entity.primary_name(ctx)
    if not primary:
        return []
    norm, raw, _count = primary
    label = entity.domain_label(ctx.ev.root_url)
    if not label:
        return []
    if tu.names_compatible(norm, tu.normalize_entity_name(label)):
        return []
    if norm.replace(" ", "").startswith(label) or label in norm.replace(" ", ""):
        return []                       # guard: squashed or partial match

    found = entity.disambiguators(ctx)
    if "url" in found or "sameAs" in found:
        return []                       # guard: the bridge exists, which is the norm

    home = ctx.homepage()
    url = home.final_url if home else ctx.ev.root_url
    return [Finding(
        id="EX-004", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity="low",
        evidence=[
            Evidence(url=url,
                     observation="the registrable domain label does not resemble the published brand name",
                     measurement=f"domain label=\"{label}\"; published brand name=\"{raw}\""),
            Evidence(url=ctx.ev.root_url,
                     observation="no entity `url` or `sameAs` assertion connects the two",
                     measurement="entity markup declares neither a url matching this origin "
                                 "nor any external identifier"),
        ],
        evidence_level="corroborated", confidence=0.74,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[ctx.ev.root_url],
        measurements={"domain_label": label, "brand_name": raw},
        effort=spec["effort"], core_page_affected=False, affected_share=0.3,
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- EX-005
def ex005(ctx) -> list:
    """Off-site route: does the brand's other hostname form reach this site?"""
    spec = ctx.spec("EX-005")
    ext = ctx.external
    if not ext.performed or not ext.host_probes:
        return []                       # no variant exists, or nothing was probed

    audited = _exact_host(ctx.ev.root_url)
    split, canonical_elsewhere = [], []
    for probe in ext.host_probes:
        if not probe.checked or not (200 <= probe.status < 300):
            continue                    # guard: a variant that does not resolve is normal
        # Compare exact hosts here, not the www-stripped form: the entire question
        # is whether the other form MOVED to the audited origin.
        if _exact_host(probe.final_url) == audited:
            continue                    # guard: it redirected home — correct consolidation
        if probe.canonical and _exact_host(probe.canonical) == audited:
            continue                    # guard: consolidated by canonical
        (canonical_elsewhere if probe.canonical else split).append(probe)

    affected = split + canonical_elsewhere
    if not affected:
        return []
    severity = "medium" if split else "low"

    evidence = [Evidence(
        url=p.url,
        observation="the other form of this site's hostname serves content without "
                    "consolidating onto the audited origin",
        measurement=f"HTTP {p.status}; resolved to {p.final_url or p.url}; "
                    f"canonical={p.canonical or 'none declared'}; "
                    f"audited origin={ctx.ev.root_url}",
    ) for p in affected]

    return [Finding(
        id="EX-005", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity=severity,
        evidence=evidence, evidence_level="verified", confidence=0.93,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.url for p in affected],
        measurements={"hostname_variants_probed": len(ext.host_probes),
                      "unconsolidated": len(affected)},
        effort=spec["effort"], core_page_affected=True, affected_share=1.0,
        suggested_action=registry_action(spec),
    )]


# ---------------------------------------------------------------- EX-006
def ex006(ctx) -> list:
    """Are the declared references mutual, or is this site talking to itself?"""
    spec = ctx.spec("EX-006")
    ext = ctx.external
    if not ext.performed:
        return []
    resolved = ext.resolved_references
    one_way = [p for p in resolved if not p.links_back]
    if len(one_way) < 2:
        return []                       # guard: one silent platform proves nothing

    audited = _bare(ctx.ev.root_url)
    evidence = [Evidence(
        url=p.url,
        observation="a declared external reference resolves but never points back to this site",
        measurement=f"HTTP {p.status}; no link to {audited} and no mention of it in the "
                    f"page text; declared via {p.source}",
    ) for p in one_way[:5]]

    return [Finding(
        id="EX-006", detector=spec["detector"], title=spec["title"], category=SKILL,
        stage=spec["stage"], failure_mode=spec["failure_mode"], severity="low",
        evidence=evidence, evidence_level="corroborated", confidence=0.74,
        impact=spec["impact"], mechanism=spec["mechanism"],
        affected_urls=[p.url for p in one_way],
        measurements={"references_resolved": len(resolved),
                      "references_linking_back": len(resolved) - len(one_way),
                      "one_way_references": len(one_way)},
        effort=spec["effort"], core_page_affected=False,
        affected_share=len(one_way) / max(1, len(resolved)),
        suggested_action=registry_action(spec),
    )]


def _exact_host(url: str) -> str:
    return (urlparse(url).netloc or "").lower()


def _bare(url: str) -> str:
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host
