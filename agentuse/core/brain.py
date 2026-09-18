"""Mission orchestrator — runs every mission, fully visible on the grid.

Two cores:
  • NEURAL  (LLM ReAct loop; auto-enabled when an API key env var exists)
  • HEURISTIC (built-in planner strategies; zero keys, fully autonomous)
"""
import asyncio
import json
import time
import uuid
from collections import deque

from .. import config, store
from ..bus import bus
from ..tools import registry
from . import llm, planner
from .facade import Agent

SYSTEM_PROMPT = """You are AGENTUSE, an autonomous JARVIS/ULTRON-class grid agent.
You control real internet routes (GitHub, PyPI, npm, general web where open),
a sandboxed CodeBox (Python/JavaScript), a persistent workspace filesystem,
and long-term memory.

Operating rules:
- Be direct, technical, and concise. No filler.
- Prefer acting over describing. Use your tools to gather real data.
- You may run tools in sequence to build up an answer.
- When you have enough evidence, produce a final answer with concrete facts
  (numbers, versions, stars, dates). If routes are blocked, say exactly which.
- Missions end with either a final answer or a clear statement of blockers.
- Honor mid-run STEER messages from the operator immediately.
"""


class MissionRunner:
    def __init__(self, goal: str, mode: str = "jarvis", mid: str | None = None):
        self.mid = mid or f"m_{uuid.uuid4().hex[:8]}"
        self.goal = goal.strip()
        self.mode = mode if mode in ("jarvis", "ultron") else "jarvis"
        self.agent = Agent(self.mid, self.mode)
        self.task: asyncio.Task | None = None
        self.steers: deque[str] = deque()

    def start(self) -> str:
        use_neural = llm.available()
        core = "neural" if use_neural else "heuristic"
        store.create_mission(self.mid, self.goal, self.mode, core)
        bus.emit("mission.created", {"id": self.mid, "goal": self.goal,
                                     "mode": self.mode, "core": core})
        self.task = asyncio.get_event_loop().create_task(self._run(use_neural))
        missions[self.mid] = self
        return self.mid

    def push_steer(self, text: str) -> None:
        self.steers.append(text.strip())
        bus.emit("steer", {"text": text.strip()}, mission=self.mid)

    async def drain_steers(self) -> list[str]:
        out = []
        while self.steers:
            text = self.steers.popleft()
            out.append(text)
            await self.agent.think(f"STEER from operator: {text}")
            await bus.emit_async("steer_applied", {"text": text}, mission=self.mid)
        return out

    async def _run(self, use_neural: bool) -> None:
        t0 = time.perf_counter()
        status, summary = "done", ""
        try:
            await bus.emit_async("mission.start",
                                 {"id": self.mid, "goal": self.goal,
                                  "mode": self.mode,
                                  "core": "neural" if use_neural else "heuristic"},
                                 mission=self.mid)
            if use_neural:
                summary = await self._run_neural()
            else:
                summary = await self._run_heuristic()
        except asyncio.CancelledError:
            status, summary = "cancelled", "mission aborted by operator"
            await bus.emit_async("sys.note", {"text": "mission aborted", "level": "warn"},
                                 mission=self.mid)
        except Exception as e:
            status, summary = "failed", f"{type(e).__name__}: {e}"
            await bus.emit_async("error", {"text": summary}, mission=self.mid)
        ms = int((time.perf_counter() - t0) * 1000)
        store.finish_mission(self.mid, status, summary, self.agent.actions_done)
        await bus.emit_async("mission.end",
                             {"id": self.mid, "status": status, "ms": ms,
                              "summary": summary,
                              "actions": self.agent.actions_done},
                             mission=self.mid)
        if status == "done":
            await self.agent.say(f"Mission complete. {summary[:160]}")

    async def _run_heuristic(self) -> str:
        if self.agent.cancelled():
            return "cancelled"
        notes = store.recall(self.goal.split()[0] if self.goal.split() else "", limit=4)
        if notes:
            await self.agent.think(
                f"Recalled {len(notes)} memory note(s) matching this directive.")
        intent = planner.classify(self.goal)
        await bus.emit_async("intent", {"intent": intent, "core": "heuristic"},
                             mission=self.mid)
        await self.agent.think(
            f"Directive received. Classified as '{intent}'. Engaging heuristic core — "
            f"mode {self.mode.upper()}.")
        strat = planner.STRATEGIES.get(intent, planner.strategy_research)
        try:
            return await strat(self.agent, self.goal)
        except Exception as e:
            await bus.emit_async("error", {"text": f"strategy error: {e}"},
                                 mission=self.mid)
            raise

    async def _run_neural(self) -> str:
        provider = llm.detect()  # type: ignore[union-attr]
        schemas_oai = registry.openai_schemas()
        schemas_anthropic = registry.anthropic_schemas()
        if provider["kind"] == "anthropic":
            kind_schemas = schemas_anthropic
        elif provider["kind"] == "gemini":
            kind_schemas = schemas_anthropic  # name + input_schema → gemini_schemas()
        else:
            kind_schemas = schemas_oai

        await self.agent.plan([
            "Reason over directive (neural core)", "Execute tools as needed",
            "Deliver evidence-backed answer"])
        await self.agent.think(f"Neural core online: {provider['name']}. "
                               f"Entering ReAct loop with {len(schemas_oai)} tools.")

        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content":
                        f"MISSION: {self.goal}\nMODE: {self.mode} "
                        f"({'parallel actions allowed' if self.mode == 'ultron' else 'be careful and sequential'})"}]
        final_text = ""

        async def on_token(piece: str):
            # stream fragments as thoughts only in small batches via think is noisy;
            # emit a lightweight token event instead.
            await bus.emit_async("llm.delta", {"text": piece}, mission=self.mid)

        for turn in range(1, config.MAX_LLM_TURNS + 1):
            if self.agent.cancelled():
                return "cancelled"
            if self.agent.actions_done >= config.MAX_STEPS:
                await self.agent.think("Hit MAX_STEPS — delivering whatever evidence I have.")
                break
            steers = await self.drain_steers()
            if steers:
                messages.append({"role": "user", "content":
                                 "OPERATOR STEER:\n" + "\n".join(steers)})
            use_stream = provider["kind"] == "openai"
            resp = await llm.chat(provider, messages, kind_schemas,
                                  on_token=on_token if use_stream else None)
            if resp.get("text"):
                await self.agent.think(resp["text"][:800])
                final_text = resp["text"]
            calls = resp.get("tool_calls") or []
            if not calls:
                if final_text:
                    await self.agent.card("answer", "Neural core conclusion", text=final_text)
                return final_text[:400] or "complete"
            messages = _append_assistant(messages, provider, resp)
            for call in calls:
                if self.agent.cancelled():
                    return "cancelled"
                name, args = call["name"], call["args"]
                result = await self.agent.act(name, label=name, **args)
                messages = _append_tool_result(messages, provider, call, result)
        return final_text[:400] or "max turns reached"


