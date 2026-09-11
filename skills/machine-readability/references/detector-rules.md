# Machine-readability detector rules

Thresholds and the reasoning behind each guard. The authoritative machine-
readable version of every rule is `../../../references/defect-registry.json`.

## MR-001 · Content paths disallowed in robots.txt
**Fires when** a discovered URL (the audit target, a sitemap entry, or an
internal link destination) is matched by a `Disallow` rule for our user-agent.
**Evidence** the raw `Disallow` line, plus a concrete URL it blocks and how
that URL was discovered.
**Guards** utility paths (`cart`, `checkout`, `login`, `account`, `admin`,
`search`, `api`, `session`, `order`, `payment`, `wishlist`) are excluded; a
blocked path that appears in neither the sitemap nor the link graph is
ignored, because blocking unused paths is ordinary hygiene.
**Severity** critical if the target or root is blocked; high if a
sitemap-listed path is blocked; otherwise medium.

## MR-002 · noindex on content pages
**Fires when** `meta[name=robots|googlebot]` or the `X-Robots-Tag` header
contains `noindex` or `none` on an informational page.
**Guards** `nofollow`, `noarchive`, `nosnippet` and `max-snippet` never fire
this rule; utility, search and pagination URLs are excluded.
**Severity** critical on the target/homepage, high at ≥25% of sampled content
pages, otherwise medium.

## MR-003 · Broken internal destinations
**Fires when** an internally-linked, non-asset, non-utility URL returns 4xx or
5xx. Pages fetched during the crawl supply most of these; a bounded extra
check (default 10 URLs, preferring destinations linked from more than one
page) verifies linked-but-unfetched URLs.
**Guards** a status code is required — timeouts alone become a limitation, not
a finding; 429 is rate limiting, not breakage; robots-blocked URLs are skipped
rather than called broken; every reported URL must have a real referring page.
**Severity** high at three or more, or when the homepage links to one.

## MR-004 · Canonical conflicts
Three distinct conditions, reported as one finding with combined evidence:
dead canonical target, cross-domain canonical, and *content collapse* — two or
more pages with different content declaring the same canonical.
**Guards** self-referential canonicals and differences of trailing slash,
scheme, `www` or tracking parameters are ignored; collapse requires main-text
similarity below 0.6, so genuine duplicates do not fire; paginated URLs
canonicalising to page one are excluded.
**Severity** high for dead targets and collapse; medium for cross-domain.

## MR-005 · Content absent from served HTML
**Fires when** a page returns 200, serves fewer than 120 main-region words,
**and** shows a rendering indicator: an empty known application root
(`root`, `app`, `__next`, `__nuxt`, …) or a script payload ≥40% of the served
document across 3+ script tags.
**Guards** low text alone never fires — script weight without a text gap is
irrelevant; naturally thin templates (contact, gallery, legal, downloads) are
excluded from the share; a `<noscript>` block carrying ≥40 words downgrades
the page to `needs_validation`; a single non-core page is withheld, so a
finding needs two pages or the homepage.
**Severity** critical when ≥80% of sampled content pages serve <80 words and
the homepage is among them; high at the homepage or ≥40%; otherwise medium.

## MR-006 · Boilerplate dominates content
**Fires when** all three hold on one page: main-region words are <25% of all
words, link text is >50% of all text characters, and the page carries >60
links.
**Guards** requires all three together, so a navigation-rich homepage with
real copy does not fire; pages already reported under MR-005 are excluded to
avoid double-reporting one missing-text problem.

## MR-007 · Page identity metadata
**Fires when** a title is missing, when two or more content-dissimilar pages
share an identical title, or when a content page (≥120 words) has no H1.
**Guards** page pairs with main-text similarity ≥0.8 are excluded and handled
by FI-004; paginated series are excluded; an isolated missing H1 alongside a
distinctive title is low severity only.

## MR-008 · Weak enumeration (rewritten in the hardening pass)
**Fires when both** hold: no usable sitemap resolves from robots.txt or
`/sitemap.xml`, **and** internal discovery is measurably weak — a key page
(about, pricing, product, service, contact, docs, help, FAQ) is unlinked from
the entry page and was first reached at depth 3+, or the entry page exposes
fewer than five distinct internal destinations.
**Guards** a missing sitemap *alone* is now a proactive opportunity and never a
finding, because small, shallow, well-linked sites are enumerable without one.
Low sitemap coverage is likewise an opportunity. Non-standard sitemap paths in
robots.txt are honoured first; index files are followed one level; gzip is
decoded. Reported at corroborated confidence rather than verified, because the
rule combines an absence with a structural measurement instead of observing an
exclusion directly. Not evaluated at all in `--scope page`.
**Severity** medium for the buried-key-page branch, low for the
thin-entry-page branch.

## MR-009 · Uninformative navigation paths (tightened in the hardening pass)
**Fires when** ≥30% of internal anchors across the sample are non-descriptive
*and unrecoverable*, with at least 25 internal anchors measured.
**Guards** an anchor whose destination is also linked with descriptive text
somewhere in the sample is not counted at all — a "Read more" beside a
descriptive card heading loses nothing, and that pattern is near-universal.
Pagination controls and pure-numeric labels are excluded; an image link with
alt text counts as descriptive. ≥45% is medium, 30–45% is low.
It also records how many key pages sit three or more hops deep, as a
measurement rather than a separate finding.
