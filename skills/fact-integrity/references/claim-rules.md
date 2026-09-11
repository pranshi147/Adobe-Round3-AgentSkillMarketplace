# Fact-integrity comparison rules

Every rule here compares assertions the site makes about itself. No external
source of truth is used. Authoritative machine-readable version:
`../../../references/defect-registry.json`.

## FI-001 · Entity name consistency
**Sources compared** (each counts as one independent source type): the title's
brand segment on core pages, `og:site_name`/`application-name`, the `name` of
any `Organization`/`WebSite`/`LocalBusiness` JSON-LD node, a JSON-LD
`publisher.name`, the logo image's alt text, and the copyright line.

**Normalisation** Unicode decomposition and accent stripping, lower-casing,
punctuation removal, then removal of legal suffixes (`inc`, `ltd`, `pvt`,
`llc`, `gmbh`, `plc`, `corp`, `co`, `group`, `holdings`, …).

**Compatible (never reported)** identical; whole-token containment in either
direction (`acme` ⊂ `acme technologies`); acronym match (`bmc` ↔
`big mountain corp`); token overlap ≥ 0.5.

**Fires when** two *different source types* yield incompatible names. One
source disagreeing with itself on one page is not enough.
**Severity** high when the homepage's own sources disagree or three or more
source types are involved; otherwise medium.

## FI-002 · Machine-readable entity identity
**Fires when both** hold: no `Organization`/`LocalBusiness`/`WebSite` node in
JSON-LD or microdata anywhere in the sample, **and** no about/company page in
the sitemap, the link graph or the fetched set.
**Guards** either one alone is sufficient identity, so neither alone fires;
capped at medium — this is an ambiguity risk, not a demonstrated
misattribution. Requires the homepage to have been reached.

## FI-003 · Structured data versus visible text
Compared per page for `Product`, `Offer`, `AggregateOffer`, `Service`,
`Event` and `Course` nodes.

| Field | Fires when |
|---|---|
| price | the declared price matches none of the prices found in the visible main text, **and** at least one visible price exists |
| name | the node `name`'s content tokens overlap the page's title, H1 and body by <34% |
| availability | markup says `InStock` while the text says out of stock (or the reverse) |

**Guards** currency symbols, separators and trailing zeros are normalised
before comparison (`4999.00` = `₹4,999`); a `lowPrice`/`highPrice` node whose
value falls inside the visible range is treated as legitimate "from" pricing;
a markup price that is simply not repeated in prose is *not* a contradiction;
malformed JSON-LD is recorded as a parse error rather than compared.
**Severity** high when ≥40% of pages carrying that markup disagree, or when a
commercially material field disagrees on a core page.

## FI-004 · Duplicate content
**Fires when** two distinct normalised URLs have 6-token shingle similarity
≥0.90 and their canonicals do not consolidate them.
**Guards** pages under 150 main-region words are excluded (thin pages resemble
each other trivially); URL pairs differing only by tracking parameters,
trailing slash, scheme or `www` are normalised away first; paginated and
filtered variants are excluded.

## FI-005 · Freshness signals
**Date signals accepted** JSON-LD `dateModified`/`datePublished`/`dateCreated`/
`uploadDate`; `<time datetime>`; `article:modified_time`, `article:published_time`,
`date`, `dc.date` meta; any parseable date in the visible main text.
**Fires when** a page contains timeliness language (`latest`, `current`,
`today`, `in stock`, `as of`, …) or names the current year, and carries none
of the above.
**Guards** evergreen pages never fire; an HTTP `Last-Modified` header
downgrades the finding to low; a single non-core page is withheld to
`needs_validation`.
**Severity** high when volatile commercial claims (price, availability,
delivery) appear undated on ≥30% of sampled pages.

## FI-006 · Stale currency claims
**Fires when** the newest date signal on a page is more than 24 months old
*and* the page either uses currency language or references a year newer than
its own date.
**Guards** archival, changelog, release and dated-post templates are excluded
by path; copyright years are not treated as content dates (they sit in chrome
text, which this rule does not read); an old date on its own never fires.

## FI-007 · Editorial attribution
**Editorial** means `Article`/`BlogPosting`/`NewsArticle`/`Report` markup, a
`/blog//news//articles//insights//guides/` path with ≥150 words, or ≥300 words
plus a date signal.
**Attribution** means a JSON-LD `author`/`publisher`/`creator`, a
`meta[name=author]`, or a visible byline in the first ~1200 characters.
**Fires when** two or more editorial pages have none of these. A separate
low-severity branch fires when a visible byline exists but nothing is
machine-readable.
**Guards** product, category, legal and marketing pages are never editorial;
one unattributed note does not fire the rule.
