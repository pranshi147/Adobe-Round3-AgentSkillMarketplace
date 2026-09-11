# Report schema

`audit-report.json` is the contract between the audit skills and anything
downstream. The machine-checkable version is `report-schema.json`; this file
explains the fields and why the extensions exist.

The **required core** matches the minimum schema in the hackathon handout:

```json
{
  "site": "https://example.com",
  "audited_at": "2026-09-10T09:14:22Z",
  "summary": {"total_findings": 7, "critical": 1, "high": 2, "medium": 3, "low": 1},
  "findings": [
    {"id": "F-001", "title": "...", "severity": "high",
     "evidence": "...", "suggested_action": {...}}
  ]
}
```

Everything below is additive, so a consumer that only knows the minimum schema
still works.

## Top level

| Field | Purpose |
|---|---|
| `site` | normalised root URL that was audited |
| `audited_at` | ISO-8601 UTC timestamp |
| `auditor` | name, version and the exact user-agent used, so a server log can be matched to this run |
| `scope` | `status` (`complete` / `partial` / `inconclusive`), pages examined and readable, requests made, duration, the list of URLs actually fetched, and `rendering_verification` — how rendering was established, which by default states that no browser engine was used |
| `summary` | total plus per-severity counts; validated against `findings` |
| `evidence_path` | per-stage roll-up: worst severity and finding ids at each of the seven stages |
| `findings` | proven defects, ordered by priority |
| `proactive_opportunities` | improvements where **no** defect was found — kept separate on purpose |
| `external_corroboration` | what the bounded off-site pass observed: mode, whether it ran, the identifiers declared and probed, each probe's outcome, and a scope note stating what was **not** consulted |
| `needs_validation` | signals observed but withheld from findings, each with the reason |
| `limitations` | what this audit could not see |

## A finding

| Field | Purpose |
|---|---|
| `id` | report-local id, `F-001`… |
| `defect_id` | registry rule id, e.g. `MR-005` — stable across runs and sites |
| `detector` | the function that produced it |
| `category` | which skill it came from: `machine-readability`, `fact-integrity`, `arrival-experience` or `external-evidence` |
| `stage`, `failure_mode` | position in the evidence path, and what it does to an answer |
| `severity`, `priority`, `confidence`, `evidence_level` | see `severity-priority-model.md` |
| `impact` | one sentence an owner can act on |
| `mechanism` | *why* a machine fails, not just what is wrong |
| `evidence` | single-string summary (the handout's required field) |
| `evidence_items` | structured evidence: `url`, `observation`, `measurement`, optional `excerpt` — at least one is required and the constructor refuses to build a finding without it |
| `affected_urls`, `measurements` | full scope and the numbers behind the call, including `priority_score` and `affected_surface` |
| `effort` | small / medium / large |
| `suggested_action` | `summary`, `implementation[]`, `why_it_works`, `verification`, `priority` |

`verification` matters as much as the fix: it is the check that tells the team
whether the change actually worked, expressed as something they can run.

## Example finding

```json
{
  "id": "F-002",
  "defect_id": "FI-003",
  "detector": "structured_data_contradicts_page",
  "category": "fact-integrity",
  "stage": "TRUST",
  "failure_mode": "misread",
  "title": "Structured data disagrees with the visible page",
  "severity": "high",
  "priority": "P1",
  "confidence": 0.88,
  "evidence_level": "corroborated",
  "impact": "A research agent can quote a price the page does not actually show.",
  "mechanism": "Structured data is trusted because it is unambiguous...",
  "evidence": "https://example.com/blender: JSON-LD price does not match the visible page [structured value=\"999\"; visible value(s)=\"1299\"]",
  "evidence_items": [
    {"url": "https://example.com/blender",
     "observation": "JSON-LD price does not match the visible page",
     "measurement": "structured value=\"999\"; visible value(s)=\"1299\""}
  ],
  "affected_urls": ["https://example.com/blender"],
  "measurements": {"pages_with_product_markup": 4, "pages_with_mismatch": 2,
                   "share": 0.5, "fields": ["price"], "priority_score": 0.4123},
  "effort": "medium",
  "suggested_action": {
    "summary": "Make price in JSON-LD render from the same source as the visible value",
    "implementation": ["Bind the JSON-LD field to the rendering data source...",
                       "Add a CI assertion that fails when they differ..."],
    "why_it_works": "The contradiction exists because two sources produce the fact independently...",
    "verification": "Fetch the page, extract the JSON-LD field and the visible value, confirm they match",
    "priority": "P1"
  }
}
```

## Audit status

`scope.status` is the first thing to read:

| Status | Meaning |
|---|---|
| `complete` | three or more pages read, no truncation |
| `partial` | fewer pages read than requested; shares are over a small sample |
| `inconclusive` | **no page returned a readable 2xx response.** Findings are suppressed and the text report leads with the reason |

The `inconclusive` case exists because the alternative is worse than useless: a
blocked, offline or robots-excluded host would otherwise produce an empty
findings list that reads exactly like a clean bill of health. The validator
rejects any report that is `inconclusive` and still carries findings.

Below five sampled content pages, breadth-driven severity escalation is
disabled: affected findings are capped at medium, carry a
`sample_floor_applied` measurement, and gain an evidence line stating the sample
size. Directly observed defects are unaffected.

## Validation

```bash
python skills/evidence-path-orchestrator/scripts/validate_report.py audit-report.json
```

The validator is dependency-free and runs automatically at the end of every
audit, so an invalid report is never written. Beyond JSON Schema it enforces
consistency rules a schema cannot express: unique ids, non-empty evidence, no
indicative findings, `critical` only with `verified` evidence, `low` never at
P0/P1, action priority equal to finding priority, and summary counts equal to
the actual findings.
