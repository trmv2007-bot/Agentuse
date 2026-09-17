"""Package registry intelligence — PyPI + npm."""
import json
import time
from urllib.parse import quote_plus

from .. import config
from . import net


def _ago(ts: float) -> str:
    if not ts:
        return "unknown"
    d = int(time.time() - ts)
    for unit, sec in (("y", 31536000), ("mo", 2592000), ("d", 86400),
                      ("h", 3600), ("m", 60)):
        if d >= sec:
            return f"{d // sec}{unit} ago"
    return "just now"


async def pypi_project(name: str) -> dict:
    r = await net.fetch(f"https://pypi.org/pypi/{quote_plus(name)}/json")
    if not r.get("ok") or r.get("status") != 200:
        return {"ok": False, "registry": "pypi", "name": name,
                "error": r.get("error") or f"HTTP {r.get('status')}"}
    try:
        data = json.loads(r["text"])
    except Exception as e:
        return {"ok": False, "registry": "pypi", "name": name, "error": str(e)}
    info = data.get("info", {})
    releases = data.get("releases", {})
    latest = info.get("version", "?")
    urls = data.get("urls", [])
    last_upload = max((u.get("upload_time_iso_8601", "") for u in urls), default="")
    deps = info.get("requires_dist") or []
    urls_map = info.get("project_urls") or {}
    return {"ok": True, "registry": "pypi", "name": info.get("name", name),
            "version": latest, "summary": (info.get("summary") or "")[:300],
            "author": info.get("author") or info.get("maintainer") or "—",
            "license": (info.get("license") or "—")[:60],
            "homepage": info.get("home_page") or urls_map.get("Homepage") or "",
            "python_req": info.get("requires_python") or "—",
            "deps_count": len(deps), "deps_sample": deps[:6],
            "releases_count": len(releases),
            "last_upload": last_upload[:10] or "—",
            "urls": {k: v for k, v in list(urls_map.items())[:4]}}


async def npm_package(name: str) -> dict:
    r = await net.fetch(f"https://registry.npmjs.org/{quote_plus(name)}")
    if not r.get("ok") or r.get("status") != 200:
        return {"ok": False, "registry": "npm", "name": name,
                "error": r.get("error") or f"HTTP {r.get('status')}"}
    try:
        data = json.loads(r["text"])
    except Exception as e:
        return {"ok": False, "registry": "npm", "name": name, "error": str(e)}
    latest = (data.get("dist-tags") or {}).get("latest", "?")
    lv = (data.get("versions") or {}).get(latest, {})
    times = data.get("time", {})
    return {"ok": True, "registry": "npm", "name": data.get("name", name),
            "version": latest,
            "summary": (data.get("description") or lv.get("description") or "")[:300],
            "author": (lv.get("author") or {}).get("name", "—") if isinstance(lv.get("author"), dict) else (lv.get("author") or "—"),
            "license": lv.get("license") or "—",
            "homepage": data.get("homepage") or "",
            "deps_count": len(lv.get("dependencies") or {}),
            "deps_sample": list((lv.get("dependencies") or {}).items())[:6],
            "releases_count": len(data.get("versions") or {}),
            "last_upload": (times.get(latest) or "")[:10] or "—",
            "modified_ago": _ago(_parse_iso(times.get("modified"))),
            "urls": {"npm": f"https://www.npmjs.com/package/{name}"}}


def _parse_iso(s: str) -> float:
    try:
        from datetime import datetime, timezone
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0
