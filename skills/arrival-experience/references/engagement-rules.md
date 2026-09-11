# Arrival-experience rules

Every rule is a measurable property of the served page. Authoritative
machine-readable version: `../../../references/defect-registry.json`.

## AX-001 · Title/body intent mismatch
**Measured** content tokens of the title with brand tokens removed, compared
against (a) the H1 via Jaccard similarity and (b) the main body via the share
of title tokens that appear anywhere in it.
**Fires when** H1 overlap < 0.20 **and** body coverage < 0.30 — two
independent failures, never one.
**Guards** brand tokens (derived from the host label and `og:site_name`) are
stripped first, so `Acme — Acme` is not a mismatch; titles with fewer than
three content tokens are too short to measure; pages under 80 main-region
words are excluded, because there the defect is missing content (MR-005/006),
not a mismatch.
**Evidence** includes the specific title terms absent from the body, which is
what makes the finding fixable rather than merely true.

## AX-002 · Orientation gap
**Measured** the first 120 served words of main-region text, split into
sentences and tested against a declarative pattern: `is/are/was/were` followed
by an article or possessive, or a capability verb (`provides`, `offers`,
`helps`, `enables`, `delivers`, `specialises`, `builds`, `sells`, `lets you`).
**Fires when** a core entity page (homepage, about, primary product/service/
pricing) contains no such sentence.
**Guards** listing and article templates are excluded; ≥40 words of served
text are required so app shells are not double-reported; a meta description
that *does* contain a definition downgrades the finding to low, because the
sentence exists but is not on the page; non-English pages are exempt from the
pattern test when a description exists.

## AX-003 · Informational dead end
**Measured** internal links inside `<main>`/`<article>` — explicitly excluding
nav, header, footer and aside — on pages with ≥150 main-region words.
**Fires when** a page has fewer than 3 such links and this holds for ≥30% of
sampled content pages.
**Guards** a clear primary call to action in the main region counts as a
continuation route; isolated cases are withheld to `needs_validation` with the
share that was measured.
**Why main-region only** global navigation is present on every page and
therefore carries no information about *this* page's relationships. Contextual
links are the only ones that tell a machine, or a person, where to go next
from here.

## AX-004 · Unresolved context dependency
**Measured** context-selection signals in the served HTML — prompts such as
"select your city", "deliver to", "enter your pincode", `<select>` elements
named for city/location/store/region/branch/pincode, and buttons with the same
intent — together with served main-region word count.
**Fires when** a context control is present **and** the page serves under 150
main-region words, i.e. the content really is behind the selection.
**Guards** language, currency and country-region switchers are filtered out;
cookie and consent dialogs are excluded; a page that offers a selector *and*
serves substantive default content is recorded under `needs_validation`, not
reported — the default is what a fetcher reads, and it exists.
**Severity** high on core commercial pages, otherwise medium. This is usually
the most expensive fix on a report, which is why the guards are strict.

## AX-006 · Interaction-gated content
**Measured** always-visible main-region words against words inside collapsed or
hidden containers — `<details>` without `open`, `hidden`, `aria-hidden="true"`,
and classes matching accordion / collapse / tab-pane / toggle-content /
faq-answer patterns.
**Fires when** visible main text is under 120 words **and** hidden content is at
least 60 words **and** at least twice the visible content.
**Guards** a page with 120+ visible words never fires however much is collapsed,
because progressive disclosure on top of a real answer is good practice; cookie,
consent, nav, menu, drawer, dropdown and search-overlay containers are excluded
from the hidden count entirely; pages already reported under MR-005 are skipped,
since there the problem is that nothing was served; an isolated non-core
instance goes to `needs_validation`.
**Why it is an engagement defect and not a rendering one** the text *is* in the
served HTML — a fetcher can read it. What fails is the arrival: the visitor has
to guess which control reveals the answer. The secondary risk is that pipelines
honouring hidden-state attributes drop it, which is why the finding reports both.

## AX-007 · Important pages buried
**Measured** key paths (about, pricing, plans, product, service, contact, docs,
help, FAQ) against the homepage's outgoing internal links and the depth at which
each page was first reached.
**Fires when** such a page is linked from the homepage in *no* region and was
first reached at depth 3 or greater.
**Guards** only recognised key paths are considered, so deep editorial content
never fires; a homepage link anywhere — navigation, body or footer — suppresses
it; the finding is downgraded to low when a usable sitemap lists the page, since
enumeration still works and only the visitor's route is affected; pages the
audit never reached are not speculated about; capped at medium.
**Overlap with MR-008** is deliberate and the remedies differ: MR-008 is about
enumeration failing in both available ways at once, AX-007 is about the route
from the entry page. A site can have one without the other.

## AX-005 · Promotional interference
**Measured** characters inside promo-classed containers (`promo`, `banner`,
`advert`, `ads`, `sponsor`, `offer`, `deal`, `carousel`, `newsletter`,
`popup`, `upsell`) as a share of main-region text, and identical multi-word
blocks repeated three or more times.
**Fires when** promotional share ≥40%, or a block repeats 3+ times, on a page
with ≥120 main-region words.
**Guards** advertising as such is not penalised — only its share of the page's
own text; campaign, offer and sale pages are exempt by path and by title;
pages under 120 words belong to MR-005/MR-006; product listings repeating
names and prices are not counted, since only identical multi-word blocks
qualify. Between 25% and 40% is recorded as `needs_validation` rather than
reported.
