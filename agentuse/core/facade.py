"""Agent facade — every move an agent makes goes through here and is
immediately broadcast to the SpaceGrid. Nothing is hidden."""
import asyncio
import time
import traceback
from typing import Any

from .. import config, store
from ..bus import bus
from ..tools import registry


class Agent:
    def __init__(self, mission_id: str, mode: str = "jarvis") -> None:
        self.mid = mission_id
        self.mode = mode
        self.step_no = 0
        self.actions_done = 0
        self.busy = False

    def _step(self) -> int:
        self.step_no += 1
        return self.step_no

    def cancelled(self) -> bool:
        return store.mission_status(self.mid) in ("cancel-requested", "cancelled")

    async def think(self, text: str) -> None:
        await bus.emit_async("thought", {"text": text}, mission=self.mid, step=self._step())

    async def note(self, text: str, level: str = "info") -> None:
        await bus.emit_async("sys.note", {"text": text, "level": level}, mission=self.mid)

    async def plan(self, steps: list[str]) -> None:
        await bus.emit_async("plan", {"steps": steps}, mission=self.mid)

    async def say(self, text: str) -> None:
        await bus.emit_async("speech", {"text": text}, mission=self.mid)

    async def card(self, kind: str, title: str, **payload) -> None:
        await bus.emit_async("card", {"kind": kind, "title": title, **payload},
                             mission=self.mid, step=self.step_no)

    async def artifact(self, path: str, content: str, title: str = "") -> dict:
        from ..tools import files
        if len(content) > 65536:
            content = content[:65536] + "\n\n… [truncated by grid — 64KB artifact cap]"
        res = files.write_file(path, content)
        await bus.emit_async("artifact", {"path": res.get("path", path),
                                          "bytes": res.get("bytes", 0),
                                          "title": title or path}, mission=self.mid)
        return res

    async def act(self, tool: str, label: str = "", timeout: float = 60.0,
                  **args) -> Any:
        if self.cancelled():
            await bus.emit_async("action.end", {
                "tool": tool, "label": label or tool, "status": "cancelled",
                "ms": 0, "summary": "aborted by operator"}, mission=self.mid)
            return {"ok": False, "error": "cancelled"}
        if self.actions_done >= config.MAX_STEPS:
            await bus.emit_async("action.end", {
                "tool": tool, "label": label or tool, "status": "error",
                "ms": 0, "summary": f"MAX_STEPS ({config.MAX_STEPS}) reached"}, mission=self.mid)
            return {"ok": False, "error": "max steps reached"}
        if tool not in registry.TOOLS:
            await bus.emit_async("action.end", {
                "tool": tool, "label": label or tool, "status": "error",
                "ms": 0, "summary": f"unknown tool '{tool}'"}, mission=self.mid)
            return {"ok": False, "error": f"unknown tool '{tool}'"}
        self.busy = True
        step = self._step()
        label = label or tool
        await bus.emit_async("action.start",
                             {"tool": tool, "label": label, "args": _jargs(args)},
                             mission=self.mid, step=step)
        t0 = time.perf_counter()
        try:
            coro = registry.TOOLS[tool]["fn"](**args)
            result = await asyncio.wait_for(coro, timeout=timeout)
            status = "ok"
        except asyncio.TimeoutError:
            result = {"ok": False, "error": f"timeout after {timeout}s"}
            status = "timeout"
        except Exception as e:
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            status = "error"
            traceback.print_exc()
        ms = int((time.perf_counter() - t0) * 1000)
        self.actions_done += 1
        self.busy = False
        await bus.emit_async("action.end", {
            "tool": tool, "label": label, "status": status, "ms": ms,
            "summary": _summarize_result(tool, result),
        }, mission=self.mid, step=step)
        return result

    async def gather(self, *acts, label: str = "") -> list:
        """ULTRON mode: parallel actions, each still individually visible."""
        await bus.emit_async("action.batch", {"label": label, "count": len(acts)},
                             mission=self.mid)
        return list(await asyncio.gather(*acts))


def _jargs(args: dict) -> dict:
    out = {}
    for k, v in list(args.items())[:8]:
        s = str(v)
        out[k] = s if len(s) <= 160 else s[:157] + "…"
    return out


def _summarize_result(tool: str, result: Any) -> str:
    try:
        if isinstance(result, dict):
            if tool == "web_search":
                n = len(result.get("results", []))
                provs = ", ".join(f"{a['provider']}:{a['count']}" for a in result.get("attempts", []))
                return f"{n} results [{provs}]" if n else "no results"
            if tool == "fetch_page":
                if result.get("ok"):
                    words = len((result.get("text") or "").split())
                    return f"HTTP {result.get('status')} · {words} words · \"{(result.get('title') or '')[:60]}\""
                return f"fetch failed: {result.get('error', 'unknown')[:80]}"
            if tool in ("github_search",):
                return f"{len(result.get('repos', []))} repos"
            if tool == "github_issues":
                return f"{len(result.get('issues', []))} open issues"
            if tool == "github_repo":
                if result.get("ok"):
                    return f"★{result.get('stars')} · {result.get('lang')} · pushed {result.get('updated')}"
                return result.get("error", "not found")[:80]
            if tool in ("pypi_info", "npm_info"):
                if result.get("ok"):
                    return f"v{result.get('version')} · last upload {result.get('last_upload')}"
                return result.get("error", "not found")[:80]
            if tool == "run_code":
                if result.get("ok"):
                    return f"exit 0 · {result.get('ms')}ms · {len(result.get('stdout',''))}B out"
                return f"exit {result.get('exit')} · {(result.get('error') or result.get('stderr',''))[:80]}"
            if tool in ("write_file",):
                return f"wrote {result.get('bytes', 0)}B → {result.get('path')}"
            if result.get("ok") is False and result.get("error"):
                return str(result["error"])[:100]
        if isinstance(result, list):
            return f"{len(result)} items"
        return type(result).__name__
    except Exception:
        return "done"
