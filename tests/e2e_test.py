"""E2E driver: connect WS, launch missions, print the event stream."""
import asyncio
import json
import sys

import httpx
import websockets

BASE = "http://localhost:8000"


async def run_mission(goal: str, mode: str = "jarvis", timeout: float = 150):
    print(f"\n{'='*78}\nMISSION: {goal}  [{mode}]\n{'='*78}")
    seen = set()
    async with websockets.connect(f"ws://localhost:8000/ws") as ws:
        await ws.recv()  # hello
        await ws.send(json.dumps({"after": 0}))
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{BASE}/api/missions",
                             json={"goal": goal, "mode": mode})
            mid = r.json()["id"]
        print(f"  → {mid}")
        end = False
        try:
            while not end:
                ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if ev.get("type") in ("hello", "ping"):
                    continue
                if ev["seq"] in seen:
                    continue
                seen.add(ev["seq"])
                if ev.get("mission") not in (None, mid):
                    continue
                t, p = ev["type"], ev.get("payload", {})
                if t == "thought":
                    print(f"  💭 {p['text'][:120]}")
                elif t == "plan":
                    for i, s in enumerate(p["steps"], 1):
                        print(f"  □ step {i}: {s}")
                elif t == "action.start":
                    print(f"  ⚙ START {p['tool']:14} {p.get('label','')[:60]}")
                elif t == "action.end":
                    print(f"  ⚙ END   {p['tool']:14} [{p['status']}] {p['ms']}ms — {p['summary'][:90]}")
                elif t == "card":
                    print(f"  ▣ CARD  {p.get('kind'):8} {p.get('title','')[:80]}")
                elif t == "artifact":
                    print(f"  📄 ARTIFACT {p['path']} ({p['bytes']}B)")
                elif t == "speech":
                    print(f"  🔊 {p['text'][:120]}")
                elif t == "mission.end":
                    print(f"  ◼ END   [{p['status']}] {p['ms']}ms — {p['summary'][:140]}")
                    end = True
                elif t == "error":
                    print(f"  ✗ ERROR {p['text'][:140]}")
        except asyncio.TimeoutError:
            print("  ! timeout waiting for mission end")


async def main():
    goals = sys.argv[1:] or ["status report"]
    for g in goals:
        mode = "ultron" if "--ultron" in g else "jarvis"
        await run_mission(g.replace("--ultron", "").strip(), mode)

asyncio.run(main())
