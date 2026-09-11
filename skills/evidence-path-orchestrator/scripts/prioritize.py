"""Priority engine.

Severity answers "how damaging is this defect if left unresolved?".
Priority answers "what should the owner do first?" — a different question,
so it is computed from a different set of inputs and is never a rename of
severity.

    priority_score = severity_weight
                   × confidence            (how sure we are it is real)
                   × affected_surface      (breadth, with a core-page floor)
                   × stage_importance      (where in the evidence path it breaks)

Guard rails applied after scoring:
  * a verified critical finding is always P0;
  * a low-severity finding is never above P2 (it should not outrank real damage);
  * a medium-severity finding is never P0 (P0 means "drop other work");
  * implementation effort never changes priority — it is reported separately
    so a team can distinguish "high severity, large effort" from
    "medium severity, five-minute fix".
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from evidencekit.findings import SEVERITY_WEIGHT, STAGE_IMPORTANCE  # noqa: E402

P0_AT = 0.52
P1_AT = 0.34
P2_AT = 0.12


def affected_surface(finding) -> float:
    surface = 0.4 + 0.6 * min(1.0, max(0.0, finding.affected_share))
    if finding.core_page_affected:
        surface = max(surface, 0.85)
    return round(surface, 3)


def score(finding) -> float:
    w = SEVERITY_WEIGHT[finding.severity]
    stage = STAGE_IMPORTANCE[finding.stage]
    return round(w * finding.confidence * affected_surface(finding) * stage, 4)


def band(value: float) -> str:
    if value >= P0_AT:
        return "P0"
    if value >= P1_AT:
        return "P1"
    if value >= P2_AT:
        return "P2"
    return "P3"


def prioritize(findings: list) -> list:
    for f in findings:
        f.priority_score = score(f)
        p = band(f.priority_score)
        if f.severity == "critical" and f.evidence_level == "verified":
            p = "P0"
        if f.severity == "medium" and p == "P0":
            p = "P1"
        if f.severity == "low" and p in ("P0", "P1"):
            p = "P2"
        f.priority = p
        if f.suggested_action:
            f.suggested_action["priority"] = p
        f.measurements = dict(f.measurements or {})
        f.measurements["priority_score"] = f.priority_score
        f.measurements["affected_surface"] = affected_surface(f)
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    findings.sort(key=lambda f: (order[f.priority], -f.priority_score, f.id))
    for idx, f in enumerate(findings, start=1):
        f.report_id = f"F-{idx:03d}"
    return findings


def summarize(findings: list) -> dict:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.severity] += 1
    return {"total_findings": len(findings), **counts}
