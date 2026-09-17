"""Heuristic planner — the autonomous strategies that let AGENTUSE run with
ZERO API keys. Each strategy is a fully-visible, adaptive mission playbook."""
import re
from typing import List

from .facade import Agent
from ..tools import net as netmod

URL_RE = re.compile(r"https?://[^\s\"'<>)]+")
CODEBLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.S)
ARITH_RE = re.compile(r"^[\d\s+\-*/().,%^]+$")

FLUFF = ("please ", "can you ", "could you ", "for me", "hey ", "jarvis ", "ultron ",
         "agentuse ", "i want ", "i'd like ", "find out ", "tell me about ",
         "research ", "look up ", "search for ", "what is ", "what are ", "who is ",
         "give me ", "show me ", "get me ", "info on ", "information about ")


def clean_goal(goal: str) -> str:
    g = goal.strip().strip("?.").lower()
    for f in FLUFF:
        g = g.replace(f, "")
    return g.strip() or goal.strip()


_CMD_WORDS = (r"\b(calculate|compute|evaluate|eval|what is|whats|what's|how much is|result of)\b")


def classify(goal: str) -> str:
    g = goal.lower()
    if URL_RE.search(goal):
        return "url_digest"
    if CODEBLOCK_RE.search(goal):
        return "code_task"
    # explicit registry mentions win over everything except urls/code
    if re.search(r"\b(pypi|pip|python package)\b", g):
        return "package_intel"
    if re.search(r"\b(npm|node package|node module|nodejs)\b", g):
        return "package_intel"
    # bare arithmetic / compute directive (strip command words first)
    stripped = re.sub(_CMD_WORDS, " ", goal).strip(" ?=.")
    if ARITH_RE.match(stripped) and any(c.isdigit() for c in stripped):
        return "code_task"
    if re.search(r"\b(status|diagnostics|diagnostic|netmap|probe|routes|system report|health)\b", g):
        return "status"
    if re.search(r"\b(help|what can you do|who are you|capabilities)\b", g):
        return "help"
    if re.search(r"\b(package|library|module) [`'\"]?([\w.\-/]+)[`'\"]?", g):
        return "package_intel"
    if re.search(r"\b(github|repo|repos|framework|frameworks|stars?\b|open.?source|compare|best|top)\b", g):
        return "github_research"
    if re.search(r"\b(run|execute|eval|compute|calculate|simulate)\b", g) and \
            re.search(r"\b(python|node|javascript|js|script|code)\b", g):
        return "code_task"
    return "research"


# --------------------------------------------------------------------------
# Strategies — async functions driving the Agent facade
# --------------------------------------------------------------------------

async def strategy_status(agent: Agent, goal: str) -> str:
    await agent.plan(["Probe every network route", "Compile route matrix + vitals",
                      "Report readiness"])
    await agent.think("Running full-spectrum diagnostics — pinging every route in the net map…")
    res = await agent.act("net_probe", label="probe all routes")
    routes = res.get("routes", []) if isinstance(res, dict) else []
    live = [r for r in routes if r["status"] == "live"]
    blocked = [r for r in routes if r["status"] == "blocked"]
    await agent.card("status", "Network readiness matrix", routes=routes,
                     live=len(live), blocked=len(blocked))
    from .. import store
    s = store.stats()
    await agent.card("answer", "System vitals", text=(
        f"Routes live: {len(live)}/{len(routes)}\n"
        f"Routes blocked: {len(blocked)} ({', '.join(r['id'] for r in blocked[:6]) or 'none'})\n"
        f"Missions run: {s['missions_total']} (done {s['missions_done']})\n"
        f"Actions executed: {s['actions_total']}\n"
        f"Events streamed: {s['events_total']}\n"
        f"Neural core: {res.get('core', 'heuristic') if isinstance(res, dict) else 'heuristic'}"))
    await agent.say(f"Diagnostics complete. {len(live)} of {len(routes)} routes live. "
                    f"All systems nominal." if live else
                    "Diagnostics complete. No live routes in this segment.")
    return f"diagnostics: {len(live)}/{len(routes)} routes live"


