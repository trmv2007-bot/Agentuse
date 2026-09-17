"""Tool registry — one schema shared by the heuristic planner AND neural core."""
from typing import Any, Callable, Coroutine

from . import codebox, files, github, net, packages, search


async def t_web_search(query: str, limit: int = 8) -> dict:
    return await search.web_search(query, limit=int(limit))


async def t_fetch_page(url: str) -> dict:
    r = await net.fetch(url)
    x = net.extract(r)
    x["bullets"] = net.bullets_from(x.get("text") or "", 6)
    return x


async def t_github_search(query: str, limit: int = 6, min_stars: int = 100) -> dict:
    repos = await github.search_repos(query, limit=int(limit), min_stars=int(min_stars))
    return {"ok": bool(repos), "query": query, "repos": repos}


async def t_github_repo(full_name: str, with_readme: bool = True) -> dict:
    d = await github.repo_details(full_name)
    if d.get("ok") and with_readme:
        d["readme_head"] = await github.readme(full_name)
    return d


async def t_pypi_info(package: str) -> dict:
    return await packages.pypi_project(package)


async def t_npm_info(package: str) -> dict:
    return await packages.npm_package(package)


async def t_run_code(code: str, lang: str = "python") -> dict:
    return await codebox.run_code(code, lang)


async def t_write_file(path: str, content: str) -> dict:
    return files.write_file(path, content)


async def t_read_file(path: str) -> dict:
    return files.read_file(path)


async def t_list_files() -> dict:
    return {"ok": True, "files": files.list_files()}


async def t_memory_write(kind: str, content: str) -> dict:
    from .. import store
    store.remember(kind, content)
    return {"ok": True}


async def t_memory_recall(query: str = "") -> dict:
    from .. import store
    return {"ok": True, "notes": store.recall(query)}


async def t_net_probe() -> dict:
    from ..tools import net
    from ..bus import bus
    routes = await net.probe_all()
    for r in routes:
        await bus.emit_async("net.route", r)
    from ..core import llm
    return {"ok": True, "routes": routes, "core": llm.core_name()}


TOOLS: dict[str, dict[str, Any]] = {
    "web_search":   {"fn": t_web_search,   "desc": "Search the web via multiple providers (DuckDuckGo, Bing, Wikipedia, HN, StackOverflow, arXiv, GitHub).",
                     "args": {"query": "str (required)", "limit": "int, default 8"}},
    "fetch_page":   {"fn": t_fetch_page,   "desc": "Fetch a URL and extract readable text, title and key bullets.",
                     "args": {"url": "str (required)"}},
    "github_search":{"fn": t_github_search,"desc": "Search GitHub repositories by keyword.",
                     "args": {"query": "str", "limit": "int"}},
    "github_repo":  {"fn": t_github_repo,  "desc": "Full intel on one GitHub repo (stars, activity, README head).",
                     "args": {"full_name": "owner/repo", "with_readme": "bool"}},
    "pypi_info":    {"fn": t_pypi_info,    "desc": "PyPI package intel: version, deps, releases, uploads.",
                     "args": {"package": "str"}},
    "npm_info":     {"fn": t_npm_info,     "desc": "npm package intel: version, deps, publish times.",
                     "args": {"package": "str"}},
    "run_code":     {"fn": t_run_code,     "desc": "Execute Python or JavaScript in a sandboxed CodeBox.",
                     "args": {"code": "str", "lang": "python|javascript"}},
    "write_file":   {"fn": t_write_file,  "desc": "Write a file into the agent workspace.",
                     "args": {"path": "relative path", "content": "str"}},
    "read_file":    {"fn": t_read_file,    "desc": "Read a workspace file.",
                     "args": {"path": "relative path"}},
    "list_files":   {"fn": t_list_files,   "desc": "List workspace files.", "args": {}},
    "memory_write": {"fn": t_memory_write, "desc": "Store a durable note in agent memory.",
                     "args": {"kind": "str", "content": "str"}},
    "memory_recall":{"fn": t_memory_recall,"desc": "Recall memory notes, optional keyword filter.",
                     "args": {"query": "str"}},
    "net_probe":    {"fn": t_net_probe,    "desc": "Probe every network route and return the live/blocked matrix.",
                     "args": {}},
}


def openai_schemas() -> list[dict]:
    """Tool schemas in OpenAI function-calling format."""
    out = []
    for name, t in TOOLS.items():
        props, req = {}, []
        for arg, spec in t.get("args", {}).items():
            typ = "string" if "str" in spec else ("integer" if "int" in spec else
                  ("boolean" if "bool" in spec else "string"))
            props[arg] = {"type": typ, "description": spec}
            if "required" in spec:
                req.append(arg)
        out.append({"type": "function", "function": {
            "name": name, "description": t["desc"],
            "parameters": {"type": "object", "properties": props, "required": req}}})
    return out


def anthropic_schemas() -> list[dict]:
    out = []
    for s in openai_schemas():
        f = s["function"]
        out.append({"name": f["name"], "description": f["description"],
                    "input_schema": f["parameters"]})
    return out
