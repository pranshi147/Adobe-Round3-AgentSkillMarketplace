"""Validate an audit report against references/report-schema.json.

A small, dependency-free validator covering the subset of JSON Schema the
report uses (type, required, enum, minimum/maximum, minItems, items,
properties, additionalProperties-as-schema). Keeping this in-package means
report validity is checked on every run without adding a runtime dependency.

Usage:
    python validate_report.py report.json
Exit code 0 = valid, 1 = invalid (errors printed one per line).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "report-schema.json"

TYPES = {
    "object": dict, "array": list, "string": str, "number": (int, float),
    "integer": int, "boolean": bool, "null": type(None),
}


def _type_ok(value, expected) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        py = TYPES.get(name)
        if py is None:
            return True
        if name == "integer" and isinstance(value, bool):
            continue
        if name == "number" and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def validate(instance, schema=None, path="$") -> list:
    if schema is None:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    errors: list = []

    if "type" in schema and not _type_ok(instance, schema["type"]):
        errors.append(f"{path}: expected type {schema['type']}, got {type(instance).__name__}")
        return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} not in {schema['enum']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} > maximum {schema['maximum']}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property '{key}'")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                errors.extend(validate(value, props[key], f"{path}.{key}"))
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(validate(value, schema["additionalProperties"],
                                       f"{path}.{key}"))
    elif isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: expected at least {schema['minItems']} item(s)")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(instance):
                errors.extend(validate(item, item_schema, f"{path}[{idx}]"))
    return errors


def semantic_checks(report: dict) -> list:
    """Consistency checks a JSON Schema cannot express."""
    errors = []
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    ids = set()
    for f in report.get("findings", []):
        counts[f.get("severity", "low")] = counts.get(f.get("severity", "low"), 0) + 1
        if f["id"] in ids:
            errors.append(f"duplicate finding id: {f['id']}")
        ids.add(f["id"])
        if not f.get("evidence"):
            errors.append(f"{f['id']}: empty evidence string")
        if not f.get("evidence_items"):
            errors.append(f"{f['id']}: no evidence items")
        if f.get("evidence_level") == "indicative":
            errors.append(f"{f['id']}: indicative evidence must not appear in findings")
        if f.get("severity") == "critical" and f.get("evidence_level") != "verified":
            errors.append(f"{f['id']}: critical severity requires verified evidence")
        if f.get("severity") == "low" and f.get("priority") in ("P0", "P1"):
            errors.append(f"{f['id']}: low severity cannot be {f['priority']}")
        action = f.get("suggested_action", {})
        if action.get("priority") and action["priority"] != f.get("priority"):
            errors.append(f"{f['id']}: suggested_action.priority disagrees with finding priority")
    scope = report.get("scope", {})
    if scope.get("status") == "inconclusive" and report.get("findings"):
        errors.append("inconclusive audits must not report findings")
    summary = report.get("summary", {})
    if summary.get("total_findings") != len(report.get("findings", [])):
        errors.append("summary.total_findings does not match len(findings)")
    for sev, n in counts.items():
        if summary.get(sev, 0) != n:
            errors.append(f"summary.{sev}={summary.get(sev)} but findings contain {n}")
    return errors


def main(argv) -> int:
    if len(argv) != 2:
        print("usage: validate_report.py <report.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        report = json.load(fh)
    errors = validate(report) + semantic_checks(report)
    if errors:
        for e in errors:
            print(f"INVALID: {e}")
        return 1
    print(f"valid: {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
