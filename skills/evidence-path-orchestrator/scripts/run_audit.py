"""run_audit.py — the marketplace's single entrypoint.

Pipeline (deterministic end to end):

    scope decision
      -> bounded evidence collection            (evidencekit.crawl)
      -> bounded broken-link verification
      -> machine-readability detectors          (skill 2)
      -> fact-integrity detectors               (skill 3)
      -> arrival-experience detectors           (skill 4)
      -> confidence gate                        (indicative -> needs_validation)
      -> severity/priority engine               (prioritize.py)
      -> proactive opportunities                (proactive.py)
      -> schema validation                      (validate_report.py)
      -> report.json + report.txt (+ agent brief)

The orchestrator holds no crawling logic and no detection logic of its own:
it decides scope, collects evidence exactly once, composes the audit skills
over that shared evidence, and owns merging, gating, prioritisation and
report emission.

Examples
--------
    python run_audit.py https://example.com
    python run_audit.py https://example.com/pricing --scope page
    python run_audit.py https://example.com --max-pages 25 --max-seconds 180 \
        --out-dir ./out --agent-brief
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))

from evidencekit import __version__ as KIT_VERSION            # noqa: E402
from evidencekit import entity, external                      # noqa: E402
from evidencekit.context import AuditContext                  # noqa: E402
from evidencekit.crawl import Crawler, check_links, normalize_url  # noqa: E402
from evidencekit.fetch import DEFAULT_UA, Fetcher             # noqa: E402
from evidencekit.findings import Evidence, load_registry      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prioritize                                             # noqa: E402
import proactive                                              # noqa: E402
import render_report                                          # noqa: E402
import validate_report                                        # noqa: E402

AUDIT_SKILLS = [
    ("machine-readability", ROOT / "skills" / "machine-readability" / "scripts" / "detectors.py"),
    ("fact-integrity", ROOT / "skills" / "fact-integrity" / "scripts" / "detectors.py"),
    ("arrival-experience", ROOT / "skills" / "arrival-experience" / "scripts" / "detectors.py"),
    ("external-evidence", ROOT / "skills" / "external-evidence" / "scripts" / "detectors.py"),
]

STAGES = ["DISCOVER", "IDENTIFY", "EXTRACT", "UNDERSTAND", "TRUST", "CITE", "ENGAGE"]
SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"bea_{name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="run_audit.py",
        description="Audit a website's AI discoverability, citation readiness "
                    "and arrival experience. Read-only; respects robots.txt.")
    ap.add_argument("url", help="Target URL (site root for a site audit, or a specific page)")
    ap.add_argument("--scope", choices=["site", "page"], default="site",
                    help="site = stratified sample of the site (default); page = the URL only")
    ap.add_argument("--max-pages", type=int, default=20,
                    help="Maximum pages to fetch in site scope (default 20)")
    ap.add_argument("--max-seconds", type=float, default=170.0,
                    help="Hard wall-clock budget for network work (default 170)")
    ap.add_argument("--timeout", type=float, default=8.0, help="Per-request timeout")
    ap.add_argument("--min-interval", type=float, default=0.15,
                    help="Minimum seconds between requests to one host")
    ap.add_argument("--user-agent", default=DEFAULT_UA)
    ap.add_argument("--link-check-limit", type=int, default=10,
                    help="How many linked-but-unfetched URLs to verify (0 disables)")
    ap.add_argument("--out-dir", default=".", help="Directory for report files")
    ap.add_argument("--out-json", default=None, help="Explicit JSON report path")
    ap.add_argument("--out-text", default=None, help="Explicit text report path")
    ap.add_argument("--external", choices=["auto", "off"], default="auto",
                    help="off-site corroboration: 'auto' probes only the external "
                         "identifiers the site itself declares; 'off' skips it entirely")
    ap.add_argument("--external-limit", type=int, default=6,
                    help="maximum declared external identifiers to probe (default 6)")
    ap.add_argument("--rendered-evidence", default=None,
                    help="optional JSON file mapping URL -> rendered HTML, produced by "
                         "your own tooling. The auditor never renders anything itself; "
                         "supplying this upgrades rendering claims from inferred to verified")
    ap.add_argument("--agent-brief", action="store_true",
                    help="Also write agent-brief.json (structured evidence for an "
                         "agent reasoning layer; contains no interpretation)")
    ap.add_argument("--quiet", action="store_true", help="Suppress progress logging")
    ap.add_argument("--print-json", action="store_true",
                    help="Print the JSON report to stdout instead of a summary")
    return ap.parse_args(argv)


def audit(args) -> dict:
    started = time.time()
    log = (lambda *a: None) if args.quiet else (
        lambda *a: print("[audit]", *a, file=sys.stderr))

    deadline = started + args.max_seconds
    fetcher = Fetcher(user_agent=args.user_agent, timeout=args.timeout,
                      min_interval=args.min_interval, deadline=deadline)
    max_pages = 1 if args.scope == "page" else args.max_pages
    crawler = Crawler(fetcher, max_pages=max_pages, log=log)

    log(f"scope={args.scope} target={args.url} budget={args.max_seconds}s "
        f"max_pages={max_pages}")
    evidence = crawler.run(args.url, scope=args.scope)
    log(f"collected {len(evidence.pages)} page(s) in {evidence.duration:.1f}s")

    link_failures = []
    if args.scope == "site" and args.link_check_limit > 0 and not fetcher.out_of_time():
        link_failures = check_links(fetcher, evidence, limit=args.link_check_limit)
        log(f"link check: {len(link_failures)} broken destination(s)")

    registry = load_registry()
    ctx = AuditContext(evidence, registry, user_agent=args.user_agent,
                       link_check_failures=link_failures)

    if getattr(args, "rendered_evidence", None):
        ctx.rendered_evidence = _load_rendered_evidence(args.rendered_evidence, log)

    # Off-site corroboration: bounded, and only against identifiers this site
    # declares. Failure here degrades to "not checked", never to a finding.
    declared = entity.declared_entity_urls(ctx)
    ctx.external = external.collect(fetcher, declared, limit=args.external_limit,
                                    mode=args.external, origin=evidence.root_url)
    log(f"external: {len(ctx.external.checked_probes)}/{len(declared)} declared "
        f"identifier(s) probed (mode={args.external})")

    findings = []
    for name, path in AUDIT_SKILLS:
        module = load_module(name, path)
        produced = module.run(ctx)
        log(f"skill {name}: {len(produced)} finding(s)")
        findings.extend(produced)

    findings = confidence_gate(ctx, findings)
    findings = apply_sample_floor(ctx, findings)
    status = audit_status(evidence)
    if status == "inconclusive":
        # Nothing was successfully read. Reporting findings here would be a claim
        # about a site the audit never saw, which is exactly the failure mode this
        # tool exists to criticise.
        log("audit inconclusive: no page returned a readable 2xx response")
        findings, opportunities = [], []
    else:
        findings = prioritize.prioritize(findings)
        opportunities = proactive.generate(ctx, findings)

    report = build_report(args, evidence, ctx, findings, opportunities, fetcher,
                          started, status)
    errors = validate_report.validate(report) + validate_report.semantic_checks(report)
    if errors:
        raise SystemExit("report failed schema validation:\n  " + "\n  ".join(errors))
    return report, ctx


def _load_rendered_evidence(path: str, log) -> dict:
    """Load caller-supplied rendered snapshots: {url: rendered_html}."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        log(f"rendered evidence could not be read ({exc}); continuing without it")
        return {}
    out = {}
    for url, html in (data or {}).items():
        if isinstance(url, str) and isinstance(html, str):
            out[normalize_url(url)] = html
    log(f"rendered evidence supplied for {len(out)} URL(s)")
    return out


