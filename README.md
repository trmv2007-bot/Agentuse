# AGENTUSE — Autonomous Grid Intelligence

A **JARVIS/ULTRON-class autonomous agent system** with live internet control and a
real-time **SpaceGrid** HUD. Every thought, plan, tool call, and artifact the agent
produces streams to your screen the instant it happens. Nothing is hidden.

```
┌──────────────────────────────────────────────────────────────────────┐
│  MISSIONS      THOUGHT STREAM (live)               NETWORK MAP       │
│  ┌─────────┐   ▸ Directive received…                 ◉ github  live   │
│  │ m_01 ●  │   ◈ TACTICAL PLAN                      ◉ pypi    live   │
│  │ m_02 ●  │     1. Sweep GitHub                    ✗ ddg     BLOCKED│
│  └─────────┘     2. Deep-scan repos               VITALS · SPARKLINE │
│  CAPABILITIES   ⚙ GITHUB_SEARCH RUNNING 0.4s       SYSTEM LOG        │
│  web.search     ▣ CARD  repo langchain ★146k       ARTIFACTS         │
│  github.repo    ✦ ANSWER  Community leader…                           │
│            [ 🎙 Issue a directive…            EXECUTE ⏎ ]            │
└──────────────────────────────────────────────────────────────────────┘
```

## Quickstart — one shot

**Linux / macOS**
```bash
git clone https://github.com/trmv2007-bot/Agentuse.git && cd Agentuse && bash install.sh
```
or fully remote:
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/trmv2007-bot/Agentuse/main/install.sh)"
```

**Windows** — double-click `install.bat`, or in PowerShell:
```powershell
git clone https://github.com/trmv2007-bot/Agentuse.git; cd Agentuse; .\install.ps1
# or fully remote:
irm https://raw.githubusercontent.com/trmv2007-bot/Agentuse/main/install.ps1 | iex
```

The installer finds Python 3.10+, builds an isolated `.venv`, installs
`fastapi / uvicorn / httpx / beautifulsoup4 / lxml`, and boots the SpaceGrid on
**http://localhost:8000** (Ctrl+C or close the window to stop it).

Manual equivalent:

```bash
pip install -r requirements.txt
python run.py
# → open http://localhost:8000
```

Zero API keys required. The built-in **heuristic core** classifies your directive,
drafts a tactical plan, and executes it tool-by-tool — fully autonomously and fully
visible on the grid.

Then try:

| Directive | What the agent does |
|---|---|
| `status report` | Live-probes every network route, reports the readiness matrix + vitals |
| `compare top python agent frameworks on github` | GitHub sweep → deep-scans top repos → writes comparison report |
| `fastapi pypi` | Pulls version, deps, release cadence from PyPI, delivers a verdict |
| `npm package express` | Same, against the npm registry |
| `calculate (2+3)*14/5` | Sandbox CodeBox evaluation |
| paste a fenced code block | Executes it in the sandbox, streams stdout/stderr |
| `https://some-site.com summarize` | Fetches, extracts readable text, digests key bullets |
| `what happened in ai this week` | Multi-provider search → deep-read → synthesized report |

## JARVIS vs ULTRON mode

- **JARVIS** — careful, sequential execution. One action at a time.
- **ULTRON** — aggressive parallelism. Independent actions (e.g. deep-scanning 3
  repos, fetching 3 sources) fire *simultaneously* via `asyncio.gather`; a
  `⚡ parallel batch` marker appears on the stream.

## Neural core (optional upgrade)

Drop any **one** of these env vars and the heuristic core is replaced by a full
LLM **ReAct loop** (reason → call tools → observe → repeat) over the same 13 tools:

```bash
export OPENAI_API_KEY=sk-...            # or any OpenAI-compatible server:
export OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama, LM Studio, Groq…
export OPENAI_MODEL=llama3.1

export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=...
export OPENROUTER_API_KEY=sk-or-...

# generic OpenAI-compatible override:
export AGENTUSE_LLM_BASE_URL=... AGENTUSE_LLM_API_KEY=... AGENTUSE_LLM_MODEL=...
```

