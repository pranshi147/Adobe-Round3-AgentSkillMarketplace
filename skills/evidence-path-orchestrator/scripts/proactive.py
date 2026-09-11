"""Proactive opportunities.

These are improvements that would strengthen discoverability, trust or
engagement where **no defect was detected**. They are kept in a separate
report section from `findings` on purpose: mixing "we proved this is broken"
with "this would be better" destroys the credibility of both.

Rules every generator here obeys:
  * it fires from an observation actually made during the audit;
  * it does not fire when the corresponding defect already fired (that would
    duplicate the finding as advice);
  * it carries the same what / where / why / how / how-to-verify shape as a
    suggested action, so it is directly actionable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from evidencekit import textutil as tu                       # noqa: E402

QUESTION_MARKERS = ("faq", "frequently asked", "how do i", "how to", "what is",
                    "can i ", "do you ", "?")


def generate(ctx, findings: list) -> list:
    fired = {f.id for f in findings}
    out = []
    for gen in (_external_identifiers, _independent_description, _sameas,
                _sitemap_absent, _faq, _breadcrumbs,
                _passage_structure, _entity_summary_block, _sitemap_lastmod,
                _product_markup):
        try:
            item = gen(ctx, fired)
        except Exception:
            item = None
        if item:
            out.append(item)
    for idx, item in enumerate(out, start=1):
        item["id"] = f"PO-{idx:03d}"
    return out


def _op(title, stage, observation, url, summary, implementation,
        why_it_works, verification, priority="P3"):
    return {
        "id": "",
        "title": title,
        "stage": stage,
        "observation": observation,
        "observed_at": url,
        "priority": priority,
        "suggested_action": {
            "summary": summary,
            "implementation": implementation,
            "why_it_works": why_it_works,
            "verification": verification,
            "priority": priority,
        },
    }


def _entity_nodes(page):
    return page.jsonld_nodes_of("Organization", "LocalBusiness", "Corporation",
                                "WebSite", "OnlineStore", "Store")


def _external_identifiers(ctx, fired):
    """No declared external identifiers at all.

    Reported as an opportunity and never as a finding: many legitimate sites
    have no external profiles worth declaring, and the audit makes no claim
    about what exists off-site that it did not look for.
    """
    if "FI-002" in fired or "EX-003" in fired:
        return None
    if ctx.external.declared:
        return None
    if not any(_entity_nodes(p) for p in ctx.content_pages()):
        return None                    # no entity markup at all -> FI-002's territory
    home = ctx.homepage()
    url = home.final_url if home else ctx.ev.root_url
    return _op(
        "Declare external identifiers so the entity can be corroborated off-site",
        "IDENTIFY",
        "The site publishes entity markup but declares no external identifiers, so there "
        "was nothing for the off-site pass to corroborate against. This is not a defect — "
        "it simply means cross-source agreement cannot currently be established from what "
        "the site publishes.",
        url,
        "Add sameAs identifiers for records that already describe this entity.",
        ["List the authoritative profiles that genuinely exist for this brand — official "
         "social accounts, registry or licensing listings, app store pages, industry "
         "directories — and add them to the Organization node's `sameAs` array.",
         "Include only records you control or can verify describe this entity; a wrong "
         "identifier is worse than none.",
         "If no such record exists, this opportunity does not apply — do not create "
         "profiles solely to satisfy it."],
        "Cross-source entity resolution works by finding the same entity asserted "
        "independently in more than one place. Declared identifiers give a research agent "
        "a route to that agreement instead of leaving it to infer the connection.",
        "Re-run the audit with external checks enabled and confirm the declared "
        "identifiers resolve and name the brand.",
        priority="P3",
    )


def _sitemap_absent(ctx, fired):
    """A missing sitemap on an otherwise well-linked site."""
    if "MR-008" in fired:
        return None
    ev = ctx.ev
    if ev.scope != "site" or ev.sitemap_status not in ("absent", "unreachable",
                                                       "invalid", "empty"):
        return None
    return _op(
        "Publish an XML sitemap",
        "DISCOVER",
        f"No usable XML sitemap resolved (status: {ev.sitemap_status}). Internal linking "
        f"is adequate, so the site is enumerable without one — this is an improvement, "
        f"not a defect.",
        ev.robots_url,
        "Generate /sitemap.xml and reference it from robots.txt.",
        ["List every canonical, indexable URL with a lastmod date reflecting the real "
         "edit time.",
         "Add `Sitemap: https://<host>/sitemap.xml` to robots.txt.",
         "Regenerate on publish rather than on a fixed schedule."],
        "A sitemap gives enumeration that does not depend on link depth, which matters "
        "most as a site grows past the point where shallow crawling reaches everything.",
        "Fetch /sitemap.xml and confirm it parses and lists canonical URLs.",
        priority="P3",
    )


def _independent_description(ctx, fired):
    """External references resolve, but none carries a description of the brand.

    An opportunity, never a defect: the audit only looked at records the site
    itself named, so it cannot and does not claim that no independent
    description of this brand exists anywhere.
    """
    ext = ctx.external
    if not ext.performed or "EX-002" in fired:
        return None
    resolved = ext.resolved_references
    if not resolved or ext.independent_descriptions:
        return None
    home = ctx.homepage()
    return _op(
        "Give the external records a usable description of the brand",
        "IDENTIFY",
        f"{len(resolved)} declared external reference(s) resolved, and none of them "
        f"carries a description of the brand that a research agent could read. The audit "
        f"only inspected records this site names, so this says nothing about what exists "
        f"elsewhere on the web.",
        resolved[0].url,
        "Fill in the description field on the external profiles you control.",
        ["On each profile, write two or three factual sentences stating what the "
         "organisation does, who it serves and where it operates.",
         "Keep the wording close to the description in the site's own entity markup, so "
         "the two records corroborate rather than compete.",
         "Include the canonical site URL on the profile so the description and the domain "
         "travel together."],
        "A description held only on the audited site has to be taken on that site's own "
        "word. The same facts stated on an independent record give a resolver something "
        "to check them against.",
        "Re-run the audit with external checks enabled and confirm "
        "external_corroboration.independent_descriptions_found is above zero.",
        priority="P3",
    )


def _sameas(ctx, fired):
    if "FI-002" in fired:
        return None
    nodes = [n for p in ctx.content_pages() for n in _entity_nodes(p)]
    if not nodes:
        return None
    if any(n.get("sameAs") for n in nodes):
        return None
    home = ctx.homepage()
    url = home.final_url if home else ctx.ev.root_url
    return _op(
        "Anchor the brand to external identifiers with sameAs",
        "IDENTIFY",
        "Organization/WebSite structured data is present but declares no sameAs identifiers.",
        url,
        "Add a sameAs array of authoritative external identifiers to the entity JSON-LD.",
        ["List the official profiles that already exist for the brand "
         "(LinkedIn, Crunchbase, Wikidata/Wikipedia, industry registries, app stores).",
         "Add them as `\"sameAs\": [...]` inside the Organization node on the homepage.",
         "Keep the list to identifiers you control or that are verifiably about this entity."],
        "Entity resolution merges assertions across sources; sameAs gives an entity-resolution step an "
        "explicit link between this site and the records that already describe the brand, "
        "which is what separates one entity from similarly-named ones.",
        "Re-fetch the homepage, confirm the sameAs array parses, and check each URL "
        "resolves to a page about this organisation.",
        priority="P2",
    )


def _faq(ctx, fired):
    pages = ctx.content_pages()
    if not pages:
        return None
    if any(p.jsonld_nodes_of("FAQPage", "QAPage", "HowTo") for p in pages):
        return None
    candidates = [p for p in pages
                  if sum(1 for m in QUESTION_MARKERS if m in p.text_main.lower()) >= 2
                  and p.text_main.count("?") >= 3]
    if not candidates:
        return None
    p = candidates[0]
    return _op(
        "Make existing answers directly quotable (FAQPage markup)",
        "CITE",
        f"{len(candidates)} sampled page(s) contain question-and-answer style content "
        f"with no FAQPage/QAPage structured data.",
        p.final_url,
        "Add FAQPage JSON-LD wrapping the questions and answers already published on the page.",
        ["Mark each existing question as a `Question` with an `acceptedAnswer` whose text "
         "matches the visible answer word for word.",
         "Keep the markup generated from the same content source as the visible copy so the "
         "two cannot drift apart.",
         "Do not invent questions for the markup that are not on the page."],
        "Question/answer pairs are the shape a retrieval system can lift directly as a "
        "self-contained, attributable answer, rather than having to segment prose itself.",
        "Re-fetch the page and confirm each Question node's acceptedAnswer text appears "
        "verbatim in the visible content.",
        priority="P3",
    )


def _breadcrumbs(ctx, fired):
    pages = ctx.content_pages()
    deep = [p for p in pages if p.depth >= 2]
    if len(deep) < 2:
        return None
    if any(p.jsonld_nodes_of("BreadcrumbList") for p in pages):
        return None
    return _op(
        "State where deep pages sit in the site (BreadcrumbList markup)",
        "UNDERSTAND",
        f"{len(deep)} sampled page(s) sit two or more hops from the homepage and no "
        f"BreadcrumbList structured data was found.",
        deep[0].final_url,
        "Add BreadcrumbList JSON-LD (and a visible breadcrumb trail) to nested templates.",
        ["Emit a BreadcrumbList with one ListItem per ancestor, ending at the current page.",
         "Render the same trail visibly so a referred visitor can see where they landed.",
         "Use the canonical URL of each ancestor as the ListItem `item`."],
        "Breadcrumbs state the parent/child relationship explicitly instead of leaving a "
        "machine to infer it from URL shape, which makes the page's place in the entity "
        "hierarchy citable rather than guessed.",
        "Re-fetch a deep page and confirm the BreadcrumbList parses and its items resolve.",
        priority="P3",
    )


def _passage_structure(ctx, fired):
    if "MR-005" in fired or "MR-006" in fired:
        return None
    long_pages = [p for p in ctx.content_pages() if p.words_main >= 400]
    flat = [p for p in long_pages if len([h for lvl, h in p.headings if lvl in (2, 3)]) < 2]
    if len(flat) < 2:
        return None
    return _op(
        "Make long pages quotable in passages (labelled sections)",
        "EXTRACT",
        f"{len(flat)} sampled page(s) carry 400+ words of content with fewer than two "
        f"H2/H3 section headings.",
        flat[0].final_url,
        "Add descriptive H2/H3 headings that segment long pages into topic sections.",
        ["Split the body into sections that each answer one question, and label each with "
         "an H2 stating that question or topic in plain words.",
         "Keep each section self-contained enough to be read without the sections above it.",
         "Add stable `id` attributes so individual sections can be linked and cited directly."],
        "Retrieval works on passages, not whole documents; labelled, self-contained sections "
        "give a retrieval system a unit it can select and quote with the right context attached.",
        "Re-run the audit and confirm long pages report two or more H2/H3 headings.",
        priority="P3",
    )


def _entity_summary_block(ctx, fired):
    if "AX-002" in fired or "FI-002" in fired:
        return None
    home = ctx.homepage()
    if home is None:
        return None
    nodes = _entity_nodes(home)
    if any(isinstance(n.get("description"), str) and tu.word_count(n["description"]) >= 12
           for n in nodes):
        return None
    return _op(
        "Publish a machine-readable brand fact block",
        "CITE",
        "The homepage entity markup carries no substantive `description` value.",
        home.final_url,
        "Add a short, factual description to the Organization JSON-LD and mirror it on the page.",
        ["Write two or three plain sentences covering what the organisation does, who it "
         "serves, where it operates and since when.",
         "Put that text in the Organization node's `description` and in a visible 'About' "
         "block on the homepage, keeping the wording identical.",
         "Avoid slogans and superlatives — state checkable facts."],
        "A concise factual statement is the passage a research agent can quote when asked "
        "'what is X?'; without one it has to assemble a description from marketing copy, "
        "which is where misdescription starts.",
        "Re-fetch the homepage and confirm the description exists in both JSON-LD and "
        "visible text with matching wording.",
        priority="P2",
    )


def _sitemap_lastmod(ctx, fired):
    ev = ctx.ev
    if "MR-008" in fired or ev.sitemap_status != "ok":
        return None
    if ev.sitemap_lastmod_count >= max(1, len(ev.sitemap_entries) // 2):
        return None
    return _op(
        "Let crawlers see what actually changed (accurate sitemap lastmod)",
        "TRUST",
        f"A sitemap was retrieved listing {len(ev.sitemap_entries)} URL(s) but only "
        f"{ev.sitemap_lastmod_count} <lastmod> value(s).",
        ev.sitemap_urls[0] if ev.sitemap_urls else ev.root_url,
        "Emit an accurate <lastmod> for every sitemap entry, driven by the content's edit time.",
        ["Generate lastmod from the content management system's modified timestamp, not the "
         "build time, so unchanged pages keep their original date.",
         "Regenerate the sitemap on publish rather than on a fixed schedule."],
        "lastmod is the cheapest freshness signal a crawler can read before spending a fetch; "
        "accurate values get changed pages re-read sooner and stop unchanged pages consuming "
        "the budget.",
        "Fetch the sitemap and confirm lastmod values differ across pages and match recent edits.",
        priority="P3",
    )


def _product_markup(ctx, fired):
    if "FI-003" in fired:
        return None
    pages = ctx.content_pages()
    priced = [p for p in pages if tu.find_prices(p.text_main)
              and not p.jsonld_nodes_of("Product", "Offer", "AggregateOffer", "Service")]
    if len(priced) < 2:
        return None
    return _op(
        "Mirror visible commercial facts in structured data",
        "TRUST",
        f"{len(priced)} sampled page(s) display a price in visible text with no "
        f"Product/Offer structured data.",
        priced[0].final_url,
        "Add Product/Offer (or Service) JSON-LD generated from the same source as the "
        "visible price.",
        ["Emit `Offer` with price, priceCurrency, availability and priceValidUntil, bound to "
         "the rendering data source.",
         "Add a build check that fails when the serialised price differs from the rendered one.",
         "Where price varies by context, use AggregateOffer with lowPrice/highPrice and say so "
         "in the visible copy."],
        "Commercial facts stated only in prose have to be located and parsed out of layout; "
        "the same fact in markup is unambiguous, and generating both from one source prevents "
        "the contradiction class this audit checks for.",
        "Re-run the audit and confirm the structured price matches the visible price on each "
        "affected page.",
        priority="P2",
    )
