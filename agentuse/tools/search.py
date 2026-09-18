"""Multi-provider search — the agent tries every live route and merges results."""
from typing import Callable
from urllib.parse import quote_plus

from . import net


def _clean(s: str, n: int = 300) -> str:
    import re
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()[:n]


async def search_duckduckgo(q: str, limit: int = 8) -> list[dict]:
    from bs4 import BeautifulSoup
    r = await net.fetch(f"https://lite.duckduckgo.com/lite/?q={quote_plus(q)}")
    if not r.get("ok"):
        r = await net.fetch(f"https://html.duckduckgo.com/html/?q={quote_plus(q)}")
    if not r.get("ok"):
        return []
    soup = BeautifulSoup(r["text"], "lxml")
    out = []
    for a in soup.select("a.result-link"):
        out.append({"title": _clean(a.get_text(), 160),
                    "url": a.get("href", ""),
                    "snippet": "", "source": "duckduckgo"})
    for snip in soup.select("td.result-snippet"):
        if out and len(out) > len([o for o in out if o["snippet"]]):
            idx = len([o for o in out if o["snippet"]])
            if idx < len(out):
                out[idx]["snippet"] = _clean(snip.get_text())
    if not out:
        for res in soup.select("div.result")[:limit]:
            a = res.select_one("a.result__a")
            s = res.select_one(".result__snippet")
            if a:
                out.append({"title": _clean(a.get_text(), 160), "url": a.get("href", ""),
                            "snippet": _clean(s.get_text()) if s else "", "source": "duckduckgo"})
    return [o for o in out if o["url"]][:limit]


async def search_bing(q: str, limit: int = 8) -> list[dict]:
    from bs4 import BeautifulSoup
    r = await net.fetch(f"https://www.bing.com/search?q={quote_plus(q)}&count={limit}")
    if not r.get("ok"):
        return []
    soup = BeautifulSoup(r["text"], "lxml")
    out = []
    for li in soup.select("li.b_algo")[:limit]:
        a = li.select_one("h2 a")
        p = li.select_one("p, .b_caption p")
        if a and a.get("href"):
            out.append({"title": _clean(a.get_text(), 160), "url": a["href"],
                        "snippet": _clean(p.get_text()) if p else "", "source": "bing"})
    return out


