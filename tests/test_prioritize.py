import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from evidencekit.findings import Evidence, Finding  # noqa: E402


def _load(name):
    path = ROOT / "skills" / "evidence-path-orchestrator" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"orch_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prioritize = _load("prioritize")


def make(defect_id="MR-001", severity="high", stage="DISCOVER", level="verified",
         confidence=0.95, share=0.5, core=False, effort="small"):
    return Finding(
        id=defect_id, detector="d", title="t", category="machine-readability",
        stage=stage, failure_mode="invisible", severity=severity,
        evidence=[Evidence(url="http://a.test/", observation="observed",
                           measurement="m")],
        evidence_level=level, confidence=confidence, impact="i", mechanism="m",
        affected_share=share, core_page_affected=core, effort=effort,
        suggested_action={"summary": "s", "implementation": [], "why_it_works": "w",
                          "verification": "v", "priority": "P2"})


class TestBandingGuards(unittest.TestCase):
    def test_verified_critical_is_always_p0(self):
        f = make(severity="critical", share=0.05, stage="ENGAGE")
        prioritize.prioritize([f])
        self.assertEqual(f.priority, "P0")

    def test_low_severity_never_outranks_p2(self):
        f = make(severity="low", share=1.0, core=True, stage="DISCOVER")
        prioritize.prioritize([f])
        self.assertIn(f.priority, ("P2", "P3"))

    def test_medium_severity_never_p0(self):
        f = make(severity="medium", share=1.0, core=True, stage="DISCOVER",
                 confidence=0.99)
        prioritize.prioritize([f])
        self.assertNotEqual(f.priority, "P0")

    def test_indicative_confidence_lowers_priority(self):
        strong = make(severity="high", level="verified", confidence=0.98)
        weak = make(severity="high", level="corroborated", confidence=0.75)
        prioritize.prioritize([strong, weak])
        self.assertGreater(strong.priority_score, weak.priority_score)


class TestScoringInputs(unittest.TestCase):
    def test_stage_importance_breaks_ties(self):
        early = make(stage="DISCOVER")
        late = make(stage="ENGAGE", severity="high", level="verified", confidence=0.95)
        prioritize.prioritize([early, late])
        self.assertGreater(early.priority_score, late.priority_score)

    def test_breadth_increases_score(self):
        narrow = make(share=0.05)
        wide = make(share=1.0)
        prioritize.prioritize([narrow, wide])
        self.assertGreater(wide.priority_score, narrow.priority_score)

    def test_core_page_sets_a_surface_floor(self):
        f = make(share=0.01, core=True)
        self.assertGreaterEqual(prioritize.affected_surface(f), 0.85)

    def test_effort_does_not_change_priority(self):
        cheap = make(severity="critical", effort="small")
        costly = make(severity="critical", effort="large")
        prioritize.prioritize([cheap, costly])
        self.assertEqual(cheap.priority, costly.priority)
        self.assertEqual(cheap.priority_score, costly.priority_score)


class TestOrderingAndIds(unittest.TestCase):
    def setUp(self):
        self.findings = [
            make("AX-003", severity="medium", stage="ENGAGE", level="corroborated",
                 confidence=0.79, share=0.3),
            make("MR-001", severity="critical", share=1.0, core=True),
            make("FI-005", severity="high", stage="TRUST", share=0.4),
        ]
        prioritize.prioritize(self.findings)

    def test_sorted_by_priority_then_score(self):
        self.assertEqual([f.id for f in self.findings], ["MR-001", "FI-005", "AX-003"])

    def test_report_ids_sequential(self):
        self.assertEqual([f.report_id for f in self.findings],
                         ["F-001", "F-002", "F-003"])

    def test_action_priority_kept_in_sync(self):
        for f in self.findings:
            self.assertEqual(f.suggested_action["priority"], f.priority)

    def test_score_recorded_in_measurements(self):
        for f in self.findings:
            self.assertIn("priority_score", f.measurements)
            self.assertIn("affected_surface", f.measurements)

    def test_summary_counts(self):
        summary = prioritize.summarize(self.findings)
        self.assertEqual(summary["total_findings"], 3)
        self.assertEqual(summary["critical"], 1)
        self.assertEqual(summary["high"], 1)
        self.assertEqual(summary["medium"], 1)
        self.assertEqual(summary["low"], 0)


class TestFindingInvariants(unittest.TestCase):
    def test_finding_requires_evidence(self):
        with self.assertRaises(ValueError):
            Finding(id="X", detector="d", title="t", category="c", stage="DISCOVER",
                    failure_mode="invisible", severity="high", evidence=[])

    def test_evidence_requires_url_and_observation(self):
        with self.assertRaises(ValueError):
            Finding(id="X", detector="d", title="t", category="c", stage="DISCOVER",
                    failure_mode="invisible", severity="high",
                    evidence=[Evidence(url="", observation="x")])

    def test_confidence_clamped_into_evidence_band(self):
        f = make(level="corroborated", confidence=0.99)
        self.assertLessEqual(f.confidence, 0.89)

    def test_indicative_cannot_be_critical(self):
        f = make(severity="critical", level="indicative", confidence=0.5)
        self.assertEqual(f.severity, "medium")

    def test_invalid_stage_rejected(self):
        with self.assertRaises(ValueError):
            make(stage="NOPE")


if __name__ == "__main__":
    unittest.main()
