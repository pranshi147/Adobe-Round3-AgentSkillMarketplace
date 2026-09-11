# False-positive audit

Every detector, reviewed against six questions:

1. What exactly is measured?
2. What evidence is required before a finding may be emitted?
3. What legitimate site would trip this?
4. What guard prevents that?
5. Is it relevant to discovery, extraction, understanding, trust, citation or engagement?
6. Is the severity justified?

Outcomes of this pass are recorded at the end. The machine-readable guards live
in `defect-registry.json`; this document is the reasoning behind them.

---

## machine-readability

### MR-001 · Content paths disallowed in robots.txt
- **Measures** discovered URLs against parsed robots rules for our user-agent.
- **Requires** the raw Disallow line, a concrete blocked URL, and how that URL was discovered.
- **Would trip** any site that correctly blocks `/cart`, `/search`, `/account`.
- **Guard** utility paths excluded; a blocked path absent from both sitemap and link graph is ignored.
- **Relevance** DISCOVER — a blocked URL is never fetched, so nothing downstream applies.
- **Severity** critical only when the audit target or root is blocked; that is an exclusion of the whole audited surface, so the ceiling is justified.

### MR-002 · noindex on content pages
- **Measures** `meta[robots|googlebot]` and `X-Robots-Tag` for `noindex`/`none`.
- **Requires** the exact directive value and its source (markup or header).
- **Would trip** sites that correctly noindex search results, filters, thank-you pages.
- **Guard** utility/search/pagination URLs excluded; `nofollow`, `noarchive`, `nosnippet` never fire it.
- **Relevance** DISCOVER — exclusion from indexes many retrieval pipelines query.
- **Severity** critical on the target/homepage only. Justified: it is a published, unambiguous exclusion directive, observed directly.

### MR-003 · Broken internal destinations
- **Measures** HTTP status of internally-linked, non-asset, non-utility URLs.
- **Requires** a status code ≥400 and at least one real referring page.
- **Would trip** a site behind rate limiting, or one with flaky infrastructure during the audit.
- **Guard** 429 excluded as rate limiting; timeouts without a status become a limitation, not a finding; robots-blocked URLs skipped.
- **Relevance** DISCOVER — dead branches truncate what a fetch-budgeted agent ever sees.
- **Severity** capped at high. **Changed in this pass:** the core-page surface floor no longer applies merely because the homepage is the *referrer*; it applies when the broken destination is itself an important page. One dead link from a homepage was previously floating to P0.

### MR-004 · Canonical conflicts
- **Measures** canonical vs own URL, vs fetched status, vs host, and vs other pages' canonicals with a content-similarity test.
- **Requires** the published canonical value and the specific conflicting observation.
- **Would trip** legitimate syndication to a partner or parent domain; genuine duplicate pages sharing a canonical.
- **Guard** trivial differences normalised away; collapse requires similarity < 0.6; pagination excluded. **Changed in this pass:** a cross-domain canonical alone is now **low** severity and worded as "confirm this is intended", because syndication is a real pattern and the audit cannot see the business relationship.
- **Relevance** IDENTIFY — decides which address a claim resolves to.
- **Severity** high reserved for dead canonical targets and content collapse, both directly observed.

### MR-005 · Content absent from served HTML
- **Measures** main-region words in served HTML, empty application roots, script-to-document byte ratio.
- **Requires** HTTP 200, a text gap, and a rendering indicator — never one alone.
- **Would trip** a legitimately thin page; a script-heavy page that serves its content.
- **Guard** low text alone never fires; thin templates (contact, gallery, legal) excluded from the share; a `<noscript>` fallback downgrades to `needs_validation`; a single non-core page is withheld.
- **Relevance** EXTRACT — nothing to quote or cite.
- **Severity** critical only at ≥80% of sampled pages including the homepage. **Wording changed in this pass:** the finding now states the rendered state was *not* verified unless the caller supplied rendered snapshots.

### MR-006 · Boilerplate dominates content
- **Measures** main-word share, link-text character share, link count.
- **Requires** all three conditions on the same page.
- **Would trip** a category or index page, which is supposed to be a list of links.
- **Guard** all three thresholds together; pages already reported under MR-005 excluded. **Changed in this pass:** a single affected page is now routed to `needs_validation` — one navigation-heavy index page is a normal site feature, not a defect.
- **Relevance** EXTRACT — the extracted text is destinations, not statements.
- **Severity** high only at ≥40% of sampled pages or a core page plus another.

