---
name: machine-readability
description: Detect why AI crawlers and retrieval agents cannot reach or read a website's pages — robots.txt blocks, noindex directives, broken internal destinations, canonical conflicts, client-side rendering gaps, boilerplate that crowds out content, unlabelled pages, missing sitemaps and uninformative anchor text. Use when a brand is absent from AI answers, when pages look fine in a browser but empty to a fetcher, or as the DISCOVER/EXTRACT stage of a full audit run by the evidence-path-orchestrator.
license: MIT
allowed-tools: Bash, Read
---

# Machine readability

**The question this skill answers:** can a retrieval agent reach the site's important
pages, and once there, is there any text to take away?

Nothing downstream matters if this fails. A perfectly written, perfectly
marked-up page behind a `Disallow` rule contributes nothing to an AI answer.

## Detectors

| ID | Defect | Stage | Ceiling |
|---|---|---|---|
| MR-001 | Content paths disallowed in robots.txt | DISCOVER | critical |
| MR-002 | noindex on content pages (markup or X-Robots-Tag) | DISCOVER | critical |
| MR-003 | Internally-linked destinations returning 4xx/5xx | DISCOVER | high |
| MR-004 | Canonical conflicts (dead, cross-domain, or collapsing) | IDENTIFY | high |
| MR-005 | Primary content absent from served HTML | EXTRACT | critical |
| MR-006 | Navigation and boilerplate outweigh content | EXTRACT | high |
| MR-007 | Pages not distinguishable by title or heading | IDENTIFY | high |
| MR-008 | No sitemap **and** measurably weak internal discovery | DISCOVER | medium |
| MR-009 | Internal links do not describe their destinations | DISCOVER | medium |

Each detector's detection logic, required evidence, false-positive guards,
severity conditions and verified fix live in
`../../references/defect-registry.json` under the matching id.

## How it is used

The orchestrator collects evidence once and calls `run(ctx)` in
`scripts/detectors.py`. The detectors never fetch anything themselves; they
measure the `SiteEvidence` object they are given, which is what makes a run
reproducible and keeps the site to a single bounded crawl.

## What it deliberately does not report

- JavaScript usage. Only a *served-text gap* is reported, never a framework
  choice. A script-heavy page that serves its content is healthy.
- Blocked utility paths. `/cart`, `/checkout`, `/login`, `/account`, `/search`
  and `/api` are supposed to be disallowed and noindexed.
- A single thin page. MR-005 needs two pages or the homepage; one isolated
  low-text page is routed to `needs_validation` instead.
- A missing sitemap on its own. MR-008 fires only when the absence is joined by
  a measured discovery weakness — key pages unlinked from the entry page and
  sitting deep, or an entry page exposing almost no internal destinations. A
  well-linked site with no sitemap gets a proactive opportunity, not a finding.
- A "Read more" link sitting beside a descriptive link to the same page. MR-009
  counts only anchors whose destination is described nowhere in the sample.
- A single navigation-heavy index page, which is a normal site feature: MR-006
  needs two.
- Duplicate titles on genuinely duplicate pages — that is FI-004's territory,
  and reporting it twice would double-count one defect.

## Reading its findings

MR-001 and MR-002 are exclusion defects: the content is invisible, so nothing
else about those pages is worth discussing until they are fixed. MR-005 and
MR-006 are extraction defects: the page is reachable but yields no usable
text. MR-004 and MR-007 are identity defects: the machine can read the page
but cannot say which page it is.

See `references/detector-rules.md` for thresholds and the reasoning behind
each guard.
