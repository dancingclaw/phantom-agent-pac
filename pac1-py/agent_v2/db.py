"""SQLite storage for runs and events."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path("benchmark-runs/pac1.db")


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'idle',
            concurrency INTEGER DEFAULT 5,
            model TEXT DEFAULT '',
            final_score REAL DEFAULT 0,
            started_at REAL DEFAULT 0,
            finished_at REAL DEFAULT 0,
            leaderboard_run_id TEXT,
            created_at REAL DEFAULT (unixepoch('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            trial_id TEXT DEFAULT '',
            harness_url TEXT DEFAULT '',
            instruction TEXT DEFAULT '',
            skill_id TEXT DEFAULT '',
            skill_confidence REAL DEFAULT 0,
            score REAL DEFAULT -1,
            score_detail TEXT DEFAULT '[]',
            tool_calls INTEGER DEFAULT 0,
            wall_time_ms INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            UNIQUE(run_id, task_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            task_id TEXT DEFAULT '',
            event_type TEXT NOT NULL,
            data TEXT NOT NULL,
            ts REAL DEFAULT (unixepoch('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_task ON events(run_id, task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id)")
    # Migrations
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN temperature REAL DEFAULT 1.0")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    return conn


_conn: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _get_conn()
    return _conn


# ── Runs ────────────────────────────────────────────────────


def create_run(run_id: str, concurrency: int, model: str = "", temperature: float = 1.0) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO runs (run_id, concurrency, model, started_at, temperature) VALUES (?, ?, ?, ?, ?)",
        (run_id, concurrency, model, time.time(), temperature),
    )
    db.commit()


def update_run(run_id: str, **kwargs) -> None:
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [run_id]
    db.execute(f"UPDATE runs SET {sets} WHERE run_id = ?", vals)
    db.commit()


def list_runs() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
    result = []
    for r in rows:
        run = dict(r)
        tasks = db.execute("SELECT * FROM tasks WHERE run_id = ?", (r["run_id"],)).fetchall()
        task_list = [dict(t) for t in tasks]
        for t in task_list:
            t["score_detail"] = json.loads(t["score_detail"])
        run["tasks"] = {t["task_id"]: t for t in task_list}
        scored = [t for t in task_list if t["score"] >= 0]
        run["passed"] = sum(1 for t in scored if t["score"] == 1.0)
        run["total"] = len(task_list)
        result.append(run)
    return result


def get_run(run_id: str) -> dict | None:
    db = get_db()
    r = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if not r:
        return None
    run = dict(r)
    tasks = db.execute("SELECT * FROM tasks WHERE run_id = ?", (run_id,)).fetchall()
    task_list = [dict(t) for t in tasks]
    for t in task_list:
        t["score_detail"] = json.loads(t["score_detail"])
    run["tasks"] = {t["task_id"]: t for t in task_list}
    scored = [t for t in task_list if t["score"] >= 0]
    run["passed"] = sum(1 for t in scored if t["score"] == 1.0)
    run["total"] = len(task_list)
    run["wall_time_ms"] = int((run["finished_at"] - run["started_at"]) * 1000) if run["finished_at"] else 0
    return run


# ── Tasks ───────────────────────────────────────────────────


def upsert_task(run_id: str, task_id: str, **kwargs) -> None:
    db = get_db()
    # Convert score_detail list to JSON string
    if "score_detail" in kwargs and isinstance(kwargs["score_detail"], list):
        kwargs["score_detail"] = json.dumps(kwargs["score_detail"])

    existing = db.execute(
        "SELECT 1 FROM tasks WHERE run_id = ? AND task_id = ?", (run_id, task_id)
    ).fetchone()

    if existing:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [run_id, task_id]
        db.execute(f"UPDATE tasks SET {sets} WHERE run_id = ? AND task_id = ?", vals)
    else:
        kwargs["run_id"] = run_id
        kwargs["task_id"] = task_id
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        db.execute(f"INSERT INTO tasks ({cols}) VALUES ({placeholders})", list(kwargs.values()))
    db.commit()


# ── Events ──────────────────────────────────────────────────


def insert_event(run_id: str, event_type: str, data: dict) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO events (run_id, task_id, event_type, data, ts) VALUES (?, ?, ?, ?, ?)",
        (run_id, data.get("task_id", ""), event_type, json.dumps(data), time.time()),
    )
    db.commit()


def get_events(run_id: str, task_id: str | None = None) -> list[dict]:
    db = get_db()
    if task_id:
        rows = db.execute(
            "SELECT data FROM events WHERE run_id = ? AND task_id = ? ORDER BY id",
            (run_id, task_id),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT data FROM events WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
    return [json.loads(r["data"]) for r in rows]
