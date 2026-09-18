"""AGENTUSE — Autonomous Grid Intelligence.

A JARVIS/ULTRON-class agent system with live internet control,
full transparency (every thought & action is streamed to the SpaceGrid),
and pluggable neural cores (xAI Grok / OpenAI / Anthropic / Gemini /
OpenRouter / any OpenAI-compatible endpoint) with a fully autonomous
heuristic core that works with zero API keys.
"""

from .config import VERSION as __version__

APP_NAME = "AGENTUSE"
TAGLINE = "AUTONOMOUS GRID INTELLIGENCE"

__all__ = ["__version__", "APP_NAME", "TAGLINE"]
