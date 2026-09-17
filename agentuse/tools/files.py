"""Workspace files — the agent's persistent territory on the grid.
All paths are confined to data/workspace."""
from pathlib import Path

from .. import config

ROOT = config.WORKSPACE.resolve()


def _safe(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if not str(p).startswith(str(ROOT)):
        raise ValueError("path escapes workspace")
    return p


def write_file(rel: str, content: str) -> dict:
    p = _safe(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": rel, "bytes": len(content.encode("utf-8"))}


def read_file(rel: str, max_chars: int = 60000) -> dict:
    p = _safe(rel)
    if not p.exists():
        return {"ok": False, "error": "not found", "path": rel}
    return {"ok": True, "path": rel, "content": p.read_text(encoding="utf-8",
            errors="replace")[:max_chars]}


def list_files(sub: str = "") -> list[dict]:
    base = _safe(sub) if sub else ROOT
    if not base.exists():
        return []
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            st = p.stat()
            out.append({"path": str(p.relative_to(ROOT)), "bytes": st.st_size,
                        "modified": int(st.st_mtime)})
    return out[:200]
