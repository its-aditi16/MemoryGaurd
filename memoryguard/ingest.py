"""Ingest real content into the agent's memory: any web page URL, or pasted email/text.

Like a typical scraper feeding an agent, it keeps text that is hidden from human readers
(HTML comments, display:none, zero-size or white text) - that is exactly where prompt
injections hide. Each chunk is retained with provenance, scored, and (optionally) flagged
or quarantined immediately ("scan on write").
"""
import ipaddress
import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

import config  # noqa: F401  (loads .env before FETCH_USER_AGENT is read)
import db
from guard.provenance import now_iso, remember
from guard.score import explain, score_memory
from store import get_store

MAX_BYTES = 3_000_000
CHUNK_CHARS = 700
MAX_VISIBLE_CHUNKS = 5
MAX_HIDDEN_CHUNKS = 2
# Some sites (e.g. Wikipedia) require contact details in a bot's User-Agent: set FETCH_USER_AGENT in .env.
USER_AGENT = os.getenv("FETCH_USER_AGENT") or "Mozilla/5.0 (compatible; MemoryGuard-demo/0.1)"

SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(px|em|rem|%)?\s*(;|$)|opacity\s*:\s*0(\.0+)?\s*(;|$)"
    r"|color\s*:\s*(#fff\b|#ffffff\b|white\b)|left\s*:\s*-\d{3,}px|height\s*:\s*0(px)?\s*;.*overflow\s*:\s*hidden",
    re.I,
)


class _PageParser(HTMLParser):
    """Split a page into visible text and text a human reader would not see."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []  # (tag, hidden, skipped)
        self.title, self.description = "", ""
        self.visible: list[str] = []
        self.hidden: list[str] = []
        self._in_title = False
        self._css = ""
        self.hidden_classes: set[str] = set()  # classes a <style> block hides (e.g. .note{display:none})

    def _state(self) -> tuple[bool, bool]:
        return (any(h for _, h, _ in self.stack), any(s for _, _, s in self.stack))

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta" and a.get("name", "").lower() in ("description", "og:description"):
            self.description = self.description or a.get("content", "")
        if tag == "title":
            self._in_title = True
        if tag in VOID_TAGS:
            return
        hidden = ("hidden" in a or a.get("aria-hidden") == "true" or bool(HIDDEN_STYLE.search(a.get("style", "")))
                  or bool(self.hidden_classes & set(a.get("class", "").split())))
        self.stack.append((tag, hidden, tag in SKIP_TAGS))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "style":
            for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", self._css):
                if HIDDEN_STYLE.search(body):
                    self.hidden_classes |= set(re.findall(r"\.([\w-]+)\s*(?=,|$)", selectors.strip()))
            self._css = ""
        for i in range(len(self.stack) - 1, -1, -1):  # tolerate malformed HTML
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        text = data.strip()
        if not text:
            return
        hidden, skipped = self._state()
        if skipped:
            if self.stack and self.stack[-1][0] == "style":
                self._css += data
            return
        if hidden:
            if len(text) > 15:
                self.hidden.append(text)
        else:
            self.visible.append(text)

    def handle_comment(self, data):
        text = data.strip()
        if len(text) > 20 and not text.startswith("[if"):
            self.hidden.append(f"<!-- {text} -->")


def _clean(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def _chunks(text: str, limit: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    out, cur = [], ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if cur and len(cur) + len(s) + 1 > CHUNK_CHARS:
            out.append(cur)
            cur = ""
            if len(out) >= limit:
                break
        cur = f"{cur} {s}".strip()
    if cur and len(out) < limit:
        out.append(cur)
    return out


SAMPLES_DIR = config.PKG_DIR / "demo" / "samples"
MAX_REDIRECTS = 3


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def _check_url(url: str) -> tuple[str, str]:
    """SSRF guard, step 1: scheme, port, policy allowlist, and every DNS answer must be a public IP."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Enter a full http(s):// URL")
    if p.port not in (None, 80, 443):
        raise ValueError("Only standard web ports (80/443) are allowed")
    host = p.hostname.lower()
    allow = [d.lower() for d in config.POLICY["ingest_domain_allowlist"]]
    if allow and not any(host == d or host.endswith("." + d) for d in allow):
        raise ValueError(f"{host} is not on this deployment's ingest allowlist")
    try:
        ips = {info[4][0] for info in socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80))}
    except socket.gaierror:
        raise ValueError(f"Could not resolve {host}")
    if not ips or not all(_is_public_ip(ip) for ip in ips):
        raise ValueError(f"Blocked: {host} points to a private, local or reserved address (SSRF protection)")
    return host, p.scheme


def _local_sample(url: str) -> str | None:
    """The built-in demo pages are read from disk, so no exception for loopback addresses is needed."""
    p = urlparse(url)
    if p.hostname in ("127.0.0.1", "localhost") and p.port == 8000 and p.path.startswith("/samples/"):
        f = (SAMPLES_DIR / Path(p.path).name)
        if f.suffix == ".html" and f.is_file():
            return f.read_text(encoding="utf-8")
        raise ValueError("Unknown sample page")
    return None


