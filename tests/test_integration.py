"""End-to-end tests: run the real entrypoint against two locally-served sites.

`site_healthy` is the negative control — the whole marketplace must produce
zero findings on it. `site_broken` is the positive control, seeded with one
concrete instance of most defects in the registry.
"""

import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_server import FixtureSite  # noqa: E402

SCRIPTS = ROOT / "skills" / "evidence-path-orchestrator" / "scripts"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_audit = _load("orch_run_audit_it", SCRIPTS / "run_audit.py")
validate_report = _load("orch_validate_it", SCRIPTS / "validate_report.py")
render_report = _load("orch_render_it", SCRIPTS / "render_report.py")

FIXTURES = ROOT / "tests" / "fixtures"


def audit_site(directory, extra_args=()):
    with FixtureSite(directory) as base_url:
        args = run_audit.parse_args([base_url, "--quiet", "--max-pages", "20",
                                     "--max-seconds", "60", "--min-interval", "0",
                                     *extra_args])
        report, ctx = run_audit.audit(args)
    return report, ctx


class TestHealthySiteNegativeControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.started = time.time()
        cls.report, cls.ctx = audit_site(FIXTURES / "site_healthy")
        cls.elapsed = time.time() - cls.started

    def test_no_findings(self):
        self.assertEqual(self.report["findings"], [],
                         "clean site produced findings: " +
                         json.dumps([f["defect_id"] for f in self.report["findings"]]))

    def test_summary_is_zeroed(self):
        self.assertEqual(self.report["summary"]["total_findings"], 0)

    def test_all_fixture_pages_were_reached(self):
        self.assertGreaterEqual(self.report["scope"]["pages_examined"], 5)

    def test_report_validates(self):
        self.assertEqual(validate_report.validate(self.report), [])
        self.assertEqual(validate_report.semantic_checks(self.report), [])

    def test_runs_well_inside_the_budget(self):
        self.assertLess(self.elapsed, 60)

    def test_proactive_opportunities_are_separate_from_findings(self):
        for op in self.report["proactive_opportunities"]:
            self.assertIn("suggested_action", op)
            self.assertTrue(op["id"].startswith("PO-"))

    def test_limitations_are_always_reported(self):
        self.assertTrue(self.report["limitations"])


class TestBrokenSitePositiveControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.ctx = audit_site(FIXTURES / "site_broken")
        cls.defects = {f["defect_id"] for f in cls.report["findings"]}

    def test_expected_defects_detected(self):
        expected = {"MR-001", "MR-002", "MR-003", "MR-004", "MR-005",
                    "FI-001", "FI-003", "FI-004", "FI-005",
                    "AX-004", "AX-005"}
        self.assertTrue(expected <= self.defects,
                        f"missing: {sorted(expected - self.defects)}")

    def test_report_validates(self):
        self.assertEqual(validate_report.validate(self.report), [])
        self.assertEqual(validate_report.semantic_checks(self.report), [])

    def test_robots_blocked_page_is_reported_but_never_fetched(self):
        fetched = set(self.report["scope"]["urls_examined"])
        self.assertFalse(any(u.endswith("/guides/torque.html") for u in fetched))
        mr001 = [f for f in self.report["findings"] if f["defect_id"] == "MR-001"][0]
        self.assertTrue(any("guides" in u for u in mr001["affected_urls"]))

    def test_every_finding_carries_evidence_with_a_url(self):
        for f in self.report["findings"]:
            self.assertTrue(f["evidence_items"])
            for item in f["evidence_items"]:
                self.assertTrue(item["url"].startswith("http"))
                self.assertTrue(item["observation"])

    def test_every_finding_has_an_actionable_fix(self):
        for f in self.report["findings"]:
            action = f["suggested_action"]
            self.assertTrue(action["summary"])
            self.assertTrue(action["implementation"])
            self.assertTrue(action["verification"])

    def test_priorities_are_assigned_and_ordered(self):
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        seq = [order[f["priority"]] for f in self.report["findings"]]
        self.assertEqual(seq, sorted(seq))

    def test_price_contradiction_names_both_values(self):
        fi003 = [f for f in self.report["findings"] if f["defect_id"] == "FI-003"][0]
        blob = json.dumps(fi003)
        self.assertIn("999", blob)
        self.assertIn("1299", blob)

    def test_evidence_path_rollup_marks_broken_stages(self):
        self.assertTrue(self.report["evidence_path"]["DISCOVER"]["findings"])

    def test_text_report_renders_all_sections(self):
        text = render_report.render(self.report)
        for heading in ("AI VISIBILITY AUDIT", "SUMMARY", "TOP PRIORITIES",
                        "DETAILED FINDINGS BY EVIDENCE-PATH STAGE",
                        "OPPORTUNITIES TO STRENGTHEN CITATION READINESS",
                        "LIMITATIONS OF THIS AUDIT"):
            self.assertIn(heading, text)

    def test_json_report_is_serialisable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps(self.report, indent=2, ensure_ascii=False),
                            encoding="utf-8")
            reloaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(reloaded["site"], self.report["site"])


