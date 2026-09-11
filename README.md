# Brand Evidence Auditor

An Agent Skill Marketplace that audits a website for **AI visibility**, across
both halves of the problem:

- **off-site discoverability** — can this entity be corroborated and told apart
  from similarly-named others?
- **on-site retrieval and engagement** — can a retrieval agent reach the pages,
  extract and trust the facts, cite them, and does a referred visitor land
  somewhere that confirms the answer?

Every finding is backed by an observation taken from the site's own served
bytes — a robots rule, an HTTP status, a word count, a price that appears in
markup but nowhere on the page. Nothing is asserted that cannot be pointed at.

```bash
python run_audit.py https://example.com
```

---

## Contents

1. [The problem](#1-the-problem)
2. [What this marketplace does differently](#2-what-this-marketplace-does-differently)
3. [The EvidencePath model](#3-the-evidencepath-model)
4. [The four skills](#4-the-four-skills)
5. [Quick start](#5-quick-start)
6. [Command reference](#6-command-reference)
7. [Output](#7-output)
8. [The defect registry](#8-the-defect-registry)
8a. [Off-site discoverability](#8a-off-site-discoverability)
8b. [Dynamic content](#8b-dynamic-content)
9. [False-positive control](#9-false-positive-control)
10. [Severity, confidence and priority](#10-severity-confidence-and-priority)
11. [Proactive opportunities](#11-proactive-opportunities)
12. [How the audit stays safe and bounded](#12-how-the-audit-stays-safe-and-bounded)
13. [Determinism, and where AI belongs](#13-determinism-and-where-ai-belongs)
14. [Composition](#14-composition)
15. [Generalisation](#15-generalisation)
16. [Testing](#16-testing)
17. [Project layout](#17-project-layout)
18. [Design decisions and trade-offs](#18-design-decisions-and-trade-offs)
19. [Limitations](#19-limitations)
20. [Extending it](#20-extending-it)

---

## 1. The problem

Brands are increasingly encountered through a retrieval-oriented research agent rather than through
a browser. The agent fetches pages, extracts claims, decides which ones it
trusts, and either cites the brand or does not. When that goes wrong the owner
usually cannot tell *why* — the site looks perfect in a browser.

The failure is rarely "bad content". It is structural, and it happens at a
specific point in a specific pipeline:

- the page is behind a `Disallow` rule, so it is never fetched;
- the page returns an empty application shell, so there is no text to extract;
- the markup says ₹999 and the page says ₹1,299, so the agent states a
  confidently wrong price;
- the brand names itself three different ways, so it is merged with another
  company;
- the page says "latest" and carries no date, so the claim cannot be relied on;
- the visitor arrives and cannot tell whether they are in the right place.

## 2. What this marketplace does differently

**Evidence before opinion.** A `Finding` cannot be constructed without at least
one evidence item carrying a URL and a measurement — the constructor raises if
you try. There is no code path that produces an unsupported finding.

**A confidence gate, published.** Signals are classified `verified`,
`corroborated` or `indicative`. Indicative signals never appear as findings;
they are published separately under `needs_validation` **with the reason they
were withheld**. Drawing that line visibly is more useful than a longer list.

**Mechanism, not just remedy.** Every finding explains why a retrieval agent fails, not
only what to change. `"Add alt text"` is a chore; `"anchor text is the only
signal available before a link is followed, so a fetch-budgeted agent cannot
choose the right destination"` is a reason.

**Fixes that can be checked.** Every action carries `implementation`,
`why_it_works` and `verification` — the command or check that proves the fix
worked.

**Severity is not priority.** They answer different questions and are computed
from different inputs. Effort is reported and deliberately excluded from the
priority score.

**Twenty-nine strong rules, not a hundred plausible ones.** Around forty
candidate signals came out of field research; nineteen were dropped because
they could not be measured structurally, could not be guarded against false
positives, or did not imply a specific fix.

## 3. The EvidencePath model

Seven stages, in dependency order. Each one only matters if the one before it
succeeded.

```
DISCOVER → EXTRACT → IDENTIFY → UNDERSTAND → TRUST → CITE → ENGAGE
```

| Stage | The machine's question |
|---|---|
| DISCOVER | Can I fetch this at all? |
| EXTRACT | Is the fact present in retrievable text? |
| IDENTIFY | Which page, and which entity, is this? |
| UNDERSTAND | Are relationships and context explicit? |
| TRUST | Is this fact consistent and datable? |
| CITE | Can I attribute a specific passage? |
| ENGAGE | Will the person I send be satisfied? |

The report names the **earliest broken stage**, because fixing citation
formatting on a page that robots.txt blocks changes nothing. Stage position
also feeds the priority score: DISCOVER is weighted 1.00, ENGAGE 0.64.

Full model: [`skills/evidence-path-orchestrator/references/evidence-path.md`](skills/evidence-path-orchestrator/references/evidence-path.md).

## 4. The four skills

| Skill | Question it answers | Detectors |
|---|---|---|
| **evidence-path-orchestrator** *(entrypoint)* | What is wrong, in what order, and what should be fixed first? | — |
| **machine-readability** | Can a retrieval agent reach these pages and extract text? | MR-001 … MR-009 |
| **fact-integrity** | Will it take away the *correct* fact, and can that fact be dated and attributed? | FI-001 … FI-007 |
| **arrival-experience** | Does a referred visitor find the answer and a next step? | AX-001 … AX-007 |
| **external-evidence** | Can this entity be corroborated and told apart from others off-site, and do references published elsewhere lead back here? | EX-001 … EX-006 |

The orchestrator is the only entrypoint. It decides scope, collects the site
evidence **once**, runs all four audit skills over that shared evidence, gates
on confidence, prioritises, and emits the report.

Each audit skill is also independently runnable — `python
skills/fact-integrity/scripts/audit.py <url>` — and returns a *skill result*
rather than a report, because prioritisation and merging are the orchestrator's
job, not a skill's. The full contract is in
[`references/composition.md`](references/composition.md).

## 5. Quick start

```bash
# no installation step — the marketplace has no third-party dependencies
python3 --version                      # 3.9 or newer

# audit a whole site (stratified sample, 20 pages, ~170s budget)
python run_audit.py https://example.com --out-dir ./out

# audit a single page
python run_audit.py https://example.com/pricing --scope page

# tighter budget, plus a grounded evidence brief for an agent layer
python run_audit.py https://example.com --max-pages 12 --max-seconds 90 --agent-brief

# skip every off-site request (sandbox, air-gapped run, or policy)
python run_audit.py https://example.com --external off

# run one skill on its own
python skills/external-evidence/scripts/audit.py https://example.com

# run the test suite (321 tests + structural checks on the marketplace itself)
python tests/run_tests.py
```

## 6. Command reference

| Flag | Default | Purpose |
|---|---|---|
| `url` | — | target URL; site root for a site audit, or one page |
| `--scope` | `site` | `site` for a stratified sample, `page` for that URL only |
| `--max-pages` | `20` | page budget for site scope |
| `--max-seconds` | `170` | hard wall-clock budget for all network work |
| `--timeout` | `8` | per-request timeout in seconds |
| `--min-interval` | `0.15` | minimum gap between requests to one host |
| `--user-agent` | `BrandEvidenceAuditor/1.0 …` | identifies the auditor in server logs |
| `--link-check-limit` | `10` | linked-but-unfetched URLs to verify (`0` disables) |
| `--external` | `auto` | off-site corroboration: `auto` probes only the identifiers the site declares; `off` skips it |
| `--external-limit` | `6` | maximum declared identifiers to probe |
| `--rendered-evidence` | — | JSON file of URL → rendered HTML from your own tooling; upgrades rendering claims from inferred to verified |
| `--out-dir` / `--out-json` / `--out-text` | `.` | where reports are written |
| `--agent-brief` | off | also write `agent-brief.json` |
| `--quiet` / `--print-json` | off | suppress progress / print the report to stdout |

## 7. Output

- `audit-report.json` — machine-readable report, validated before it is written
- `audit-report.txt` — the same findings as a prioritised, readable report
- `agent-brief.json` — optional; evidence only, for a reasoning layer

Worked examples of both are in [`examples/`](examples), generated from the
broken test fixture. The JSON contract is documented in
[`report-schema.md`](skills/evidence-path-orchestrator/references/report-schema.md)
and enforced by `report-schema.json`.

The required core (`site`, `audited_at`, `summary` counts, and findings with
`id` / `title` / `severity` / `evidence` / `suggested_action`) matches the
brief's minimum schema exactly; everything else is additive.

## 8. The defect registry

[`references/defect-registry.json`](references/defect-registry.json) is the
methodology expressed as **data**, not prose. Each of the 29 defects declares:

```
id · detector · skill · stage · failure_mode · title
mechanism            why a retrieval agent fails, in one paragraph
impact               what it costs the brand
detection_logic      what is measured
required_evidence    what must be observed before a finding may be emitted
false_positive_guards what must NOT trigger it
severity_conditions  how severity scales with breadth and page importance
recommended_fix      summary · implementation[] · why_it_works · verification
effort               small | medium | large
```

Detector code reads this file for the explanatory text, so the reasoning lives
in one reviewable place. `tests/run_tests.py` fails if a registry entry lacks
guards or a verification step, or if a declared defect has no implementation.

| ID | Defect | Stage |
|---|---|---|
| MR-001 | Content paths disallowed in robots.txt | DISCOVER |
| MR-002 | noindex on content pages | DISCOVER |
| MR-003 | Internally-linked destinations returning errors | DISCOVER |
| MR-004 | Canonical conflicts | IDENTIFY |
| MR-005 | Primary content absent from served HTML | EXTRACT |
| MR-006 | Navigation and boilerplate outweigh content | EXTRACT |
| MR-007 | Pages not distinguishable by title or heading | IDENTIFY |
| MR-008 | No usable XML sitemap | DISCOVER |
| MR-009 | Internal links do not describe destinations | DISCOVER |
| FI-001 | Brand named inconsistently across surfaces | IDENTIFY |
| FI-002 | No machine-readable entity identity | IDENTIFY |
| FI-003 | Structured data disagrees with the visible page | TRUST |
| FI-004 | Duplicate content without consolidation | CITE |
| FI-005 | Current-information claims with no date signal | TRUST |
| FI-006 | Currency claimed while dates are old | TRUST |
| FI-007 | Editorial content with no attribution | CITE |
| AX-001 | Title promises what the page does not deliver | ENGAGE |
| AX-002 | Page never states plainly what it is | UNDERSTAND |
| AX-003 | Content pages offer no route onward | ENGAGE |
| AX-004 | Content gated behind unavailable context | UNDERSTAND |
| AX-005 | Promotional/repeated blocks crowd out substance | EXTRACT |
| AX-006 | Substance hidden until the visitor interacts | ENGAGE |
| AX-007 | Important pages not reachable from the entry page | ENGAGE |
| EX-001 | Declared external identifiers do not resolve | IDENTIFY |
| EX-002 | A declared identifier never names the brand | IDENTIFY |
| EX-003 | Common-word name with nothing to disambiguate it | IDENTIFY |
| EX-004 | Domain and brand unrelated, with no bridging assertion | IDENTIFY |
| EX-005 | The brand's other hostname serves a separate site | IDENTIFY |
| EX-006 | Declared external references never point back to this site | IDENTIFY |

## 8a. Off-site discoverability

The `external-evidence` skill answers the half of the question that on-site
checks cannot: given this brand name encountered somewhere else, does anything
published lead back to this domain, and can this entity be told apart from
another with a similar name?

**What it does.** It probes the site's *discoverability surface* — the routes by
which something published elsewhere leads back here — using at most eight
read-only requests, all derived from the site itself:

| Probed | Answers |
|---|---|
| external references the site declares (`sameAs`, `identifier`, `rel=me`, `rel=author`, `rel=publisher`, cross-domain `rel=alternate`), up to six | do they resolve (EX-001), do they concern this brand (EX-002), do they point back (EX-006), do they carry an independent description? |
| the other form of the site's own hostname (www ↔ apex), up to two | does a reference using that form reach this site, or a separate one (EX-005)? |
| nothing — computed offline | is the name ambiguous with nothing to disambiguate it (EX-003), and is the domain bridged to the brand name (EX-004)? |

**What it does not do.** No search engine, directory or knowledge base is
queried. No third party the site did not name is contacted. It never concludes
that a brand is "not discoverable on the web" — it has not looked at the web at
large, only at what this site publishes and at its own hostnames — and a single
absent source is never evidence of anything. No claim is made about whether any
AI product has indexed, used or ignored the site.

**Absence is not failure.** A site with no external references is not failing
anything; many legitimate organisations have none worth declaring. Nor is a
hostname variant that does not resolve — serving one form only is correct. Both
cases produce at most a proactive opportunity, worded so that it does not apply
if no suitable record exists. Creating profiles to satisfy an audit is
explicitly not the recommendation.

**It degrades, it does not fail.** With no network, `--external off`, or an
exhausted budget, each probe is recorded as `not_checked` with its reason, the
two network-dependent detectors report nothing, and the audit completes
normally. Everything observed and everything skipped is published in the
report's `external_corroboration` block.

## 8b. Dynamic content

The auditor is raw-HTML-first and adds no browser dependency. It therefore
distinguishes four states explicitly rather than blurring them:

| State | Meaning |
|---|---|
| `server_rendered` | substantive text is in the served HTML |
| `server_rendered_thin` | little text served, and no rendering indicator — not called a rendering problem |
| `likely_client_rendered` | the served HTML shows client-assembly signatures. **An inference from bytes, not a verified rendered state** |
| `interaction_required` | the text *is* served but sits behind a control (AX-006) |
| `verified_after_render` | a rendered snapshot **you supplied** confirms content appears only after client-side rendering |

Every report states which applies in `scope.rendering_verification`, and by
default says plainly that no browser engine was used. `--rendered-evidence`
accepts a JSON file of URL → rendered HTML from your own tooling; without it,
the audit never claims to have inspected a rendered page.

## 9. False-positive control

An audit tool earns trust by what it refuses to report. Four mechanisms:

A full detector-by-detector review — what is measured, what evidence is
required, what legitimate site would trip it, what guard prevents that, and
whether the severity is justified — is in
[`references/false-positive-audit.md`](references/false-positive-audit.md),
along with the changes that review produced.

**Structural guards** — every detector declares what must not trigger it, and
the guards are implemented, not aspirational. JavaScript usage alone never
fires MR-005. `Acme` and `Acme Technologies Pvt. Ltd.` are one entity. A price
in markup that simply is not repeated in prose is not a contradiction. Blocked
`/cart` and noindexed search results are correct behaviour.

**Corroboration requirements** — several rules need two independent signals.
AX-001 requires the title to mismatch both the H1 *and* the body. MR-005
requires both a served-text gap *and* a rendering indicator. FI-002 requires
both missing markup *and* a missing about page.

**Minimum-evidence gates** — a single non-core low-text page, one undated
sentence, one dead-end page: each is recorded under `needs_validation` rather
than reported, with the threshold it fell short of.

**Absence is not evidence** — a missing sitemap on a well-linked site, no
external identifiers, and low sitemap coverage are all proactive opportunities
rather than findings. MR-008 fires only when a missing sitemap is joined by a
*measured* discovery weakness.

**Negative controls in the test suite** — `tests/fixtures/site_healthy/` is a
complete, well-built site. The suite asserts the whole marketplace returns
**zero findings** on it, and every detector has a paired test proving it stays
silent on a page that resembles the defect without being it.

## 10. Severity, confidence and priority

```
priority_score = severity_weight × confidence × affected_surface × stage_importance
```

| Evidence level | Meaning | Confidence | Reported as |
|---|---|---|---|
| `verified` | direct observation of the defect (a matching Disallow line, an HTTP 404, a `noindex`) | 0.90–0.99 | a finding |
| `corroborated` | two or more independent signals agree | 0.72–0.89 | a finding |
| `indicative` | one heuristic signal | 0.40–0.65 | never a finding |

Bands: P0 ≥ 0.52, P1 ≥ 0.34, P2 ≥ 0.12, else P3. Guard rails after scoring: a
verified critical is always P0; a medium is never P0; a low is never above P2;
effort never moves priority.

Details and a worked example:
[`severity-priority-model.md`](skills/evidence-path-orchestrator/references/severity-priority-model.md).

## 11. Proactive opportunities

Reported in a **separate section** from findings, because mixing "this is
broken" with "this would be better" devalues both. Each opportunity fires from
a real observation and is suppressed when the corresponding defect already
fired — `sameAs` identifiers when entity markup exists without them, FAQPage
markup for question-and-answer content already on the page, BreadcrumbList on
deep pages, section headings on long unsegmented pages, a factual entity
description, accurate sitemap `lastmod`, Product/Offer markup for prices shown
only in prose.

## 11a. Audit status, and refusing to guess

Two report-level rules sit on top of every detector, because both failures they
prevent produce a *confidently wrong* report — the exact thing this tool exists
to criticise in others.

**`scope.status`** is the first field to read: `complete`, `partial`, or
`inconclusive`. When no page returns a readable 2xx response — the host is
offline, blocked by the sandbox, or excluded by robots.txt — the audit reports
**no findings at all** and leads the text report with the reason. An empty
findings list must never be mistakable for a clean bill of health on a site that
was never read. The validator rejects any report that is `inconclusive` and
still carries findings.

**The sample floor.** Below five sampled content pages, breadth-driven severity
escalation is disabled: affected findings are capped at `medium`, record
`sample_floor_applied` in their measurements, and gain an evidence line stating
the sample size. Directly observed defects are exempt — one page is enough to
see a robots rule matching a URL, a 404, or a noindex directive. Without this, a
two-page sample of application shells produced a `critical` finding that was
consistent with the thresholds and indefensible to anyone reading the evidence.

**Declared blind spots.** Where main-content and navigation regions cannot be
separated — no semantic landmarks and no recognisable chrome class names, as
with hashed CSS-module names — the three detectors that depend on that
separation skip the page and record why under `needs_validation`, rather than
judging it on a guess.

## 12. How the audit stays safe and bounded

| Guarantee | How it is enforced |
|---|---|
| Read-only | `Fetcher.fetch` raises `ValueError` on any method other than GET/HEAD |
| robots.txt respected | fetched before anything else and consulted for every URL, including link verification; a 5xx robots response restricts the crawl to the supplied URL |
| Crawl-delay honoured | adopted as the minimum inter-request interval, capped at 2s |
| Bounded time | a global deadline aborts fetching; the default 170s sits well inside a 5-minute limit |
| Bounded volume | page cap, 1.5 MB response cap, per-request timeout, bounded link checking |
| Polite | identifiable user-agent, minimum interval between requests, no parallel hammering |
| Recommend-only | the audit never modifies the audited site; it writes report files only |
| Bounded decompression | gzip output is read in chunks against a hard cap, so a small compressed response cannot expand without limit |

A typical fixture audit completes in under a second of network time; a real
20-page site audit runs in seconds to tens of seconds. The default 170s budget
leaves a wide margin under a five-minute limit.

**Running in a restricted sandbox.** The marketplace needs no browser, no
external service, no API key and no install step. If outbound network is blocked
entirely, the audit does not fail: robots and page fetches are recorded as
errors, `scope.status` becomes `inconclusive`, and the report says so instead of
reporting findings. If only third-party egress is blocked, pass `--external off`
and the on-site audit runs normally with the off-site pass recorded as not
performed.

## 13. Determinism, and where AI belongs

Detection is entirely deterministic Python. Given the same bytes, the audit
produces the same findings every time — which is what makes a report
defensible, diffable in CI, and safe to act on.

AI belongs at the layer *above*: explaining findings in the owner's language,
grouping them into a remediation plan, drafting the copy a fix needs.
`--agent-brief` exists for exactly that, and carries a contract the agent must
follow:

> Every statement you make must trace to an observation in this file. Do not
> introduce URLs, numbers or claims that are not present here. You may merge,
> rank, and explain findings; you may not create them. If evidence is
> insufficient, say so rather than inferring a cause.

## 14. Composition

The four audit skills are independent — each answers a different question and
can be reasoned about alone — but they compose over one shared evidence
collection:

```
run_audit.py
  ├─ scope decision (site | page)
  ├─ evidencekit.crawl  ── ONE bounded, stratified, robots-respecting crawl
  ├─ bounded link verification
  ├─ machine-readability.run(ctx) ─┐
  ├─ fact-integrity.run(ctx)       ├─ same SiteEvidence, no re-fetching
  ├─ arrival-experience.run(ctx) ──┘
  ├─ confidence gate  → needs_validation
  ├─ prioritise       → P0…P3, F-001…
  ├─ proactive        → PO-001…
  └─ validate → audit-report.json + audit-report.txt
```

Composition is what makes cross-skill judgements possible: MR-005 suppresses
MR-006 on the same page so one missing-text problem is not billed twice, MR-007
defers duplicate-title pairs to FI-004, and the proactive generators consult
which defects fired before suggesting anything.

## 15. Generalisation

The rules came from studying how research agents handled a mixed set of real sites,
but **no site name, domain or selector is hard-coded anywhere**. Each
observation was converted into a structural property any site can exhibit, with
an explicit guard for the legitimate sites that would otherwise trip it. The
observation-to-detector mapping, including what was deliberately *not* built,
is in [`references/research-matrix.md`](references/research-matrix.md).

The audit makes no assumption about industry, CMS, framework or language beyond
one documented case: AX-002's sentence-pattern test is English-specific and
exempts non-English pages that carry a meta description.

## 16. Testing

```bash
python tests/run_tests.py             # everything
python tests/run_tests.py -k crawl    # one module
```

321 tests across twelve modules:

| Module | Covers |
|---|---|
| `test_textutil.py` | normalisation, entity-name compatibility, date and price parsing, anchor and sentence classification |
| `test_htmlparse.py` | identity extraction, region classification, JSON-LD flattening and parse-error capture, rendering signals, malformed markup |
| `test_crawl.py` | URL normalisation, templates, sitemaps, robots parsing, and that write methods are refused |
| `test_machine_readability.py` | MR-001…009, each with a positive and a negative control |
| `test_fact_integrity.py` | FI-001…007, each with a positive and a negative control |
| `test_arrival_experience.py` | AX-001…007, each with a positive and a negative control |
| `test_external_evidence.py` | EX-001…006, the six discoverability scenarios (strong presence, missing references, conflicting identity, unreachable reference, consistent sources, false-positive control), plus no-network degradation |
| `test_dynamic_content.py` | the four-way rendering classification and honest rendering claims |
| `test_composition.py` | one entrypoint, the skill contract, standalone reuse, manifest/registry agreement, and that no research target is named in code |
| `test_proactive.py` | each opportunity fires from an observation, is suppressed when the matching defect fired, and a well-built site correctly gets none |
| `test_prioritize.py` | scoring inputs, banding guard rails, ordering, and the `Finding` invariants |
| `test_report_schema.py` | schema validation and the semantic rules a schema cannot express |
| `test_integration.py` | the real entrypoint against two locally-served fixture sites |

The runner also performs structural checks on the marketplace itself: the
manifest declares exactly one entrypoint, every declared skill directory exists
with valid `SKILL.md` frontmatter, every registry entry has guards and a
verification step, and every declared defect is implemented.

## 17. Project layout

```
brand-evidence-auditor/
├── marketplace.json                 manifest — exactly one entrypoint
├── run_audit.py                     convenience wrapper for the entrypoint
├── README.md · LICENSE · requirements.txt
├── references/
│   ├── defect-registry.json         29 defects: mechanism, guards, fixes
│   ├── composition.md               the skill/orchestrator contract
│   ├── false-positive-audit.md      every detector, reviewed against six questions
│   └── research-matrix.md           field research → generic detectors
├── lib/evidencekit/                 shared, stdlib-only evidence collection
│   ├── fetch.py                     read-only HTTP, robots, budgets
│   ├── crawl.py                     bounded stratified sampling, sitemaps
│   ├── htmlparse.py                 HTML → structured page evidence
│   ├── textutil.py                  deterministic text measurement
│   ├── findings.py                  Finding/Evidence model, confidence gate
│   ├── entity.py                    brand-name and identity primitives (shared)
│   ├── external.py                  bounded off-site probing, graceful degradation
│   ├── skillrunner.py               standalone execution for one skill
│   └── context.py                   shared AuditContext
├── skills/
│   ├── evidence-path-orchestrator/  ENTRYPOINT
│   │   ├── SKILL.md
│   │   ├── scripts/{run_audit,prioritize,proactive,render_report,validate_report}.py
│   │   └── references/{evidence-path,severity-priority-model,report-schema}.md
│   │                   report-schema.json
│   ├── machine-readability/  SKILL.md · scripts/{detectors,audit}.py · references/
│   ├── fact-integrity/       SKILL.md · scripts/{detectors,audit}.py · references/
│   ├── arrival-experience/   SKILL.md · scripts/{detectors,audit}.py · references/
│   └── external-evidence/    SKILL.md · scripts/{detectors,audit}.py · references/
├── examples/                        sample-report.json · sample-report.txt
└── tests/
    ├── run_tests.py · helpers.py · fixture_server.py
    ├── test_*.py                    321 tests
    └── fixtures/{site_healthy,site_broken}/
```

## 18. Design decisions and trade-offs

**No third-party dependencies.** Everything is stdlib. It costs a hand-written
HTML extractor, sitemap parser and JSON-Schema subset validator, and buys a
marketplace that runs anywhere Python does, with no install step and no
dependency surface.

**No JavaScript execution.** Adding a headless browser would find more content
— and would defeat the purpose, since many retrieval fetchers do not run one.
The audit measures what a non-rendering reader actually receives. This is
stated in `limitations` on every run.

**A small stratified sample rather than a full crawl.** Twenty pages chosen
across URL templates say more about a site's *templates* than two hundred pages
from one template, and keep the audit polite and inside its budget. Every share
in the report is explicitly relative to the sample.

**Registry as data, not code.** The reasoning is reviewable by someone who does
not read Python, and detector logic cannot silently drift from the documented
methodology.

**Text reports, not dashboards.** The output is meant to be pasted into a
ticket and acted on. Every finding carries the URL, the measurement, the fix,
and the check that proves the fix worked.

## 19. Limitations

Reported in every run, not buried here:

- Served HTML only; no JavaScript is executed. Client-side rendering is
  *inferred* from served bytes unless you supply rendered snapshots.
- Content inside `<iframe>` elements, images and linked PDFs is not extracted,
  so pages that carry their substance there are judged on what remains.
- Where region detection is unreliable, three detectors abstain rather than
  guess; those pages appear under `needs_validation`, not as findings.
- Findings describe a bounded sample, and shares are relative to it.
- Off-site checks cover only the identifiers the site itself declares. How the
  open web describes the brand unprompted is out of scope, no search engine is
  queried, and the absence of external references is never treated as a defect.
- The auditor models failure mechanisms for retrieval-oriented research agents
  and context-limited fetch-and-extract systems. It does not claim that every AI
  system behaves this way, nor that any particular product uses or ignores a
  given site.
- robots-blocked URLs are reported as findings but never inspected.
- Detects structural defects, not content quality. A page can pass every check
  and still say the wrong thing.
- AX-002's definitional-sentence test is English-specific and is skipped for
  non-English pages that carry a meta description.

## 20. Extending it

To add a detector:

1. Add an entry to `references/defect-registry.json` — including
   `false_positive_guards` and a `verification` step. The test runner fails if
   either is missing.
2. Implement it in the appropriate `skills/*/scripts/detectors.py`, returning
   `Finding` objects built from real `Evidence`. Add it to that module's `run()`.
3. Add a **positive and a negative** test, and confirm the healthy fixture
   still yields zero findings.
4. Run `python tests/run_tests.py`.

To add a skill: create `skills/<name>/` with a `SKILL.md`, expose `run(ctx)`,
add it to `AUDIT_SKILLS` in the orchestrator and to `marketplace.json`. The
entrypoint stays exactly one.
