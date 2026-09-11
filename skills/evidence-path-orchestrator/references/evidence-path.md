# The EvidencePath model

Most site audits return a flat list: 40 issues, sorted by a score, with no
account of how they relate. That framing hides the only thing an owner
actually needs to know — *where the chain breaks first*.

A retrieval-oriented research agent that uses a brand as a source passes through seven stages, in
order. Each depends on the one before it. A defect at stage 1 makes every
later stage irrelevant for the affected pages.

```
DISCOVER → EXTRACT → IDENTIFY → UNDERSTAND → TRUST → CITE → ENGAGE
```

| Stage | The machine's question | Fails when | Detectors |
|---|---|---|---|
| DISCOVER | Can I fetch this at all? | robots blocks it, it is noindexed, the link is dead, no sitemap enumerates it, no anchor tells me it is worth following | MR-001, MR-002, MR-003, MR-008, MR-009 |
| EXTRACT | Is the fact in retrievable text? | the served HTML is an app shell, or the text I keep after boilerplate removal is navigation and promotions | MR-005, MR-006, AX-005 |
| IDENTIFY | Which page and which entity is this? | titles are duplicated or absent, canonicals collapse or point away, the brand names itself differently in different places, no entity markup and no about page — and, off-site, the identifiers it declares do not resolve or do not name it, or nothing distinguishes it from a similarly-named entity | MR-004, MR-007, FI-001, FI-002, EX-001…EX-006 |
| UNDERSTAND | Are relationships and context explicit? | the page never says what it is, or its content depends on a location/store selection I cannot supply | AX-002, AX-004 |
| TRUST | Is this fact consistent and datable? | markup contradicts visible text, current-sounding claims carry no date, or "latest" sits on a three-year-old page | FI-003, FI-005, FI-006 |
| CITE | Can I attribute a specific passage? | the same content lives at several addresses, or editorial pages name no author or publisher | FI-004, FI-007 |
| ENGAGE | Will the person I send be satisfied? | the title promised something the page does not cover, the page offers no route onward, its substance is hidden until the visitor interacts, or the pages that answer the question are unlinked from the entry page | AX-001, AX-003, AX-006, AX-007 |

## Why the ordering is load-bearing

`stage_importance` in the priority engine is derived from this ordering, not
chosen for effect. DISCOVER is weighted 1.00 and ENGAGE 0.64 because a
discovery failure costs 100% of the value of every page behind it, whereas an
engagement failure costs the conversion of referrals that already arrived.

The report's `evidence_path` block rolls findings up per stage so the first
line of the summary can be "your chain breaks at EXTRACT" rather than "you
have 14 issues".

## Failure modes

Cutting across the stages, every defect is classified by what it does to the
answer. This is what makes the report explainable to a non-technical owner:

| Failure mode | The agent… | Example |
|---|---|---|
| `invisible` | never sees the content | MR-001, MR-005, AX-004 |
| `misread` | states something the page does not support | FI-003 |
| `stale` | repeats something that stopped being true | FI-005, FI-006 |
| `ambiguous` | cannot pin the content to one entity or address | FI-001, FI-004, MR-004, MR-007, EX-001…EX-006 |
| `bounce` | sends someone who leaves unsatisfied | AX-001, AX-002, AX-003, AX-005, AX-006, AX-007 |

## Off-site, without leaving first-party evidence

IDENTIFY is the one stage where the site boundary is crossed, and only in one
direction: the audit follows the external identifiers the site *itself*
declares, to check whether they resolve and whether they name the brand. Every
observation therefore remains first-party in origin while still answering the
off-site question — can this entity be corroborated and told apart from others?

## What the model excludes

How third parties describe the brand unprompted, what a live research agent
currently says about it, and how the brand ranks against competitors are all
outside a first-party, read-only audit. No search engine is queried, and the
absence of external references is never treated as a defect. The report states
this in `limitations` and in `external_corroboration.scope_note` on every run
rather than implying coverage it does not have.
