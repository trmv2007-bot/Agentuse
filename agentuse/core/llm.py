"""Neural core — LLM providers with unified ReAct tool-calling.

Supported automatically from env vars (any one upgrades the system):
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
from typing import Any, Optional

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


# ---------------------------------------------------------------------------
# One unified chat-with-tools per provider kind. Returns:
#   {"text": str, "tool_calls": [{"id","name","args":dict}]}
# ---------------------------------------------------------------------------

async def chat(provider: dict, messages: list[dict], tools: list[dict]) -> dict:
    kind = provider["kind"]
    if kind == "openai":
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


async def _chat_anthropic(p: dict, messages: list[dict], tools: list[dict]) -> dict:
    system = ""
    msgs = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
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
        role = "user" if m["role"] in ("system", "user") else "model"
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
    body: dict[str, Any] = {"contents": contents}
    if tools:
        body["tools"] = [{"functionDeclarations": [
            {"name": t["name"], "description": t["description"],
             "parameters": t["input_schema"]} for t in tools]}]
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
