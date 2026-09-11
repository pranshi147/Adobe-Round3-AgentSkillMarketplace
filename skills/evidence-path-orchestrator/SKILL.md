---
name: evidence-path-orchestrator
description: Run a complete AI-visibility audit of a website and produce an evidence-backed report covering both off-site discoverability and on-site retrieval and engagement. Use this when someone asks whether AI agents performing web research can find, understand, trust or cite a site, why a brand is missing or misrepresented in AI answers, or what to fix first. This is the single entry point for the brand-evidence-auditor marketplace. It decides scope, collects the site evidence once, then composes four reusable audit skills over that shared evidence — machine-readability, fact-integrity, arrival-experience and external-evidence, which corroborates the brand against the external identifiers the site itself declares — before gating on confidence, prioritising, and emitting audit-report.json plus a readable report.
license: MIT
allowed-tools: Bash, Read, Write
---

# Evidence-path orchestrator

## What this audits

A brand is only usable by a retrieval-oriented research agent if seven things hold, in order.
Each one depends on the one before it:

| Stage | Question | Owned by |
|---|---|---|
| DISCOVER | Can a retrieval agent reach the page at all? | machine-readability |
| EXTRACT | Is the fact present in retrievable text? | machine-readability |
| IDENTIFY | Can the page and the entity be named unambiguously? | machine-readability, fact-integrity |
| TRUST | Are the facts consistent and datable? | fact-integrity |
| CITE | Can a specific passage be attributed and quoted? | fact-integrity |
| UNDERSTAND | Are relationships and context explicit? | arrival-experience |
| ENGAGE | Does a referred visitor confirm the answer and continue? | arrival-experience |

IDENTIFY is also where the off-site half is answered: `external-evidence` checks
whether the identifiers the site declares about itself resolve and name it, and
whether anything distinguishes the brand from a similarly-named entity.

The report names the earliest stage that breaks. That ordering is the point:
fixing citation formatting on a page that robots.txt blocks changes nothing.

## Run it

```bash
# whole site (default): stratified sample, 20 pages, ~170s budget
python skills/evidence-path-orchestrator/scripts/run_audit.py https://example.com

# one page only
python skills/evidence-path-orchestrator/scripts/run_audit.py https://example.com/pricing --scope page

# tighter budget, custom output, plus a grounded brief for an agent layer
python skills/evidence-path-orchestrator/scripts/run_audit.py https://example.com \
    --max-pages 12 --max-seconds 90 --out-dir ./out --agent-brief

# skip all off-site requests (sandbox, air-gapped run, or policy)
python skills/evidence-path-orchestrator/scripts/run_audit.py https://example.com --external off

# supply your own rendered snapshots so rendering claims become verified
python skills/evidence-path-orchestrator/scripts/run_audit.py https://example.com \
    --rendered-evidence rendered.json
```

`--external auto` (the default) runs a bounded off-site probe of at most 8
read-only requests: up to 6 external references the site declares in its own
markup (`sameAs`, `identifier`, `rel=me`, `rel=author`, `rel=publisher`,
cross-domain `rel=alternate`), plus up to 2 variants of its own hostname
(www ↔ apex). No search engine is queried, and absence of external presence is
never a defect.
If the network is unavailable the probes degrade to `not_checked` and the audit
completes normally.

`--rendered-evidence` takes a JSON file mapping URL to rendered HTML produced by
your own tooling. The auditor never runs a browser itself; without this file it
reports rendering as *inferred from served bytes*, and says so in
`scope.rendering_verification`.

Outputs, written to `--out-dir` (default `.`):

- `audit-report.json` — the machine-readable report (schema: `references/report-schema.json`)
- `audit-report.txt` — the same findings as a prioritised, readable report
- `agent-brief.json` — optional; evidence only, for a reasoning layer

`--scope page` is the right choice when the question is about one URL. Site
scope samples by URL template so the sample covers entity, product, pricing
and editorial page types rather than 20 near-identical listing pages.

## Choosing what to say first

Severity answers "how damaging is this?". Priority answers "what should they
do first?". They are computed differently and both are reported:

```
priority_score = severity_weight × confidence × affected_surface × stage_importance
```

Effort is reported alongside but never folded into priority, so a team can
see "high severity, large effort" separately from "medium severity,
five-minute fix". Full model: `references/severity-priority-model.md`.

## Reading the report to a human

1. Lead with the earliest broken stage, not the longest list.
2. Give the mechanism before the fix — why the machine fails, not just what
   to change.
3. Quote the evidence measurement. Every finding carries the URL and the
   number behind it.
4. Keep `proactive_opportunities` separate from `findings`. Findings are
   proven defects; opportunities are improvements where nothing was broken.
5. State the limitations. The sample size and the no-JavaScript rule are in
   every report for a reason.

## If you are an agent extending this output

`--agent-brief` writes the evidence in a form you can reason over. The
contract is in the file and is not optional: you may merge, rank, group and
explain findings; you may not introduce a URL, a number or a claim that is
not already in the brief. If the evidence does not support a conclusion, say
so rather than inferring a cause. The detectors are deterministic so the same
site produces the same findings on every run; interpretation must not break
that property.

## Guarantees

Read-only (GET and HEAD only — any other method raises), robots.txt fetched
first and obeyed for every URL including link verification, and hard caps on
pages, per-request timeout, response size and total wall-clock time. The
audit never modifies the audited site.

## References

- `references/evidence-path.md` — the seven-stage model and why it is ordered
- `references/severity-priority-model.md` — scoring, bands, confidence gating
- `references/report-schema.md` — every report field, with an example
- `references/report-schema.json` — the machine-checkable contract
- `../../references/defect-registry.json` — all 29 defects with guards and fixes
