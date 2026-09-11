"""evidencekit — shared, dependency-free evidence collection for the
brand-evidence-auditor marketplace.

Modules
-------
fetch      read-only HTTP with robots, timeouts, size caps and budgets
crawl      bounded, stratified sampling of a site (never a recursive spider)
htmlparse  raw-HTML -> structured page evidence (what a non-rendering reader sees)
textutil   deterministic text measurements (dates, prices, shingles, names)
findings   Finding/Evidence model with confidence gating
context    AuditContext shared by every detector module
"""

__version__ = "1.0.0"

__all__ = ["fetch", "crawl", "htmlparse", "textutil", "findings", "context"]
