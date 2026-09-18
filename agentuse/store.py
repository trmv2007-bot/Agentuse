"""SQLite-backed persistent memory: missions + events + FTS5 notes."""
import json
import sqlite3
import threading
import time
from typing import Any, List, Optional

from . import config

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None
_fts = False


def _get() -> sqlite3.Connection:
    global _conn, _fts
    if _conn is None:
        _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS missions(
                id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'jarvis',
                status TEXT NOT NULL DEFAULT 'queued',
                core TEXT NOT NULL DEFAULT 'heuristic',
                summary TEXT DEFAULT '',
                steps_done INTEGER DEFAULT 0,
                created REAL, finished REAL
            );
            CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, mission TEXT, step INTEGER, type TEXT, payload TEXT
            );
            CREATE TABLE IF NOT EXISTS notes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, mission TEXT, kind TEXT, content TEXT
            );
            """
        )
        try:
            _conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts "
                "USING fts5(content, kind, mission, content='notes', content_rowid='id')"
            )
            _conn.execute(
                "CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN "
                "INSERT INTO notes_fts(rowid, content, kind, mission) "
                "VALUES (new.id, new.content, new.kind, new.mission); END;"
            )
            _fts = True
        except sqlite3.OperationalError:
            _fts = False
        _conn.commit()
    return _conn


def create_mission(mid: str, goal: str, mode: str, core: str) -> None:
    with _lock:
        _get().execute(
            "INSERT INTO missions(id, goal, mode, status, core, created) VALUES(?,?,?,?,?,?)",
            (mid, goal, mode, "running", core, time.time()))
        _get().commit()


def finish_mission(mid: str, status: str, summary: str = "", steps_done: int = 0) -> None:
    with _lock:
        _get().execute(
            "UPDATE missions SET status=?, summary=?, steps_done=?, finished=? WHERE id=?",
            (status, summary[:4000], steps_done, time.time(), mid))
        _get().commit()


def cancel_mission(mid: str) -> bool:
    with _lock:
        c = _get().execute(
            "UPDATE missions SET status='cancel-requested' WHERE id=? AND status='running'",
            (mid,))
        _get().commit()
    return c.rowcount > 0


def mission_status(mid: str) -> Optional[str]:
    with _lock:
        row = _get().execute("SELECT status FROM missions WHERE id=?", (mid,)).fetchone()
    return row["status"] if row else None


def list_missions(limit: int = 60) -> List[dict]:
    with _lock:
        rows = _get().execute(
            "SELECT * FROM missions ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def save_event(ev: dict) -> None:
    with _lock:
        _get().execute(
            "INSERT OR REPLACE INTO events(seq, ts, mission, step, type, payload) VALUES(?,?,?,?,?,?)",
            (ev["seq"], ev["ts"], ev["mission"], ev["step"], ev["type"],
             json.dumps(ev["payload"], ensure_ascii=False, default=str)))
        _get().commit()


def load_events(after: int = 0, limit: int = 5000, newest: bool = False) -> List[dict]:
    order = "DESC" if newest else "ASC"
    with _lock:
        rows = _get().execute(
            f"SELECT * FROM events WHERE seq > ? ORDER BY seq {order} LIMIT ?",
            (after, limit)).fetchall()
    rows = list(rows)[::-1] if newest else rows
    out = []
    for r in rows:
        try:
            payload = json.loads(r["payload"])
        except Exception:
            payload = {}
        out.append({"seq": r["seq"], "ts": r["ts"], "mission": r["mission"],
                    "step": r["step"], "type": r["type"], "payload": payload})
    return out


def remember(kind: str, content: str, mission: Optional[str] = None) -> None:
    with _lock:
        _get().execute("INSERT INTO notes(ts, mission, kind, content) VALUES(?,?,?,?)",
                       (time.time(), mission, kind, content[:8000]))
        _get().commit()


def recall(query: str = "", limit: int = 12) -> List[dict]:
    with _lock:
        c = _get()
        if query and _fts:
            try:
                rows = c.execute(
                    "SELECT n.* FROM notes n JOIN notes_fts f ON n.id = f.rowid "
                    "WHERE notes_fts MATCH ? ORDER BY n.id DESC LIMIT ?",
                    (query, limit)).fetchall()
                if rows:
                    return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        if query:
            rows = c.execute(
                "SELECT * FROM notes WHERE content LIKE ? OR kind LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with _lock:
        c = _get()
        m_total = c.execute("SELECT COUNT(*) n FROM missions").fetchone()["n"]
        m_done = c.execute("SELECT COUNT(*) n FROM missions WHERE status='done'").fetchone()["n"]
        ev_total = c.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]
        actions = c.execute("SELECT COUNT(*) n FROM events WHERE type='action.end'").fetchone()["n"]
    return {"missions_total": m_total, "missions_done": m_done,
            "events_total": ev_total, "actions_total": actions}


def max_seq() -> int:
    with _lock:
        row = _get().execute("SELECT COALESCE(MAX(seq), 0) m FROM events").fetchone()
    return row["m"]
