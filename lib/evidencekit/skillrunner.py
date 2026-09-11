"""Standalone execution for a single audit skill.

Each audit skill is a reusable unit: it answers one question over shared
evidence and returns findings. This module lets an agent run exactly one of
them — `python skills/fact-integrity/scripts/audit.py https://example.com` —
without pulling in the orchestrator.

What standalone mode deliberately does NOT do, because these are the
orchestrator's responsibilities and not any single skill's:

  * merge findings across skills, or apply cross-skill suppression
  * assign priorities and report ids
  * generate proactive opportunities
  * emit or validate the marketplace report schema

Standalone output is therefore a *skill result* — findings plus withheld
signals plus limitations — not an audit report. Keeping the two shapes
distinct is what stops "reusable skill" from meaning "the orchestrator with
some flags".
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import entity, external
from .context import AuditContext
from .crawl import Crawler
from .fetch import DEFAULT_UA, Fetcher
from .findings import load_registry


def build_parser(skill_name: str, question: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=f"{skill_name}/scripts/audit.py",
        description=f"Run the {skill_name} skill on its own. {question} "
                    f"Output is a skill result, not a marketplace report: for a "
                    f"prioritised report across all skills, use the "
                    f"evidence-path-orchestrator entrypoint.")
    ap.add_argument("url")
    ap.add_argument("--scope", choices=["site", "page"], default="site")
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--max-seconds", type=float, default=120.0)
    ap.add_argument("--min-interval", type=float, default=0.15)
    ap.add_argument("--user-agent", default=DEFAULT_UA)
    ap.add_argument("--external", choices=["auto", "off"], default="auto",
                    help="probe the external identifiers the site declares "
                         "(used by the external-evidence skill only)")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--quiet", action="store_true")
    return ap


def run_standalone(skill_name: str, detectors, question: str, argv=None) -> int:
    args = build_parser(skill_name, question).parse_args(argv)
    log = (lambda *a: None) if args.quiet else (
        lambda *a: print(f"[{skill_name}]", *a, file=sys.stderr))

    started = time.time()
    fetcher = Fetcher(user_agent=args.user_agent, min_interval=args.min_interval,
                      deadline=started + args.max_seconds)
    crawler = Crawler(fetcher, max_pages=1 if args.scope == "page" else args.max_pages)
    evidence = crawler.run(args.url, scope=args.scope)
    log(f"collected {len(evidence.pages)} page(s)")

    ctx = AuditContext(evidence, load_registry(), user_agent=args.user_agent)
    if skill_name == "external-evidence":
        ctx.external = external.collect(fetcher, entity.declared_entity_urls(ctx),
                                        mode=args.external, origin=evidence.root_url)

    findings = detectors.run(ctx)
    result = {
        "skill": skill_name,
        "site": evidence.root_url,
        "pages_examined": len(evidence.pages),
        "duration_seconds": round(time.time() - started, 1),
        "findings": [f.to_dict() for f in findings],
        "needs_validation": ctx.needs_validation,
        "limitations": list(evidence.limitations) + list(ctx.external.limitations),
        "note": ("Skill result only. Priorities, cross-skill merging, proactive "
                 "opportunities and schema validation are applied by the "
                 "evidence-path-orchestrator entrypoint."),
    }
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            fh.write(text)
        log(f"wrote {args.out_json}")
    else:
        print(text)
    return 0
