"""Neural core — LLM providers with unified ReAct tool-calling.

Supported automatically from env vars (any one upgrades the system):
  XAI_API_KEY                 xAI Grok (https://api.x.ai/v1)
  OPENAI_API_KEY              (+ OPENAI_BASE_URL/OPENAI_MODEL for compat APIs:
                               Groq, DeepSeek, Together, LM Studio, Ollama…)
  ANTHROPIC_API_KEY
  GEMINI_API_KEY
  OPENROUTER_API_KEY
  AGENTUSE_LLM_BASE_URL + AGENTUSE_LLM_API_KEY + AGENTUSE_LLM_MODEL (generic)

With none set, AGENTUSE runs on the built-in heuristic core — still fully
autonomous, still internet-capable.
"""
import json
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .. import config
from ..tools.net import ssl_context

PROVIDERS: list[dict] = []  # filled by detect()


def detect() -> Optional[dict]:
    """Pick the first configured provider. Returns provider descriptor."""
    PROVIDERS.clear()
    if config.CUSTOM_BASE_URL and config.CUSTOM_MODEL:
        PROVIDERS.append({"kind": "openai", "name": f"custom:{config.CUSTOM_MODEL}",
                          "base": config.CUSTOM_BASE_URL.rstrip("/"),
                          "key": config.CUSTOM_API_KEY, "model": config.CUSTOM_MODEL})
    if config.XAI_API_KEY:
        PROVIDERS.append({"kind": "openai", "name": f"xai:{config.XAI_MODEL}",
                          "base": config.XAI_BASE_URL.rstrip("/"),
                          "key": config.XAI_API_KEY, "model": config.XAI_MODEL})
    if config.OPENAI_API_KEY:
        PROVIDERS.append({"kind": "openai", "name": f"openai:{config.OPENAI_MODEL}",
                          "base": config.OPENAI_BASE_URL.rstrip("/"),
                          "key": config.OPENAI_API_KEY, "model": config.OPENAI_MODEL})
    if config.ANTHROPIC_API_KEY:
        PROVIDERS.append({"kind": "anthropic", "name": f"anthropic:{config.ANTHROPIC_MODEL}",
                          "base": "https://api.anthropic.com/v1",
                          "key": config.ANTHROPIC_API_KEY, "model": config.ANTHROPIC_MODEL})
    if config.GEMINI_API_KEY:
        PROVIDERS.append({"kind": "gemini", "name": f"gemini:{config.GEMINI_MODEL}",
                          "base": "https://generativelanguage.googleapis.com/v1beta",
                          "key": config.GEMINI_API_KEY, "model": config.GEMINI_MODEL})
    if config.OPENROUTER_API_KEY:
        PROVIDERS.append({"kind": "openai", "name": f"openrouter:{config.OPENROUTER_MODEL}",
                          "base": "https://openrouter.ai/api/v1",
                          "key": config.OPENROUTER_API_KEY, "model": config.OPENROUTER_MODEL})
    return PROVIDERS[0] if PROVIDERS else None


def core_name() -> str:
    p = detect()
    return p["name"] if p else "heuristic-core"


def available() -> bool:
    return bool(detect())