async def strategy_help(agent: Agent, goal: str) -> str:
    await agent.plan(["Enumerate capabilities", "Brief the operator"])
    await agent.think("Standing by. Briefing operator on my capability set.")
    await agent.card("answer", "AGENTUSE — capability brief", text=(
        "I am an autonomous grid agent. Missions I run natively (no API keys needed):\n\n"
        "• Research — multi-provider web search, deep-read pages, synthesize a report\n"
        "• GitHub intel — repo search, stars/activity, README analysis, comparisons\n"
        "• Package intel — PyPI & npm: versions, dependencies, release cadence\n"
        "• URL digest — fetch any page, extract readable content + key bullets\n"
        "• CodeBox — execute Python / JavaScript in a sandboxed box\n"
        "• Diagnostics — probe every network route live\n\n"
        "Attach a NEURAL CORE (OpenAI / Anthropic / Gemini / OpenRouter / any "
        "OpenAI-compatible endpoint via env vars) and I upgrade to full ReAct "
        "reasoning over these same tools. Everything I do streams to this grid."))
    await agent.say("All systems online. Issue a directive and I will execute it on the grid.")
    return "briefed"


async def strategy_code(agent: Agent, goal: str) -> str:
    m = CODEBLOCK_RE.search(goal)
    if m:
        lang = (m.group(1) or "python").lower()
        code = m.group(2)
        await agent.plan([f"Extract {lang} block", "Execute in sandboxed CodeBox",
                          "Stream results"])
        await agent.think(f"Isolated {len(code)} bytes of {lang} — dispatching to CodeBox with CPU/RAM/time limits.")
        res = await agent.act("run_code", label=f"execute {lang}", lang=lang, code=code)
    elif ARITH_RE.match(re.sub(_CMD_WORDS, " ", goal).strip(" ?=.")):
        expr = re.sub(_CMD_WORDS, " ", goal).strip(" ?=.").rstrip("=")
        code = (f"from decimal import Decimal, getcontext\n"
                f"getcontext().prec = 28\n"
                f"expr = {expr!r}\n"
                f"try:\n"
                f"    val = eval(expr, {{'__builtins__': {{}}}}, {{}})\n"
                f"    print(f'{{expr}} = {{val}}')\n"
                f"except Exception as e:\n"
                f"    print('error:', e)\n")
        await agent.plan(["Parse arithmetic directive", "Execute in CodeBox"])
        await agent.think("Pure computation directive detected — evaluating in isolation.")
        res = await agent.act("run_code", label="compute expression", lang="python", code=code)
    else:
        await agent.think("No code block found — treating as a research mission instead.")
        return await strategy_research(agent, goal)
    await agent.card("code", "CodeBox result", lang=res.get("lang", "?"),
                     code=(CODEBLOCK_RE.search(goal).group(2) if m and CODEBLOCK_RE.search(goal) else goal.strip()),
                     stdout=res.get("stdout", ""), stderr=res.get("stderr", ""),
                     exit=res.get("exit"), ms=res.get("ms", 0))
    if res.get("ok"):
        first = res.get("stdout", "").strip().splitlines()
        await agent.say(f"CodeBox finished with exit zero. " + (first[0][:140] if first else ""))
        return "code executed cleanly"
    await agent.say("CodeBox run failed — the error is on the grid.")
    return "code failed"


async def strategy_url(agent: Agent, goal: str) -> str:
    url = URL_RE.search(goal).group(0).rstrip(".,;)")
    await agent.plan([f"Fetch {url[:48]}…", "Extract readable content",
                      "Summarize key points"])
    await agent.think(f"Opening channel to {netmod.urlparse(url).netloc} — pulling raw document…")
    res = await agent.act("fetch_page", label="fetch page", url=url)
    if not res.get("ok"):
        await agent.think("Route refused the connection. Marking route state and aborting digest.")
        await agent.say("That route is unreachable from my grid segment.")
        return "fetch failed"
    text = res.get("text", "")
    from ..tools.summarize import top_sentences, keywords
    bullets = top_sentences(text, 7)
    kws = keywords(text, 8)
    await agent.card("page", res.get("title") or url, url=res.get("url", url),
                     excerpt=text[:1200], bullets=bullets, words=len(text.split()),
                     status=res.get("status"))
    verdict = (f"Digested \"{res.get('title', '')[:70]}\" — {len(text.split())} words extracted. "
               f"Key themes: {', '.join(kws[:5])}.")
    await agent.card("answer", "Digest", text="\n".join(f"• {b}" for b in bullets))
    await agent.say(verdict)
    await agent.artifact("digests/latest-digest.md",
                         f"# Digest: {res.get('title','')}\n\nSource: {url}\n\n"
                         + "\n".join(f"- {b}" for b in bullets),
                         title="Page digest")
    store_kw = keywords(text, 5)
    return f"digested {url}"


