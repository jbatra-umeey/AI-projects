"""SQLite checkpoint + event journal; one atomic transaction per state transition."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .domain import Run


class Store:
    def __init__(self, path: str = "data/agentloop.db"):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    stage TEXT NOT NULL, body TEXT NOT NULL, timestamp TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS memories(
                    id INTEGER PRIMARY KEY, scenario TEXT NOT NULL,
                    run_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def checkpoint(self, run: Run, events: list[tuple[str, dict]]):
        with self.connection() as conn:
            conn.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (run.id, json.dumps(run.to_dict())))
            for stage, payload in events:
                conn.execute("INSERT INTO events(run_id,stage,body,timestamp) VALUES (?,?,?,?)",
                             (run.id, stage, json.dumps(payload), datetime.now(timezone.utc).isoformat()))
            if run.status == "completed" and run.result and run.result["evaluation"]["passed"]:
                body = {"summary": run.result["summary"], "evidence_ids": run.result["evidence_ids"],
                        "source_run": run.id, "trust": "historical_hint"}
                conn.execute("INSERT OR IGNORE INTO memories(scenario,run_id,body) VALUES (?,?,?)",
                             (run.scenario, run.id, json.dumps(body)))

    def get(self, run_id: str) -> Run:
        with self.connection() as conn:
            row = conn.execute("SELECT body FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return Run(**json.loads(row["body"]))

    def events(self, run_id: str) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        return [{"seq": r["seq"], "stage": r["stage"], "payload": json.loads(r["body"]),
                 "timestamp": r["timestamp"]} for r in rows]

    def memories(self, scenario: str) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT body FROM memories WHERE scenario=? ORDER BY id DESC LIMIT 3", (scenario,)).fetchall()
        return [json.loads(r["body"]) for r in rows]

    def list_runs(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT body FROM runs ORDER BY rowid DESC LIMIT 50").fetchall()
        return [json.loads(r["body"]) for r in rows]
