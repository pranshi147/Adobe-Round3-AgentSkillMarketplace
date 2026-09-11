---
name: arrival-experience
description: Detect why a visitor sent to a page by a retrieval-oriented research agent fails to find the answer they were promised — titles that promise a subject the page does not cover, pages that never state plainly what they are, content pages with no route to the next step, content gated behind a location or store selection a fetcher cannot supply, and promotional or repeated blocks crowding out the substance. Use when AI referrals bounce, when a landing page is context-dependent, or as the UNDERSTAND/ENGAGE stage of a full audit run by the evidence-path-orchestrator.
license: MIT
allowed-tools: Bash, Read
---

# Arrival experience

**The question this skill answers:** when a research agent sends a person here,
does the destination confirm the answer and offer a next step?

An AI referral is not a search click. The visitor did not browse to the page,
did not see a results list, and arrives mid-question with an answer already
in mind. The page has to confirm that answer immediately or the referral is
wasted — and the citation that produced it stops earning its place.

## Detectors

| ID | Defect | Stage | Ceiling |
|---|---|---|---|
| AX-001 | Title promises what the heading and body do not deliver | ENGAGE | high |
| AX-002 | Page never states plainly what it is | UNDERSTAND | medium |
| AX-003 | Content pages offer no in-body route onward | ENGAGE | medium |
| AX-004 | Content depends on a context the fetcher cannot supply | UNDERSTAND | high |
| AX-005 | Promotional and repeated blocks crowd out the substance | EXTRACT | medium |
| AX-006 | The page's substance is hidden until the visitor interacts | ENGAGE | high |
| AX-007 | Important pages are not reachable from the entry page | ENGAGE | medium |

Detection logic, guards, severity conditions and fixes:
`../../references/defect-registry.json`.

## Structural only, by design

This is not a UX audit and contains no aesthetic judgements. There is no rule for
"the design is dated" or "the page is not engaging", because neither is
measurable from served bytes. Every check is a measurable structural property:

| Signal | Measured as |
|---|---|
| the page promises something it does not deliver | token overlap between title, H1 and body |
| the page never orients the visitor | a declarative sentence pattern in the opening content |
| no next step | internal links inside the main region, excluding nav/header/footer |
| interaction required before useful information | always-visible words vs words inside collapsed containers |
| excessive navigation depth | key pages unlinked from the entry page, and their crawl depth |
| content buried under competing content | promotional container text as a share of the page's own text |
| duplicate/repeated content | identical multi-word blocks emitted three or more times |
| unresolved context dependency | a context selector together with an absence of served content |

If a claim cannot be measured from the served bytes, it is not a detector here.

## What it deliberately does not report

- Advertising as such. AX-005 measures promotional text as a *share of the
  page's own text*, and exempts campaign and offer pages, where promotion is
  the point.
- Location selectors on pages that also serve substantive default content —
  the default is what a fetcher reads, and it exists. Those are recorded under
  `needs_validation`, not as findings.
- Language and currency switchers, which are not context gates.
- Thin pages. Where there is no content, the defect is MR-005 or MR-006, not a
  mismatch or a dead end.
- Progressive disclosure over a real answer. AX-006 needs the *visible* content
  to be thin; an FAQ accordion under a full article never fires, and cookie
  banners, nav drawers and search overlays are excluded from the hidden count.
- Deep content that is supposed to be deep. AX-007 only considers key pages
  people ask for by name, and stays silent if the homepage links to them in any
  region — including the footer.

## Reading its findings

AX-004 is usually the expensive one: serving a crawlable default view is
architectural work. AX-002 is usually the cheapest high-value fix on the whole
report — one plain sentence saying what the thing is, mirrored into the entity
markup, serves the referred visitor and the citing machine at the same time.

See `references/engagement-rules.md` for thresholds and worked examples.