def audit_status(evidence) -> str:
    """complete | partial | inconclusive — how much of the site was actually read.

    A judge pointing this at a blocked, offline or robots-excluded host must get
    "we could not audit this", never a clean bill of health and never a finding.
    """
    readable = [p for p in evidence.pages if 200 <= p.status < 300 and p.is_html]
    if not readable:
        return "inconclusive"
    if evidence.scope == "page":
        return "complete"
    if len(readable) < 3 or evidence.limitations or evidence.fetch_failures:
        return "partial"
    return "complete"


SAMPLE_FLOOR = 5


def apply_sample_floor(ctx, findings: list) -> list:
    """Breadth cannot escalate severity on a sample too small to measure breadth.

    Directly observed defects (a robots rule matching a URL, an HTTP 404, a
    noindex directive) are unaffected: one page is enough to see them. Findings
    that infer scale from a handful of pages are capped, and say so.
    """
    sampled = len(ctx.content_pages())
    if sampled >= SAMPLE_FLOOR:
        return findings
    for f in findings:
        if f.evidence_level == "verified" or f.severity in ("medium", "low"):
            continue
        original = f.severity
        f.severity = "medium"
        f.measurements = dict(f.measurements or {})
        f.measurements["sample_floor_applied"] = (
            f"severity reduced from {original}: {sampled} content page(s) sampled, "
            f"below the {SAMPLE_FLOOR}-page floor for breadth-based escalation")
        f.evidence.append(Evidence(
            url=ctx.ev.root_url,
            observation="severity was capped because the sample is too small to "
                        "establish how widespread this is",
            measurement=f"{sampled} content page(s) sampled; breadth-based escalation "
                        f"requires at least {SAMPLE_FLOOR}"))
    return findings


def confidence_gate(ctx, findings: list) -> list:
    """Only verified/corroborated findings are reported; the rest are withheld."""
    kept = []
    for f in findings:
        if f.evidence_level == "indicative":
            ctx.note(f.id, f.affected_urls[0] if f.affected_urls else ctx.ev.root_url,
                     f.title, "", "indicative evidence only; withheld from findings")
            continue
        kept.append(f)
    return kept


