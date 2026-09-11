import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

SCRIPTS = ROOT / "skills" / "evidence-path-orchestrator" / "scripts"
spec = importlib.util.spec_from_file_location("orch_validate", SCRIPTS / "validate_report.py")
validate_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_report)

VALID = {
    "site": "http://example.test",
    "audited_at": "2026-09-10T09:00:00Z",
    "auditor": {"name": "brand-evidence-auditor", "version": "1.0.0", "user_agent": "UA"},
    "scope": {"type": "site", "status": "complete", "pages_examined": 3,
              "pages_readable": 3, "requests_made": 5,
              "duration_seconds": 2.5, "urls_examined": ["http://example.test/"],
              "rendering_verification": "not performed — no browser engine was used"},
    "summary": {"total_findings": 1, "critical": 0, "high": 1, "medium": 0, "low": 0},
    "evidence_path": {"DISCOVER": {"worst_severity": "high", "findings": ["F-001"]}},
    "findings": [{
        "id": "F-001",
        "defect_id": "MR-001",
        "detector": "important_paths_blocked_by_robots",
        "category": "machine-readability",
        "stage": "DISCOVER",
        "failure_mode": "invisible",
        "title": "Content paths are disallowed to crawlers in robots.txt",
        "severity": "high",
        "priority": "P0",
        "confidence": 0.98,
        "evidence_level": "verified",
        "impact": "Pages cannot be read.",
        "mechanism": "Compliant fetchers obey Disallow.",
        "evidence": "http://example.test/robots.txt: Disallow matches content URLs",
        "evidence_items": [{"url": "http://example.test/robots.txt",
                            "observation": "Disallow: /guides/ matches content URLs",
                            "measurement": "3 URLs matched"}],
        "affected_urls": ["http://example.test/guides/a"],
        "measurements": {"blocked_urls": 3},
        "effort": "small",
        "suggested_action": {"summary": "Narrow the rule", "implementation": ["edit"],
                             "why_it_works": "because", "verification": "refetch",
                             "priority": "P0"},
    }],
    "external_corroboration": {
        "mode": "auto", "performed": True, "declared_identifiers": 1,
        "probes_attempted": 1, "probes_completed": 1,
        "scope_note": "Only external URLs declared by the site were requested.",
        "probes": [{"url": "https://profile.test/a", "declared_in": "sameAs",
                    "checked": True, "status": 404}],
    },
    "proactive_opportunities": [],
    "needs_validation": [],
    "limitations": ["sample of 3 pages"],
}


