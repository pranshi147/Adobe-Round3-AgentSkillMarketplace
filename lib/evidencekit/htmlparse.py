"""Deterministic HTML -> structured evidence extraction.

Uses only `html.parser` from the standard library. The goal is not a perfect
DOM: it is a *stable, reproducible* projection of the raw (unrendered) HTML
into the observations detectors need:

  - page identity (title, canonical, meta, lang)
  - heading outline
  - links, with a region label (main / nav / header / footer / aside)
  - JSON-LD blocks (parsed, with parse errors recorded rather than swallowed)
  - main text vs. chrome text vs. promotional text
  - client-side-rendering indicators (empty app roots, script weight)
  - interaction gates (forms, selects, location/context pickers)

Everything here reads HTML exactly as a lightweight crawler would see it,
which is the point: the audit measures what a non-rendering machine reader
can actually obtain.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import textutil as tu

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

SKIP_TEXT_TAGS = {"script", "style", "template", "svg", "canvas", "noscript"}

CHROME_TAGS = {"nav", "header", "footer", "aside"}

# Text nodes on either side of these tags are separate words, never one word.
PAD_TAGS = {"p", "div", "li", "section", "article", "h1", "h2", "h3", "h4", "h5",
            "h6", "td", "th", "tr", "br", "blockquote", "figcaption", "dd", "dt",
            "pre", "main", "nav", "header", "footer", "aside", "ul", "ol", "table"}

BLOCK_TAGS = {
    "p", "div", "li", "section", "article", "h1", "h2", "h3", "h4", "h5",
    "h6", "td", "th", "blockquote", "figcaption", "dd", "dt", "pre", "main",
    "span",
}

CHROME_CLASS_RE = re.compile(
    r"(?:^|[\s_-])(nav|navbar|menu|header|footer|breadcrumb|sidebar|"
    r"topbar|subnav|megamenu|cookie|drawer)(?:$|[\s_-])", re.IGNORECASE)

PROMO_CLASS_RE = re.compile(
    r"(?:^|[\s_-])(promo|promotion|banner|advert|advertisement|ads?|"
    r"sponsor|offer|deal|carousel|newsletter|popup|modal|marketing|"
    r"upsell|cta-banner)(?:$|[\s_-])", re.IGNORECASE)

# Containers whose content a visitor must reveal by interacting, and which some
# extraction pipelines drop because of their hidden-state attributes.
COLLAPSED_CLASS_RE = re.compile(
    r"(?:^|[\s_-])(accordion[-_]?(?:content|body|panel)?|collaps(?:e|ible)[-_]?(?:content|body)?|"
    r"tab[-_]?pane|tabpanel|toggle[-_]?content|expandable[-_]?content|faq[-_]?answer|"
    r"reveal[-_]?content|read[-_]?more[-_]?content)(?:$|[\s_-])", re.IGNORECASE)

# Never counted as hidden *content* — these are chrome, not the page's substance.
NOT_CONTENT_CLASS_RE = re.compile(
    r"(?:^|[\s_-])(cookie|consent|gdpr|nav|navbar|menu|megamenu|drawer|offcanvas|"
    r"search[-_]?overlay|modal[-_]?backdrop|dropdown|tooltip|skip[-_]?link)(?:$|[\s_-])",
    re.IGNORECASE)

APP_ROOT_IDS = {"root", "app", "__next", "__nuxt", "app-root", "main-app",
                "react-root", "ember-app", "q-app"}

LOCATION_HINT_RE = re.compile(
    r"(select\s+(?:your\s+)?(?:city|location|store|region|area|branch)|"
    r"change\s+(?:city|location|store|address)|choose\s+(?:city|location|store)|"
    r"deliver\s+to|delivery\s+location|enter\s+(?:your\s+)?(?:pincode|pin code|zip|postcode|postal code)|"
    r"set\s+(?:your\s+)?location|nearest\s+store|pick\s+(?:a\s+)?(?:city|store))",
    re.IGNORECASE)

LANG_SWITCH_RE = re.compile(
    r"(language|idioma|langue|sprache|currency|country/region)", re.IGNORECASE)

CTA_TEXT_RE = re.compile(
    r"\b(buy|shop|order|book|start|get started|sign ?up|subscribe|"
    r"try|download|contact|request|demo|add to cart|apply|register|"
    r"enrol|enroll|checkout|donate|join)\b", re.IGNORECASE)


@dataclass
class Link:
    href: str
    text: str
    rel: str = ""
    region: str = "main"
    internal: bool = False
    has_img: bool = False
    img_alt: str = ""

    @property
    def label(self) -> str:
        return self.text or self.img_alt


@dataclass
class PageDoc:
    url: str
    final_url: str = ""
    status: int = 0
    headers: dict = field(default_factory=dict)
    depth: int = 0
    source: str = "seed"           # seed | sitemap | link
    redirect_chain: list = field(default_factory=list)
    fetch_error: str = ""

    title: str = ""
    lang: str = ""
    canonical: str = ""
    link_rels: list = field(default_factory=list)      # [(rel, absolute href)]
    meta: dict = field(default_factory=dict)          # name/property -> content
    headings: list = field(default_factory=list)      # [(level, text)]
    links: list = field(default_factory=list)         # [Link]
    jsonld: list = field(default_factory=list)        # parsed objects
    jsonld_errors: list = field(default_factory=list)
    microdata_types: list = field(default_factory=list)
    images: list = field(default_factory=list)        # [(src, alt)]
    time_elements: list = field(default_factory=list)  # [(datetime, text)]

    text_main: str = ""
    text_chrome: str = ""
    text_promo: str = ""
    text_hidden: str = ""                              # inside collapsed containers
    hidden_containers: list = field(default_factory=list)
    blocks: list = field(default_factory=list)        # normalised block texts
    noscript_text: str = ""

    html_bytes: int = 0
    script_bytes: int = 0
    inline_script_bytes: int = 0
    script_tags: int = 0
    empty_app_root: bool = False
    app_root_id: str = ""

    forms: int = 0
    selects: list = field(default_factory=list)       # [(name, n_options)]
    buttons: list = field(default_factory=list)       # button/CTA texts
    location_gate_hits: list = field(default_factory=list)

    # ---- derived helpers -------------------------------------------------
    @property
    def path(self) -> str:
        return urlparse(self.final_url or self.url).path or "/"

    @property
    def words_main(self) -> int:
        return tu.word_count(self.text_main)

    @property
    def regions_unreliable(self) -> bool:
        """True when main/chrome separation cannot be trusted on this page.

        Region detection needs either semantic landmarks (<main>, <nav>) or
        readable class names. Sites using hashed class names give neither, and
        every link then counts as main-region content. Rather than guess, the
        detectors that depend on that separation skip the page and say so.
        """
        return not self.text_chrome.strip() and len(self.links) > 25

    @property
    def words_hidden(self) -> int:
        return tu.word_count(self.text_hidden)

    @property
    def words_visible_main(self) -> int:
        """Main-region words a visitor sees without interacting."""
        return max(0, self.words_main - self.words_hidden)

    @property
    def words_all(self) -> int:
        return tu.word_count(self.text_main) + tu.word_count(self.text_chrome)

    @property
    def h1s(self) -> list:
        return [t for lvl, t in self.headings if lvl == 1 and t.strip()]

    @property
    def internal_links(self) -> list:
        return [l for l in self.links if l.internal]

    @property
    def main_internal_links(self) -> list:
        return [l for l in self.links if l.internal and l.region == "main"]

    @property
    def link_text_chars(self) -> int:
        return sum(len(l.text) for l in self.links)

    @property
    def is_html(self) -> bool:
        ct = (self.headers.get("content-type") or "").lower()
        return "html" in ct or (not ct and bool(self.title or self.text_main))

    def meta_get(self, *names) -> str:
        for n in names:
            v = self.meta.get(n.lower())
            if v:
                return v
        return ""

    def robots_directives(self) -> list:
        vals = []
        for key in ("robots", "googlebot"):
            v = self.meta.get(key)
            if v:
                vals.extend(p.strip().lower() for p in v.split(","))
        xr = self.headers.get("x-robots-tag")
        if xr:
            vals.extend(p.strip().lower() for p in xr.split(","))
        return vals

    def jsonld_types(self) -> list:
        out = []
        for node in self.jsonld:
            t = node.get("@type")
            if isinstance(t, list):
                out.extend(str(x) for x in t)
            elif t:
                out.append(str(t))
        return out

    def jsonld_nodes_of(self, *types) -> list:
        want = {t.lower() for t in types}
        out = []
        for node in self.jsonld:
            t = node.get("@type")
            tl = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
            if any(str(x).lower() in want for x in tl):
                out.append(node)
        return out


class _Extractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.doc = PageDoc(url=base_url)
        self.stack: list[tuple[str, dict]] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._heading: tuple[int, list[str]] | None = None
        self._anchor: dict | None = None
        self._script_type = None
        self._script_buf: list[str] = []
        self._noscript_buf: list[str] = []
        self._block_buf: list[str] = []
        self._select: tuple[str, int] | None = None
        self._button_buf: list[str] | None = None
        self._time_attr: str | None = None
        self._time_buf: list[str] = []
        self._app_root_stack: list[tuple[str, int]] = []
        self._app_root_text: dict[str, int] = {}

    # ---- region helpers --------------------------------------------------
    def _region(self) -> str:
        for tag, attrs in reversed(self.stack):
            if tag in ("main", "article"):
                return "main"
            if tag in CHROME_TAGS:
                return tag if tag != "aside" else "aside"
            cls = f"{attrs.get('class', '')} {attrs.get('id', '')}"
            if cls.strip() and CHROME_CLASS_RE.search(cls):
                return "nav"
        return "main"

    def _hidden_container(self):
        """Return a description of the nearest collapsed container, if any."""
        for tag, attrs in reversed(self.stack):
            cls = f"{attrs.get('class', '')} {attrs.get('id', '')}"
            if cls.strip() and NOT_CONTENT_CLASS_RE.search(cls):
                return None                       # chrome, not page substance
            if tag == "details" and "open" not in attrs:
                return "<details> without the open attribute"
            if "hidden" in attrs:
                return f"<{tag} hidden>"
            if (attrs.get("aria-hidden") or "").lower() == "true":
                return f"<{tag} aria-hidden=\"true\">"
            if cls.strip() and COLLAPSED_CLASS_RE.search(cls):
                return f"<{tag} class=\"{tu.truncate(attrs.get('class', ''), 40)}\">"
        return None

    def _in_promo(self) -> bool:
        for tag, attrs in reversed(self.stack):
            cls = f"{attrs.get('class', '')} {attrs.get('id', '')}"
            if cls.strip() and PROMO_CLASS_RE.search(cls):
                return True
        return False

    def _skipping(self) -> bool:
        return any(t in SKIP_TEXT_TAGS for t, _ in self.stack)

    # ---- parser callbacks ------------------------------------------------
    def _pad(self):
        """Insert a separator so adjacent block texts do not fuse into one word."""
        if self.doc.text_main and not self.doc.text_main.endswith(" "):
            self.doc.text_main += " "
        if self.doc.text_chrome and not self.doc.text_chrome.endswith(" "):
            self.doc.text_chrome += " "

    def handle_starttag(self, tag, attrs):
        d = {k.lower(): (v or "") for k, v in attrs}
        if tag in PAD_TAGS:
            self._pad()
        if tag in VOID_TAGS:
            self._handle_void(tag, d)
            return
        # Implicit close for repeated inline-ish blocks.
        if tag in ("p", "li", "option", "tr", "td", "th") and self.stack and self.stack[-1][0] == tag:
            self.handle_endtag(tag)
        self.stack.append((tag, d))

        if tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_block()
            self._heading = (int(tag[1]), [])
        elif tag == "a":
            self._anchor = {"href": d.get("href", ""), "rel": d.get("rel", ""),
                            "text": [], "has_img": False, "img_alt": "",
                            "region": self._region()}
        elif tag == "script":
            self._script_type = (d.get("type") or "").lower()
            self.doc.script_tags += 1
            if d.get("src"):
                self.doc.script_bytes += 4096  # nominal weight for externals
            self._script_buf = []
        elif tag == "noscript":
            self._noscript_buf = []
        elif tag == "form":
            self.doc.forms += 1
        elif tag == "select":
            self._select = (d.get("name") or d.get("id") or "", 0)
        elif tag == "button":
            self._button_buf = []
        elif tag == "time":
            self._time_attr = d.get("datetime", "")
            self._time_buf = []
        elif tag in BLOCK_TAGS:
            self._flush_block()

        el_id = (d.get("id") or "").lower()
        if el_id in APP_ROOT_IDS or (d.get("class") or "").lower() in APP_ROOT_IDS:
            self._app_root_stack.append((el_id or "app", len(self.stack)))
            self._app_root_text.setdefault(el_id or "app", 0)

    def _handle_void(self, tag, d):
        if tag == "meta":
            key = (d.get("name") or d.get("property") or d.get("itemprop")
                   or d.get("http-equiv") or "").lower()
            if key:
                self.doc.meta.setdefault(key, d.get("content", ""))
        elif tag == "link":
            rel = (d.get("rel") or "").lower()
            href = d.get("href", "")
            if href:
                try:
                    self.doc.link_rels.append((rel, urljoin(self.base_url, href)))
                except ValueError:
                    pass
            if "canonical" in rel and href and not self.doc.canonical:
                self.doc.canonical = urljoin(self.base_url, href)
        elif tag == "img":
            src = d.get("src") or d.get("data-src") or ""
            alt = d.get("alt", "")
            self.doc.images.append((src, alt))
            if self._anchor is not None:
                self._anchor["has_img"] = True
                if alt and not self._anchor["img_alt"]:
                    self._anchor["img_alt"] = tu.normalize_ws(alt)
        elif tag == "input":
            itype = (d.get("type") or "text").lower()
            if itype in ("submit", "button"):
                val = tu.normalize_ws(d.get("value", ""))
                if val:
                    self.doc.buttons.append(val)
            placeholder = d.get("placeholder", "")
            if placeholder and LOCATION_HINT_RE.search(placeholder):
                self.doc.location_gate_hits.append(tu.normalize_ws(placeholder))

    def handle_endtag(self, tag):
        if tag in PAD_TAGS:
            self._pad()
        if tag in VOID_TAGS:
            return
        # Pop until we find the matching open tag (tolerate malformed markup).
        idx = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                idx = i
                break
        if idx is None:
            return

        if tag == "title":
            self._in_title = False
            self.doc.title = tu.normalize_ws("".join(self._title_parts))
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._heading:
            lvl, parts = self._heading
            self.doc.headings.append((lvl, tu.normalize_ws("".join(parts))))
            self._heading = None
        elif tag == "a" and self._anchor is not None:
            self._finish_anchor()
        elif tag == "script":
            body = "".join(self._script_buf)
            self.doc.inline_script_bytes += len(body)
            self.doc.script_bytes += len(body)
            if self._script_type in ("application/ld+json", "application/json+ld"):
                self._consume_jsonld(body)
            self._script_buf = []
            self._script_type = None
        elif tag == "noscript":
            self.doc.noscript_text += " " + tu.normalize_ws("".join(self._noscript_buf))
            self._noscript_buf = []
        elif tag == "select" and self._select is not None:
            self.doc.selects.append(self._select)
            self._select = None
        elif tag == "button" and self._button_buf is not None:
            txt = tu.normalize_ws("".join(self._button_buf))
            if txt:
                self.doc.buttons.append(txt)
            self._button_buf = None
        elif tag == "time":
            self.doc.time_elements.append(
                (self._time_attr or "", tu.normalize_ws("".join(self._time_buf))))
            self._time_attr = None
            self._time_buf = []
        elif tag in BLOCK_TAGS:
            self._flush_block()

        while self._app_root_stack and self._app_root_stack[-1][1] > idx:
            self._app_root_stack.pop()
        del self.stack[idx:]

    def _finish_anchor(self):
        a = self._anchor
        self._anchor = None
        href = (a["href"] or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            return
        try:
            abs_url = urljoin(self.base_url, href)
        except ValueError:
            return
        if urlparse(abs_url).scheme not in ("http", "https"):
            return
        text = tu.normalize_ws("".join(a["text"]))
        self.doc.links.append(Link(
            href=abs_url, text=text, rel=a["rel"], region=a["region"],
            has_img=a["has_img"], img_alt=a["img_alt"],
        ))

    def _consume_jsonld(self, body: str):
        body = body.strip()
        if not body:
            return
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            self.doc.jsonld_errors.append(f"{exc.msg} (line {exc.lineno}, col {exc.colno})")
            return
        for node in _flatten_jsonld(data):
            self.doc.jsonld.append(node)

    def handle_data(self, data):
        if not data:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._script_type is not None:
            self._script_buf.append(data)
            return
        top = [t for t, _ in self.stack]
        if "noscript" in top:
            self._noscript_buf.append(data)
            return
        if self._skipping():
            return
        if self._select is not None and "option" in top:
            name, n = self._select
            self._select = (name, n + 1)
        if self._button_buf is not None:
            self._button_buf.append(data)
        if self._time_attr is not None:
            self._time_buf.append(data)
        if self._heading is not None:
            self._heading[1].append(data)
        if self._anchor is not None:
            self._anchor["text"].append(data)

        text = data
        if not text.strip():
            return
        region = self._region()
        if self._in_promo():
            self.doc.text_promo += text
        if region == "main":
            container = self._hidden_container()
            if container:
                self.doc.text_hidden += text
                if container not in self.doc.hidden_containers:
                    self.doc.hidden_containers.append(container)
            self.doc.text_main += text
            self._block_buf.append(text)
            for _id, _ in self._app_root_stack:
                self._app_root_text[_id] = self._app_root_text.get(_id, 0) + len(text.strip())
        else:
            self.doc.text_chrome += text

        if LOCATION_HINT_RE.search(text):
            hit = tu.truncate(text, 120)
            if hit not in self.doc.location_gate_hits:
                self.doc.location_gate_hits.append(hit)

    def _flush_block(self):
        if not self._block_buf:
            return
        txt = tu.normalize_ws("".join(self._block_buf))
        self._block_buf = []
        if tu.word_count(txt) >= 5:
            self.doc.blocks.append(txt)

    def close(self):  # noqa: D102
        super().close()
        self._flush_block()


def _flatten_jsonld(data) -> list:
    """Flatten @graph structures and lists into a list of dict nodes."""
    out = []
    if isinstance(data, list):
        for item in data:
            out.extend(_flatten_jsonld(item))
    elif isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            base = {k: v for k, v in data.items() if k != "@graph"}
            for item in data["@graph"]:
                out.extend(_flatten_jsonld(item))
            if base.get("@type"):
                out.append(base)
        else:
            out.append(data)
    return out


def parse_html(url: str, html: str, headers: dict | None = None,
               status: int = 200, final_url: str = "") -> PageDoc:
    """Parse raw HTML into a PageDoc. Never raises on malformed markup."""
    base = final_url or url
    ex = _Extractor(base)
    try:
        ex.feed(html or "")
        ex.close()
    except Exception:  # malformed HTML must not abort an audit
        pass
    doc = ex.doc
    doc.url = url
    doc.final_url = final_url or url
    doc.status = status
    doc.headers = {k.lower(): v for k, v in (headers or {}).items()}
    doc.html_bytes = len(html or "")
    doc.lang = _extract_lang(html)
    doc.microdata_types = _extract_microdata_types(html)
    doc.text_main = tu.normalize_ws(doc.text_main)
    doc.text_chrome = tu.normalize_ws(doc.text_chrome)
    doc.text_promo = tu.normalize_ws(doc.text_promo)
    doc.text_hidden = tu.normalize_ws(doc.text_hidden)
    doc.noscript_text = tu.normalize_ws(doc.noscript_text)

    host = urlparse(doc.final_url).netloc.lower()
    for link in doc.links:
        link.internal = urlparse(link.href).netloc.lower() == host

    for root_id, chars in ex._app_root_text.items():
        if chars < 40:
            doc.empty_app_root = True
            doc.app_root_id = root_id
            break
    if not doc.app_root_id and ex._app_root_text:
        doc.app_root_id = next(iter(ex._app_root_text))
    return doc


_ITEMTYPE_RE = re.compile(
    r"itemtype\s*=\s*[\"']?https?://schema\.org/([A-Za-z]+)", re.IGNORECASE)


def _extract_microdata_types(html: str) -> list:
    return list(dict.fromkeys(m.group(1) for m in _ITEMTYPE_RE.finditer(html or "")))


_LANG_RE = re.compile(r"<html[^>]*\blang\s*=\s*[\"']?([A-Za-z\-]+)", re.IGNORECASE)


def _extract_lang(html: str) -> str:
    m = _LANG_RE.search(html or "")
    return m.group(1).lower() if m else ""


def visible_price_strings(doc: PageDoc) -> list:
    return tu.find_prices(doc.text_main)


def has_cta(doc: PageDoc) -> bool:
    for b in doc.buttons:
        if CTA_TEXT_RE.search(b):
            return True
    for l in doc.links:
        if l.region == "main" and CTA_TEXT_RE.search(l.text or ""):
            return True
    return False


def rendering_classification(doc: PageDoc) -> str:
    """How the page's content reaches a reader, judged from the served bytes only.

    Never claims to know the rendered state: `likely_client_rendered` means the
    served HTML shows the signature of client-side assembly, not that a browser
    was run to confirm it. See `interaction_required` for content that is
    present but gated behind a control.
    """
    if doc.words_visible_main >= 120:
        return "server_rendered"
    if doc.empty_app_root or (doc.html_bytes and doc.script_bytes / doc.html_bytes >= 0.4
                              and doc.script_tags >= 3):
        return "likely_client_rendered"
    if doc.words_hidden >= 60 and doc.words_hidden >= 2 * max(1, doc.words_visible_main):
        return "interaction_required"
    return "server_rendered_thin"


def context_gate_signals(doc: PageDoc) -> list:
    """Signals that page content depends on an unresolved user context."""
    hits = list(doc.location_gate_hits)
    for name, n_opts in doc.selects:
        low = (name or "").lower()
        if any(k in low for k in ("city", "location", "store", "region",
                                  "branch", "pincode", "zip", "area")):
            hits.append(f"<select name=\"{name}\"> with {n_opts} options")
    for b in doc.buttons:
        if LOCATION_HINT_RE.search(b):
            hits.append(f"control: {tu.truncate(b, 80)}")
    # Language / currency switchers alone are not a context gate.
    return [h for h in hits if not (LANG_SWITCH_RE.search(h) and not LOCATION_HINT_RE.search(h))]