async def strategy_package(agent: Agent, goal: str) -> str:
    g = clean_goal(goal)
    g = re.sub(r"\b(pypi|pip|npm|nodejs?|packages?|modules?|librar(?:y|ies)|registry|status|info|information|about|on|check|is|maintained|the|latest|version)\b",
               " ", g, flags=re.I)
    tokens = re.findall(r"[A-Za-z@/][\w@/.\-+]*", g)
    name = tokens[0].strip("./-") if tokens else ""
    if not name:
        await agent.think("No package identifier found in directive — diverting to research mode.")
        return await strategy_research(agent, goal)
    want_npm = bool(re.search(r"\b(npm|node)\b", goal.lower()))
    want_pypi = bool(re.search(r"\b(pypi|pip|python)\b", goal.lower()))
    if not want_npm and not want_pypi:
        want_pypi = True  # default assumption; npm tried as fallback below
    await agent.plan([f"Query {'PyPI' if want_pypi else 'npm'} registry for '{name}'",
                      "Analyze release cadence & dependencies", "Deliver verdict"])
    results = []
    if want_pypi:
        await agent.think(f"Querying PyPI registry for package '{name}'…")
        results.append(("pypi", await agent.act("pypi_info", label=f"pypi:{name}", package=name)))
    if want_npm:
        await agent.think(f"Querying npm registry for package '{name}'…")
        results.append(("npm", await agent.act("npm_info", label=f"npm:{name}", package=name)))
    hits = [(reg, r) for reg, r in results if r.get("ok")]
    if not hits and not (want_pypi and want_npm):
        # try the other registry before giving up
        if want_pypi:
            await agent.think(f"Not on PyPI — probing npm registry for '{name}'…")
            results.append(("npm", await agent.act("npm_info", label=f"npm:{name}", package=name)))
        else:
            await agent.think(f"Not on npm — probing PyPI for '{name}'…")
            results.append(("pypi", await agent.act("pypi_info", label=f"pypi:{name}", package=name)))
        hits = [(reg, r) for reg, r in results if r.get("ok")]
    if not hits:
        await agent.think("Registry returned nothing on that identifier. Attempting GitHub cross-reference…")
        alt = await agent.act("github_search", label="cross-reference", query=name, limit=3)
        if alt.get("repos"):
            for r in alt["repos"][:2]:
                d = await agent.act("github_repo", label=r["full_name"], full_name=r["full_name"])
                if d.get("ok"):
                    await agent.card("repo", d["full_name"], **_repo_card(d))
            return "fell back to github intel"
        await agent.say(f"No package named '{name}' found on any reachable registry.")
        return "package not found"
    for reg, r in hits:
        await agent.card("package", f"{r['name']} · {reg}", **_pkg_card(r))
        verdict = _package_verdict(r)
        await agent.think(verdict)
    await agent.say(f"{hits[0][1]['name']} v{hits[0][1]['version']} — "
                    f"last upload {hits[0][1]['last_upload']}, "
                    f"{hits[0][1]['releases_count']} releases tracked.")
    return "package intel delivered"


def _package_verdict(r: dict) -> str:
    age = r.get("last_upload", "—")
    return (f"Verdict on {r['name']}: {r['releases_count']} releases, latest v{r['version']} "
            f"uploaded {age}, {r['deps_count']} direct dependencies, license {r['license']}.")