class TestSchemaShape(unittest.TestCase):
    def test_valid_report_passes(self):
        self.assertEqual(validate_report.validate(VALID), [])
        self.assertEqual(validate_report.semantic_checks(VALID), [])

    def test_schema_file_is_parseable_json(self):
        with open(validate_report.SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertEqual(schema["type"], "object")
        self.assertIn("findings", schema["required"])

    def test_minimum_handout_fields_are_required(self):
        with open(validate_report.SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        finding_required = schema["properties"]["findings"]["items"]["required"]
        for key in ("id", "title", "severity", "evidence", "suggested_action"):
            self.assertIn(key, finding_required)

    def test_missing_required_top_level_field(self):
        broken = copy.deepcopy(VALID)
        del broken["audited_at"]
        self.assertTrue(any("audited_at" in e for e in validate_report.validate(broken)))

    def test_invalid_severity_enum(self):
        broken = copy.deepcopy(VALID)
        broken["findings"][0]["severity"] = "catastrophic"
        self.assertTrue(any("not in" in e for e in validate_report.validate(broken)))

    def test_confidence_out_of_range(self):
        broken = copy.deepcopy(VALID)
        broken["findings"][0]["confidence"] = 1.4
        self.assertTrue(any("maximum" in e for e in validate_report.validate(broken)))

    def test_evidence_items_cannot_be_empty(self):
        broken = copy.deepcopy(VALID)
        broken["findings"][0]["evidence_items"] = []
        self.assertTrue(any("at least" in e for e in validate_report.validate(broken)))

    def test_wrong_type_rejected(self):
        broken = copy.deepcopy(VALID)
        broken["summary"]["total_findings"] = "one"
        self.assertTrue(any("expected type" in e for e in validate_report.validate(broken)))


class TestExternalCorroborationBlock(unittest.TestCase):
    def test_valid_external_block_passes(self):
        self.assertEqual(validate_report.validate(VALID), [])

    def test_external_category_is_allowed_for_findings(self):
        report = copy.deepcopy(VALID)
        report["findings"][0]["category"] = "external-evidence"
        self.assertEqual(validate_report.validate(report), [])

    def test_invalid_external_mode_rejected(self):
        report = copy.deepcopy(VALID)
        report["external_corroboration"]["mode"] = "aggressive"
        self.assertTrue(any("not in" in e for e in validate_report.validate(report)))

    def test_probe_requires_url_and_checked_flag(self):
        report = copy.deepcopy(VALID)
        del report["external_corroboration"]["probes"][0]["checked"]
        self.assertTrue(any("checked" in e for e in validate_report.validate(report)))

    def test_unchecked_probe_may_carry_a_null_status(self):
        report = copy.deepcopy(VALID)
        report["external_corroboration"]["probes"][0] = {
            "url": "https://profile.test/b", "declared_in": "sameAs",
            "checked": False, "status": None,
            "not_checked_because": "network unavailable"}
        self.assertEqual(validate_report.validate(report), [])


class TestAuditStatus(unittest.TestCase):
    def test_status_is_required(self):
        broken = copy.deepcopy(VALID)
        del broken["scope"]["status"]
        self.assertTrue(any("status" in e for e in validate_report.validate(broken)))

    def test_invalid_status_rejected(self):
        broken = copy.deepcopy(VALID)
        broken["scope"]["status"] = "probably fine"
        self.assertTrue(any("not in" in e for e in validate_report.validate(broken)))

    def test_inconclusive_audit_may_not_carry_findings(self):
        broken = copy.deepcopy(VALID)
        broken["scope"]["status"] = "inconclusive"
        self.assertTrue(any("inconclusive" in e
                            for e in validate_report.semantic_checks(broken)))

    def test_inconclusive_audit_with_no_findings_is_valid(self):
        report = copy.deepcopy(VALID)
        report["scope"]["status"] = "inconclusive"
        report["findings"] = []
        report["summary"] = {"total_findings": 0, "critical": 0, "high": 0,
                             "medium": 0, "low": 0}
        self.assertEqual(validate_report.validate(report), [])
        self.assertEqual(validate_report.semantic_checks(report), [])


class TestSemanticRules(unittest.TestCase):
    def test_summary_must_match_findings(self):
        broken = copy.deepcopy(VALID)
        broken["summary"]["high"] = 5
        self.assertTrue(any("summary.high" in e
                            for e in validate_report.semantic_checks(broken)))

    def test_duplicate_finding_ids_rejected(self):
        broken = copy.deepcopy(VALID)
        broken["findings"].append(copy.deepcopy(broken["findings"][0]))
        broken["summary"] = {"total_findings": 2, "critical": 0, "high": 2,
                             "medium": 0, "low": 0}
        self.assertTrue(any("duplicate" in e
                            for e in validate_report.semantic_checks(broken)))

    def test_indicative_findings_rejected(self):
        broken = copy.deepcopy(VALID)
        broken["findings"][0]["evidence_level"] = "indicative"
        self.assertTrue(any("indicative" in e
                            for e in validate_report.semantic_checks(broken)))

    def test_critical_requires_verified_evidence(self):
        broken = copy.deepcopy(VALID)
        broken["findings"][0]["severity"] = "critical"
        broken["findings"][0]["evidence_level"] = "corroborated"
        broken["summary"] = {"total_findings": 1, "critical": 1, "high": 0,
                             "medium": 0, "low": 0}
        self.assertTrue(any("verified evidence" in e
                            for e in validate_report.semantic_checks(broken)))

    def test_low_severity_cannot_be_p0(self):
        broken = copy.deepcopy(VALID)
        broken["findings"][0]["severity"] = "low"
        broken["findings"][0]["suggested_action"]["priority"] = "P0"
        broken["summary"] = {"total_findings": 1, "critical": 0, "high": 0,
                             "medium": 0, "low": 1}
        self.assertTrue(any("cannot be P0" in e
                            for e in validate_report.semantic_checks(broken)))

    def test_action_priority_must_agree(self):
        broken = copy.deepcopy(VALID)
        broken["findings"][0]["suggested_action"]["priority"] = "P3"
        self.assertTrue(any("disagrees" in e
                            for e in validate_report.semantic_checks(broken)))

    def test_empty_evidence_string_rejected(self):
        broken = copy.deepcopy(VALID)
        broken["findings"][0]["evidence"] = ""
        self.assertTrue(any("empty evidence" in e
                            for e in validate_report.semantic_checks(broken)))


if __name__ == "__main__":
    unittest.main()
