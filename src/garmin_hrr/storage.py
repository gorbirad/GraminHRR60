"""Prosty storage wyników HRR60 w SQLite."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .hrr_calculator import HRRResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    activity_name TEXT,
    start_time TEXT,
    t0 TEXT NOT NULL,
    hr_at_t0 INTEGER NOT NULL,
    t1 TEXT NOT NULL,
    hr_at_t1 REAL NOT NULL,
    hrr60 REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class ActivityRecord:
    activity_id: str
    source: str
    activity_name: str | None
    start_time: str | None
    result: HRRResult


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save_result(self, record: ActivityRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO activities
                    (activity_id, source, activity_name, start_time,
                     t0, hr_at_t0, t1, hr_at_t1, hrr60, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id) DO UPDATE SET
                    source=excluded.source,
                    activity_name=excluded.activity_name,
                    start_time=excluded.start_time,
                    t0=excluded.t0,
                    hr_at_t0=excluded.hr_at_t0,
                    t1=excluded.t1,
                    hr_at_t1=excluded.hr_at_t1,
                    hrr60=excluded.hrr60,
                    created_at=excluded.created_at
                """,
                (
                    record.activity_id,
                    record.source,
                    record.activity_name,
                    record.start_time,
                    record.result.t0.isoformat(),
                    record.result.hr_at_t0,
                    record.result.t1.isoformat(),
                    record.result.hr_at_t1,
                    record.result.hrr60,
                    datetime.utcnow().isoformat(),
                ),
            )

    def list_activities(self) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM activities ORDER BY start_time DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_activity(self, activity_id: str) -> dict | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM activities WHERE activity_id = ?", (activity_id,)
            ).fetchone()
            return dict(row) if row else None
