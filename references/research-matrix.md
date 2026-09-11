# From field research to generic detectors

The team's Round 2 research examined how AI agents performing web research handled a deliberately
mixed set of real sites: a stock media library, a beauty marketplace, a
quick-commerce app, a ticketing platform, a competitive programming site, a
professional design tool's documentation, a railway booking service, a large
social-commerce marketplace, and one document-tooling site that behaved *well*
as a positive control.

The value of that research is in the **failure shapes**, not the sites. This
document records how each observed shape was converted into a rule that would
fire on any site with the same structural property, and — just as importantly
— what had to be excluded to stop the rule firing on sites that merely
resembled the pattern.

**Nothing about any studied site is hard-coded anywhere in this marketplace.**
There are no domain names, no brand names and no site-specific selectors in
the detectors or the registry. The only site-derived strings are generic
vocabulary lists (stock anchor phrases, timeliness words, promotional class
names) that any site can match.

## The generalisation test

Every candidate observation had to pass three questions before it became a
detector:

1. **Is it structural?** Can it be measured from the served bytes of any site,
   without knowing the industry? "Prices are hard to find" fails. "The
   declared price in markup appears nowhere in the visible text" passes.
2. **Can it be wrong?** What legitimate site would trip this rule, and what
   guard excludes that site? A rule with no answer here was dropped.
3. **Does the fix follow from the evidence?** If the observation does not
   determine a specific change, it is an opinion, not a finding.

Roughly forty candidate signals went in; twenty-one came out. The
larger number would have looked more thorough and been less useful.

## Observation → detector matrix

| Observed failure shape (across several sites) | Structural property behind it | Detector | Guard that keeps it honest |
|---|---|---|---|
| Assistant described a product catalogue as "empty" although the browser showed hundreds of items | primary content assembled client-side; served HTML is an application shell | MR-005 | script weight alone never fires; a `<noscript>` fallback downgrades; needs two pages or the homepage |
| Assistant could summarise the navigation of a site but not a single claim about the entity | extracted text is dominated by link labels | MR-006 | requires low main share *and* high link-text share *and* >60 links together |
| Assistant answered about the wrong page of a large catalogue | many distinct URLs share one title; no H1 | MR-007 | near-duplicate pages excluded and routed to FI-004; pagination excluded |
| Whole content sections absent from AI answers although publicly visible | those paths disallowed in robots.txt, or noindexed | MR-001, MR-002 | utility paths excluded; unused blocked paths ignored; `nofollow`/`noarchive` never fire |
| Assistant surfaced a stale or removed page and the link went nowhere | internally-linked destinations returning 4xx/5xx | MR-003 | status code required; 429 and timeouts excluded; a real referrer required |
| Assistant conflated a brand with a similarly-named company | brand named differently across independent identity surfaces; no entity markup or about page | FI-001, FI-002 | containment, acronym and legal-suffix variants treated as one entity; either markup or an about page is sufficient |
| Assistant quoted a price the page did not show | structured data and rendered value come from different sources | FI-003 | requires a *competing* visible value; ranges and "from" pricing exempt |
| Assistant repeated an offer that had expired; another refused to state anything because it "could not confirm the date" | timeliness language with no machine-readable date; or an old date under "latest" wording | FI-005, FI-006 | evergreen pages never fire; archival and dated-post templates exempt from FI-006; HTTP `Last-Modified` downgrades |
| The same guidance existed at several addresses; citations pointed at different ones | near-identical content, self-canonical, unconsolidated | FI-004 | thin pages excluded; already-consolidated pairs excluded |
| Editorial guidance could be quoted but not attributed to anyone | no author or publisher in markup or text on article-like pages | FI-007 | product, legal and marketing pages are not editorial; needs two pages |
| Assistant sent a user to a page that did not contain the promised answer | title's subject terms absent from both H1 and body | AX-001 | brand tokens stripped; thin pages excluded; two independent failures required |
| Assistant could not say what an entity *is*, only what it markets itself as | no declarative sentence in the opening served content | AX-002 | core entity pages only; a definitional meta description downgrades to low |
| Availability and pricing differed by city, and the agent reported one context as if it were universal | content gated behind a location/store selector, with no default served | AX-004 | language and currency switchers excluded; a page serving default content is withheld, not reported |
| Answers extracted promotional copy instead of product facts; identical modules repeated down the page | promotional containers hold a large share of the page's own text; identical blocks repeated | AX-005 | campaign pages exempt; advertising measured only as a share; listing repetition excluded |
| Referred visitors had no way onward without re-searching | no internal links inside the main content region | AX-003 | nav/header/footer excluded by design; a main-region CTA counts; needs 30% of pages |
| Deep sections were never enumerated; menus required interaction to expand | no usable sitemap **combined with** key pages unlinked from the entry page; non-descriptive anchor text | MR-008, MR-009, AX-007 | a missing sitemap alone is an opportunity, never a finding; anchors need ≥25 samples and count only where the destination is described nowhere else |
| Key facts sat behind tabs and accordions; nothing was visible on arrival | always-visible text is thin while collapsed containers hold the substance | AX-006 | never fires when the visible content is already substantive; cookie banners, nav drawers and search overlays excluded from the hidden count |
| A research agent conflated the brand with a differently-named organisation, and the site's own external references did not help | declared external identifiers that do not resolve or never name the brand; a common-word name with nothing published to disambiguate it; a domain unrelated to the brand with no bridging assertion | EX-001…EX-006 | only identifiers the site itself declares are fetched; platform refusals (401/403/429) are not dead profiles; one disambiguator of any kind suppresses EX-003; an entity `url` matching the origin suppresses EX-004; **absence of external presence is never a defect** |

## The positive control

One studied site behaved well: research agents described it accurately, cited
specific pages, and referred users to destinations that answered the question.
That site is why `tests/fixtures/site_healthy/` exists. A rule set that cannot
stay silent on a healthy site is a rule set that will bury a real defect under
noise, so the negative control is asserted in the test suite: the whole
marketplace must return **zero findings** on it. Nine tests fail loudly if any
detector starts firing there.

## What the research told us *not* to build

- **Search-quality checks.** Several sites had genuinely poor on-site search,
  but a retrieval agent does not use on-site search, so it is not an AI
  visibility defect.
- **Ranking and competitor comparison.** Out of scope for a first-party,
  read-only audit; it would require data the audit does not and should not
  collect.
- **Aesthetic and UX judgement.** "Cluttered" is not measurable from served
  bytes. AX-005 measures a text share instead, which is.
- **Live research-agent probing.** Asking a model what it currently says about a
  brand produces results that change between runs and cannot be attributed to a
  specific defect on a specific URL. Every finding here traces to bytes the site
  served, or to bytes served by an identifier the site itself declared.
- **Search-based off-site discovery.** Measuring what the open web says about a
  brand would need a search API, a key, and a ranking that changes between runs —
  none of it reproducible by someone holding the same URL and no credentials. The
  off-site skill therefore checks the corroboration the site *offers*, and states
  plainly that it consulted nothing else.
- **A "thin content" rule and a "page weight" rule.** Neither survived the
  false-positive question "what legitimate site would trip this?": concise pages
  are legitimate, and page weight is a performance concern rather than a
  retrieval, trust or engagement one.
