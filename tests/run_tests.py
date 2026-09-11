#!/usr/bin/env python3
"""Run the whole test suite, plus structural checks on the marketplace itself.

    python tests/run_tests.py            # everything
    python tests/run_tests.py -k crawl   # only modules matching a substring

Exit code 0 means: every unit test passed, the registry and manifest are
well-formed, every skill declared in marketplace.json exists with a SKILL.md,
exactly one entrypoint is declared, and every detector in the registry is
implemented (and vice versa).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))


def structural_checks() -> list:
    errors: list = []

    manifest_path = ROOT / "marketplace.json"
    if not manifest_path.exists():
        return ["marketplace.json is missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    entrypoints = [s for s in manifest["skills"] if s.get("entrypoint")]
    if len(entrypoints) != 1:
        errors.append(f"expected exactly one entrypoint skill, found {len(entrypoints)}")

    for skill in manifest["skills"]:
        skill_dir = ROOT / skill["path"]
        if not skill_dir.is_dir():
            errors.append(f"declared skill path missing: {skill['path']}")
            continue
        if not skill.get("entrypoint") and not (skill_dir / "scripts" / "audit.py").is_file():
            errors.append(f"{skill['name']}: no standalone scripts/audit.py")
        if not (skill_dir / "SKILL.md").is_file():
            errors.append(f"{skill['name']}: SKILL.md missing")
        else:
            text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            if not text.startswith("---"):
                errors.append(f"{skill['name']}: SKILL.md has no YAML frontmatter")
            frontmatter = text.split("---")[1]
            for key in ("name:", "description:"):
                if key not in frontmatter:
                    errors.append(f"{skill['name']}: SKILL.md frontmatter lacks {key}")
            # A bare ": " inside an unquoted YAML value makes the frontmatter
            # unparseable, which is rejected on upload. Checked without PyYAML
            # so the marketplace keeps its zero-dependency guarantee.
            for line in frontmatter.strip().splitlines():
                match = re.match(r"^([a-z][a-z0-9-]*): (.*)$", line)
                if not match:
                    continue
                value = match.group(2).strip()
                quoted = len(value) > 1 and value[0] == value[-1] and value[0] in "'\""
                if ": " in value and not quoted:
                    errors.append(
                        f"{skill['name']}: SKILL.md frontmatter key '{match.group(1)}' has "
                        f"an unquoted value containing ': ', which is invalid YAML")
                if match.group(1) == "name" and value != skill["name"]:
                    errors.append(
                        f"{skill['name']}: SKILL.md name '{value}' does not match the "
                        f"manifest/folder name")

    for skill in entrypoints:
        cmd = skill.get("entrypoint_command", "")
        script = ROOT / skill["path"] / "scripts" / "run_audit.py"
        if not script.is_file():
            errors.append("entrypoint script scripts/run_audit.py is missing")
        if "run_audit.py" not in cmd:
            errors.append("entrypoint_command does not invoke run_audit.py")

    registry = json.loads((ROOT / "references" / "defect-registry.json").read_text("utf-8"))
    declared = {d["id"] for d in registry["defects"]}
    required_keys = {"id", "detector", "skill", "stage", "failure_mode", "title",
                     "mechanism", "impact", "detection_logic", "required_evidence",
                     "false_positive_guards", "severity_conditions", "recommended_fix",
                     "effort"}
    for defect in registry["defects"]:
        missing = required_keys - set(defect)
        if missing:
            errors.append(f"{defect.get('id')}: registry entry missing {sorted(missing)}")
        fix = defect.get("recommended_fix", {})
        for key in ("summary", "implementation", "why_it_works", "verification"):
            if not fix.get(key):
                errors.append(f"{defect.get('id')}: recommended_fix.{key} is empty")
        if not defect.get("false_positive_guards"):
            errors.append(f"{defect.get('id')}: no false-positive guards declared")
        if len(defect.get("false_positive_guards", [])) < 2:
            errors.append(f"{defect.get('id')}: fewer than two false-positive guards")

    implemented = set()
    for skill_name in (s["name"] for s in manifest["skills"] if not s.get("entrypoint")):
        source = (ROOT / "skills" / skill_name / "scripts" / "detectors.py").read_text("utf-8")
        for defect_id in declared:
            if f'"{defect_id}"' in source:
                implemented.add(defect_id)
    for missing in sorted(declared - implemented):
        errors.append(f"{missing}: declared in the registry but not implemented")

    blob = json.dumps(manifest).lower()
    for placeholder in ("example.com", "github.com/example", "todo", "changeme"):
        if placeholder in blob:
            errors.append(f"marketplace.json contains placeholder metadata: {placeholder}")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", "--filter", default="", help="substring filter on test modules")
    ap.add_argument("--skip-structure", action="store_true")
    args = ap.parse_args()

    pattern = f"test_*{args.filter}*.py" if args.filter else "test_*.py"
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    errors: list = []
    if not args.skip_structure:
        print("\nstructural checks")
        print("-" * 70)
        errors = structural_checks()
        for e in errors:
            print(f"  FAIL {e}")
        if not errors:
            print("  ok: manifest, skill folders, standalone entries, registry, "
                  "guards and detector coverage")

    ok = result.wasSuccessful() and not errors
    print(f"\n{'PASS' if ok else 'FAIL'}: "
          f"{result.testsRun} test(s), {len(errors)} structural error(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
