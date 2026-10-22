"""SQLite storage: conversations, messages, audit log, settings, pending confirmations, long-term memory.
One connection per call (thread-safe with FastAPI's thread pool). Schema is created on open."""
import contextlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, conv_id TEXT NOT NULL, role TEXT NOT NULL,
  content TEXT NOT NULL, meta TEXT, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_messages_conv ON messages(conv_id, id);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT NOT NULL, conv_id TEXT, tool TEXT NOT NULL,
  status TEXT NOT NULL, permission TEXT, args_summary TEXT, result_summary TEXT, ms INTEGER);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pending (id TEXT PRIMARY KEY, conv_id TEXT NOT NULL, tool TEXT NOT NULL, args TEXT NOT NULL,
  call_id TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, decided_at TEXT);
CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, text TEXT NOT NULL, source TEXT NOT NULL, at TEXT NOT NULL);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextlib.contextmanager
    def _conn(self):
        """Commit on success, roll back on error, always close."""
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    # messages
    def add_message(self, conv_id, role, content, meta=None):
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO messages(conv_id, role, content, meta, at) VALUES (?,?,?,?,?)",
                      (conv_id, role, content, json.dumps(meta or {}), now()))

    def messages(self, conv_id, limit=200):
        with self._conn() as c:
            rows = c.execute("SELECT role, content, meta, at FROM messages WHERE conv_id=? ORDER BY id DESC LIMIT ?",
                             (conv_id, limit)).fetchall()
        return [dict(r, meta=json.loads(r["meta"] or "{}")) for r in reversed(rows)]

    # audit (never secrets: callers pass summaries only)
    def audit(self, tool, status, conv_id=None, permission=None, args_summary="", result_summary="", ms=None):
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO audit(at, conv_id, tool, status, permission, args_summary, result_summary, ms) "
                      "VALUES (?,?,?,?,?,?,?,?)", (now(), conv_id, tool, status, permission,
                                                   args_summary[:500], result_summary[:500], ms))

    def audit_log(self, limit=100):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

    # settings
    def get_setting(self, key, default=None):
        with self._conn() as c:
            r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def set_setting(self, key, value):
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, json.dumps(value)))

    # pending confirmations
    def add_pending(self, conv_id, tool, args, call_id=None):
        pid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO pending(id, conv_id, tool, args, call_id, status, created_at) VALUES (?,?,?,?,?,?,?)",
                      (pid, conv_id, tool, json.dumps(args), call_id, "pending", now()))
        return pid

    def get_pending(self, pid):
        with self._conn() as c:
            r = c.execute("SELECT * FROM pending WHERE id=?", (pid,)).fetchone()
        return dict(r, args=json.loads(r["args"])) if r else None

    def open_pending(self):
        with self._conn() as c:
            return [dict(r, args=json.loads(r["args"]))
                    for r in c.execute("SELECT * FROM pending WHERE status='pending' ORDER BY created_at")]

    def decide_pending(self, pid, status):
        """Atomically move pending → approved/rejected. Returns False if it was not pending (no double execution)."""
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE pending SET status=?, decided_at=? WHERE id=? AND status='pending'",
                            (status, now(), pid))
            return cur.rowcount == 1

    # long-term memory
    def add_memory(self, text, source):
        with self._lock, self._conn() as c:
            cur = c.execute("INSERT INTO memory(text, source, at) VALUES (?,?,?)", (text, source, now()))
            return cur.lastrowid

    def memories(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM memory ORDER BY id")]

    def delete_memory(self, mid):
        with self._lock, self._conn() as c:
            return c.execute("DELETE FROM memory WHERE id=?", (mid,)).rowcount == 1
