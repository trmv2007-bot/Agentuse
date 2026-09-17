#!/usr/bin/env python3
"""AGENTUSE launcher — boots the SpaceGrid + agent core.

  python run.py            # http://localhost:8000
  PORT=9000 python run.py
"""
import uvicorn

from agentuse import config
from agentuse.server import app

if __name__ == "__main__":
    print(f"""
    ╔══════════════════════════════════════════════╗
    ║   A G E N T U S E  —  Autonomous Grid        ║
    ║   Intelligence · JARVIS/ULTRON class         ║
    ║                                              ║
    ║   SpaceGrid  →  http://localhost:{config.PORT:<6}      ║
    ║   Core       →  heuristic (add API key to    ║
    ║                 upgrade to neural ReAct)     ║
    ╚══════════════════════════════════════════════╝
""")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")