The top-bar chip shows which core is live: `◈ CORE · HEURISTIC` or `◈ CORE · NEURAL`.

## Internet control, honestly

The agent ships a **NetProbe** that maps every route at boot and shows it on the
Network Map panel — `live` in green, `BLOCKED` in red, with latency. It never
pretends: in a firewalled environment (like a locked-down sandbox) general-web
routes show as blocked and the agent says so, then routes missions through the
routes that *are* alive (GitHub API, PyPI, npm are open in many dev sandboxes).
On an unrestricted machine, DuckDuckGo, Bing, Wikipedia, HackerNews, StackOverflow
and arXiv light up automatically.

Search is a **provider fallback chain**: DDG-lite → Bing → Wikipedia → HN →
StackOverflow → arXiv → GitHub, merging + de-duplicating results, and every attempt
is streamed to the grid.

## The 13 tools

| Tool | Purpose |
|---|---|
| `web_search` | multi-provider web sweep |
| `fetch_page` | fetch + readability extraction + bullets |
| `github_search` / `github_repo` | repo sweep / deep intel incl. README |
| `pypi_info` / `npm_info` | registry intel: versions, deps, cadence |
| `run_code` | sandboxed Python/JavaScript (CPU/RAM/time-limited subprocess) |
| `write_file` / `read_file` / `list_files` | workspace territory (`data/workspace/`) |
| `memory_write` / `memory_recall` | durable SQLite notes across restarts |
| `net_probe` | live route matrix |

## Architecture

```
run.py ─→ agentuse/server.py (FastAPI)
            ├─ /ws      WebSocket event stream (the SpaceGrid feed)
            ├─ /api/*   REST: missions, state, events, exec, netmap, artifacts
            ├─ static/  SpaceGrid HUD (vanilla JS + canvas, no build step)
            │
            ├─ core/brain.py      mission orchestrator (heuristic ⇄ neural ReAct)
            ├─ core/planner.py    autonomous playbooks: research, github, package,
            │                     code, url-digest, diagnostics
            ├─ core/facade.py     Agent facade — every move → bus → your screen
            ├─ core/llm.py        OpenAI / Anthropic / Gemini / OpenRouter / custom
            ├─ bus.py             event bus → WS fanout + JSONL + SQLite
            └─ tools/             net, search, github, packages, codebox, files,
                                  registry (one schema shared by both cores)
```

Every event (`thought`, `plan`, `action.start/end`, `card`, `artifact`,
`net.route`, `speech`, `mission.*`) is persisted to SQLite and replayed to new
browser sessions — reload the page and the last 800 events rebuild the grid.

## Voice

Hit **VOICE** (top right): mission reports and key findings are spoken via the
Web Speech API. Hit the 🎙 for voice directives (Chrome/Edge). All client-side —
no audio leaves your machine.

## REST API

```
POST /api/missions            {goal, mode: jarvis|ultron} → {id}
POST /api/missions/{id}/cancel
GET  /api/state               core, netmap, missions, artifacts, stats
GET  /api/events?after=N      persisted event replay
POST /api/netmap/probe        re-probe all routes
POST /api/exec                {code, lang} manual CodeBox run (also streamed)
GET  /api/artifact?path=      read a workspace artifact
WS   /ws                      live event stream (send {after: seq} after hello)
```

## Security notes

`run_code` executes untrusted code in a subprocess with CPU/RAM/file-size limits
and a scrubbed environment — but it is **not** a security boundary. Run AGENTUSE
on a machine or container you control. File tools are confined to
`data/workspace/`.

## Repo layout

```
agentuse/            Python package (server, core, tools)
static/              SpaceGrid HUD — index.html, style.css, app.js, grid.js
tests/e2e_test.py    WebSocket-driven end-to-end mission runner
data/                runtime: SQLite, events.jsonl, workspace, sandbox (gitignored)
```
