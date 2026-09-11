# Off-site corroboration rules

Authoritative machine-readable version: `../../../references/defect-registry.json`.

## Scope boundary

The audit fetches two categories of URL, both derived from the site itself:

1. **Declared external references** — `sameAs` and `identifier` in entity markup,
   plus `<link rel=me>`, `<link rel=author>`, `<link rel=publisher>` and
   cross-domain `<link rel=alternate>`. These are registry/IndieWeb conventions,
   not provider APIs. Up to six.
2. **The site's own hostname variants** — the other common form of its own host
   (www to apex, or back). Up to two.

At most eight requests, read-only, inside the same global time budget as the rest
of the audit, with the same identifiable user-agent, each subject to the
destination host's robots.txt.

It does not query a search engine, resolve a knowledge-base entity, read a
directory, or follow links out of the audited site's content. That boundary is
deliberate: everything the audit reports must be reproducible by anyone with
the same URL and no credentials, and nothing should depend on a paid API or a
ranking that changes between runs.

## EX-001 · Declared external identifier does not resolve
**Fires when** a declared identifier returns 4xx or 5xx.
**Guards** 401, 403, 405, 406, 429 and 451 are treated as *platform refusal of
an automated client*, not as a missing profile — plenty of platforms serve a
real page to a browser and refuse a crawler. Network errors and timeouts are
recorded as `not_checked`, never as findings. Non-HTTP identifiers (URNs, ISBNs)
are skipped.
**Severity** medium; a dead identifier weakens an anchor, it does not exclude
the site from anything.

## EX-002 · Declared identifier does not corroborate the brand
**Measured** normalised brand-name forms against the destination's `<title>`,
`og:site_name`, visible text, and its own URL path.
**Fires when** no compatible form appears anywhere in the retrieved content.
**Guards** name comparison uses the same containment, acronym and legal-suffix
rules as the on-site identity checks, so abbreviations and trading names do not
fire; a handle in the URL path counts as a mention, because many platforms carry
the brand only there; a destination that could not be read as text — login wall,
empty body, non-HTML response — is recorded as not-checked rather than as a
failure to corroborate.
**Severity** medium at two or more, low for a single identifier.

## EX-003 · Ambiguous name with no disambiguators
**Ambiguity** is scored from the name alone: every token is an ordinary
dictionary word, or the name is a single token of four characters or fewer.
Coined names, names with an uncommon token, and multi-token names with a
distinctive element are not ambiguous.
**Disambiguators** searched for in the site's own markup: `sameAs`, `legalName`,
`identifier`, `foundingDate`, `address`, `areaServed`, `taxID`, `vatID`, `duns`,
`leiCode`, `naics`, `isicV4`, `telephone`, and an Organization `url`.
**Fires only when** the name is ambiguous **and** none of those is present. A
single disambiguator of any kind suppresses the finding entirely.
**Downgraded to low** when the site at least states its category in a
definitional sentence.
**Explicitly not measured** how many other entities actually share the name. The
audit performs no external search, so it makes no claim about the competitive
namespace — only about what this site publishes to distinguish itself in it.

## EX-004 · Domain and brand name unrelated, unbridged
**Measured** the registrable domain label (`example` from `www.example.co.uk`,
with common two-part suffixes handled; IP-literal hosts are skipped) against the
most-attested published brand name.
**Fires only when** the two are incompatible under containment, acronym,
squashed-string and token-overlap rules **and** the entity markup declares
neither a `url` matching this origin nor any `sameAs`.
**Guards** an Organization node whose `url` points at this origin is itself the
bridging assertion and suppresses the finding — that is the common, correct
case, so this detector stays quiet on the overwhelming majority of sites with a
deliberately unrelated domain name.
**Severity** capped at low. The finding is about the missing bridge, never about
the choice of domain.

## EX-005 · Canonical domain consistency
**Measured** the other common form of the audited hostname: its HTTP status, the
URL it finally resolves to, and the canonical it declares.
**Fires when** the variant returns 2xx AND neither redirects to the audited
origin nor declares a canonical pointing at it.
**Guards** a variant that does not resolve — DNS failure, refused connection,
4xx, 5xx — never fires: serving only one hostname form is normal and correct. A
redirect home at any depth, or a canonical pointing home, is correct
consolidation and is silent. IP-literal hosts have no variant and are skipped.
Robots-blocked requests are recorded as not-checked. Host comparison here is
exact rather than www-stripped, because the entire question is whether the other
form moved to the audited origin.
**Severity** medium when the variant consolidates onto nothing; low when it
declares a canonical, but to some third address.

## EX-006 · Reciprocity of declared references
**Measured** for each resolved, readable reference: does its content link to the
audited registrable domain, or name that domain in its text?
**Fires when** two or more resolved references contain no reference back.
**Guards** the destination must have resolved AND been readable as HTML — a login
wall, empty body or non-HTML response is not-checked, never a missing
back-reference. Two references are required, so one platform that strips
outbound links proves nothing. The check is deliberately generous: a link
anywhere on the page counts, and so does the bare domain in text. Capped at low
and reported at corroborated confidence, because many platforms legitimately
omit outbound links.
**Why it is not "absence"** the references exist and resolve; what is missing is
agreement in the other direction. That is an observation about records the site
chose to name, not an inference from something not found.

## Why these sit at the IDENTIFY stage

All four are entity-resolution risks: given a brand name encountered somewhere
else, can a resolver get back to this site, and can it tell this entity apart
from a similarly-named one? That is the same question the on-site identity
checks (FI-001, FI-002) ask from the inside, which is why both skills share the
name-extraction code in `lib/evidencekit/entity.py` and cannot drift apart in
what they consider "the brand name".