### MR-007 · Page identity metadata
- **Measures** title presence and uniqueness, H1 presence, and content similarity between title-sharing pages.
- **Requires** the duplicated or missing value plus the URLs and their similarity score.
- **Would trip** paginated series; genuinely duplicate pages.
- **Guard** similarity ≥ 0.8 defers to FI-004; pagination excluded; isolated missing H1 alongside a distinctive title is low only.
- **Relevance** IDENTIFY — selection and citation labelling operate on these fields.
- **Severity** high only at three or more pages sharing a title, or a homepage with no title.

### MR-008 · Weak enumeration
- **Measures** sitemap resolvability **and** link-graph discovery strength.
- **Requires** both the failed sitemap attempts and a specific structural weakness (important pages unlinked from the entry page at depth 3+, or an entry page exposing fewer than five internal destinations).
- **Would trip** every small, well-linked site that simply has no sitemap.
- **Guard** **rewritten in this pass.** A missing sitemap alone is now a proactive opportunity and never a finding. Low sitemap coverage is likewise an opportunity. Confidence downgraded from verified to corroborated, because the finding combines an absence with a structural measurement rather than observing an exclusion.
- **Relevance** DISCOVER — enumeration is how pages enter a corpus at all.
- **Severity** capped at medium; low when only the thin-entry-page branch fires.

### MR-009 · Uninformative navigation paths
- **Measures** the share of internal anchors with no destination-describing label.
- **Requires** ≥25 anchors measured and example labels with destinations.
- **Would trip** any site using "Read more" beneath an already-descriptive card heading — a near-universal pattern.
- **Guard** **strengthened in this pass.** A weak anchor whose destination is *also* linked descriptively somewhere in the sample is no longer counted: the semantic signal exists, nothing is lost. Minimum anchor count raised 15 → 25; thresholds raised to 30% (low) and 45% (medium).
- **Relevance** DISCOVER — anchor text is one of the few signals available before a link is followed.
- **Severity** capped at medium; this is retrieval efficiency, not exclusion.

---

## fact-integrity

### FI-001 · Entity name inconsistency
- **Measures** normalised brand names from independent identity surfaces.
- **Requires** two *different source types* to disagree, each with its URL.
- **Would trip** any brand with a legal suffix, a trading name, or an acronym.
- **Guard** containment, acronym and ≥0.5 token-overlap treated as compatible; legal suffixes stripped; same-source disagreement insufficient.
- **Relevance** IDENTIFY — misattribution to a similarly-named entity.
- **Severity** high only when the homepage's own sources disagree or three source types are involved.

### FI-002 · No machine-readable entity identity
- **Measures** presence of entity JSON-LD/microdata and of an about page.
- **Requires** both to be absent across the whole sample.
- **Would trip** a site that describes itself well in prose but publishes no markup.
- **Guard** an about page alone satisfies the requirement; microdata counts; requires the homepage to have been reached.
- **Relevance** IDENTIFY — ambiguity risk, not a demonstrated failure.
- **Severity** capped at medium, deliberately.

### FI-003 · Structured data contradicts the page
- **Measures** JSON-LD price/name/availability against visible values.
- **Requires** a *competing* visible value of the same kind.
- **Would trip** "from" pricing, expanded product titles in markup, ranges.
- **Guard** currency and separator normalisation; `lowPrice`/`highPrice` inside the visible range exempt; markup values simply not repeated in prose are not contradictions. **Changed in this pass:** a name mismatch now requires ≥2 content tokens and <25% overlap (was <34%), so a fuller product title in markup no longer reads as a contradiction.
- **Relevance** TRUST — this is the confidently-wrong-answer defect.
- **Severity** high justified for commercially material fields on core pages; the contradiction is directly observed.

### FI-004 · Duplicate content unconsolidated
- **Measures** 6-token shingle similarity between distinct URLs.
- **Requires** ≥0.9 similarity, ≥150 words each, and canonicals that do not consolidate.
- **Would trip** thin pages that resemble each other trivially; paginated variants.
- **Guard** word floor, canonical check, URL normalisation, pagination exclusion.
- **Relevance** CITE — citation targets fragment across addresses.
- **Severity** high at three clusters or a core page.

### FI-005 · Timeliness without a date signal
- **Measures** timeliness/volatility language against every available date signal.
- **Requires** the phrase found and the confirmed absence of markup, `<time>` and visible dates.
- **Would trip** evergreen pages containing the word "new"; pages dated only by an HTTP header.
- **Guard** evergreen pages never fire; `Last-Modified` downgrades to low; single non-core page withheld.
- **Relevance** TRUST — undatable claims are dropped or repeated after they expire.
- **Severity** high only for volatile commercial claims across ≥30% of pages.