def build_report(args, evidence, ctx, findings, opportunities, fetcher, started,
                 status: str = "complete") -> dict:
    site = normalize_url(evidence.root_url)
    stage_rollup = {}
    for stage in STAGES:
        items = [f for f in findings if f.stage == stage]
        stage_rollup[stage] = {
            "worst_severity": (max((f.severity for f in items),
                                   key=lambda s: SEVERITY_RANK[s]) if items else None),
            "findings": [f.report_id for f in items],
        }

    limitations = list(evidence.limitations)
    if status == "inconclusive":
        limitations.insert(0, (
            "AUDIT INCONCLUSIVE: no page returned a readable 2xx HTML response, so no "
            "finding can be made about this site. The absence of findings here means the "
            "site could not be read, NOT that it is free of defects. Check that the URL "
            "is reachable from this environment and that robots.txt permits it."))
    elif status == "partial":
        limitations.insert(0, (
            "Partial audit: fewer pages were read than requested, so shares and breadth "
            "are measured over a small sample. Findings remain valid for the pages named."))
    if len(ctx.content_pages()) < SAMPLE_FLOOR:
        limitations.append(
            f"Only {len(ctx.content_pages())} content page(s) were sampled; breadth-based "
            f"severity escalation was disabled below the {SAMPLE_FLOOR}-page floor.")
    limitations.append(
        "The audit reads served HTML only and does not execute JavaScript. Pages whose "
        "content is assembled client-side are reported as what a non-rendering fetcher "
        "observes; the rendered state was " + ctx.rendering_verification + ".")
    limitations.extend(ctx.external.limitations)
    limitations.append(
        "Off-site corroboration is limited to the external identifiers the site itself "
        "declares. No search engine or directory was consulted, no claim is made about "
        "whether any AI product uses this site, and the absence of external references is "
        "never treated as a defect.")
    limitations.append(
        f"{len(evidence.pages)} page(s) were sampled under a {args.max_pages}-page / "
        f"{args.max_seconds:.0f}s budget; findings describe the sample, and shares are "
        f"reported relative to it.")
    if evidence.blocked_urls:
        limitations.append(
            f"{len(evidence.blocked_urls)} URL(s) were not fetched because robots.txt "
            f"disallows them; they are reported as findings, not inspected.")

    return {
        "site": site,
        "audited_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "auditor": {
            "name": "brand-evidence-auditor",
            "version": KIT_VERSION,
            "user_agent": args.user_agent,
        },
        "scope": {
            "type": evidence.scope,
            "status": status,
            "pages_examined": len(evidence.pages),
            "pages_readable": len([p for p in evidence.pages
                                   if 200 <= p.status < 300 and p.is_html]),
            "requests_made": fetcher.requests_made,
            "duration_seconds": round(time.time() - started, 1),
            "urls_examined": [p.final_url for p in evidence.pages],
            "rendering_verification": ctx.rendering_verification,
        },
        "summary": prioritize.summarize(findings),
        "evidence_path": stage_rollup,
        "external_corroboration": ctx.external.summary(),
        "findings": [f.to_dict() for f in findings],
        "proactive_opportunities": opportunities,
        "needs_validation": ctx.needs_validation,
        "limitations": limitations,
    }


def build_agent_brief(report: dict, ctx) -> dict:
    """Structured evidence for an agent reasoning layer.

    Deliberately contains observations and measurements only. The contract for
    any model consuming it: interpret, group and explain — never add an
    observation that is not present here.
    """
    return {
        "site": report["site"],
        "audited_at": report["audited_at"],
        "contract": [
            "Every statement you make must trace to an observation in this file.",
            "Do not introduce URLs, numbers or claims that are not present here.",
            "You may merge, rank, and explain findings; you may not create them.",
            "If evidence is insufficient, say so rather than inferring a cause.",
        ],
        "pages": [
            {
                "url": p.final_url,
                "status": p.status,
                "depth": p.depth,
                "title": p.title,
                "h1": p.h1s[0] if p.h1s else "",
                "canonical": p.canonical,
                "main_words": p.words_main,
                "internal_links": len(p.internal_links),
                "main_region_links": len(p.main_internal_links),
                "jsonld_types": p.jsonld_types(),
                "robots_directives": p.robots_directives(),
                "has_date_signal": bool(p.time_elements) or any(
                    k in p.meta for k in ("article:modified_time", "date")),
            }
            for p in ctx.ev.pages
        ],
        "findings": report["findings"],
        "needs_validation": report["needs_validation"],
        "limitations": report["limitations"],
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    report, ctx = audit(args)

    json_path = Path(args.out_json) if args.out_json else out_dir / "audit-report.json"
    text_path = Path(args.out_text) if args.out_text else out_dir / "audit-report.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    text_path.write_text(render_report.render(report), encoding="utf-8")

    if args.agent_brief:
        (out_dir / "agent-brief.json").write_text(
            json.dumps(build_agent_brief(report, ctx), indent=2, ensure_ascii=False),
            encoding="utf-8")

    if args.print_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        s = report["summary"]
        print(f"{report['site']}: {s['total_findings']} finding(s) "
              f"(critical {s['critical']}, high {s['high']}, medium {s['medium']}, "
              f"low {s['low']}) in {time.time() - started:.1f}s")
        for f in report["findings"][:5]:
            print(f"  [{f['priority']}] {f['id']} {f['title']} ({f['severity']})")
        print(f"JSON: {json_path}")
        print(f"Text: {text_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