async def strategy_github(agent: Agent, goal: str) -> str:
    q = clean_goal(goal)
    q = re.sub(r"\b(on github|repos|repositories|compare|best|top \d+|stars?)\b", "", q).strip() or "agent framework"
    # strip generic fillers that attract keyword-stuffed spam repos
    _filler = {"top", "best", "most", "popular", "the", "a", "an", "good",
               "great", "leading", "current", "popular"}
    words = [w for w in q.split() if w.lower() not in _filler]
    q_tight = " ".join(words) if len(words) >= 2 else q
    limit = 5
    await agent.plan([f"Sweep GitHub for '{q_tight}'", "Deep-scan top repositories",
                      "Cross-compare stars, activity, ecosystem", "Deliver intel report"])
    await agent.think(f"Sweeping GitHub's index for '{q_tight}' — ranking by community gravity…")
    res = await agent.act("github_search", label=f"github:{q_tight[:44]}",
                          query=q_tight, limit=limit, min_stars=1000)
    repos = res.get("repos", [])
    if len(repos) < 3:
        await agent.think("Tight sweep returned few candidates — lowering the gravity filter…")
        res = await agent.act("github_search", label="widened sweep",
                              query=q_tight, limit=limit, min_stars=100)
        repos = res.get("repos", [])
    if not repos:
        await agent.say("GitHub sweep came back empty; the route may be rate-limited.")
        return "github search empty"
    await agent.card("search", f"GitHub sweep — {q}",
                     query=q, items=[{"title": f"{r['full_name']}  ★{r['stars']}",
                                      "url": r["url"], "snippet": r["desc"][:200],
                                      "source": "github"} for r in repos])
    await agent.think(f"{len(repos)} candidates acquired. Deep-scanning top {min(3, len(repos))}…")
    details = []
    top = repos[:3]
    if agent.mode == "ultron":
        details = await agent.gather(*[agent.act("github_repo", label=r["full_name"],
                                                 full_name=r["full_name"]) for r in top],
                                     label="parallel deep-scan")
    else:
        for r in top:
            details.append(await agent.act("github_repo", label=r["full_name"],
                                           full_name=r["full_name"]))
    report_lines = [f"# GitHub Intel — {q}", ""]
    leader = None
    for d in details:
        if not d.get("ok"):
            continue
        await agent.card("repo", d["full_name"], **_repo_card(d))
        report_lines += [f"## {d['full_name']}  ★{d['stars']}",
                         f"{d.get('desc','')}", "",
                         f"- Language: {d['lang']} · License: {d['license']}",
                         f"- Stars: {d['stars']} · Forks: {d['forks']} · Issues: {d['open_issues']}",
                         f"- Last push: {d['updated']} · Created: {d['created']}",
                         f"- Topics: {', '.join(d.get('topics', [])) or '—'}", ""]
        if leader is None or d["stars"] > leader["stars"]:
            leader = d
    if leader:
        verdict = (f"Community leader: {leader['full_name']} at {leader['stars']:,} stars, "
                   f"primary language {leader['lang']}, last push {leader['updated']}.")
        await agent.card("answer", "Comparison verdict", text=verdict)
        await agent.say(f"Sweep complete. Leading candidate is {leader['name']} with "
                        f"{leader['stars']} stars.")
        report_lines = [f"# GitHub Intel — {q}", "", verdict, ""] + report_lines
        await agent.artifact("reports/github-intel.md", "\n".join(report_lines),
                             title=f"GitHub intel — {q}")
    return "github intel delivered"