### FI-006 · Stale currency claims
- **Measures** the newest date signal against the audit date, plus currency language.
- **Requires** >24 months old **and** an explicit currency claim or a newer year in the text.
- **Would trip** archives, changelogs, dated blog posts — where old dates are correct.
- **Guard** those templates excluded by path; copyright years not treated as content dates; an old date alone never fires.
- **Relevance** TRUST — the page contradicts itself, so it is unusable either way.
- **Severity** high only on core pages.

### FI-007 · Unattributed editorial
- **Measures** author/publisher/byline presence on article-like pages.
- **Requires** two or more such pages with none of the three.
- **Would trip** product, category, legal and marketing pages.
- **Guard** those are never classified editorial; a visible byline counts; two-page minimum.
- **Relevance** CITE — quotable but not attributable.
- **Severity** medium, with a low branch when attribution exists in text but not in markup.

---

## arrival-experience

### AX-001 · Title/body intent mismatch
- **Measures** title tokens (brand removed) against H1 and body.
- **Requires** both comparisons to fail.
- **Would trip** brand-heavy titles; very short titles; thin pages.
- **Guard** brand tokens stripped; <3 content tokens excluded; <80-word pages excluded.
- **Relevance** ENGAGE — the referral was selected on a label the page does not support.
- **Severity** high only on core pages.

### AX-002 · Orientation gap
- **Measures** the first 120 served words for a declarative sentence pattern.
- **Requires** a core entity page with ≥40 words and no matching sentence.
- **Would trip** listing pages; non-English pages; sites whose definition lives in markup.
- **Guard** listing templates and article pages excluded; non-English pages with a description exempt; a definitional meta description downgrades to low. **Added in this pass:** a substantive `description` in the page's own structured data also downgrades to low.
- **Relevance** UNDERSTAND — no self-contained statement for a visitor or a citing system.
- **Severity** capped at medium.

### AX-003 · Informational dead end
- **Measures** internal links inside the main region on pages ≥150 words.
- **Requires** <3 such links across ≥30% of sampled content pages.
- **Would trip** a single standalone policy page.
- **Guard** a main-region CTA counts as a route; isolated cases withheld with the measured share.
- **Relevance** ENGAGE — the visitor must restart their search.
- **Severity** medium.

### AX-004 · Unresolved context dependency
- **Measures** context-selection controls together with served main-region words.
- **Requires** both the control and the content gap.
- **Would trip** any site with a country, language or currency switcher.
- **Guard** language/currency/region switchers filtered; consent dialogs excluded; a page serving substantive default content is withheld, not reported.
- **Relevance** UNDERSTAND — the context-free reader extracts something unrepresentative.
- **Severity** high on core commercial pages; this is the most expensive fix on a report, which is why the guards are the strictest here.

### AX-005 · Promotional interference
- **Measures** promo-container text share and identical repeated blocks.
- **Requires** ≥120 main words and either ≥40% promotional share or a block repeated 3+ times.
- **Would trip** campaign and offer landing pages, where promotion is the point.
- **Guard** those exempt by path and title; advertising measured only as a share of the page's own text; listing repetition of names/prices excluded; 25–40% recorded as `needs_validation`.
- **Relevance** EXTRACT — the extracted content is offers rather than facts.
- **Severity** medium.

### AX-006 · Interaction-gated content *(new in this pass)*
- **Measures** always-visible main-region words against words inside collapsed or hidden containers.
- **Requires** visible <120 words **and** hidden ≥60 words **and** hidden ≥2× visible.
- **Would trip** any page with an FAQ accordion beneath a real article; cookie banners; nav drawers.
- **Guard** a page with ≥120 visible words never fires, however much is collapsed; cookie/consent/nav/menu/drawer/search-overlay containers are excluded from the hidden count entirely; MR-005 pages excluded; single non-core instance withheld.
- **Relevance** ENGAGE — the visitor must guess which control reveals the answer, and pipelines honouring hidden-state attributes may drop the text.
- **Severity** high only on a core page.

### AX-007 · Important pages buried *(new in this pass)*
- **Measures** recognised important paths against homepage links and crawl depth.
- **Requires** the page to be unlinked from the homepage in *any* region and first reached at depth ≥3.
- **Would trip** deep content that is supposed to be deep.
- **Guard** only recognised important paths considered; a homepage link in any region — including footer — suppresses it; downgraded to low when a usable sitemap lists the page; pages never reached are not speculated about.
- **Relevance** ENGAGE — routing weakness for both the visitor and a fetch-budgeted agent.
- **Severity** capped at medium.

---

## external-evidence *(new in this pass)*

