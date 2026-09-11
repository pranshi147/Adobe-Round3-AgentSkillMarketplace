"""Finding and evidence model shared by every audit skill.

Two hard rules are enforced here rather than left to convention:

  1. A Finding cannot be constructed without at least one Evidence item that
     carries a URL and a concrete measurement or observation.
  2. Confidence is derived from the *evidence level*, not asserted freely.
     `indicative` findings are diverted to `needs_validation` and never
     appear in the prioritised findings list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

SEVERITIES = ("critical", "high", "medium", "low")
PRIORITIES = ("P0", "P1", "P2", "P3")
STAGES = ("DISCOVER", "IDENTIFY", "EXTRACT", "UNDERSTAND", "TRUST", "CITE", "ENGAGE")
EVIDENCE_LEVELS = ("verified", "corroborated", "indicative")

# Confidence is a function of the evidence level, tightened or loosened only
# within the band the level allows.
LEVEL_CONFIDENCE = {
    "verified": (0.90, 0.99),
    "corroborated": (0.72, 0.89),
    "indicative": (0.40, 0.65),
}

SEVERITY_WEIGHT = {"critical": 1.0, "high": 0.78, "medium": 0.46, "low": 0.22}

STAGE_IMPORTANCE = {
    "DISCOVER": 1.00,   # nothing downstream can succeed if this fails
    "EXTRACT": 0.94,
    "IDENTIFY": 0.88,
    "TRUST": 0.82,
    "CITE": 0.76,
    "UNDERSTAND": 0.70,
    "ENGAGE": 0.64,
}


@dataclass
class Evidence:
    url: str
    observation: str
    measurement: str = ""
    excerpt: str = ""

    def to_dict(self) -> dict:
        d = {"url": self.url, "observation": self.observation}
        if self.measurement:
            d["measurement"] = self.measurement
        if self.excerpt:
            d["excerpt"] = self.excerpt
        return d


@dataclass
class Finding:
    id: str
    detector: str
    title: str
    category: str            # skill that produced it
    stage: str               # EvidencePath stage
    failure_mode: str        # invisible | misread | stale | ambiguous | bounce
    severity: str
    evidence: list = field(default_factory=list)   # [Evidence]
    evidence_level: str = "verified"
    confidence: float = 0.9
    impact: str = ""
    mechanism: str = ""
    affected_urls: list = field(default_factory=list)
    measurements: dict = field(default_factory=dict)
    effort: str = "medium"                          # small | medium | large
    core_page_affected: bool = False
    affected_share: float = 0.0                     # 0..1 of sampled pages
    suggested_action: dict = field(default_factory=dict)
    priority: str = "P2"
    priority_score: float = 0.0
    report_id: str = ""

    def __post_init__(self):
        if self.severity not in SEVERITIES:
            raise ValueError(f"{self.detector}: invalid severity {self.severity!r}")
        if self.stage not in STAGES:
            raise ValueError(f"{self.detector}: invalid stage {self.stage!r}")
        if self.evidence_level not in EVIDENCE_LEVELS:
            raise ValueError(f"{self.detector}: invalid evidence level")
        if not self.evidence:
            raise ValueError(f"{self.detector}: findings require evidence")
        for ev in self.evidence:
            if not ev.url or not ev.observation:
                raise ValueError(f"{self.detector}: evidence needs url + observation")
        lo, hi = LEVEL_CONFIDENCE[self.evidence_level]
        self.confidence = round(min(hi, max(lo, self.confidence)), 2)
        if self.severity == "critical" and self.evidence_level == "indicative":
            # Never let a heuristic signal produce a critical finding.
            self.severity = "medium"
        if not self.affected_urls:
            self.affected_urls = list(dict.fromkeys(e.url for e in self.evidence))

    # -- serialisation ----------------------------------------------------
    def evidence_text(self) -> str:
        """Single-string evidence summary (required by the report schema)."""
        parts = []
        for ev in self.evidence[:4]:
            bit = f"{ev.url}: {ev.observation}"
            if ev.measurement:
                bit += f" [{ev.measurement}]"
            parts.append(bit)
        extra = len(self.evidence) - 4
        if extra > 0:
            parts.append(f"(+{extra} further affected page(s))")
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.report_id or self.id,
            "defect_id": self.id,
            "detector": self.detector,
            "title": self.title,
            "category": self.category,
            "stage": self.stage,
            "failure_mode": self.failure_mode,
            "severity": self.severity,
            "priority": self.priority,
            "confidence": self.confidence,
            "evidence_level": self.evidence_level,
            "impact": self.impact,
            "mechanism": self.mechanism,
            "evidence": self.evidence_text(),
            "evidence_items": [e.to_dict() for e in self.evidence],
            "affected_urls": self.affected_urls[:25],
            "measurements": self.measurements,
            "effort": self.effort,
            "suggested_action": self.suggested_action,
        }


def make_action(summary: str, implementation: list, why_it_works: str,
                verification: str, priority: str = "P2") -> dict:
    return {
        "summary": summary,
        "implementation": list(implementation),
        "why_it_works": why_it_works,
        "verification": verification,
        "priority": priority,
    }


def severity_from_share(share: float, core_page: bool,
                        high_at: float = 0.4, medium_at: float = 0.15,
                        allow_critical: bool = False) -> str:
    """Breadth-driven severity: how much of the sampled surface is affected."""
    if allow_critical and (share >= 0.8 or (core_page and share >= 0.5)):
        return "critical"
    if share >= high_at or (core_page and share >= medium_at):
        return "high"
    if share >= medium_at:
        return "medium"
    return "low"


def load_registry(path: str | Path | None = None) -> dict:
    """Load the defect registry (detector metadata: mechanism, fixes, guards)."""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "references" / "defect-registry.json"
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {entry["id"]: entry for entry in data["defects"]}


def registry_action(spec: dict, priority: str = "P2", **fmt) -> dict:
    """Build a suggested_action from a registry entry, with formatting slots."""
    fix = spec["recommended_fix"]
    return make_action(
        summary=fix["summary"].format(**fmt) if fmt else fix["summary"],
        implementation=[s.format(**fmt) if fmt else s for s in fix["implementation"]],
        why_it_works=fix["why_it_works"],
        verification=fix["verification"],
        priority=priority,
    )
