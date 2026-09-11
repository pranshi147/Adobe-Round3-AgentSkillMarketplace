"""Render the machine-readable report as a decision-oriented text report.

The text report is written for a product/engineering team, not for a search
consultant: top priorities first, each with evidence, mechanism, fix and a
verification step, then the full findings grouped by the evidence-path stage
that broke.
"""

from __future__ import annotations

import textwrap

STAGE_ORDER = ["DISCOVER", "IDENTIFY", "EXTRACT", "UNDERSTAND", "TRUST", "CITE", "ENGAGE"]

STAGE_QUESTION = {
    "DISCOVER": "Can a retrieval agent reach the page at all?",
    "IDENTIFY": "Can it tell what entity/page this is?",
    "EXTRACT": "Can it read the facts out of the page?",
    "UNDERSTAND": "Are relationships and context explicit?",
    "TRUST": "Are the facts consistent and datable?",
    "CITE": "Can a specific passage be attributed and quoted?",
    "ENGAGE": "Does a referred visitor find the answer and a next step?",
}

WIDTH = 88


def _wrap(text: str, indent: str = "  ") -> str:
    return "\n".join(textwrap.fill(line, WIDTH, initial_indent=indent,
                                   subsequent_indent=indent)
                     for line in str(text).splitlines() if line.strip())


def render(report: dict) -> str:
    out: list = []
    add = out.append

    add("AI VISIBILITY AUDIT")
    add("=" * WIDTH)
    status = report.get("scope", {}).get("status", "complete")
    if status == "inconclusive":
        add("")
        add("*** AUDIT INCONCLUSIVE — the site could not be read ***")
        add(_wrap("No page returned a readable 2xx HTML response, so no finding can be "
                  "made. An empty findings list below means this site was not audited, "
                  "not that it is healthy."))
        add("")
    elif status == "partial":
        add("(partial audit — fewer pages were read than requested; see LIMITATIONS)")
    add(f"Site        : {report['site']}")
    add(f"Audited at  : {report['audited_at']}")
    scope = report.get("scope", {})
    add(f"Scope       : {scope.get('type', 'site')} — {scope.get('pages_examined', 0)} page(s) "
        f"examined, {scope.get('requests_made', 0)} request(s), "
        f"{scope.get('duration_seconds', 0)}s")
    add("")

    s = report["summary"]
    add("SUMMARY")
    add("-" * WIDTH)
    add(f"Findings: {s['total_findings']}    "
        f"Critical: {s.get('critical', 0)}   High: {s.get('high', 0)}   "
        f"Medium: {s.get('medium', 0)}   Low: {s.get('low', 0)}")
    ep = report.get("evidence_path", {})
    if ep:
        broken = [k for k in STAGE_ORDER if ep.get(k, {}).get("findings")]
        add("Evidence path stages with findings: "
            + (", ".join(broken) if broken else "none — no stage failed a check"))
    add("")

    top = [f for f in report["findings"] if f["priority"] in ("P0", "P1")]
    add("TOP PRIORITIES")
    add("-" * WIDTH)
    if not top:
        add("  No P0/P1 findings. See the detailed section for lower-priority items.")
    for f in top:
        add(f"[{f['priority']}] {f['id']} · {f['title']}  ({f['severity']}, "
            f"{f['stage']}, confidence {f['confidence']})")
        add(_wrap(f"Why it matters: {f['impact']}"))
        add(_wrap(f"Mechanism: {f['mechanism']}"))
        add("  Evidence:")
        for item in f.get("evidence_items", [])[:3]:
            line = f"- {item['url']} — {item['observation']}"
            if item.get("measurement"):
                line += f" [{item['measurement']}]"
            add(_wrap(line, indent="    "))
        action = f.get("suggested_action", {})
        add(_wrap(f"Fix: {action.get('summary', '')}"))
        for step in action.get("implementation", [])[:4]:
            add(_wrap(f"- {step}", indent="    "))
        add(_wrap(f"Verify: {action.get('verification', '')}"))
        add(_wrap(f"Effort: {f.get('effort', 'medium')}"))
        add("")

    add("DETAILED FINDINGS BY EVIDENCE-PATH STAGE")
    add("-" * WIDTH)
    for stage in STAGE_ORDER:
        items = [f for f in report["findings"] if f["stage"] == stage]
        add(f"{stage} — {STAGE_QUESTION[stage]}")
        if not items:
            add("  (no findings)")
            add("")
            continue
        for f in items:
            add(f"  {f['id']} [{f['severity']}/{f['priority']}] {f['title']}")
            add(_wrap(f"Detector: {f['detector']} ({f['defect_id']}), "
                      f"evidence level: {f['evidence_level']}", indent="    "))
            add(_wrap(f"Evidence: {f['evidence']}", indent="    "))
            add(_wrap(f"Action: {f['suggested_action'].get('summary', '')}", indent="    "))
            urls = f.get("affected_urls", [])
            if len(urls) > 1:
                add(_wrap(f"Affected URLs: {len(urls)}", indent="    "))
            add("")

    ops = report.get("proactive_opportunities", [])
    add("OPPORTUNITIES TO STRENGTHEN CITATION READINESS (no defect detected)")
    add("-" * WIDTH)
    if not ops:
        add("  None generated for this site.")
    for op in ops:
        add(f"  {op['id']} [{op['priority']}] {op['title']} ({op['stage']})")
        add(_wrap(f"Observed: {op['observation']}", indent="    "))
        add(_wrap(f"Do: {op['suggested_action']['summary']}", indent="    "))
        add(_wrap(f"Verify: {op['suggested_action']['verification']}", indent="    "))
        add("")

    nv = report.get("needs_validation", [])
    if nv:
        add("SIGNALS WITHHELD (below the confidence gate)")
        add("-" * WIDTH)
        for item in nv[:12]:
            add(f"  {item['defect_id']} · {item['url']}")
            add(_wrap(f"{item['observation']} — {item.get('measurement', '')}", indent="    "))
            add(_wrap(f"Withheld because: {item['why_withheld']}", indent="    "))
        add("")

    lim = report.get("limitations", [])
    add("LIMITATIONS OF THIS AUDIT")
    add("-" * WIDTH)
    for line in lim:
        add(_wrap(f"- {line}"))
    add("")
    return "\n".join(out)
