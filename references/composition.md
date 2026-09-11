# Composition

```
agent
  └─ evidence-path-orchestrator            ← the one marketplace entrypoint
       ├─ scope decision                    site | page
       ├─ ONE bounded evidence collection   evidencekit.crawl (robots-respecting)
       ├─ bounded link verification         evidencekit.crawl.check_links
       ├─ bounded off-site probe            evidencekit.external (declared IDs only)
       │
       ├─ machine-readability.run(ctx) ─┐
       ├─ fact-integrity.run(ctx)       ├─ the same SiteEvidence, no re-fetching
       ├─ arrival-experience.run(ctx)   │
       ├─ external-evidence.run(ctx) ───┘
       │
       ├─ confidence gate        indicative → needs_validation
       ├─ prioritisation         P0…P3, F-001…, severity ≠ priority
       ├─ proactive generation   opportunities where nothing was broken
       ├─ schema validation      structural + semantic
       └─ report                 audit-report.json · audit-report.txt · agent-brief.json
```

## The contract

Every audit skill exposes exactly one function:

```python
def run(ctx: AuditContext) -> list[Finding]
```

`ctx` carries the evidence, the defect registry, memoised text measurements,
and the `needs_validation` sink. A skill:

- **measures** the evidence it is given;
- **returns** findings, each with at least one `Evidence` item carrying a URL
  and a measurement;
- **routes** anything below its confidence gate to `ctx.note(...)`.

A skill never fetches, never assigns a priority, never allocates a report id,
never generates a proactive opportunity, and never emits or validates a report.
Those are the orchestrator's jobs, and the split is enforced by the fact that
skills receive no fetcher.

## Why these four skills and not one auditor, or twelve

Each answers a different question, over the same evidence, with different
expertise. That is the test for whether a skill deserves to exist:

| Skill | Question | Would you ask this separately? |
|---|---|---|
| machine-readability | Can a retrieval agent reach the pages and extract text? | Yes — "why is nothing being read?" is a distinct investigation |
| fact-integrity | Will it take away the *correct* fact, and can that fact be dated and attributed? | Yes — "why is the wrong price being quoted?" |
| arrival-experience | Does a referred visitor find the answer and a route onward? | Yes — "why do AI referrals bounce?" |
| external-evidence | Can this entity be corroborated and told apart from others off-site? | Yes — "why are we confused with another company?" |

No fifth skill was added for sitemaps, structured data or performance, because
each of those is an *input* to one of the four questions rather than a question
of its own. Splitting by artefact instead of by question is how a marketplace
ends up with twelve skills that all have to be run together to mean anything.

## Reuse, demonstrated

Each audit skill runs alone:

```bash
python skills/fact-integrity/scripts/audit.py https://example.com
python skills/external-evidence/scripts/audit.py https://example.com --external auto
```

Standalone output is a **skill result** — findings, withheld signals,
limitations — and it says so in a `note` field. It is deliberately *not* a
marketplace report: no priorities, no cross-skill merging, no proactive
opportunities, no schema validation. If those shapes were identical, "reusable
skill" would just mean "the orchestrator with some flags".

## What composition buys that four separate tools would not

Cross-skill judgements only exist because one component sees all the findings:

- **MR-005 suppresses MR-006** on the same page: one missing-text problem is
  not billed twice as two defects.
- **MR-007 defers duplicate-title pairs to FI-004** when the pages really are
  duplicates, so the remedy reported is consolidation, not retitling.
- **AX-006 skips pages MR-005 already claimed**, because "hidden behind
  interaction" and "never served at all" need different fixes.
- **MR-008 fires only in combination** with the discovery weakness measured
  from the link graph the crawler built once for everyone.
- **Proactive generators consult which defects fired**, so the report never
  suggests adding `sameAs` in the same breath as reporting that the declared
  `sameAs` entries are broken.
- **fact-integrity and external-evidence share `evidencekit.entity`**, so both
  reason over exactly the same set of published brand names and cannot disagree
  about what the brand is called.

## Shared evidence, collected once

`lib/evidencekit/` is the substrate, not a fifth skill: read-only budgeted
fetching, robots parsing, bounded stratified crawling, HTML-to-evidence
extraction, deterministic text measurement, entity-identity primitives, bounded
off-site probing, and the finding/confidence model. Twenty audited pages cost
twenty fetches regardless of how many skills run, which is what makes it polite
to audit a real site and cheap to add a fifth question later.