async def strategy_research(agent: Agent, goal: str) -> str:
    q = clean_goal(goal)
    q = q[:220]
    await agent.plan([f"Multi-provider search: '{q}'", "Deep-read the strongest sources",
                      "Cross-extract key findings", "Synthesize report + answer"])
    attempts_log: List[str] = []
    def on_attempt(pid, msg):
        attempts_log.append(f"{pid}: {msg}")
    await agent.think(f"Engaging internet control. Querying every live search provider for '{q}'…")
    res = await agent.act("web_search", label=f"search: {q[:48]}", query=q, limit=8)
    results = res.get("results", [])
    if not results:
        await agent.think("All general-web routes refused. Falling back to GitHub sweep — "
                          "the strongest live route in this segment…")
        res = await agent.act("github_search", label="fallback sweep", query=q.split()[0] if q.split() else q, limit=5)
        repos = res.get("repos", [])
        if not repos:
            await agent.card("answer", "No live route could answer", text=(
                "Every search route in this network segment is firewalled, and the "
                "fallback sweep found nothing. Routes marked BLOCKED on the Network Map "
                "will open automatically when AGENTUSE runs on an unrestricted network. "
                "Live capabilities right now: GitHub, PyPI, npm, CodeBox, diagnostics."))
            await agent.say("No route could complete that research. Check the network map.")
            return "all routes blocked"
        for r in repos[:3]:
            d = await agent.act("github_repo", label=r["full_name"], full_name=r["full_name"])
            if d.get("ok"):
                await agent.card("repo", d["full_name"], **_repo_card(d))
        return "github fallback delivered"
    await agent.card("search", f"Search — {q}", query=q,
                     items=[{"title": r["title"], "url": r["url"],
                             "snippet": r["snippet"][:240], "source": r["source"]}
                            for r in results])
    # dedupe by domain, deep-read top N
    picked, domains = [], set()
    for r in results:
        dom = netmod.urlparse(r["url"]).netloc
        if dom in domains:
            continue
        domains.add(dom)
        picked.append(r)
        if len(picked) >= 3:
            break
    await agent.think(f"Merged {len(results)} results. Deep-reading top {len(picked)} sources"
                      + (" in parallel — ULTRON mode." if agent.mode == "ultron" else " sequentially — JARVIS mode."))
    pages = []
    if agent.mode == "ultron":
        pages = await agent.gather(*[agent.act("fetch_page", label=netmod.urlparse(r["url"]).netloc,
                                               url=r["url"]) for r in picked],
                                   label="parallel deep-read")
    else:
        for r in picked:
            pages.append(await agent.act("fetch_page", label=netmod.urlparse(r["url"]).netloc,
                                         url=r["url"]))
    from ..tools.summarize import top_sentences, keywords
    all_findings, report_srcs = [], [f"# Research — {q}", ""]
    for src, page in zip(picked, pages):
        if not (page or {}).get("ok"):
            await agent.note(f"source unreachable: {src['url']}", level="warn")
            continue
        text = page.get("text", "")
        bullets = top_sentences(text, 5)
        all_findings += bullets
        await agent.card("page", page.get("title") or src["title"],
                         url=page.get("url"), excerpt=text[:900],
                         bullets=bullets, words=len(text.split()),
                         status=page.get("status"))
        report_srcs += [f"## {page.get('title') or src['title']}",
                        f"Source: {page.get('url')}", ""]
        report_srcs += [f"- {b}" for b in bullets] + [""]
    kws = keywords(" ".join(all_findings), 10)
    findings_txt = "\n".join(f"• {b}" for b in all_findings[:12])
    await agent.card("answer", f"Findings — {q}",
                     text=findings_txt + (f"\n\nKey themes: {', '.join(kws[:6])}" if kws else ""))
    await agent.say(f"Research complete. {len(all_findings)} findings extracted from "
                    f"{len([p for p in pages if p and p.get('ok')])} sources.")
    report = "\n".join(report_srcs) + (f"\n## Key themes\n\n{kws and ', '.join(kws)}\n" if kws else "")
    await agent.artifact("reports/research.md", report, title=f"Research — {q}")
    from .. import store
    store.remember("research", f"{q} :: {'; '.join(all_findings[:3])}", mission=agent.mid)
    return "research complete"


def _repo_card(d: dict) -> dict:
    return {"full_name": d.get("full_name"), "stars": d.get("stars"),
            "forks": d.get("forks"), "open_issues": d.get("open_issues"),
            "lang": d.get("lang"), "license": d.get("license"),
            "desc": d.get("desc"), "url": d.get("url"),
            "topics": d.get("topics", []), "updated": d.get("updated"),
            "created": d.get("created"),
            "readme_head": (d.get("readme_head") or "")[:700],
            "homepage": d.get("homepage")}


def _pkg_card(r: dict) -> dict:
    return {"registry": r.get("registry"), "name": r.get("name"),
            "version": r.get("version"), "summary": r.get("summary"),
            "author": r.get("author"), "license": r.get("license"),
            "homepage": r.get("homepage"), "deps_count": r.get("deps_count"),
            "deps_sample": [f"{k} {v}" if isinstance(v, str) else str(k)
                            for k, v in (r.get("deps_sample") or [])][:6]
            if isinstance(r.get("deps_sample"), list) and r.get("deps_sample")
            and not isinstance(r.get("deps_sample")[0], str)
            else (r.get("deps_sample") or []),
            "releases_count": r.get("releases_count"),
            "last_upload": r.get("last_upload"),
            "python_req": r.get("python_req"), "urls": r.get("urls", {})}


STRATEGIES = {
    "status": strategy_status,
    "help": strategy_help,
    "code_task": strategy_code,
    "url_digest": strategy_url,
    "package_intel": strategy_package,
    "github_research": strategy_github,
    "research": strategy_research,
}
