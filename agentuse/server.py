"""AGENTUSE server — WebSocket event stream + REST control + SpaceGrid UI."""
import asyncio
import time
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from . import config, store
from .bus import bus
from .core import brain, llm
from .tools import files, net, registry

app = FastAPI(title="AGENTUSE", version=config.VERSION, docs_url="/api/docs")
BOOT_TS = time.time()


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if config.TOKEN:
            path = request.url.path
            open_paths = path.startswith("/api/docs") or path.startswith("/openapi") or path == "/redoc"
            is_ws = path == "/ws"
            if not open_paths and request.method != "OPTIONS":
                supplied = request.headers.get("x-agentuse-token") or request.query_params.get("token") or ""
                if supplied != config.TOKEN:
                    if is_ws:
                        return JSONResponse({"error": "unauthorized"}, status_code=401)
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Agentuse-Version"] = config.VERSION
        return response


app.add_middleware(SecurityHeaders)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    bus.bind_loop(asyncio.get_event_loop())
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


class SteerIn(BaseModel):
    text: str


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


@app.post("/api/missions/{mid}/steer")
async def steer_mission(mid: str, body: SteerIn):
    text = (body.text or "").strip()
    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)
    ok = brain.steer(mid, text)
    if not ok:
        return JSONResponse({"error": "mission not running"}, status_code=404)
    return {"id": mid, "steered": True}


@app.get("/api/state")
async def state():
    p = llm.detect()
    return {
        "app": "AGENTUSE",
        "version": config.VERSION,
        "uptime": int(time.time() - BOOT_TS),
        "core": {"kind": "neural" if p else "heuristic",
                 "provider": p["name"] if p else "built-in planner",
                 "tools": len(registry.TOOLS)},
        "netmap": net.route_state(),
        "missions": store.list_missions(40),
        "artifacts": files.list_files(),
        "stats": store.stats(),
        "seq": bus.seq,
        "auth": bool(config.TOKEN),
    }


@app.get("/api/events")
async def events(after: int = 0):
    return {"events": store.load_events(after=after)}


@app.get("/api/artifact")
async def get_artifact(path: str = Query(..., min_length=1)):
    try:
        res = files.read_file(path)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    if not res.get("ok"):
        return JSONResponse(res, status_code=404)
    return res


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
    await bus.emit_async("action.start", {"tool": "run_code", "label": "manual exec",
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
    if config.TOKEN:
        qtoken = ws.query_params.get("token", "")
        hdr = ws.headers.get("x-agentuse-token", "")
        if qtoken != config.TOKEN and hdr != config.TOKEN:
            await ws.close(code=1008)
            return
    await ws.accept()
    await ws.send_json({"type": "hello", "payload": {
        "seq": bus.seq, "core": llm.core_name(),
        "neural": llm.available(), "version": config.VERSION}})
    sid, q = bus.subscribe()
    try:
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
