"""Deterministic text utilities used by every detector.

Standard library only. No language models, no pretrained weights.
Every function here is pure and side-effect free so that detector
behaviour is reproducible for identical inputs.
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata

WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "at", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "it", "its", "this", "that", "these", "those", "you", "your",
    "we", "our", "us", "they", "their", "he", "she", "his", "her", "i", "me",
    "my", "not", "no", "yes", "can", "will", "just", "do", "does", "did",
    "have", "has", "had", "more", "most", "other", "some", "such", "than",
    "then", "so", "too", "very", "all", "any", "each", "how", "what", "when",
    "where", "which", "who", "why", "about", "into", "over", "up", "down",
    "out", "off", "again", "further", "once", "here", "there", "also",
}

LEGAL_SUFFIXES = {
    "inc", "inc.", "llc", "l.l.c", "ltd", "ltd.", "limited", "pvt", "pvt.",
    "private", "corp", "corp.", "corporation", "gmbh", "plc", "co", "co.",
    "company", "sa", "s.a", "bv", "b.v", "ag", "srl", "oy", "ab", "as",
    "group", "holdings", "technologies", "labs",
}

CURRENCY_RE = re.compile(
    r"(?:₹|rs\.?|inr|\$|usd|us\$|€|eur|£|gbp|¥|jpy|aud|cad)\s?"
    r"(\d{1,3}(?:[,\u202f\s]\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

TEXT_DATE_RE = re.compile(
    r"\b(?:(\d{1,2})\s+(" + _MONTH_ALT + r")\.?\,?\s+(\d{4})"
    r"|(" + _MONTH_ALT + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\,?\s+(\d{4}))\b",
    re.IGNORECASE,
)

NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/](\d{1,2})[/](\d{4})\b")

# Phrases that assert currency/timeliness. Used only to decide whether the
# absence of a date signal is materially harmful, never on their own.
# Explicit claims that the page's content is CURRENT. Availability wording
# ("in stock", "now available") is deliberately excluded: it describes a state,
# not a claim about freshness, and treating it as one made FI-005 fire on
# essentially every product page ever published.
TIME_SENSITIVE_PHRASES = (
    "latest", "current", "currently", "today", "this week", "this month",
    "right now", "as of", "up to date", "up-to-date", "newest", "just launched",
    "today's", "updated daily", "last updated", "most recent",
)

VOLATILE_PHRASES = (
    "in stock", "out of stock", "availability", "price", "pricing", "offer",
    "discount", "delivery", "shipping", "sale", "book now", "seats",
)

NONDESCRIPTIVE_ANCHORS = {
    "", "here", "click here", "click", "read more", "learn more", "more",
    "more info", "details", "view", "view more", "see more", "link", "this",
    "continue", "go", "next", "previous", ">", "<", "»", "«", "→", "...",
    "…", "read", "show more", "explore", "discover", "find out more",
}

DEFINITIONAL_RE = re.compile(
    r"\b(?:is|are|was|were)\s+(?:a|an|the|one of|india's|the world's|"
    r"our|your|\w+'s)\b|"
    r"\b(?:provides?|offers?|helps?|enables?|delivers?|specialis[ez]es?|"
    r"builds?|makes?|sells?|lets you|allows you)\b",
    re.IGNORECASE,
)


def normalize_ws(text: str) -> str:
    """Collapse all whitespace runs into single spaces."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> list[str]:
    return WORD_RE.findall((text or "").lower())


def word_count(text: str) -> int:
    return len(words(text))


def content_tokens(text: str) -> set[str]:
    """Lower-cased tokens with stopwords and 1-character tokens removed."""
    return {w for w in words(text) if w not in STOPWORDS and len(w) > 1}


