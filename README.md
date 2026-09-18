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

**Windows** — double-click `install.bat`, or in PowerShell
(needs Python 3.10+; see [Windows: `Python was not found`](#windows-python-was-not-found)):
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

## Windows: `Python was not found`

If the PowerShell installer dies with this, **Python is not actually installed** —
or Windows is hiding it behind its Microsoft Store shortcut:

```
python.exe : Python was not found; run without arguments to install from the
Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app
settings > App execution aliases.
```

Windows 10/11 ship a 0-byte *App Execution Alias* at
`%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe`. It answers `where python`,
then prints that message and exits — so any installer that only checks
*"is python on PATH?"* gets fooled. Fix it:

1. Install Python 3.10+ from <https://www.python.org/downloads/> and **tick
   "Add python.exe to PATH"** — or `winget install -e --id Python.Python.3.12`.
2. Turn the stub off: **Settings → Apps → Advanced app settings → App execution
   aliases** → switch **python.exe** and **python3.exe** to *Off*.
3. Open a **new** terminal (PATH changes don't reach already-open shells) and
   rerun `install.ps1` / `install.bat`.

Already installed? `py -3 --version` is the reliable check — the `py` launcher
ignores the Store stub, and both installers prefer it. `install.ps1` also skips
the stub automatically, falls back to `py -3` and to the usual install folders,
and prints what it tried when nothing works.

## JARVIS vs ULTRON mode

- **JARVIS** — careful, sequential execution. One action at a time.
- **ULTRON** — aggressive parallelism. Independent actions (e.g. deep-scanning 3
  repos, fetching 3 sources) fire *simultaneously* via `asyncio.gather`; a
  `⚡ parallel batch` marker appears on the stream.

## Neural core (optional upgrade)

Drop any **one** of these env vars and the heuristic core is replaced by a full
LLM **ReAct loop** (reason → call tools → observe → repeat) over 14 tools.
OpenAI-compatible providers (including **xAI Grok**) stream tokens onto the grid.

```bash
export XAI_API_KEY=xai-...              # Grok — first-class, streams thoughts
export XAI_MODEL=grok-4                 # default

export OPENAI_API_KEY=sk-...            # or any OpenAI-compatible server:
export OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama, LM Studio, Groq…
export OPENAI_MODEL=llama3.1

export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=...               # native functionResponse history
export OPENROUTER_API_KEY=sk-or-...

# generic OpenAI-compatible override:
export AGENTUSE_LLM_BASE_URL=... AGENTUSE_LLM_API_KEY=... AGENTUSE_LLM_MODEL=...

# optional lock: AGENTUSE_TOKEN on every REST/WS call (header x-agentuse-token)
export AGENTUSE_TOKEN=...
```

The top-bar chip shows which core is live: `◈ CORE · HEURISTIC` or `◈ CORE · NEURAL`.
While a mission is running, type `/steer <instruction>` in the command bar to
inject a mid-run operator instruction.

**Docker:** `docker compose up --build` → SpaceGrid on port 8000, data in a volume.

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

## The 14 tools

| Tool | Purpose |
|---|---|
| `web_search` | multi-provider web sweep |
| `fetch_page` | fetch + readability extraction + bullets |
| `github_search` / `github_repo` / `github_issues` | repo sweep / deep intel / open issues |
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
POST /api/missions/{id}/steer  {text}   mid-run operator instruction
GET  /api/state               core, netmap, missions, artifacts, stats, version
GET  /api/events?after=N      persisted event replay
POST /api/netmap/probe        re-probe all routes
POST /api/exec                {code, lang} manual CodeBox run (also streamed)
GET  /api/artifact?path=      read a workspace artifact (path-jailed)
WS   /ws                      live event stream (send {after: seq} after hello)
                              ?token= if AGENTUSE_TOKEN is set
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
