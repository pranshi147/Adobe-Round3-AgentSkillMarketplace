"""Shared entity-identity evidence.

Both the on-site identity checks (FI-001, FI-002) and the off-site
corroboration checks (EX-002, EX-003, EX-004) need the same primitives: what
names does this site publish for itself, from which independent surfaces, and
what does it publish that would let a resolver tell this entity apart from
another with a similar name?

Keeping those primitives here means the two skills agree on what "the brand
name" is, instead of each deriving it separately and drifting apart.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from . import textutil as tu

ENTITY_TYPES = ("organization", "localbusiness", "corporation", "website",
                "onlinestore", "store", "ngo", "educationalorganization",
                "governmentorganization", "restaurant", "medicalorganization",
                "sportsorganization", "performinggroup", "airline")

TITLE_SPLIT_RE = re.compile(r"\s*[|\u2013\u2014\u00b7\u2022:]\s*|\s+-\s+")

COPYRIGHT_RE = re.compile(
    r"(?:©|\(c\)|copyright)\s*(?:\d{4}(?:\s*[-–]\s*\d{4})?)?\s*,?\s*"
    r"([A-Z][A-Za-z0-9&'’.\- ]{1,50})", re.IGNORECASE)

# Two-part public suffixes common enough to matter when reading a domain label.
MULTI_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "co.in", "net.in", "org.in", "ac.in",
    "co.jp", "co.kr", "co.nz", "co.za", "com.au", "com.br", "com.cn", "com.mx",
    "com.sg", "com.tr", "com.tw", "com.hk", "com.my", "com.ph", "com.ar",
}

# Ordinary English words. A brand built only from these competes with every
# other use of them, which is a *disambiguation* question, never a defect in
# itself. Used only to decide whether disambiguating assertions are needed.
COMMON_WORDS = {
    "above", "access", "account", "active", "add", "advance", "after", "agent",
    "air", "all", "alpha", "always", "anchor", "apple", "apply", "arc", "area",
    "arrow", "art", "aspect", "atlas", "auto", "axis", "back", "balance", "bank",
    "base", "basket", "bay", "beam", "bear", "bell", "best", "beta", "better",
    "big", "bird", "black", "blue", "board", "bold", "bolt", "book", "boost",
    "border", "box", "brand", "bridge", "bright", "broad", "brook", "brown",
    "build", "bull", "cable", "call", "camp", "cap", "capital", "care", "cargo",
    "case", "cast", "center", "central", "centre", "chain", "chair", "chance",
    "change", "channel", "charge", "chart", "check", "choice", "circle", "city",
    "class", "clean", "clear", "climb", "cloud", "coast", "code", "coin", "cold",
    "colour", "color", "common", "compass", "connect", "core", "corner", "count",
    "country", "craft", "creek", "cross", "crown", "cube", "current", "curve",
    "cycle", "daily", "dart", "dash", "data", "dawn", "day", "deep", "delta",
    "desk", "dial", "digital", "direct", "dock", "dot", "double", "down", "draft",
    "dream", "drive", "drop", "dynamic", "eagle", "early", "earth", "east", "easy",
    "echo", "edge", "elevate", "elite", "empire", "energy", "engine", "equal",
    "evergreen", "exact", "express", "fair", "falcon", "fall", "family", "fast",
    "field", "filter", "fine", "fire", "first", "fit", "five", "flag", "flame",
    "flash", "flat", "flex", "flow", "focus", "fold", "food", "force", "forest",
    "form", "forward", "found", "four", "fox", "frame", "free", "fresh", "front",
    "fuel", "full", "future", "garden", "gate", "gear", "gem", "general", "gift",
    "glass", "global", "glow", "gold", "good", "grand", "grape", "grass", "great",
    "green", "grid", "ground", "group", "grove", "guard", "guide", "hall", "hand",
    "happy", "harbor", "harbour", "hard", "hawk", "head", "health", "heart",
    "heat", "high", "hill", "home", "honest", "hope", "horizon", "house", "hub",
    "human", "ice", "ideal", "impact", "index", "inside", "iron", "island",
    "jet", "joy", "jump", "key", "kind", "king", "lab", "lake", "land", "large",
    "last", "launch", "layer", "leaf", "leap", "learn", "level", "life", "light",
    "line", "link", "lion", "list", "live", "local", "lock", "logic", "long",
    "look", "loop", "lucky", "main", "major", "maker", "map", "mark", "market",
    "mass", "master", "match", "matrix", "meadow", "media", "meet", "mega",
    "mercury", "merge", "metro", "middle", "mind", "mint", "mirror", "mobile",
    "modern", "moment", "money", "monitor", "moon", "motion", "mountain", "move",
    "national", "native", "natural", "nature", "near", "neat", "nest", "net",
    "new", "next", "night", "nine", "noble", "node", "north", "nova", "now",
    "oak", "ocean", "offer", "office", "one", "open", "optimal", "orange",
    "orbit", "order", "origin", "other", "outside", "pace", "pack", "page",
    "paper", "park", "part", "path", "peak", "pearl", "people", "perfect",
    "phase", "pilot", "pine", "pivot", "place", "plain", "plan", "planet",
    "plant", "play", "plus", "point", "polar", "pool", "port", "power",
    "prime", "print", "prism", "pro", "pulse", "pure", "quality", "quantum",
    "quest", "quick", "radius", "rain", "range", "rapid", "reach", "ready",
    "real", "record", "red", "reef", "relay", "reliable", "rise", "river",
    "road", "rock", "root", "round", "route", "royal", "run", "safe", "sage",
    "sail", "salt", "sand", "scale", "scope", "sea", "search", "second",
    "secure", "seed", "select", "sense", "seven", "shade", "shape", "share",
    "sharp", "shield", "shift", "shine", "ship", "shop", "short", "side",
    "sight", "signal", "silver", "simple", "single", "six", "sky", "slate",
    "sleek", "slide", "small", "smart", "smooth", "snow", "social", "solid",
    "sonic", "sound", "source", "south", "space", "spark", "speed", "sphere",
    "spirit", "split", "sport", "spot", "spring", "square", "stack", "staff",
    "stage", "stand", "star", "start", "state", "steel", "step", "stone",
    "storm", "story", "straight", "stream", "street", "strong", "studio",
    "style", "summit", "sun", "sunny", "super", "supply", "sure", "swift",
    "table", "tag", "take", "talent", "target", "task", "team", "tech", "ten",
    "test", "third", "thread", "three", "thrive", "tide", "tiger", "time",
    "tiny", "title", "today", "together", "top", "torch", "total", "touch",
    "tower", "town", "track", "trade", "trail", "train", "transfer", "travel",
    "tree", "trend", "tribe", "true", "trust", "turn", "twin", "two", "union",
    "unique", "unit", "united", "universal", "up", "urban", "valley", "value",
    "vault", "venture", "view", "village", "vision", "vital", "voice", "wave",
    "way", "west", "white", "wide", "wild", "wind", "window", "wing", "wise",
    "wolf", "wonder", "wood", "work", "world", "yellow", "young", "zone",
}

DISAMBIGUATOR_FIELDS = ("sameAs", "legalName", "identifier", "foundingDate",
                        "address", "areaServed", "taxID", "vatID", "duns",
                        "leiCode", "naics", "isicV4", "telephone")


def entity_nodes(page) -> list:
    """Organization/WebSite-family JSON-LD nodes on a page."""
    out = []
    for node in page.jsonld:
        t = node.get("@type")
        tl = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
        if any(str(x).lower() in ENTITY_TYPES for x in tl):
            out.append(node)
    return out


def recurring_title_segment(ctx) -> tuple:
    """The constant part of the site's titles, whichever end it sits on.

    Titles are written both ways round — `Page — Brand` and `Brand | Page` — so
    taking a fixed end produces a phantom brand name on half of all sites. The
    brand is the segment that RECURS across titles; a segment seen on only one
    page is page-specific and is not a name claim at all.
    """
    counts: dict = {}
    raws: dict = {}
    pages = [p for p in ctx.content_pages() if p.title]
    for p in pages:
        parts = [s.strip() for s in TITLE_SPLIT_RE.split(p.title) if s.strip()]
        if len(parts) < 2:
            continue
        for segment in (parts[0], parts[-1]):
            norm = tu.normalize_entity_name(segment)
            if not norm or len(norm) < 2:
                continue
            counts[norm] = counts.get(norm, 0) + 1
            raws.setdefault(norm, (segment, p.final_url))
    if not counts:
        return None
    norm, n = max(counts.items(), key=lambda kv: kv[1])
    if n < 2:
        return None            # seen once: page-specific, not an identity claim
    raw, url = raws[norm]
    return norm, raw, url


def name_candidates(ctx) -> list:
    """(source_type, raw_name, url, is_core) from independent site-level surfaces.

    A title-derived segment is included only when it recurs across titles, and
    even then it is emitted as a corroborating source rather than as an
    independent one, because title word order is a stylistic choice rather than
    an identity assertion.
    """
    out = []
    for p in ctx.content_pages():
        core = ctx.is_core(p)
        site_name = p.meta_get("og:site_name", "application-name")
        if site_name:
            out.append(("og:site_name", site_name, p.final_url, core))
        for node in entity_nodes(p):
            nm = node.get("name")
            if isinstance(nm, str) and nm.strip():
                out.append(("Organization/WebSite JSON-LD name", nm, p.final_url, core))
            pub = node.get("publisher")
            if isinstance(pub, dict) and isinstance(pub.get("name"), str):
                out.append(("JSON-LD publisher name", pub["name"], p.final_url, core))
        for src, alt in p.images:
            if alt and ("logo" in (src or "").lower() or "logo" in alt.lower()):
                cleaned = re.sub(r"\blogo\b", "", alt, flags=re.IGNORECASE).strip(" -–—|")
                if cleaned:
                    out.append(("logo alt text", cleaned, p.final_url, core))
                break
        m = COPYRIGHT_RE.search(p.text_chrome or "") or COPYRIGHT_RE.search(p.text_main or "")
        if m:
            out.append(("copyright line", m.group(1).strip(" .,"), p.final_url, core))
    recurring = recurring_title_segment(ctx)
    if recurring:
        _norm, raw, url = recurring
        out.append(("recurring title segment", raw, url, True))
    return out


def published_names(ctx) -> list:
    """Distinct normalised brand names the site publishes, most-attested first."""
    counts: dict = {}
    raws: dict = {}
    for source, raw, _url, _core in name_candidates(ctx):
        norm = tu.normalize_entity_name(raw)
        if not norm or len(norm) < 2:
            continue
        counts[norm] = counts.get(norm, 0) + 1
        raws.setdefault(norm, raw)
    return [(norm, raws[norm], n) for norm, n in
            sorted(counts.items(), key=lambda kv: -kv[1])]


def primary_name(ctx):
    """The most-attested published brand name, or None if the site names itself nowhere."""
    names = published_names(ctx)
    return names[0] if names else None


def domain_label(url: str) -> str:
    """The registrable label of a host: `example` from `www.example.co.uk`."""
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if all(part.isdigit() for part in parts):
        return ""                      # IP literal: no registrable brand label to compare
    if len(parts) < 2:
        return parts[0] if parts else ""
    if ".".join(parts[-2:]) in MULTI_SUFFIXES and len(parts) >= 3:
        return parts[-3]
    return parts[-2]


def name_is_ambiguous(norm_name: str) -> tuple:
    """(is_ambiguous, reason). Ambiguity is a disambiguation need, not a defect."""
    toks = [t for t in norm_name.split() if t]
    if not toks:
        return False, ""
    if len(toks) == 1 and len(toks[0]) <= 4:
        return True, f"single short token \"{toks[0]}\" ({len(toks[0])} characters)"
    if all(t in COMMON_WORDS for t in toks):
        return True, ("every token is an ordinary dictionary word: "
                      + ", ".join(f"\"{t}\"" for t in toks))
    return False, ""


def disambiguators(ctx) -> dict:
    """Assertions the site publishes that would let a resolver pick this entity."""
    found: dict = {}
    for p in ctx.content_pages():
        for node in entity_nodes(p):
            for field in DISAMBIGUATOR_FIELDS:
                value = node.get(field)
                if value:
                    found.setdefault(field, p.final_url)
        for node in p.jsonld:
            if node.get("@type") in ("Organization", "LocalBusiness") and node.get("url"):
                found.setdefault("url", p.final_url)
        if any(tu.looks_definitional(s) for s in tu.sentences(p.text_main[:900])) \
                and ctx.is_core(p):
            found.setdefault("definitional_sentence", p.final_url)
    return found


# Standard link relations that publish a stable external reference for the
# entity. These are conventions (HTML rel registry, IndieWeb rel-me), not
# provider APIs: nothing here is specific to any platform.
REFERENCE_RELS = ("me", "author", "publisher", "alternate")


def declared_entity_urls(ctx) -> list:
    """(url, source) pairs the site itself declares as external references.

    Sources: `sameAs` and `identifier` in entity markup, plus `<link rel=me>`,
    `<link rel=author>`, `<link rel=publisher>` and cross-domain
    `<link rel=alternate>`. All of it is published BY the audited site — the
    audit never searches the web and never probes a third party the site did
    not name.
    """
    out: list = []
    seen = set()
    host = urlparse(ctx.ev.root_url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    for p in ctx.content_pages():
        for node in entity_nodes(p):
            same_as = node.get("sameAs")
            values = ([same_as] if isinstance(same_as, str)
                      else same_as if isinstance(same_as, list) else [])
            for value in values:
                if not isinstance(value, str):
                    continue
                value = value.strip()
                if value.startswith("http") and value not in seen:
                    seen.add(value)
                    out.append((value, f"sameAs in entity markup on {p.final_url}"))
            ident = node.get("identifier")
            if isinstance(ident, str) and ident.startswith("http") and ident not in seen:
                seen.add(ident)
                out.append((ident, f"identifier in entity markup on {p.final_url}"))
        for rel, href in p.link_rels:
            rels = {r.strip() for r in (rel or "").split()}
            if not (rels & set(REFERENCE_RELS)) or not href.startswith("http"):
                continue
            target_host = urlparse(href).netloc.lower()
            target_host = target_host[4:] if target_host.startswith("www.") else target_host
            if not target_host or target_host == host:
                continue          # same-site rel=alternate is not an external reference
            if href in seen:
                continue
            seen.add(href)
            matched = sorted(rels & set(REFERENCE_RELS))[0]
            out.append((href, f"link rel=\"{matched}\" on {p.final_url}"))
    return out


def hostname_variants(url: str) -> list:
    """The other common hostname form for this origin (www <-> apex).

    References to a brand circulate in both forms. If only one of them serves
    the site, or the two serve different content without consolidating, a
    reference that uses the other form does not reach this site.
    """
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if not host or not domain_label(url):
        return []                     # IP literals and bare hosts have no variant
    scheme = parsed.scheme or "https"
    if host.startswith("www."):
        return [f"{scheme}://{host[4:]}/"]
    if host.count(".") >= 1:
        return [f"{scheme}://www.{host}/"]
    return []
