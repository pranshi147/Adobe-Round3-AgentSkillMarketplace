---
name: external-evidence
description: Assess off-site AI discoverability — whether a brand can be corroborated outside its own website and told apart from similarly-named entities. Checks the external identifiers a site declares about itself (do they resolve, do they name the brand), whether a common-word brand name is published with anything that disambiguates it, and whether the domain and the brand name are connected by any published assertion. Use when a brand is confused with another organisation, when entity resolution matters, or as the off-site half of a full audit run by the evidence-path-orchestrator. Never treats absence of external presence as a defect and never searches the web.
license: MIT
allowed-tools: Bash, Read
---

# External evidence

**The question this skill answers:** can this entity be corroborated and told
apart from others *outside* the four walls of its own site?

On-site checks can prove a site is internally consistent. They cannot tell you
whether a research agent that encounters this brand name somewhere else will
resolve it to this domain, or to a different organisation with a similar name.
That is what this skill measures.

## Detectors

| ID | Defect | Needs network | Ceiling |
|---|---|---|---|
| EX-001 | Declared external identifiers do not resolve | yes | medium |
| EX-002 | A declared identifier resolves but never names the brand | yes | medium |
| EX-003 | Common-word brand name published with nothing to disambiguate it | no | medium |
| EX-004 | Domain label and brand name unrelated, with no bridging assertion | no | low |
| EX-005 | The brand's other hostname serves a separate site | yes | medium |
| EX-006 | Declared external references never point back to this site | yes | low |

EX-003 and EX-004 are computed entirely from what the site publishes and always
run. EX-001, EX-002, EX-005 and EX-006 require the bounded probe described
below. Request budget: at most eight, inside the audit's single shared deadline,
each subject to the destination host's robots.txt.

## What is tested, and what is not

**Tested.** The site's off-site discoverability surface, meaning the routes by
which something published elsewhere leads back here. Concretely: the external
URLs the site itself declares — `sameAs`, `identifier`, `rel=me`, `rel=author`,
`rel=publisher` and cross-domain `rel=alternate` — up to six of them, requested
read-only; and up to two alternate forms of the site's own hostname (www to apex
or back). For each the audit records whether it resolved, whether the
destination recognisably concerns this brand, whether it references this domain
back, and whether it carries an independent description of the brand. Also tested, without any network access: the
ambiguity profile of the published brand name, the disambiguating assertions
the site makes about itself, and whether the domain label and brand name are
connected by a published assertion.

**Not tested.** Anything the site did not name. No search engine, directory,
knowledge base or social platform is queried. No third-party source is crawled.
No attempt is made to count how many other entities share the brand name, to
measure what is said about the brand elsewhere, or to determine whether any AI
product has indexed, used or ignored this site — none of that is observable
from a first-party, read-only audit, so none of it is claimed.

## Three things this skill will not do

**It will not treat absence as failure.** A site with no external profiles is
not failing anything. Many legitimate organisations — private companies, local
businesses, internal tools, new brands — have none worth declaring. Absence
produces at most a proactive opportunity, worded so that it does not apply if no
suitable record exists. Creating profiles to satisfy an audit is not the
recommendation.

**It will not assume every site needs a particular kind of record.** There is no
check for a Wikipedia entry, a social account, or a directory listing. The
checks are about the identifiers the site *chose* to publish, and about
disambiguation where the name genuinely needs it.

**It will not claim anything about specific AI products, or about the web at
large.** The audit has not looked at the web at large — only at what this site
publishes and at its own hostnames. It therefore never concludes that a brand is
"not discoverable", and a single absent source is never evidence of anything.
Findings are phrased as retrieval and trust risks with the evidence attached.

## Degradation

If the network is unavailable, `--external off` is passed, or a probe exceeds
the budget, each probe is recorded as `not_checked` with its reason, and
EX-001/EX-002 report nothing. The reasons appear in the report's
`external_corroboration` block and `limitations`. A sandbox with no egress
produces zero external findings and a complete audit — never a failed run.

## Run it

```bash
# as part of a full audit (default: probes declared identifiers only)
python skills/evidence-path-orchestrator/scripts/run_audit.py https://example.com

# skip all external requests
python skills/evidence-path-orchestrator/scripts/run_audit.py https://example.com --external off

# this skill alone
python skills/external-evidence/scripts/audit.py https://example.com
```

## Reading its findings

EX-001, EX-002 and EX-006 are the site's own corroboration failing on its own
terms: it offered references, and they do not resolve, do not concern this
entity, or never agree in the other direction. EX-005 is about the route in —
whether a reference using the brand's other hostname reaches this site at all.
EX-003 and EX-004 are about selection: given several entities that could match a
name, has this site published anything a resolver could choose on? All six are
entity-resolution risks, which is why they sit at the IDENTIFY stage.

See `references/external-rules.md` for thresholds, comparison rules and guards.