def _append_assistant(messages: list, provider: dict, resp: dict) -> list:
    if provider["kind"] == "anthropic":
        content = []
        if resp.get("text"):
            content.append({"type": "text", "text": resp["text"]})
        for c in resp["tool_calls"]:
            content.append({"type": "tool_use", "id": c["id"], "name": c["name"],
                            "input": c["args"]})
        messages = messages + [{"role": "assistant", "content": content}]
    elif provider["kind"] == "openai":
        messages = messages + [{"role": "assistant",
                                "content": resp.get("text") or None,
                                "tool_calls": [
                                    {"id": c["id"], "type": "function",
                                     "function": {"name": c["name"],
                                                  "arguments": json.dumps(c["args"])}}
                                    for c in resp["tool_calls"]]}]
    else:  # gemini — keep structured tool_calls so _chat_gemini can emit functionCall parts
        messages = messages + [{"role": "assistant",
                                "content": resp.get("text") or "(calling tools)",
                                "tool_calls": resp.get("tool_calls") or []}]
    return messages


def _append_tool_result(messages: list, provider: dict, call: dict, result) -> list:
    payload = json.dumps(result, ensure_ascii=False, default=str)[:12000]
    if provider["kind"] == "anthropic":
        messages = messages + [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call["id"],
             "content": payload[:8000]}]}]
    elif provider["kind"] == "openai":
        messages = messages + [{"role": "tool", "tool_call_id": call["id"],
                                "content": payload}]
    else:  # gemini functionResponse
        messages = messages + [{"role": "tool", "name": call["name"],
                                "content": payload[:8000]}]
    return messages


missions: dict[str, MissionRunner] = {}


def launch(goal: str, mode: str = "jarvis") -> str:
    runner = MissionRunner(goal, mode)
    return runner.start()


def cancel(mid: str) -> bool:
    if store.cancel_mission(mid):
        runner = missions.get(mid)
        if runner and runner.task and not runner.task.done():
            runner.task.cancel()
        return True
    return False


def steer(mid: str, text: str) -> bool:
    runner = missions.get(mid)
    if not runner or not runner.task or runner.task.done():
        return False
    runner.push_steer(text)
    return True
