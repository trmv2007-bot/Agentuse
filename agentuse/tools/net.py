"""Internet control — HTTP engine + readability extraction + live NetProbe.

Every route the agent can use is probed at startup and shown on the SpaceGrid.
Blocked routes (sandbox firewalls etc.) are displayed honestly, never hidden.
"""
import asyncio
import ssl
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .. import config

_client: Optional[httpx.AsyncClient] = None

_SSL_CTX: Optional[ssl.SSLContext] = None


def ssl_context() -> ssl.SSLContext:
    """System-trusting SSL context (works through interception proxies)."""
    global _SSL_CTX
    if _SSL_CTX is None:
        _SSL_CTX = ssl.create_default_context()
        try:
            _SSL_CTX.load_default_certs()
        except Exception:
            pass
    return _SSL_CTX


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers={"User-Agent": config.USER_AGENT,
                     "Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True,
            timeout=config.HTTP_TIMEOUT,
            verify=ssl_context(),
        )
    return _client


async def fetch(url: str, max_bytes: int = config.MAX_BODY_BYTES) -> dict:
    """Raw fetch with metrics. Returns dict with status/text/headers/timing."""
    t0 = time.perf_counter()
    try:
        r = await client().get(url)
        ms = int((time.perf_counter() - t0) * 1000)
        body = r.content[:max_bytes]
        ctype = r.headers.get("content-type", "")
        text = ""
        if "html" in ctype or "xml" in ctype or not ctype:
            text = body.decode(r.encoding or "utf-8", errors="replace")
        else:
            text = body.decode("utf-8", errors="replace")
        return {"ok": True, "status": r.status_code, "url": url,
                "final_url": str(r.url), "content_type": ctype,
                "bytes": len(r.content), "ms": ms, "text": text}
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "status": 0, "url": url, "final_url": url,
                "error": f"{type(e).__name__}: {e}", "ms": ms, "text": ""}


_SKIP_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "header",
              "form", "iframe", "aside", "button")


def extract(readable: dict) -> dict:
    """HTML -> clean readable structure (title, meta, text, links)."""
    import re
    html = readable.get("text", "")
    out = {"url": readable.get("final_url", readable.get("url", "")),
           "status": readable.get("status", 0), "ok": readable.get("ok", False),
           "ms": readable.get("ms", 0), "title": "", "byline": "",
           "text": "", "links": [], "error": readable.get("error")}
    if not readable.get("ok") or not html:
        return out
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        out["title"] = soup.title.string.strip()[:300]
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        out["byline"] = md["content"].strip()[:400]
    for t in _SKIP_TAGS:
        for tag in soup.find_all(t):
            tag.decompose()
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and len(ln) > 1]
    body, last = [], None
    for ln in lines:
        if ln != last:
            body.append(ln)
        last = ln
    out["text"] = "\n".join(body)[:20000]
    if not out["title"]:
        out["title"] = (body[0] if body else out["url"])[:200]
    seen = set()
    for a in soup.find_all("a", href=True)[:60]:
        href = a["href"]
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        if href not in seen:
            seen.add(href)
            out["links"].append({"text": a.get_text(" ", strip=True)[:120], "href": href})
    return out


def bullets_from(text: str, n: int = 6) -> list[str]:
    from .summarize import top_sentences
    return top_sentences(text, n)


# ---------------- NetProbe ----------------

@dataclass
class Route:
    id: str
    label: str
    url: str
    kind: str            # search | data | web | registry
    status: str = "unknown"   # live | blocked | unknown | probing
    ms: int = 0
    detail: str = ""
    last_check: float = 0.0


ROUTES: list[Route] = [
    Route("github-api", "GitHub API", "https://api.github.com/zen", "data"),
    Route("pypi", "PyPI Registry", "https://pypi.org/pypi/pip/json", "registry"),
    Route("npm", "npm Registry", "https://registry.npmjs.org/express", "registry"),
    Route("wikipedia", "Wikipedia API", "https://en.wikipedia.org/api/rest_v1/page/summary/WebSocket", "data"),
    Route("ddg-lite", "DuckDuckGo (lite)", "https://lite.duckduckgo.com/lite/?q=probe", "search"),
    Route("bing", "Bing Search", "https://www.bing.com/search?q=probe", "search"),
    Route("hackernews", "HackerNews (Algolia)", "https://hn.algolia.com/api/v1/search?query=ai&hitsPerPage=1", "search"),
    Route("stackexchange", "StackExchange API", "https://api.stackexchange.com/2.3/info?site=stackoverflow", "data"),
    Route("arxiv", "arXiv Papers", "https://arxiv.org/api/query?search_query=all:ai&max_results=1", "data"),
    Route("openlibrary", "Open Library", "https://openlibrary.org/search.json?q=ai&limit=1", "data"),
    Route("generic-web", "Open Web (example.com)", "https://example.com", "web"),
]


def route_state() -> list[dict]:
    return [{"id": r.id, "label": r.label, "kind": r.kind, "status": r.status,
             "ms": r.ms, "detail": r.detail, "url": r.url,
             "age": int(time.time() - r.last_check) if r.last_check else None}
            for r in ROUTES]


def live_route_ids() -> set[str]:
    return {r.id for r in ROUTES if r.status == "live"}


async def probe_route(r: Route) -> Route:
    r.status = "probing"
    res = await fetch(r.url, max_bytes=200_000)
    r.ms = res.get("ms", 0)
    r.last_check = time.time()
    if res.get("ok") and res.get("status", 0) < 500:
        r.status, r.detail = "live", f"HTTP {res['status']} · {res.get('bytes', 0)} B"
    else:
        r.status = "blocked"
        r.detail = (res.get("error") or f"HTTP {res.get('status')}")[:120]
    return r


async def probe_all() -> list[dict]:
    """Probe every route concurrently."""
    async def one(r: Route) -> Route:
        try:
            return await probe_route(r)
        except Exception as e:
            r.status, r.detail, r.last_check = "blocked", str(e)[:120], time.time()
            return r
    await asyncio.gather(*(one(r) for r in ROUTES))
    return route_state()
