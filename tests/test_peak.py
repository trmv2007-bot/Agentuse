"""Peak-grid unit tests — no live internet required."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AGENTUSE_HOST", "127.0.0.1")

from agentuse.core import llm, planner
from agentuse.tools import files, registry
from agentuse import config, store


def test_version():
    assert config.VERSION == "2.0.0"
    from agentuse import __version__
    assert __version__ == "2.0.0"


def test_classify_playbooks():
    assert planner.classify("status report") == "status"
    assert planner.classify("https://example.com summarize") == "url_digest"
    assert planner.classify("fastapi pypi") == "package_intel"
    assert planner.classify("npm package express") == "package_intel"
    assert planner.classify("calculate (2+3)*14/5") == "code_task"
    assert planner.classify("compare top python agent frameworks on github") == "github_research"
    assert planner.classify("help") == "help"


def test_tool_schemas_mark_required():
    schemas = {s["function"]["name"]: s["function"]["parameters"]["required"]
               for s in registry.openai_schemas()}
    assert "query" in schemas["web_search"]
    assert "url" in schemas["fetch_page"]
    assert "query" in schemas["github_search"]
    assert "full_name" in schemas["github_repo"]
    assert "full_name" in schemas["github_issues"]
    assert "package" in schemas["pypi_info"]
    assert "code" in schemas["run_code"]
    assert "github_issues" in registry.TOOLS
    assert len(registry.TOOLS) >= 14


def test_gemini_schema_converter():
    decls = llm.gemini_schemas(registry.openai_schemas())
    names = {d["name"] for d in decls}
    assert "web_search" in names
    assert "parameters" in decls[0]


def test_xai_detect(monkeypatch):
    monkeypatch.setattr(config, "CUSTOM_BASE_URL", "")
    monkeypatch.setattr(config, "CUSTOM_MODEL", "")
    monkeypatch.setattr(config, "XAI_API_KEY", "xai-test")
    monkeypatch.setattr(config, "XAI_MODEL", "grok-4")
    monkeypatch.setattr(config, "XAI_BASE_URL", "https://api.x.ai/v1")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    p = llm.detect()
    assert p is not None
    assert p["kind"] == "openai"
    assert p["name"].startswith("xai:")
    assert p["base"] == "https://api.x.ai/v1"


def test_workspace_jail(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "ROOT", tmp_path.resolve())
    files.write_file("hello.md", "# hi")
    got = files.read_file("hello.md")
    assert got["ok"] and "hi" in got["content"]
    try:
        files.read_file("../etc/passwd")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_memory_fts_roundtrip(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    store._conn = None
    store._fts = False
    store.remember("fact", "AGENTUSE peak grid uses grok-4 as the xAI default")
    hits = store.recall("grok")
    assert any("grok" in (h.get("content") or "").lower() for h in hits)


def test_api_state_and_artifact():
    from fastapi.testclient import TestClient
    from agentuse.server import app
    files.write_file("reports/peak.md", "# peak\nhello grid")
    with TestClient(app) as c:
        r = c.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert body["app"] == "AGENTUSE"
        assert body["version"] == "2.0.0"
        assert "github_issues" in registry.TOOLS
        a = c.get("/api/artifact", params={"path": "reports/peak.md"})
        assert a.status_code == 200
        assert "hello grid" in a.json()["content"]
        missing = c.get("/api/artifact", params={"path": "nope.md"})
        assert missing.status_code == 404
        bad = c.get("/api/artifact", params={"path": "../etc/passwd"})
        assert bad.status_code == 400
        docs = c.get("/api/docs")
        assert docs.status_code == 200


def test_token_gate(monkeypatch):
    from fastapi.testclient import TestClient
    import agentuse.server as server
    monkeypatch.setattr(config, "TOKEN", "secret-grid")
    with TestClient(server.app) as c:
        denied = c.get("/api/state")
        assert denied.status_code == 401
        ok = c.get("/api/state", headers={"x-agentuse-token": "secret-grid"})
        assert ok.status_code == 200
    monkeypatch.setattr(config, "TOKEN", "")