### EX-001 · Declared identifier does not resolve
- **Measures** HTTP status of URLs the site declares in `sameAs`/`identifier`.
- **Requires** a 4xx/5xx status from a completed probe.
- **Would trip** platforms that refuse automated clients while the profile exists.
- **Guard** 401/403/405/406/429/451 excluded as refusals; network errors and timeouts recorded as `not_checked`; non-HTTP identifiers skipped.
- **Relevance** IDENTIFY — the corroboration the site offered fails on its own terms.
- **Severity** medium; a dead anchor weakens resolution, it excludes nothing.

### EX-002 · Identifier does not corroborate the brand
- **Measures** brand-name forms against the destination's title, site name, text and URL path.
- **Requires** a retrieved, readable destination.
- **Would trip** profiles using a trading name or an abbreviation; login-walled platforms.
- **Guard** same name-compatibility rules as on-site checks; URL-path handles count as a mention; unreadable destinations recorded as not-checked rather than uncorroborated.
- **Relevance** IDENTIFY — cross-source agreement is what distinguishes similarly-named entities.
- **Severity** medium at two or more, low for one.

### EX-003 · Ambiguous name without disambiguators
- **Measures** the name's ambiguity profile and the presence of any disambiguating assertion.
- **Requires** both an ambiguous name and the absence of all thirteen checked assertions.
- **Would trip** every strong brand built from ordinary words — which is many of them.
- **Guard** a common-word name alone never fires; one disambiguator of any kind suppresses it; no claim is made about how many other entities share the name, because no external search is performed.
- **Relevance** IDENTIFY — a resolver needs at least one asserted attribute to select on.
- **Severity** capped at medium, phrased as a retrieval risk rather than a naming defect.

### EX-004 · Domain/brand mismatch unbridged
- **Measures** the registrable domain label against the most-attested published brand name.
- **Requires** incompatibility **and** no entity `url` and no `sameAs`.
- **Would trip** the very many legitimate sites whose domain is deliberately unrelated to the brand.
- **Guard** an Organization `url` matching the origin is the bridge and suppresses the finding — the common, correct case; acronym/partial/squashed matches treated as compatible; IP-literal hosts skipped.
- **Relevance** IDENTIFY — a brand name encountered elsewhere has no published route back to this domain.
- **Severity** capped at low.

### EX-005 · Canonical domain inconsistent
- **Measures** the other common form of the audited hostname: HTTP status, the URL it finally resolves to, and the canonical it declares.
- **Requires** a 2xx response from a completed probe, plus the resolved URL and canonical.
- **Would trip** any site that serves only one hostname form, or whose variant is parked.
- **Guard** a variant that does not resolve — DNS failure, refused connection, 4xx, 5xx — never fires; serving one form only is normal and correct. A redirect home at any depth, or a canonical pointing home, is silent. Host comparison is exact rather than www-stripped, because the question is whether the other form *moved*. IP-literal hosts are skipped.
- **Relevance** IDENTIFY — a reference circulating in the other form must reach this site.
- **Severity** capped at medium; this splits signals, it does not exclude the site.

### EX-006 · Declared references do not point back
- **Measures** whether each resolved, readable reference links to or names the audited registrable domain.
- **Requires** two or more resolved, readable references with no back-reference.
- **Would trip** platforms that strip outbound links, or profiles behind a login wall.
- **Guard** the destination must have resolved AND been readable; unreadable is not-checked, never a missing back-reference. Two are required, so one silent platform proves nothing. The check is generous — a link anywhere, or the bare domain in text, counts.
- **Relevance** IDENTIFY — one-way declaration is an assertion; two-way agreement is corroboration.
- **Severity** capped at low, corroborated confidence, because omitting outbound links is common and legitimate.

---

## Outcome of this pass

| Change | Detector |
|---|---|
| Rewritten to require corroboration; absence downgraded to a proactive opportunity | MR-008 |
| Guard strengthened so unrecoverable anchors only are counted; thresholds raised | MR-009 |
| Single-page instance downgraded to `needs_validation` | MR-006 |
| Cross-domain canonical downgraded to low and reworded as "confirm intent" | MR-004 |
| Surface floor corrected: referrer ≠ affected core page | MR-003 |
| Name-mismatch threshold tightened; two-token minimum added | FI-003 |
| Markup `description` added as a downgrade condition | AX-002 |
| Added, with guards written before the implementation | AX-006, AX-007, EX-001…EX-006 |

Two detectors were considered and **not** added, because neither survived
question 3: a "thin content" rule (indistinguishable from legitimately concise
pages) and an "excessive page weight" rule (a performance concern, not a
retrieval, trust or engagement one).