class TestOffSiteDiscoverability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.ctx = audit_site(FIXTURES / "site_broken")
        cls.defects = {f["defect_id"] for f in cls.report["findings"]}

    def test_declared_identifiers_are_probed(self):
        block = self.report["external_corroboration"]
        self.assertTrue(block["performed"])
        self.assertEqual(block["declared_identifiers"], 2)
        self.assertEqual(block["probes_completed"], 2)

    def test_dead_and_uncorroborating_identifiers_are_detected(self):
        self.assertIn("EX-001", self.defects)
        self.assertIn("EX-002", self.defects)

    def test_report_states_the_off_site_scope_boundary(self):
        note = self.report["external_corroboration"]["scope_note"]
        self.assertIn("No search engine", note)
        limitations = " ".join(self.report["limitations"])
        self.assertIn("absence of external references", limitations)

    def test_external_findings_are_capped_below_high(self):
        for f in self.report["findings"]:
            if f["defect_id"].startswith("EX-"):
                self.assertIn(f["severity"], ("medium", "low"), f["defect_id"])

    def test_external_off_disables_probing_without_failing_the_audit(self):
        report, _ctx = audit_site(FIXTURES / "site_broken", ("--external", "off"))
        block = report["external_corroboration"]
        self.assertEqual(block["mode"], "off")
        self.assertFalse(block["performed"])
        self.assertEqual(block["probes_attempted"], 0)
        self.assertFalse([f for f in report["findings"]
                          if f["defect_id"] in ("EX-001", "EX-002")])
        self.assertEqual(validate_report.validate(report), [])
        self.assertTrue(report["findings"], "the rest of the audit must still run")


class TestRenderingHonesty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, _ctx = audit_site(FIXTURES / "site_broken")

    def test_scope_records_that_rendering_was_not_performed(self):
        self.assertIn("not performed", self.report["scope"]["rendering_verification"])

    def test_limitations_say_no_javascript_was_executed(self):
        limitations = " ".join(self.report["limitations"])
        self.assertIn("does not execute JavaScript", limitations)
        self.assertIn("no browser engine was used", limitations)


class TestSitemapIsNotAutomaticallyAFailure(unittest.TestCase):
    def test_healthy_site_without_a_sitemap_reports_an_opportunity_not_a_finding(self):
        with FixtureSite(FIXTURES / "site_healthy") as base_url:
            args = run_audit.parse_args([base_url, "--quiet", "--max-seconds", "60",
                                         "--min-interval", "0", "--external", "off"])
            report, _ctx = run_audit.audit(args)
        self.assertNotIn("MR-008", {f["defect_id"] for f in report["findings"]})


class TestUnreachableSiteIsInconclusive(unittest.TestCase):
    """A blocked, offline or robots-excluded host must never look healthy."""

    @classmethod
    def setUpClass(cls):
        args = run_audit.parse_args(["http://127.0.0.1:9/", "--quiet",
                                     "--max-seconds", "8", "--min-interval", "0",
                                     "--external", "off"])
        cls.report, _ctx = run_audit.audit(args)

    def test_status_is_inconclusive(self):
        self.assertEqual(self.report["scope"]["status"], "inconclusive")
        self.assertEqual(self.report["scope"]["pages_readable"], 0)

    def test_no_findings_are_claimed_about_a_site_never_read(self):
        self.assertEqual(self.report["findings"], [])
        self.assertEqual(self.report["proactive_opportunities"], [])

    def test_the_reason_leads_the_limitations(self):
        self.assertIn("AUDIT INCONCLUSIVE", self.report["limitations"][0])

    def test_the_text_report_says_so_before_anything_else(self):
        text = render_report.render(self.report)
        self.assertIn("AUDIT INCONCLUSIVE", text.split("SUMMARY")[0])

    def test_report_still_validates(self):
        self.assertEqual(validate_report.validate(self.report), [])
        self.assertEqual(validate_report.semantic_checks(self.report), [])


class TestSampleFloor(unittest.TestCase):
    def test_small_sample_caps_breadth_driven_severity(self):
        """Two shell pages must not yield a critical finding."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shell = ('<html lang="en"><head><title>{t} — Tiny</title></head><body>'
                     '<div id="root"></div><script>' + 'var a="x";' * 40 +
                     '</script></body></html>')
            (root / "index.html").write_text(shell.format(t="Home"), encoding="utf-8")
            (root / "b.html").write_text(shell.format(t="Second"), encoding="utf-8")
            with FixtureSite(root) as base_url:
                args = run_audit.parse_args([base_url, "--quiet", "--max-seconds", "30",
                                             "--min-interval", "0", "--external", "off"])
                report, _ctx = run_audit.audit(args)
        mr005 = [f for f in report["findings"] if f["defect_id"] == "MR-005"]
        self.assertTrue(mr005)
        self.assertEqual(mr005[0]["severity"], "medium")
        self.assertIn("sample_floor_applied", mr005[0]["measurements"])
        self.assertEqual(validate_report.validate(report), [])


class TestPageScope(unittest.TestCase):
    def test_single_page_scope_fetches_one_page(self):
        with FixtureSite(FIXTURES / "site_broken") as base_url:
            args = run_audit.parse_args([base_url + "product-blender.html", "--quiet",
                                         "--scope", "page", "--max-seconds", "30",
                                         "--min-interval", "0"])
            report, _ctx = run_audit.audit(args)
        self.assertEqual(report["scope"]["type"], "page")
        self.assertEqual(report["scope"]["pages_examined"], 1)
        self.assertEqual(validate_report.validate(report), [])

    def test_sitemap_rule_not_applied_in_page_scope(self):
        with FixtureSite(FIXTURES / "site_healthy") as base_url:
            args = run_audit.parse_args([base_url + "about.html", "--quiet",
                                         "--scope", "page", "--max-seconds", "30",
                                         "--min-interval", "0"])
            report, _ctx = run_audit.audit(args)
        self.assertNotIn("MR-008", {f["defect_id"] for f in report["findings"]})


if __name__ == "__main__":
    unittest.main()
