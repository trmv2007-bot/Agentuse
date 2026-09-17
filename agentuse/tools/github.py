"""GitHub intelligence — search repos, details, READMEs, issues.
Uses GH_TOKEN/GITHUB_TOKEN if present (5000 req/h vs 60 anonymous)."""
import base64
import json
from urllib.parse import quote_plus

import httpx

from .. import config
from .net import ssl_context

API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json",
         "User-Agent": config.USER_AGENT,
         "X-GitHub-Api-Version": "2022-11-28"}
    if config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return h


async def _get(path: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT,
                                     follow_redirects=True,
                                     verify=ssl_context()) as c:
            r = await c.get(f"{API}{path}", headers=_headers())
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code,
                    "error": r.json().get("message", r.text[:200]) if r.text else "error"}
        return {"ok": True, "data": r.json()}
    except Exception as e:
        return {"ok": False, "status": 0, "error": f"{type(e).__name__}: {e}"}


async def search_repos(q: str, limit: int = 6, sort: str = "stars",
                       min_stars: int = 100) -> list[dict]:
    query = q
    if "stars:" not in q and min_stars > 0:
        query = f"{q} stars:>{min_stars}"
    res = await _get(f"/search/repositories?q={quote_plus(query)}&sort={sort}"
                     f"&order=desc&per_page={limit}")
    if not res.get("ok"):
        return []
    out = []
    for it in res["data"].get("items", [])[:limit]:
        out.append({
            "full_name": it["full_name"], "name": it["name"],
            "owner": it["owner"]["login"], "stars": it["stargazers_count"],
            "forks": it["forks_count"], "open_issues": it["open_issues_count"],
            "lang": it.get("language") or "—",
            "desc": (it.get("description") or "")[:320],
            "url": it["html_url"], "topics": it.get("topics", [])[:8],
            "updated": (it.get("pushed_at") or it.get("updated_at") or "")[:10],
            "created": (it.get("created_at") or "")[:10],
            "license": (it.get("license") or {}).get("spdx_id") or "—",
        })
    return out


async def repo_details(full_name: str) -> dict:
    res = await _get(f"/repos/{full_name}")
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "not found")}
    it = res["data"]
    return {"ok": True, "full_name": it["full_name"], "name": it["name"],
            "owner": it["owner"]["login"], "stars": it["stargazers_count"],
            "forks": it["forks_count"], "watchers": it["subscribers_count"],
            "open_issues": it["open_issues_count"], "lang": it.get("language") or "—",
            "desc": (it.get("description") or "")[:320], "url": it["html_url"],
            "topics": it.get("topics", [])[:10],
            "updated": (it.get("pushed_at") or "")[:10],
            "created": (it.get("created_at") or "")[:10],
            "license": (it.get("license") or {}).get("spdx_id") or "—",
            "default_branch": it.get("default_branch", "main"),
            "homepage": it.get("homepage") or ""}


async def readme(full_name: str, max_chars: int = 2400) -> str:
    h = _headers()
    h["Accept"] = "application/vnd.github.raw+json"
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT,
                                     follow_redirects=True,
                                     verify=ssl_context()) as c:
            r = await c.get(f"{API}/repos/{full_name}/readme", headers=h)
        if r.status_code == 200:
            return r.text[:max_chars]
        # fallback: decode JSON payload
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT,
                                     verify=ssl_context()) as c:
            r2 = await c.get(f"{API}/repos/{full_name}/readme", headers=_headers())
        if r2.status_code == 200:
            return base64.b64decode(r2.json()["content"]).decode("utf-8", "replace")[:max_chars]
    except Exception:
        pass
    return ""


async def recent_issues(full_name: str, limit: int = 5) -> list[dict]:
    res = await _get(f"/repos/{full_name}/issues?state=open&per_page={limit}")
    if not res.get("ok"):
        return []
    return [{"title": i["title"], "url": i["html_url"],
             "labels": [l["name"] for l in i.get("labels", [])][:4],
             "comments": i.get("comments", 0)}
            for i in res["data"][:limit] if "pull_request" not in i]