def _download(url: str) -> tuple[str, str, str]:
    """SSRF-safe GET: manual redirects (each hop re-checked), connected-peer IP check, streamed size cap."""
    with httpx.Client(follow_redirects=False, timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _check_url(url)
            with client.stream("GET", url) as resp:
                # SSRF guard, step 2: check the IP the socket actually reached (defeats DNS rebinding).
                stream = resp.extensions.get("network_stream")
                peer = stream.get_extra_info("server_addr") if stream else None
                if peer and not _is_public_ip(str(peer[0])):
                    raise ValueError("Blocked: connection went to a private or local address (SSRF protection)")
                if resp.is_redirect:
                    url = urljoin(url, resp.headers.get("location", ""))
                    continue
                if resp.status_code >= 400:
                    raise ValueError(f"The site returned HTTP {resp.status_code} "
                                     "(it may block automated fetches - try paste mode)")
                ctype = resp.headers.get("content-type", "")
                if "html" not in ctype and "text" not in ctype:
                    raise ValueError(f"Not a web page (content-type {ctype or 'unknown'})")
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise ValueError("Page is larger than 3 MB")
                return str(resp.url), ctype, body.decode(resp.encoding or "utf-8", errors="replace")
    raise ValueError(f"Too many redirects (max {MAX_REDIRECTS})")


def fetch_page(url: str) -> dict:
    """Fetch a URL and return {url, title, visible, hidden} (texts, not yet chunked)."""
    html = _local_sample(url)
    if html is not None:
        final_url, ctype = url, "text/html"
    else:
        final_url, ctype, html = _download(url)
    netloc = urlparse(final_url).netloc
    if "html" not in ctype:
        return {"url": final_url, "title": netloc, "visible": html, "hidden": []}
    p = _PageParser()
    p.feed(html)
    visible = _clean("\n".join(p.visible)) or p.description
    return {"url": final_url, "title": _clean(p.title) or netloc, "visible": visible,
            "hidden": [_clean(h) for h in p.hidden]}


def ingest_url(url: str, source_class: str = "web", scan: bool = True) -> dict:
    page = fetch_page(url)
    if not page["visible"] and not page["hidden"]:
        raise ValueError("No readable text on that page (it may be rendered by JavaScript - try paste mode)")
    host = urlparse(page["url"]).netloc
    source_id = f"{source_class}:{host}{urlparse(page['url']).path}"[:120]
    texts = [(f"Web page '{page['title']}' ({page['url']}): {c}", False)
             for c in _chunks(page["visible"], MAX_VISIBLE_CHUNKS)]
    texts += [(f"Hidden content on web page '{page['title']}' ({page['url']}), not visible to human readers: {c}", True)
              for c in _chunks("\n".join(page["hidden"]), MAX_HIDDEN_CHUNKS)]
    result = _retain_and_scan(texts, source_class, source_id, scan, label=page["url"])
    return {**result, "title": page["title"], "url": page["url"], "hidden_snippets": len(page["hidden"])}


def email_sender(text: str) -> str | None:
    """Sender address of a pasted email: the 'From:' line if present, else the first address."""
    from guard.privacy import EMAIL_RE

    m = re.search(r"^\s*From:.*?([\w.+-]+@[\w-]+(?:\.[\w-]+)+)", text, re.I | re.M)
    if m:
        return m.group(1).lower()
    first = EMAIL_RE.search(text)
    return first.group(0).lower() if first else None


def check_sender(text: str) -> None:
    """Policy: only process email from trusted senders (Meta 'Rule of Two' advice), when a list is set."""
    allow = [a.lower() for a in config.POLICY.get("ingest_sender_allowlist", [])]
    if not allow:
        return
    sender = email_sender(text)
    if not sender or not any(sender == a or (a.startswith("@") and sender.endswith(a)) for a in allow):
        raise ValueError(f"Sender {sender or '(unknown)'} is not on this deployment's trusted-sender allowlist")


def ingest_text(text: str, source_class: str = "email", scan: bool = True, title: str = "") -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Paste some text to ingest")
    if source_class == "email":
        check_sender(text)
    n = len(db.query("SELECT id FROM nodes WHERE type = 'source' AND id LIKE ?", (f"src:{source_class}:pasted-%",))) + 1
    source_id = f"{source_class}:pasted-{n}"
    label = title or f"pasted {source_class}"
    texts = [(c, False) for c in _chunks(text, MAX_VISIBLE_CHUNKS)]
    result = _retain_and_scan(texts, source_class, source_id, scan, label=label)
    return {**result, "title": label, "url": None, "hidden_snippets": 0}


def _retain_and_scan(texts: list[tuple[str, bool]], source_class: str, source_id: str, scan: bool, label: str) -> dict:
    from guard import gate

    ids = [remember(t, source_class, source_id, session_id="ingest", event_time=now_iso()) for t, _ in texts]
    store = get_store()
    with ThreadPoolExecutor(max_workers=4) as pool:  # LLM-judge calls run in parallel
        scores = list(pool.map(lambda mid: score_memory(store.get(mid)), ids))

    to_flag = [mid for mid, s in zip(ids, scores) if s["suggested_status"] != "live"]
    top = max((s["score"] for s in scores), default=0.0)
    db.log_event("ingested", f"Ingested {label} as {len(ids)} memor{'y' if len(ids) == 1 else 'ies'} "
                             f"(max suspicion {top:.2f}{', scan on' if scan else ', scan off'})",
                 memory_ids=ids, source_id=source_id)
    if scan and to_flag:
        gate.raise_incident(to_flag)

    out = []
    for (text, hidden), mid, s in zip(texts, ids, scores):
        m = store.get(mid)
        out.append({"id": mid, "preview": text[:220], "hidden": hidden, "score": s["score"],
                    "suggested_status": s["suggested_status"], "status": m.status if m else "quarantined",
                    "why": explain(s)})
    return {"source_id": f"src:{source_id}", "memories": out, "max_score": top, "scanned": scan}
