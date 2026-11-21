"""Consent-gated outbox for a future approved enterprise event adapter."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from random import uniform
import sqlite3
from time import time
from typing import Literal, Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class SyncEvent(BaseModel):
    """Only enum outcomes are accepted, avoiding free-form telemetry or employee content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    occurred_at: AwareDatetime
    kind: Literal["preflight_completed", "connectivity_changed", "local_action_completed"]
    outcome: Literal["ready", "attention", "unknown", "offline", "connected", "verified", "failed"]


class SyncAdapter(Protocol):
    async def send(self, event: SyncEvent, *, idempotency_key: str) -> None:
        """Return on acknowledgement; the receiver must deduplicate by idempotency_key."""
        ...


class SyncStatus(BaseModel):
    configured: bool
    state: Literal["not_configured", "idle", "pending", "retry_wait", "synced", "needs_attention"]
    pending_events: int
    failed_events: int
    last_sync_at: AwareDatetime | None


class LocalSyncService:
    def __init__(
        self,
        *,
        db_path: str | Path,
        retention_days: int = 7,
        adapter: SyncAdapter | None = None,
        max_attempts: int = 5,
        base_backoff: float = 8,
        timeout: float = 6,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.close(os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError:
            pass
        self.retention_seconds = max(1, retention_days) * 86_400
        self.adapter = adapter
        self.max_attempts = max(1, max_attempts)
        self.base_backoff = max(1.0, base_backoff)
        self.timeout = max(timeout, 0.1)
        self._lock = asyncio.Lock()
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sync_events (
                    id TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    occurred_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_at REAL NOT NULL,
                    lease_until REAL NOT NULL DEFAULT 0,
                    lease_token TEXT,
                    sent_at REAL
                );
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_sync_at REAL NOT NULL
                );
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _prune(self, db: sqlite3.Connection, now: float) -> None:
        db.execute("DELETE FROM sync_events WHERE occurred_at < ? AND lease_until <= ?",
                   (now - self.retention_seconds, now))

    def enqueue(self, event: SyncEvent, *, authorized: bool = False) -> bool:
        """Queue an explicitly authorized event for a configured adapter."""
        if self.adapter is None or not authorized:
            return False
        now = time()
        occurred_at = event.occurred_at.timestamp()
        if not now - self.retention_seconds <= occurred_at <= now + 60:
            return False
        with self._db() as db:
            self._prune(db, now)
            cursor = db.execute("""
                INSERT OR IGNORE INTO sync_events (id, body, occurred_at, next_at)
                VALUES (?, ?, ?, ?)
            """, (str(event.id), event.model_dump_json(), occurred_at, now))
            return cursor.rowcount == 1

    def status(self) -> SyncStatus:
        now = time()
        with self._db() as db:
            self._prune(db, now)
            row = db.execute("""
                WITH unresolved AS (
                    SELECT next_at, lease_until, (attempts < ? OR lease_until > ?) AS can_progress
                    FROM sync_events WHERE sent_at IS NULL
                )
                SELECT COUNT(CASE WHEN can_progress THEN 1 END) AS pending,
                       COUNT(CASE WHEN NOT can_progress THEN 1 END) AS failed,
                       MIN(CASE WHEN can_progress THEN MAX(lease_until, next_at) END) AS earliest
                FROM unresolved
            """, (self.max_attempts, now)).fetchone()
            last = db.execute("SELECT last_sync_at FROM sync_metadata WHERE id = 1").fetchone()
        state: Literal["not_configured", "idle", "pending", "retry_wait", "synced", "needs_attention"]
        if self.adapter is None:
            state = "not_configured"
        elif row["pending"]:
            state = "pending" if row["earliest"] <= now else "retry_wait"
        elif row["failed"]:
            state = "needs_attention"
        else:
            state = "synced" if last else "idle"
        return SyncStatus(
            configured=self.adapter is not None, state=state, pending_events=row["pending"],
            failed_events=row["failed"], last_sync_at=datetime.fromtimestamp(last[0], timezone.utc) if last else None,
        )

    def clear(self) -> None:
        with self._db() as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("DELETE FROM sync_events")
            db.execute("DELETE FROM sync_metadata")

    def _claim(self, now: float) -> tuple[SyncEvent, str, float] | None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._prune(db, now)
            picked = db.execute("""
                SELECT id, body, attempts FROM sync_events
                WHERE sent_at IS NULL AND attempts < ? AND next_at <= ? AND lease_until <= ?
                ORDER BY occurred_at, id LIMIT 1
            """, (self.max_attempts, now, now)).fetchone()
            if picked is None:
                return None
            token = str(uuid4())
            delay = min(600.0, self.base_backoff * 2 ** min(picked["attempts"], 12)) * uniform(0.8, 1.2)
            # Count the attempt in the same transaction as the lease so a restart cannot reset the budget.
            db.execute("""
                UPDATE sync_events
                SET attempts = attempts + 1, next_at = ?, lease_token = ?, lease_until = ?
                WHERE id = ?
            """, (now + delay, token, now + self.timeout + 5, picked["id"]))
            return SyncEvent.model_validate_json(picked["body"]), token, delay

    def _complete(self, event: SyncEvent, token: str, delay: float, success: bool) -> None:
        now = time()
        with self._db() as db:
            if success:
                row = db.execute("""
                    UPDATE sync_events SET sent_at = ?, lease_until = 0, lease_token = NULL
                    WHERE id = ? AND lease_token = ?
                """, (now, str(event.id), token))
                if row.rowcount:
                    db.execute("""
                        INSERT INTO sync_metadata (id, last_sync_at) VALUES (1, ?)
                        ON CONFLICT(id) DO UPDATE SET last_sync_at = excluded.last_sync_at
                    """, (now,))
                return
            db.execute("""
                UPDATE sync_events
                SET next_at = ?, lease_until = 0, lease_token = NULL
                WHERE id = ? AND lease_token = ?
            """, (now + delay, str(event.id), token))

    async def process_due(self, *, online: bool, authorized: bool = False, limit: int = 4) -> int:
        """Deliver due events while the caller affirms restored connectivity and current consent."""
        if not online or not authorized or self.adapter is None:
            return 0
        sent = 0
        async with self._lock:
            for _ in range(max(0, min(limit, 10))):
                claim = await asyncio.to_thread(self._claim, time())
                if not claim:
                    break
                event, token, delay = claim
                try:
                    await asyncio.wait_for(self.adapter.send(event, idempotency_key=str(event.id)), self.timeout)
                except (OSError, httpx.HTTPError, TimeoutError, asyncio.TimeoutError):
                    await asyncio.to_thread(self._complete, event, token, delay, False)
                else:
                    await asyncio.to_thread(self._complete, event, token, delay, True)
                    sent += 1
        return sent
