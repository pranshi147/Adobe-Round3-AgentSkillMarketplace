#!/usr/bin/env python3
"""Standalone entry for the arrival-experience skill.

    python skills/arrival-experience/scripts/audit.py https://example.com

Runs this skill alone and prints a skill result (findings, withheld signals,
limitations). This is NOT a marketplace entrypoint: prioritisation, cross-skill
merging and report emission belong to the evidence-path-orchestrator.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import detectors                                              # noqa: E402
from evidencekit.skillrunner import run_standalone            # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_standalone("arrival-experience", detectors,
                                    "Does a referred visitor find the answer and a route onward?"))
