"""Runtime configuration — env-driven, zero-config by default."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WORKSPACE = DATA / "workspace"
SANDBOX = DATA / "sandbox"
DB_PATH = DATA / "agentuse.db"
EVENTS_LOG = DATA / "events.jsonl"

for d in (DATA, WORKSPACE, SANDBOX):
    d.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("AGENTUSE_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGENTUSE_PORT", "8000"))

# --- Neural core providers (all optional; heuristic core used if none) ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/auto")

# Generic OpenAI-compatible override (Groq/DeepSeek/Together/Ollama/LM Studio...)
CUSTOM_BASE_URL = os.environ.get("AGENTUSE_LLM_BASE_URL", "")
CUSTOM_API_KEY = os.environ.get("AGENTUSE_LLM_API_KEY", "")
CUSTOM_MODEL = os.environ.get("AGENTUSE_LLM_MODEL", "")

# GitHub token raises api.github.com rate limits (60/h anonymous -> 5000/h)
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 AgentUseBot/1.0"
)

HTTP_TIMEOUT = float(os.environ.get("AGENTUSE_HTTP_TIMEOUT", "12"))
MAX_BODY_BYTES = 3_000_000  # 3 MB cap per fetch

# Mission engine limits
MAX_STEPS = 24                 # hard cap of tool actions per mission
MAX_LLM_TURNS = 14             # ReAct turns when neural core active
FETCH_TOP_RESULTS = 3          # pages deep-read per research mission
