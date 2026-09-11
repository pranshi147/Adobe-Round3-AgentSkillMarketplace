"""Read-only, budgeted HTTP access.

Hard guarantees enforced here (not merely documented):

  * Only GET and HEAD are ever issued. Any other method raises.
  * Every request has a connect/read timeout and a response size cap.
  * A minimum interval between requests to the same host is enforced.
  * robots.txt is fetched first and consulted for every URL.
  * A global deadline aborts fetching so the audit stays inside its budget.

Nothing in this module writes to, or submits anything to, the audited site.
"""

from __future__ import annotations

import gzip
import io
import socket
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

DEFAULT_UA = ("BrandEvidenceAuditor/1.0 (read-only site audit; "
              "respects robots.txt; contact: site owner)")

TEXTUAL_TYPES = ("text/html", "application/xhtml", "text/xml",
                 "application/xml", "text/plain", "application/json",
                 "application/ld+json", "application/rss")


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status: int = 0
    headers: dict = field(default_factory=dict)
    body: str = ""
    error: str = ""
    elapsed: float = 0.0
    redirect_chain: list = field(default_factory=list)
    blocked_by_robots: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.error

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") or "").split(";")[0].strip().lower()


class _RedirectRecorder(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.chain: list = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append({"from": req.full_url, "status": code, "to": newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    def __init__(self, user_agent: str = DEFAULT_UA, timeout: float = 8.0,
                 max_bytes: int = 1_500_000, min_interval: float = 0.15,
                 deadline: float | None = None, max_redirects: int = 6):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_decompressed = max_bytes * 8
        self.min_interval = min_interval
        self.deadline = deadline
        self.max_redirects = max_redirects
        self._lock = threading.Lock()
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, "RobotsInfo"] = {}
        self.requests_made = 0
        self.bytes_downloaded = 0

    # -- budget ---------------------------------------------------------
    def out_of_time(self) -> bool:
        return self.deadline is not None and time.time() >= self.deadline

    def remaining(self) -> float:
        if self.deadline is None:
            return float("inf")
        return max(0.0, self.deadline - time.time())

    def _throttle(self, host: str):
        with self._lock:
            last = self._last_hit.get(host, 0.0)
            wait = self.min_interval - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            self._last_hit[host] = time.time()

    # -- core -----------------------------------------------------------
    def fetch(self, url: str, method: str = "GET",
              respect_robots: bool = True) -> FetchResult:
        method = method.upper()
        if method not in ("GET", "HEAD"):
            raise ValueError(f"read-only auditor: refusing method {method!r}")

        res = FetchResult(url=url, final_url=url)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            res.error = f"unsupported scheme: {parsed.scheme or 'none'}"
            return res

        if respect_robots:
            robots = self.robots_for(url)
            if not robots.allowed(url, self.user_agent):
                res.blocked_by_robots = True
                res.error = "blocked by robots.txt"
                return res

        if self.out_of_time():
            res.error = "audit time budget exhausted"
            return res

        self._throttle(parsed.netloc.lower())
        recorder = _RedirectRecorder()
        recorder.max_redirections = self.max_redirects
        opener = urllib.request.build_opener(recorder)
        opener.addheaders = []
        req = urllib.request.Request(url, method=method, headers={
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en",
            "Accept-Encoding": "gzip",
        })

        started = time.time()
        timeout = min(self.timeout, max(1.0, self.remaining()))
        try:
            with opener.open(req, timeout=timeout) as resp:
                res.status = resp.status
                res.headers = {k.lower(): v for k, v in resp.headers.items()}
                res.final_url = resp.geturl()
                if method == "GET":
                    res.body, res.truncated = self._read_body(resp, res.headers)
        except urllib.error.HTTPError as exc:
            res.status = exc.code
            res.headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
            res.final_url = exc.url if hasattr(exc, "url") else url
            try:
                if method == "GET":
                    res.body, res.truncated = self._read_body(exc, res.headers)
            except Exception:
                pass
        except urllib.error.URLError as exc:
            res.error = f"network error: {getattr(exc, 'reason', exc)}"
        except socket.timeout:
            res.error = "timeout"
        except Exception as exc:  # never let one bad URL kill an audit
            res.error = f"{type(exc).__name__}: {exc}"

        res.elapsed = time.time() - started
        res.redirect_chain = recorder.chain
        with self._lock:
            self.requests_made += 1
            self.bytes_downloaded += len(res.body or "")
        return res

    def _read_body(self, resp, headers) -> tuple:
        ctype = (headers.get("content-type") or "").lower()
        if ctype and not any(t in ctype for t in TEXTUAL_TYPES):
            return "", False
        raw = resp.read(self.max_bytes + 1)
        truncated = len(raw) > self.max_bytes
        raw = raw[: self.max_bytes]
        if (headers.get("content-encoding") or "").lower() == "gzip":
            # Read the decompressed stream in bounded chunks: a small compressed
            # response can expand without limit, and an unbounded .read() here
            # is the one place this auditor could be made to hang.
            try:
                stream = gzip.GzipFile(fileobj=io.BytesIO(raw))
                out, total = [], 0
                while total < self.max_decompressed:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    out.append(chunk)
                    total += len(chunk)
                if total >= self.max_decompressed:
                    truncated = True
                raw = b"".join(out)[: self.max_decompressed]
            except Exception:
                pass
        charset = "utf-8"
        if "charset=" in ctype:
            charset = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        return text, truncated

    # -- robots ----------------------------------------------------------
    def robots_for(self, url: str) -> "RobotsInfo":
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            cached = self._robots.get(origin)
        if cached is not None:
            return cached
        info = self._load_robots(origin)
        with self._lock:
            self._robots[origin] = info
        return info

    def _load_robots(self, origin: str) -> "RobotsInfo":
        url = origin + "/robots.txt"
        res = self.fetch(url, respect_robots=False)
        return RobotsInfo.from_fetch(origin, res)


class RobotsInfo:
    """Parsed robots.txt plus the raw lines needed as finding evidence."""

    def __init__(self, origin: str, status: int = 0, text: str = "",
                 error: str = "", present: bool = False, unknown: bool = False):
        self.origin = origin
        self.status = status
        self.text = text
        self.error = error
        self.present = present
        self.unknown = unknown          # fetch failed in an ambiguous way
        self.sitemaps: list = []
        self.disallow_lines: list = []  # [(user_agent, raw_line, path)]
        self.crawl_delay = None
        self._parser = urllib.robotparser.RobotFileParser()
        self._parser.set_url(origin + "/robots.txt")
        if present and text:
            try:
                self._parser.parse(text.splitlines())
            except Exception:
                pass
            self._scan_lines(text)
        else:
            self._parser.parse([])

    @classmethod
    def from_fetch(cls, origin: str, res: FetchResult) -> "RobotsInfo":
        if res.ok and res.body.strip():
            return cls(origin, res.status, res.body, present=True)
        if res.status in (404, 410) or (res.ok and not res.body.strip()):
            return cls(origin, res.status, present=False)
        # 5xx / network failure: treat as unknown -> crawl only what the user
        # explicitly asked for (handled by the crawler), never broaden.
        return cls(origin, res.status, error=res.error, present=False, unknown=True)

    def _scan_lines(self, text: str):
        agent = "*"
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key == "user-agent":
                agent = val or "*"
            elif key == "disallow" and val:
                self.disallow_lines.append((agent, raw.strip(), val))
            elif key == "sitemap" and val:
                self.sitemaps.append(val)
            elif key == "crawl-delay":
                try:
                    self.crawl_delay = float(val)
                except ValueError:
                    pass

    def allowed(self, url: str, user_agent: str) -> bool:
        if not self.present:
            return True
        try:
            return bool(self._parser.can_fetch(user_agent, url))
        except Exception:
            return True

    def blocking_rule(self, url: str, user_agent: str):
        """Return the raw Disallow line most likely responsible for a block."""
        if self.allowed(url, user_agent):
            return None
        path = urlparse(url).path or "/"
        best = None
        for agent, raw, val in self.disallow_lines:
            prefix = val.rstrip("*$")
            if path.startswith(prefix):
                if best is None or len(prefix) > len(best[2].rstrip("*$")):
                    best = (agent, raw, val)
        return best
