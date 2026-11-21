import os
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Iterator, TypeVar

from pydantic import BaseModel

from .models import Activity, utc_now

Record = TypeVar("Record", bound=BaseModel)


class Store:
    def __init__(self, path: Path, retention_days: int):
        self.path = path
        self.retention_days = retention_days
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError:
            pass
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA secure_delete=ON")
            db.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    bucket TEXT NOT NULL,
                    id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (bucket, id)
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS records_by_date ON records(bucket, created_at DESC)")
        self.prune()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, bucket: str, key: str, item: BaseModel, db: sqlite3.Connection | None = None) -> None:
        params = bucket, key, utc_now().isoformat(), item.model_dump_json()
        query = """
            INSERT INTO records VALUES (?, ?, ?, ?)
            ON CONFLICT(bucket, id) DO UPDATE SET payload=excluded.payload
        """
        if db is not None:
            db.execute(query, params)
        else:
            with self.connect() as connection:
                connection.execute(query, params)

    def get(self, bucket: str, key: str, model: type[Record]) -> Record | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM records WHERE bucket=? AND id=?", (bucket, key)).fetchone()
        return model.model_validate_json(row[0]) if row else None

    def list(self, bucket: str, model: type[Record], limit: int = 100) -> list[Record]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM records WHERE bucket=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (bucket, limit),
            ).fetchall()
        return [model.model_validate_json(row[0]) for row in rows]

    def prune(self) -> None:
        cutoff = (utc_now() - timedelta(days=self.retention_days)).isoformat()
        with self.connect() as db:
            db.execute("DELETE FROM records WHERE bucket NOT IN ('meeting', 'demo_meeting') AND created_at < ?", (cutoff,))

    def clear_history(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("DELETE FROM records WHERE bucket NOT IN ('meeting', 'demo_meeting')")

    def event(self, kind: str, title: str, detail: str) -> None:
        activity = Activity(kind=kind, title=title, detail=detail)
        self.put("activity", activity.id, activity)