def shingles(text: str, size: int = 6) -> set[str]:
    toks = words(text)
    if len(toks) < size:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + size]) for i in range(len(toks) - size + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def overlap_ratio(a: set, b: set) -> float:
    """Fraction of `a` that also appears in `b`."""
    if not a:
        return 1.0
    return len(a & b) / len(a)


def normalize_entity_name(name: str) -> str:
    """Normalise a brand/organisation name for cross-source comparison."""
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[®™©]", " ", name)
    name = re.sub(r"[^a-z0-9]+", " ", name)
    toks = [t for t in name.split() if t and t not in LEGAL_SUFFIXES]
    return " ".join(toks).strip()


def names_compatible(a: str, b: str) -> bool:
    """True when two normalised names plausibly denote the same entity.

    Compatible means: identical, one contained in the other as a whole-token
    prefix/suffix, or high token overlap. This is deliberately permissive so
    that `Acme` / `Acme Technologies` never produces a finding.
    """
    if not a or not b:
        return True
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    if not ta or not tb:
        return True
    sa, sb = set(ta), set(tb)
    if sa <= sb or sb <= sa:
        return True
    # Whole-token containment in either direction.
    if a in b or b in a:
        return True
    # Acronym match: "bmc" vs "big mountain corp"
    if len(ta) == 1 and len(ta[0]) >= 2:
        acro = "".join(t[0] for t in tb)
        if acro == ta[0]:
            return True
    if len(tb) == 1 and len(tb[0]) >= 2:
        acro = "".join(t[0] for t in ta)
        if acro == tb[0]:
            return True
    return jaccard(sa, sb) >= 0.5


def sentences(text: str) -> list[str]:
    text = normalize_ws(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if p.strip()]


def find_years(text: str) -> list[int]:
    return [int(m.group(0)) for m in YEAR_RE.finditer(text or "")]


def find_dates(text: str) -> list[_dt.date]:
    """Extract dates from free text using unambiguous, common formats."""
    out: list[_dt.date] = []
    if not text:
        return out
    for m in ISO_DATE_RE.finditer(text):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            out.append(d)
    for m in TEXT_DATE_RE.finditer(text):
        if m.group(1):
            day, mon, year = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
        else:
            mon, day, year = MONTHS[m.group(4).lower()], int(m.group(5)), int(m.group(6))
        d = _safe_date(year, mon, day)
        if d:
            out.append(d)
    for m in NUMERIC_DATE_RE.finditer(text):
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Ambiguous d/m vs m/d: only accept when one field is unambiguous.
        if a > 12 and b <= 12:
            d = _safe_date(year, b, a)
        elif b > 12 and a <= 12:
            d = _safe_date(year, a, b)
        else:
            d = None
        if d:
            out.append(d)
    return out


def parse_datetime_attr(value: str):
    """Parse a datetime attribute (`<time datetime=...>`, JSON-LD dates)."""
    if not value:
        return None
    value = value.strip()
    m = ISO_DATE_RE.search(value)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    ys = find_dates(value)
    return ys[0] if ys else None


def _safe_date(year: int, month: int, day: int):
    try:
        d = _dt.date(year, month, day)
    except ValueError:
        return None
    if d.year < 1990 or d.year > _dt.date.today().year + 2:
        return None
    return d


def find_prices(text: str) -> list[str]:
    """Return normalised numeric price strings found in text."""
    out = []
    for m in CURRENCY_RE.finditer(text or ""):
        raw = m.group(1)
        norm = normalize_number(raw)
        if norm is not None:
            out.append(norm)
    return out


def normalize_number(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw)
    s = re.sub(r"[^\d.]", "", s)
    if not s or s.count(".") > 1:
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    if val.is_integer():
        return str(int(val))
    return f"{val:.2f}".rstrip("0").rstrip(".")


def has_any(text: str, phrases) -> list[str]:
    low = (text or "").lower()
    return [p for p in phrases if p in low]


def is_nondescriptive_anchor(text: str) -> bool:
    t = normalize_ws(text).lower().strip(" .:-–—>»")
    if not t:
        return True
    if t in NONDESCRIPTIVE_ANCHORS:
        return True
    toks = [w for w in words(t) if w not in STOPWORDS]
    return len(toks) == 0


def looks_definitional(sentence: str) -> bool:
    return bool(DEFINITIONAL_RE.search(sentence or ""))


def truncate(text: str, limit: int = 220) -> str:
    text = normalize_ws(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
