#!/usr/bin/env python3
"""Convenience wrapper for the marketplace entrypoint.

The canonical entrypoint declared in marketplace.json is
`skills/evidence-path-orchestrator/scripts/run_audit.py`. This file exists so
the audit can also be started from the marketplace root:

    python run_audit.py https://example.com --out-dir ./out

It adds no behaviour of its own — it delegates argument parsing and execution
to the entrypoint script.
"""

import runpy
import sys
from pathlib import Path

ENTRYPOINT = (Path(__file__).resolve().parent / "skills" /
              "evidence-path-orchestrator" / "scripts" / "run_audit.py")

if __name__ == "__main__":
    sys.argv[0] = str(ENTRYPOINT)
    runpy.run_path(str(ENTRYPOINT), run_name="__main__")
