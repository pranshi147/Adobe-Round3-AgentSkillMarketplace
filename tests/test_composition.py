"""Marketplace composition tests.

These assert the structural claims the marketplace makes about itself: exactly
one entrypoint, four independently runnable audit skills, a shared evidence
substrate, and a clean split of responsibilities between skills and the
orchestrator.
"""

import importlib.util
import inspect
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import helpers  # noqa: E402
from helpers import context, page  # noqa: E402
from evidencekit.findings import Finding  # noqa: E402

MANIFEST = json.loads((ROOT / "marketplace.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "references" / "defect-registry.json").read_text("utf-8"))
AUDIT_SKILLS = [s for s in MANIFEST["skills"] if not s.get("entrypoint")]

RESEARCH_TARGETS = ("adobe stock", "tira", "zepto", "bookmyshow", "codeforces",
                    "illustrator", "irctc", "meesho", "acrobat")


class TestEntrypoint(unittest.TestCase):
    def test_exactly_one_entrypoint(self):
        entrypoints = [s for s in MANIFEST["skills"] if s.get("entrypoint")]
        self.assertEqual(len(entrypoints), 1)
        self.assertEqual(entrypoints[0]["name"], "evidence-path-orchestrator")

    def test_entrypoint_command_points_at_a_real_script(self):
        ep = [s for s in MANIFEST["skills"] if s.get("entrypoint")][0]
        self.assertIn("run_audit.py", ep["entrypoint_command"])
        self.assertTrue((ROOT / ep["path"] / "scripts" / "run_audit.py").is_file())

    def test_audit_skills_are_not_entrypoints(self):
        for skill in AUDIT_SKILLS:
            self.assertFalse(skill.get("entrypoint"), skill["name"])
            self.assertIn("standalone_command", skill)


class TestSkillContract(unittest.TestCase):
    """Every audit skill exposes run(ctx) -> list[Finding] and nothing more."""

    def setUp(self):
        self.modules = {s["name"]: helpers.load_detectors(s["name"]) for s in AUDIT_SKILLS}

    def test_every_skill_exposes_run_with_one_argument(self):
        for name, module in self.modules.items():
            self.assertTrue(hasattr(module, "run"), name)
            params = list(inspect.signature(module.run).parameters)
            self.assertEqual(params, ["ctx"], name)

    def test_every_skill_returns_findings_with_evidence(self):
        ctx = context({"/": page("Home — Northwind Tools")}, sitemap=["/"])
        for name, module in self.modules.items():
            for finding in module.run(ctx):
                self.assertIsInstance(finding, Finding, name)
                self.assertTrue(finding.evidence, f"{name}/{finding.id}")

    def test_skills_do_not_fetch(self):
        """A skill receives no fetcher, and must not construct one."""
        for skill in AUDIT_SKILLS:
            source = (ROOT / skill["path"] / "scripts" / "detectors.py").read_text("utf-8")
            self.assertNotIn("Fetcher(", source, skill["name"])
            self.assertNotIn("Crawler(", source, skill["name"])

    def test_skills_do_not_assign_priority_or_report_ids(self):
        for skill in AUDIT_SKILLS:
            source = (ROOT / skill["path"] / "scripts" / "detectors.py").read_text("utf-8")
            self.assertNotIn("report_id", source, skill["name"])
            self.assertNotIn("priority_score", source, skill["name"])

    def test_each_skill_answers_a_distinct_question(self):
        summaries = {s["name"]: s["summary"] for s in AUDIT_SKILLS}
        self.assertEqual(len(set(summaries.values())), len(summaries))
        stages = {}
        for skill in AUDIT_SKILLS:
            stages[skill["name"]] = {d["stage"] for d in REGISTRY["defects"]
                                     if d["skill"] == skill["name"]}
        self.assertTrue(all(stages.values()), stages)


class TestStandaloneReuse(unittest.TestCase):
    def test_every_audit_skill_has_a_standalone_entry(self):
        for skill in AUDIT_SKILLS:
            self.assertTrue((ROOT / skill["path"] / "scripts" / "audit.py").is_file(),
                            skill["name"])

    def test_standalone_entries_use_the_shared_runner(self):
        for skill in AUDIT_SKILLS:
            source = (ROOT / skill["path"] / "scripts" / "audit.py").read_text("utf-8")
            self.assertIn("run_standalone", source, skill["name"])

    def test_standalone_result_is_not_a_marketplace_report(self):
        """Skill results and audit reports are deliberately different shapes."""
        from evidencekit import skillrunner
        source = inspect.getsource(skillrunner.run_standalone)
        self.assertIn('"skill"', source)
        self.assertIn('"note"', source)
        for report_only in ('"summary"', '"evidence_path"', '"proactive_opportunities"'):
            self.assertNotIn(report_only, source)


class TestOrchestratorComposesAllSkills(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "orch_for_composition",
            ROOT / "skills" / "evidence-path-orchestrator" / "scripts" / "run_audit.py")
        self.orch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.orch)

    def test_orchestrator_runs_every_declared_audit_skill(self):
        composed = {name for name, _path in self.orch.AUDIT_SKILLS}
        self.assertEqual(composed, {s["name"] for s in AUDIT_SKILLS})

    def test_orchestrator_paths_exist(self):
        for _name, path in self.orch.AUDIT_SKILLS:
            self.assertTrue(Path(path).is_file(), path)

    def test_orchestrator_owns_prioritisation_and_gating(self):
        source = (ROOT / "skills" / "evidence-path-orchestrator" / "scripts"
                  / "run_audit.py").read_text("utf-8")
        for owned in ("confidence_gate", "prioritize.prioritize", "proactive.generate",
                      "validate_report.validate"):
            self.assertIn(owned, source)


class TestManifestRegistryAgreement(unittest.TestCase):
    def test_declared_detectors_match_the_registry(self):
        declared = {d for s in AUDIT_SKILLS for d in s["detectors"]}
        registered = {d["id"] for d in REGISTRY["defects"]}
        self.assertEqual(declared, registered)

    def test_each_registry_entry_belongs_to_a_declared_skill(self):
        names = {s["name"] for s in AUDIT_SKILLS}
        for defect in REGISTRY["defects"]:
            self.assertIn(defect["skill"], names, defect["id"])

    def test_manifest_has_no_placeholder_metadata(self):
        blob = json.dumps(MANIFEST).lower()
        for placeholder in ("example.com", "github.com/example", "todo", "changeme",
                            "your-org"):
            self.assertNotIn(placeholder, blob, placeholder)

    def test_manifest_declares_no_runtime_dependencies(self):
        self.assertEqual(MANIFEST["runtime"]["dependencies"], [])


class TestGeneralisation(unittest.TestCase):
    """Research sites informed the rules; they are never referenced by them."""

    def test_no_research_target_is_named_in_code_or_registry(self):
        files = list((ROOT / "skills").rglob("*.py")) + list((ROOT / "lib").rglob("*.py"))
        files += [ROOT / "references" / "defect-registry.json", ROOT / "marketplace.json"]
        for path in files:
            text = path.read_text(encoding="utf-8").lower()
            for target in RESEARCH_TARGETS:
                self.assertNotIn(target, text, f"{path.name} names {target!r}")

    def test_detectors_contain_no_host_specific_branching(self):
        """No detector may key off a particular host, brand or domain literal."""
        host_literal = re.compile(
            r"https?://(?!schema\.org)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
        for path in (ROOT / "skills").rglob("detectors.py"):
            text = path.read_text(encoding="utf-8")
            skill = path.parent.parent.name
            self.assertEqual(host_literal.findall(text), [], skill)
            for branching in ("netloc ==", "host ==", 'if "www.', "domain =="):
                self.assertNotIn(branching, text, skill)


if __name__ == "__main__":
    unittest.main()
