# Severity, confidence and priority

Three separate judgements are reported separately because they answer three
different questions. Collapsing them into one number is the most common way an
audit becomes unactionable.

| Field | Question | Set by |
|---|---|---|
| `severity` | How damaging is this defect if left alone? | the detector, from the registry's `severity_conditions` |
| `confidence` | How sure are we that it is real? | the evidence level, clamped to that level's band |
| `priority` | What should be done first? | the scoring model below |
| `effort` | How much work is the fix? | the registry; reported, never folded into priority |

## Evidence levels and the confidence gate

| Level | Meaning | Confidence band | Reported as |
|---|---|---|---|
| `verified` | direct observation of the defect itself — a Disallow line matching the URL, an HTTP 404, a `noindex` value | 0.90–0.99 | a finding |
| `corroborated` | two or more independent deterministic signals agree — e.g. a markup price differing from every visible price, on several pages | 0.72–0.89 | a finding |
| `indicative` | one heuristic signal | 0.40–0.65 | **never** a finding; goes to `needs_validation` |

The gate is enforced in three places rather than trusted to convention: the
`Finding` constructor clamps confidence into its level's band and downgrades a
`critical` + `indicative` combination to `medium`; the orchestrator's
`confidence_gate()` diverts anything still marked indicative; and
`validate_report.semantic_checks()` fails the report if an indicative finding
reaches the output.

`needs_validation` is published in the report on purpose. Withholding a weak
signal silently would look like the auditor missed it; publishing it with the
reason it was withheld shows the boundary was drawn deliberately.

## The priority score

```
priority_score = severity_weight × confidence × affected_surface × stage_importance
```

| Input | Values |
|---|---|
| `severity_weight` | critical 1.00, high 0.78, medium 0.46, low 0.22 |
| `confidence` | 0.40–0.99, from the evidence level |
| `affected_surface` | `0.4 + 0.6 × share_of_sampled_pages`, floored at 0.85 when a core page (homepage, about, primary product/pricing) is affected |
| `stage_importance` | DISCOVER 1.00, EXTRACT 0.94, IDENTIFY 0.88, TRUST 0.82, CITE 0.76, UNDERSTAND 0.70, ENGAGE 0.64 |

Bands: **P0** ≥ 0.52, **P1** ≥ 0.34, **P2** ≥ 0.12, otherwise **P3**.

## Sample floor

Breadth cannot escalate severity on a sample too small to measure breadth. Below
five sampled content pages, any `corroborated` finding is capped at `medium`,
records why in `measurements.sample_floor_applied`, and gains an evidence line
stating the sample size. `verified` findings are exempt: one page is enough to
observe a robots rule matching a URL, an HTTP 404 or a noindex directive.

Without this, a two-page sample where both pages are application shells produced
a `critical` finding — technically consistent with the thresholds, and
indefensible to anyone reading the evidence.

## Guard rails applied after scoring

- A `verified` + `critical` finding is always P0, whatever the arithmetic says.
- A `medium` finding is never P0 — P0 means "stop other work".
- A `low` finding is never above P2, so breadth alone cannot let a small defect
  outrank a real one.
- Effort never moves priority. A large-effort P0 stays P0; the team decides
  scheduling with the effort field in hand.

## Why breadth is capped rather than linear

A defect on one page out of twenty still starts at 0.4 surface, because
"only the pricing page" is not a small problem if the pricing page is the one
that gets cited. Conversely a site-wide low-severity defect cannot climb into
P1, because volume is not damage.

## Worked example

MR-005 (content absent from served HTML), corroborated at 0.86, affecting the
homepage plus 3 of 8 sampled pages:

```
severity        = high  (homepage affected)      → 0.78
confidence      = 0.86
affected_surface= max(0.4 + 0.6×0.5, 0.85)       → 0.85
stage_importance= EXTRACT                        → 0.94
score           = 0.78 × 0.86 × 0.85 × 0.94      = 0.536  → P0
```

Compare AX-003 (dead ends), corroborated at 0.79, on 30% of pages, no core
page:

```
0.46 × 0.79 × (0.4 + 0.6×0.3) × 0.64 = 0.135 → P2
```

Both are real. Only one belongs at the top of the list.
