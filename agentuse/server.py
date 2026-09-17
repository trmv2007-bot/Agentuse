"""AGENTUSE server — WebSocket event stream + REST control + SpaceGrid UI."""
import asyncio
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, store
from .bus import bus
from .core import brain, llm
from .tools import files, net, registry

app = FastAPI(title="AGENTUSE", docs_url="/api/docs")
BOOT_TS = time.time()


@app.on_event("startup")
async def startup() -> None:
    bus.bind_loop(asyncio.get_event_loop())
    # continue the global event sequence across restarts (sqlite is source of truth)
    bus._seq = store.max_seq()

    async def initial_probe() -> None:
        await asyncio.sleep(0.4)
        await bus.emit_async("sys.note", {"text": "net-probe: mapping network routes…"})
        routes = await net.probe_all()
        for r in routes:
            await bus.emit_async("net.route", r)
        live = [r for r in routes if r["status"] == "live"]
        await bus.emit_async("sys.note", {
            "text": f"net-probe complete: {len(live)}/{len(routes)} routes live",
            "level": "info" if live else "warn"})
        store.remember("boot", f"net probe: {len(live)}/{len(routes)} live: "
                               f"{', '.join(r['id'] for r in live)}")
    asyncio.get_event_loop().create_task(initial_probe())


class MissionIn(BaseModel):
    goal: str
    mode: str = "jarvis"


class ExecIn(BaseModel):
    code: str
    lang: str = "python"


@app.post("/api/missions")
async def create_mission(body: MissionIn):
    goal = body.goal.strip()
    if not goal:
        return JSONResponse({"error": "goal required"}, status_code=400)
    if len(goal) > 4000:
        return JSONResponse({"error": "goal too long"}, status_code=400)
    mid = brain.launch(goal, body.mode)
    return {"id": mid, "status": "launched"}


@app.post("/api/missions/{mid}/cancel")
async def cancel_mission(mid: str):
    ok = brain.cancel(mid)
    return {"id": mid, "cancelled": ok}


@app.get("/api/state")
async def state():
    p = llm.detect()
    return {
        "app": "AGENTUSE",
        "version": "1.0.0",
        "uptime": int(time.time() - BOOT_TS),
        "core": {"kind": "neural" if p else "heuristic",
                 "provider": p["name"] if p else "built-in planner",
                 "tools": len(brain.registry.TOOLS) if hasattr(brain, "registry") else None},
        "netmap": net.route_state(),
        "missions": store.list_missions(40),
        "artifacts": files.list_files(),
        "stats": store.stats(),
        "seq": bus.seq,
    }


@app.get("/api/events")
async def events(after: int = 0):
    return {"events": store.load_events(after=after)}


@app.post("/api/netmap/probe")
async def probe():
    routes = await net.probe_all()
    for r in routes:
        await bus.emit_async("net.route", r)
    return {"routes": routes}


@app.post("/api/exec")
async def direct_exec(body: ExecIn):
    """Manual CodeBox execution — also fully visible on the grid."""
    from .tools.codebox import run_code
    ev = await bus.emit_async("action.start", {"tool": "run_code", "label": "manual exec",
                                               "args": {"lang": body.lang}})
    res = await run_code(body.code, body.lang)
    await bus.emit_async("action.end", {"tool": "run_code", "label": "manual exec",
                                        "status": "ok" if res.get("ok") else "error",
                                        "ms": res.get("ms", 0),
                                        "summary": f"exit {res.get('exit')}",
                                        "mission": None})
    return res


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"type": "hello", "payload": {
        "seq": bus.seq, "core": llm.core_name(),
        "neural": llm.available()}})
    sid, q = bus.subscribe()
    try:
        # replay recent history since client's last known seq (client sends after hello)
        replay_req = await ws.receive_json()
        after = int(replay_req.get("after", 0))
        for ev in store.load_events(after=after, limit=800, newest=True):
            await ws.send_json(ev)
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=15)
                await ws.send_json(ev)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "payload": {"t": time.time()}})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        bus.unsubscribe(sid)


app.mount("/", StaticFiles(directory=str(config.ROOT / "static"), html=True),
          name="static")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")


if __name__ == "__main__":
    main()
