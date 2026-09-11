---
name: fact-integrity
description: Detect why a retrieval-oriented research agent would take away the wrong fact about a brand, or be unable to date or attribute a correct one — inconsistent brand naming across identity surfaces, missing entity identity markup, structured data that contradicts the visible page, unconsolidated duplicate content, timeliness claims with no date signal, stale dates behind "latest" wording, and unattributed editorial pages. Use when a brand is described inaccurately or confused with another, when prices or availability are quoted wrongly, or as the IDENTIFY/TRUST/CITE stage of a full audit run by the evidence-path-orchestrator.
license: MIT
allowed-tools: Bash, Read
---

# Fact integrity

**The question this skill answers:** if a retrieval agent does read the page, will it
take away the *correct* fact — and can that fact be dated and attributed?

This is where confidently wrong answers come from. A page that is missing is
a gap; a page whose markup contradicts its own text produces a wrong answer
stated with full confidence.

## Detectors

| ID | Defect | Stage | Ceiling |
|---|---|---|---|
| FI-001 | Brand named inconsistently across identity surfaces | IDENTIFY | high |
| FI-002 | No machine-readable statement of what the organisation is | IDENTIFY | medium |
| FI-003 | Structured data disagrees with the visible page | TRUST | high |
| FI-004 | Same content at several URLs without consolidation | CITE | high |
| FI-005 | Current-information claims with no date signal | TRUST | high |
| FI-006 | Currency claimed while the page's dates are old | TRUST | high |
| FI-007 | Editorial content with no author or publisher | CITE | medium |

Detection logic, evidence requirements, guards, severity conditions and fixes:
`../../references/defect-registry.json`.

## The comparison principle

Every detector here compares two assertions the site makes *about itself* and
reports only where they conflict, or where a claim exists that cannot be dated
or attributed at all. No external source of truth is consulted, and none is
needed: a contradiction between a page's markup and its own visible text is
the site's own evidence against itself.

That is why FI-003 requires a competing visible value before it fires. A price
in markup that simply is not repeated in prose is not a contradiction, and
reporting it as one would be exactly the kind of noise this marketplace is
built to avoid.

## What it deliberately does not report

- Name variants related by containment, acronym or a legal suffix. "Acme" and
  "Acme Technologies Pvt. Ltd." are one entity.
- Missing structured data on its own. FI-002 needs *both* no entity markup and
  no about page; a plain-language about page satisfies the identity need.
- Old dates on archival, changelog or dated-post templates, where an old date
  is correct.
- Attribution on product, category, legal or marketing pages, where a byline
  is not expected.

## Reading its findings

FI-001 and FI-002 mean the brand may be merged with a different entity.
FI-003 means a research agent can state a specific wrong number. FI-005 and FI-006
mean time-sensitive claims cannot be relied on, so they are either dropped or
repeated after they stop being true. FI-004 and FI-007 mean the content is
readable but weak as a citation: no single address to point at, or nobody to
attribute it to.

See `references/claim-rules.md` for how each comparison is made.
