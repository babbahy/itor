from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from services.agent import sync
from services.agent.sync import LocalSyncService, SyncEvent


def readiness_event():
    return SyncEvent(occurred_at=datetime.now(timezone.utc), kind="preflight_completed", outcome="ready")


class RecordingAdapter:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
        self.seen = set()

    async def send(self, event, *, idempotency_key):
        assert str(event.id) == idempotency_key
        self.calls.append(idempotency_key)
        if self.fail:
            raise OSError("temporary disconnect")
        self.seen.add(idempotency_key)


def test_sync_is_disabled_and_consent_is_checked_twice(tmp_path):
    async def verify():
        event = readiness_event()
        path = tmp_path / "state.sqlite"
        service = LocalSyncService(db_path=path)
        assert not service.enqueue(event, authorized=True)
        assert await service.process_due(online=True, authorized=True) == 0
        assert service.status().state == "not_configured"
        adapter = RecordingAdapter()
        configured = LocalSyncService(db_path=path, adapter=adapter)
        assert not configured.enqueue(event)
        assert configured.enqueue(event, authorized=True)
        assert await configured.process_due(online=True) == 0
        assert await configured.process_due(online=False, authorized=True) == 0
        assert not adapter.calls
        assert configured.status().pending_events == 1

    asyncio.run(verify())


def test_sync_payload_is_minimal_and_cannot_contain_action_requests():
    with pytest.raises(ValidationError):
        SyncEvent(
            occurred_at=datetime.now(timezone.utc), kind="preflight_completed",
            outcome="ready", evidence="private payload",
        )
    with pytest.raises(ValidationError):
        SyncEvent(
            occurred_at=datetime.now(timezone.utc), kind="stop_demo_workload", outcome="ready",
        )


def test_duplicate_events_and_concurrent_delivery(tmp_path):
    async def verify():
        path = tmp_path / "state.sqlite"
        adapter = RecordingAdapter()
        service = LocalSyncService(db_path=path, adapter=adapter)
        other = LocalSyncService(db_path=path, adapter=adapter)
        event = readiness_event()
        assert service.enqueue(event, authorized=True)
        assert not other.enqueue(event, authorized=True)
        results = await asyncio.gather(
            service.process_due(online=True, authorized=True),
            other.process_due(online=True, authorized=True),
        )
        assert sum(results) == 1
        assert adapter.calls == [str(event.id)]
        assert not service.enqueue(event, authorized=True)
        status = other.status()
        assert status.state == "synced"
        assert status.last_sync_at is not None
        assert status.pending_events == 0

    asyncio.run(verify())


def test_retry_backoff_is_exponential_bounded_and_recoverable(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    monkeypatch.setattr(sync, "time", lambda: now)
    monkeypatch.setattr(sync, "uniform", lambda _low, _high: 1)

    async def verify():
        nonlocal now
        adapter = RecordingAdapter(fail=True)
        service = LocalSyncService(db_path=tmp_path / "state.sqlite", adapter=adapter, max_attempts=3, base_backoff=5)
        assert service.enqueue(readiness_event(), authorized=True)
        assert await service.process_due(online=True, authorized=True) == 0
        assert service.status().state == "retry_wait"
        now += 4
        assert await service.process_due(online=True, authorized=True) == 0
        assert len(adapter.calls) == 1
        now += 1
        assert await service.process_due(online=True, authorized=True) == 0
        assert len(adapter.calls) == 2
        now += 9
        assert await service.process_due(online=True, authorized=True) == 0
        assert len(adapter.calls) == 2
        now += 1
        adapter.fail = False
        assert await service.process_due(online=True, authorized=True) == 1
        assert service.status().state == "synced"

    asyncio.run(verify())


def test_exhausted_retries_and_retention(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    monkeypatch.setattr(sync, "time", lambda: now)

    async def verify():
        nonlocal now
        adapter = RecordingAdapter(fail=True)
        service = LocalSyncService(
            db_path=tmp_path / "state.sqlite", adapter=adapter, max_attempts=1, retention_days=1,
        )
        old = readiness_event().model_copy(update={"occurred_at": datetime.now(timezone.utc) - timedelta(days=2)})
        assert not service.enqueue(old, authorized=True)
        assert service.enqueue(readiness_event(), authorized=True)
        assert await service.process_due(online=True, authorized=True) == 0
        assert service.status().failed_events == 1
        now += 3600
        assert await service.process_due(online=True, authorized=True) == 0
        assert len(adapter.calls) == 1
        now += 86_400
        assert service.status().state == "idle"

    asyncio.run(verify())


def test_interrupted_delivery_still_uses_a_retry_attempt(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    monkeypatch.setattr(sync, "time", lambda: now)

    class InterruptedAdapter(RecordingAdapter):
        async def send(self, event, *, idempotency_key):
            await super().send(event, idempotency_key=idempotency_key)
            raise asyncio.CancelledError

    async def verify():
        nonlocal now
        path = tmp_path / "state.sqlite"
        adapter = InterruptedAdapter()
        service = LocalSyncService(db_path=path, adapter=adapter, max_attempts=1)
        assert service.enqueue(readiness_event(), authorized=True)
        with pytest.raises(asyncio.CancelledError):
            await service.process_due(online=True, authorized=True)
        assert service.status().state == "retry_wait"
        now += 60
        restarted = LocalSyncService(db_path=path, adapter=adapter, max_attempts=1)
        assert await restarted.process_due(online=True, authorized=True) == 0
        assert restarted.status().state == "needs_attention"
        assert len(adapter.calls) == 1

    asyncio.run(verify())