async def search_wikipedia(q: str, limit: int = 6) -> list[dict]:
    import json as _json
    r = await net.fetch(
        "https://en.wikipedia.org/w/api.php?action=opensearch&format=json&limit="
        f"{limit}&search={quote_plus(q)}")
    if not r.get("ok"):
        return []
    try:
        data = _json.loads(r["text"])
        titles, urls = data[1], data[3]
    except Exception:
        return []
    out = []
    for t, u in list(zip(titles, urls))[:limit]:
        s = await net.fetch("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote_plus(t))
        snippet = ""
        if s.get("ok"):
            try:
                snippet = _clean(_json.loads(s["text"]).get("extract", ""))
            except Exception:
                pass
        out.append({"title": t, "url": u, "snippet": snippet or "(wikipedia entry)",
                    "source": "wikipedia"})
    return out


async def search_hackernews(q: str, limit: int = 6) -> list[dict]:
    import json as _json
    r = await net.fetch(
        f"https://hn.algolia.com/api/v1/search?query={quote_plus(q)}&hitsPerPage={limit}")
    if not r.get("ok"):
        return []
    try:
        hits = _json.loads(r["text"]).get("hits", [])
    except Exception:
        return []
    return [{"title": h.get("title") or h.get("story_title") or "(comment)",
             "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
             "snippet": _clean(h.get("story_text") or h.get("comment_text") or ""),
             "source": "hackernews"}
            for h in hits[:limit] if (h.get("title") or h.get("story_title"))]


async def search_stackexchange(q: str, limit: int = 6) -> list[dict]:
    import json as _json
    r = await net.fetch(
        "https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance"
        f"&site=stackoverflow&q={quote_plus(q)}&pagesize={limit}")
    if not r.get("ok"):
        return []
    try:
        items = _json.loads(r["text"]).get("items", [])
    except Exception:
        return []
    return [{"title": _clean(i.get("title", ""), 160),
             "url": i.get("link", ""),
             "snippet": f"score {i.get('score', 0)} · {i.get('answer_count', 0)} answers · "
                        f"views {i.get('view_count', 0)}",
             "source": "stackoverflow"}
            for i in items[:limit]]


async def search_github(q: str, limit: int = 6) -> list[dict]:
    from . import github
    repos = await github.search_repos(q, limit=limit)
    return [{"title": f"{r['full_name']}  ★{r['stars']}",
             "url": r["url"],
             "snippet": _clean(r.get("desc") or "", 260),
             "source": "github"}
            for r in repos]


async def search_arxiv(q: str, limit: int = 5) -> list[dict]:
    from bs4 import BeautifulSoup
    r = await net.fetch(
        f"https://export.arxiv.org/api/query?search_query=all:{quote_plus(q)}&max_results={limit}")
    if not r.get("ok"):
        r = await net.fetch(f"https://arxiv.org/api/query?search_query=all:{quote_plus(q)}&max_results={limit}")
    if not r.get("ok"):
        return []
    soup = BeautifulSoup(r["text"], "lxml-xml")
    out = []
    for e in soup.find_all("entry")[:limit]:
        t = e.find("title")
        s = e.find("summary")
        i = e.find("id")
        if t:
            out.append({"title": _clean(t.get_text(), 200),
                        "url": _clean(i.get_text()) if i else "https://arxiv.org",
                        "snippet": _clean(s.get_text(), 280) if s else "",
                        "source": "arxiv"})
    return out


# Ordered fallback chain. The NetProbe knows which are live in this environment.
PROVIDERS: list[tuple[str, str, Callable]] = [
    ("duckduckgo", "DuckDuckGo", search_duckduckgo),
    ("bing", "Bing", search_bing),
    ("wikipedia", "Wikipedia", search_wikipedia),
    ("hackernews", "HackerNews", search_hackernews),
    ("stackexchange", "StackOverflow", search_stackexchange),
    ("arxiv", "arXiv", search_arxiv),
    ("github", "GitHub", search_github),
]

# search provider id → NetProbe route id
ROUTE_FOR: dict[str, str] = {
    "duckduckgo": "ddg-lite",
    "bing": "bing",
    "wikipedia": "wikipedia",
    "hackernews": "hackernews",
    "stackexchange": "stackexchange",
    "arxiv": "arxiv",
    "github": "github-api",
}


async def web_search(q: str, limit: int = 8, providers: list[str] | None = None,
                     on_attempt: Callable[[str, str], None] | None = None) -> dict:
    """Run through live providers until enough results merge. Reports every attempt."""
    results, attempts = [], []
    live = net.live_route_ids()
    probed = any(r.status != "unknown" for r in net.ROUTES)
    for pid, label, fn in PROVIDERS:
        if providers and pid not in providers:
            continue
        route_id = ROUTE_FOR.get(pid)
        if probed and live and route_id and route_id not in live:
            attempts.append({"provider": label, "count": 0, "skipped": "blocked"})
            if on_attempt:
                on_attempt(pid, f"{label} skipped (route blocked)")
            continue
        if on_attempt:
            on_attempt(pid, label)
        try:
            got = await fn(q, limit=limit)
        except Exception as e:
            got = []
            if on_attempt:
                on_attempt(pid, f"{label} failed: {type(e).__name__}")
        attempts.append({"provider": label, "count": len(got)})
        seen = {r["url"] for r in results}
        for item in got:
            if item["url"] and item["url"] not in seen:
                seen.add(item["url"])
                results.append(item)
        if len(results) >= limit:
            break
    return {"query": q, "results": results[:limit], "attempts": attempts}
