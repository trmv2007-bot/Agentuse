"""Event bus — every single thing the system does flows through here.

Events are: broadcast to all WebSocket clients (the SpaceGrid), appended to
data/events.jsonl, and persisted to SQLite for replay/history.
"""
import asyncio
import json
import threading
import time
from typing import AsyncIterator, Dict, List, Optional

from . import config


class Bus:
    def __init__(self) -> None:
        self._subs: Dict[int, asyncio.Queue] = {}
        self._sid = 0
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.listeners = []  # sync callbacks (e.g. stats counters)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---- subscription ----
    def subscribe(self) -> (int, asyncio.Queue):
        self._sid += 1
        q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._subs[self._sid] = q
        return self._sid, q

    def unsubscribe(self, sid: int) -> None:
        self._subs.pop(sid, None)

    # ---- emission ----
    def emit(self, type_: str, payload: dict | None = None,
             mission: str | None = None, step: int | None = None) -> dict:
        with self._seq_lock:
            self._seq += 1
            seq = self._seq
        event = {
            "seq": seq,
            "ts": time.time(),
            "mission": mission,
            "step": step,
            "type": type_,
            "payload": payload or {},
        }
        line = json.dumps(event, ensure_ascii=False, default=str)
        try:
            with open(config.EVENTS_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        try:
            from . import store
            store.save_event(event)
        except Exception:
            pass
        for fn in self.listeners:
            try:
                fn(event)
            except Exception:
                pass
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)
        return event

    async def emit_async(self, type_: str, payload: dict | None = None,
                         mission: str | None = None, step: int | None = None) -> dict:
        return self.emit(type_, payload, mission, step)

    async def _broadcast(self, event: dict) -> None:
        dead = []
        for sid, q in self._subs.items():
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(sid)
        for sid in dead:
            self.unsubscribe(sid)

    @property
    def seq(self) -> int:
        return self._seq

    async def stream(self) -> AsyncIterator[dict]:
        sid, q = self.subscribe()
        try:
            while True:
                ev = await q.get()
                yield ev
        finally:
            self.unsubscribe(sid)


bus = Bus()