def gemini_schemas(openai_or_anthropic: list[dict]) -> list[dict]:
    """Convert OpenAI or Anthropic tool schemas to Gemini functionDeclarations."""
    out = []
    for t in openai_or_anthropic:
        if "function" in t:  # OpenAI wrapper
            f = t["function"]
            out.append({"name": f["name"], "description": f.get("description", ""),
                        "parameters": f.get("parameters", {"type": "object", "properties": {}})})
        elif "input_schema" in t:  # Anthropic
            out.append({"name": t["name"], "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {"type": "object", "properties": {}})})
        elif "name" in t:
            out.append({"name": t["name"], "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}})})
    return out


# ---------------------------------------------------------------------------
# One unified chat-with-tools per provider kind. Returns:
#   {"text": str, "tool_calls": [{"id","name","args":dict}]}
# ---------------------------------------------------------------------------

async def chat(provider: dict, messages: list[dict], tools: list[dict],
               on_token: Optional[Callable[[str], Any]] = None) -> dict:
    kind = provider["kind"]
    if kind == "openai":
        if on_token:
            return await _chat_openai_stream(provider, messages, tools, on_token)
        return await _chat_openai(provider, messages, tools)
    if kind == "anthropic":
        return await _chat_anthropic(provider, messages, tools)
    if kind == "gemini":
        return await _chat_gemini(provider, messages, tools)
    raise ValueError(f"unknown provider kind {kind}")


async def _chat_openai(p: dict, messages: list[dict], tools: list[dict]) -> dict:
    body: dict[str, Any] = {"model": p["model"], "messages": messages}
    if tools:
        body["tools"] = tools
    async with httpx.AsyncClient(timeout=90, verify=ssl_context()) as c:
        r = await c.post(f"{p['base']}/chat/completions",
                         headers={"Authorization": f"Bearer {p['key']}"},
                         json=body)
        r.raise_for_status()
        data = r.json()
    msg = data["choices"][0]["message"]
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc["function"]
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        calls.append({"id": tc["id"], "name": fn["name"], "args": args})
    return {"text": msg.get("content") or "", "tool_calls": calls,
            "raw_message": msg}


async def _chat_openai_stream(p: dict, messages: list[dict], tools: list[dict],
                              on_token: Callable[[str], Any]) -> dict:
    """SSE token stream → thought events. Assembles tool_call deltas."""
    body: dict[str, Any] = {"model": p["model"], "messages": messages, "stream": True}
    if tools:
        body["tools"] = tools
    text_parts: list[str] = []
    tool_acc: dict[int, dict] = {}
    async with httpx.AsyncClient(timeout=90, verify=ssl_context()) as c:
        async with c.stream("POST", f"{p['base']}/chat/completions",
                            headers={"Authorization": f"Bearer {p['key']}"},
                            json=body) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except Exception:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    text_parts.append(piece)
                    maybe = on_token(piece)
                    if hasattr(maybe, "__await__"):
                        await maybe
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tool_acc.setdefault(idx, {"id": "", "name": "", "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args"] += fn["arguments"]
    calls = []
    for slot in tool_acc.values():
        try:
            args = json.loads(slot["args"] or "{}")
        except Exception:
            args = {}
        calls.append({"id": slot["id"] or slot["name"] or "call",
                      "name": slot["name"], "args": args})
    return {"text": "".join(text_parts), "tool_calls": calls}


async def _chat_anthropic(p: dict, messages: list[dict], tools: list[dict]) -> dict:
    system = ""
    msgs = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"] if isinstance(m["content"], str) else ""
        else:
            msgs.append({"role": m["role"], "content": m["content"]})
    body: dict[str, Any] = {"model": p["model"], "max_tokens": 2048,
                            "messages": msgs}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools
    async with httpx.AsyncClient(timeout=90, verify=ssl_context()) as c:
        r = await c.post(f"{p['base']}/messages",
                         headers={"x-api-key": p["key"],
                                  "anthropic-version": "2023-06-01"},
                         json=body)
        r.raise_for_status()
        data = r.json()
    text_parts, calls = [], []
    for block in data.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            calls.append({"id": block["id"], "name": block["name"],
                          "args": block.get("input", {})})
    return {"text": "\n".join(text_parts), "tool_calls": calls}


async def _chat_gemini(p: dict, messages: list[dict], tools: list[dict]) -> dict:
    contents = []
    for m in messages:
        role = m.get("role", "user")
        if role == "tool":
            contents.append({
                "role": "user",
                "parts": [{"functionResponse": {
                    "name": m.get("name") or "tool",
                    "response": {"result": m.get("content", "")}}}],
            })
            continue
        if role == "assistant":
            parts = []
            text = m.get("content")
            if isinstance(text, str) and text:
                parts.append({"text": text})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or tc
                name = fn.get("name") or tc.get("name")
                args = fn.get("arguments") or tc.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                parts.append({"functionCall": {"name": name, "args": args}})
            if not parts:
                parts = [{"text": "(calling tools)"}]
            contents.append({"role": "model", "parts": parts})
            continue
        # system + user → user
        text = m.get("content", "")
        if not isinstance(text, str):
            text = json.dumps(text, default=str)
        contents.append({"role": "user", "parts": [{"text": text}]})
    body: dict[str, Any] = {"contents": contents}
    decls = gemini_schemas(tools) if tools else []
    if decls:
        body["tools"] = [{"functionDeclarations": decls}]
    async with httpx.AsyncClient(timeout=90, verify=ssl_context()) as c:
        r = await c.post(
            f"{p['base']}/models/{p['model']}:generateContent?key={p['key']}",
            json=body)
        r.raise_for_status()
        data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    text, calls = [], []
    for part in parts:
        if "text" in part:
            text.append(part["text"])
        if "functionCall" in part:
            fc = part["functionCall"]
            calls.append({"id": fc.get("name", "call"), "name": fc["name"],
                          "args": fc.get("args", {})})
    return {"text": "\n".join(text), "tool_calls": calls}
