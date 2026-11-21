import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta

import httpx
import psutil
import pytest

from services.agent.config import Settings
from services.agent.main import create_app
from services.agent.models import DeviceSnapshot, WorkloadStatus, utc_now
from services.agent.readiness import ReadinessEngine
from services.agent.telemetry import FixtureTelemetryProvider, LocalTelemetryProvider
from services.agent.workload import WorkloadError, WorkloadManager

KEY = "local-key-for-pytest-only"
HEADERS = {"X-Spark-Key": KEY}
BASE_URL = "http://127.0.0.1:8765"


def settings(tmp_path, **kwargs):
    return Settings(api_key=KEY, db_path=tmp_path / "test.sqlite", ollama_url="http://127.0.0.1:1", **kwargs)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@asynccontextmanager
async def local_client(config, headers=None):
    app = create_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL, headers=headers) as client:
            yield client


def observed(cpu=20, **kwargs):
    return DeviceSnapshot(cpu_percent=cpu, memory_percent=45, disk_percent=55, network_up=True, **kwargs)


async def wait_for(client, path, condition, limit=5):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        result = (await client.get(path)).json()
        if condition(result):
            return result
        await asyncio.sleep(0.08)
    pytest.fail(f"No expected outcome observed on {path} within {limit} seconds.")


def test_readiness_uses_sustained_cpu_and_hysteresis():
    engine = ReadinessEngine()
    now = utc_now()
    first = observed(95, captured_at=now - timedelta(seconds=4))
    assert engine.evaluate(first, [first]).readiness == "ready"
    second = observed(90, captured_at=now - timedelta(seconds=2))
    third = observed(92, captured_at=now)
    assert engine.evaluate(third, [first, second, third]).findings[0].category == "cpu"
    samples = [observed(74, captured_at=now + timedelta(seconds=offset)) for offset in (2, 4, 6)]
    assert engine.evaluate(samples[-1], samples).readiness == "attention"
    samples = [observed(62, captured_at=now + timedelta(seconds=offset)) for offset in (8, 10, 12)]
    assert engine.evaluate(samples[-1], samples).readiness == "ready"


def test_missing_metric_and_audio_are_labeled():
    fixture = FixtureTelemetryProvider([observed(None)])
    reading = fixture.capture()
    report = ReadinessEngine().evaluate(reading, fixture.history())
    assert report.readiness == "unknown"
    assert report.findings[0].source == "fixture"
    assert report.findings[0].severity == "unknown"
    assert next(check for check in report.checks if check.id == "audio").state == "unsupported"
    assert reading.model_dump(mode="json")["captured_at"].endswith("Z")


def test_network_state_preserves_independent_local_checks():
    reading = observed()
    report = ReadinessEngine().evaluate(reading, [reading], internet_unavailable=True)
    assert report.readiness == "not_ready"
    assert next(check for check in report.checks if check.id == "cpu").state == "passed"
    assert "endpoint" in next(item for item in report.findings if item.category == "network").evidence


def test_fixture_workload_cannot_offer_real_action():
    fixture = FixtureTelemetryProvider([observed(workload=WorkloadStatus(active=True, cpu_percent=47))])
    report = ReadinessEngine().evaluate(fixture.capture(), fixture.history())
    assert report.findings[0].recommended_action_ids == []


def test_workload_has_bounded_runtime_and_independent_units():
    manager = WorkloadManager(duration_seconds=2)
    try:
        started = manager.start()
        assert started.active and started.cpu_percent is None
        provider = LocalTelemetryProvider(manager)
        reading = provider.capture()
        assert 0 <= reading.cpu_percent <= 100
        deadline = time.monotonic() + 1
        while reading.workload.cpu_percent is None or reading.workload.cpu_percent < 20:
            assert time.monotonic() < deadline
            reading = provider.capture()
        assert reading.workload.cpu_percent <= 120
        handle = manager.current.handle
        handle.wait(timeout=3)
        assert handle.returncode == 0
        assert not manager.status().active
    finally:
        manager.close()


@pytest.mark.parametrize("field", ["start", "parent_pid"])
def test_process_identity_mismatch_does_not_terminate_child(field):
    manager = WorkloadManager(duration_seconds=10)
    try:
        started = manager.start()
        record = manager.current
        original = record.identity
        record.identity = replace(original, **{field: getattr(original, field) + 1})
        try:
            with pytest.raises(WorkloadError, match="identity has changed"):
                manager.stop(started.id)
            assert record.handle.poll() is None
            assert psutil.pid_exists(record.handle.pid)
        finally:
            record.identity = original
    finally:
        manager.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Reproduces Linux boot epoch adjustment")
@pytest.mark.parametrize("disable_pidfd", [False, True])
def test_linux_wall_clock_adjustment_preserves_owned_process_identity(monkeypatch, disable_pidfd):
    from psutil import _pslinux

    if disable_pidfd:
        monkeypatch.delattr(os, "pidfd_open", raising=False)
    manager = WorkloadManager(duration_seconds=10)
    try:
        started = manager.start()
        record = manager.current
        captured_pidfd = record.pidfd
        original_birth = psutil.Process(record.handle.pid).create_time()
        boot_epoch = _pslinux.boot_time()
        monkeypatch.setattr(_pslinux, "boot_time", lambda: boot_epoch + 1)
        assert psutil.Process(record.handle.pid).create_time() == original_birth + 1
        assert manager.stop(started.id)
        assert not manager.status().active
        assert record.pidfd is None
        if captured_pidfd is not None:
            with pytest.raises(OSError):
                os.fstat(captured_pidfd)
    finally:
        manager.close()


@pytest.mark.anyio
async def test_require_key_and_reject_direct_browser_mutation(tmp_path):
    async with local_client(settings(tmp_path)) as client:
        assert (await client.get("/api/health")).json() == {"status": "ok"}
        assert (await client.get("/api/status")).status_code == 401
        response = await client.post("/api/demo/start", headers={**HEADERS, "Origin": "https://example.org"})
        assert response.status_code == 403
        assert not (await client.get("/api/demo/status", headers=HEADERS)).json()["active"]
        assert (await client.get("/api/health", headers={"Host": "bad.invalid"})).status_code == 400


@pytest.mark.anyio
async def test_meeting_cache_persists_and_unsafe_url_is_rejected(tmp_path):
    data = {"title": "Réunion quotidienne", "start_at": (utc_now() + timedelta(minutes=1)).isoformat(),
            "duration_minutes": 30, "platform": "Teams", "join_url": "https://example.com/room", "notes": "Agenda"}
    config = settings(tmp_path)
    async with local_client(config, HEADERS) as client:
        assert (await client.get("/api/meetings/next")).json()["source"] == "demo"
        unsafe = await client.post("/api/meetings", json={**data, "join_url": "javascript:alert(1)"})
        assert unsafe.status_code == 422 and "alert(1)" not in unsafe.text
        registered = await client.post("/api/meetings", json=data)
        assert registered.status_code == 201
        details = registered.json()
    async with local_client(config, HEADERS) as client:
        assert (await client.get("/api/meetings/next")).json() == details
        assert (await client.get("/api/connectivity")).json()["nexthink"]["state"] == "not_configured"
        assert (await client.delete("/api/privacy/history")).status_code == 204
        assert (await client.get("/api/meetings/next")).json() == details


@pytest.mark.anyio
async def test_end_to_end_remediation_during_cloud_outage_and_demo_reset(tmp_path):
    config = settings(tmp_path)
    async with local_client(config, HEADERS) as client:
        original = (await client.get("/api/meetings/next")).json()
        assert (await client.post("/api/demo/cloud", json={"enabled": True})).json()["offline_rescue"]
        assert (await client.post("/api/demo/start")).status_code == 201
        assert (await client.post("/api/demo/start")).status_code == 409
        assert (await client.post("/api/demo/reset")).status_code == 409
        await wait_for(client, "/api/demo/status", lambda x: (x["cpu_percent"] or 0) >= 20)
        session = (await client.post("/api/preflight", json={"meeting_id": original["id"]})).json()
        assert session["status"] == "completed"
        assert any(item["category"] == "workload" for item in session["findings"])
        diagnosis = (await client.post("/api/diagnose", json={"session_id": session["id"]})).json()
        assert diagnosis["provider"] == "rules"
        assert diagnosis["recommended_action_id"] == "stop_demo_workload"
        available = (await client.get("/api/actions/available")).json()
        assert len(available) == 1 and available[0]["action_id"] == "stop_demo_workload"
        plan = (await client.post("/api/actions/plan", json={"session_id": session["id"], "action_id": "stop_demo_workload"})).json()
        token = plan["approval_token"]
        assert token and plan["status"] == "awaiting_approval"
        path = f"/api/actions/{plan['id']}"
        assert (await client.get(path)).json()["approval_token"] is None
        assert (await client.post(f"{path}/approve", json={"approval_token": "invalid-sample-token", "approved": True})).status_code == 403
        assert (await client.post(f"{path}/approve", json={"approval_token": token})).status_code == 422
        assert (await client.post(f"{path}/approve", json={"approval_token": token, "approved": 1})).status_code == 422
        assert (await client.get("/api/demo/status")).json()["active"]
        approval = {"approval_token": token, "approved": True}
        assert (await client.post(f"{path}/approve", json=approval)).status_code == 202
        assert (await client.post(f"{path}/approve", json=approval)).status_code == 409
        action = await wait_for(client, path, lambda x: x["status"] in {"succeeded", "failed"})
        assert action["status"] == "succeeded", action
        assert action["verification"]["process_exited"] is True
        assert action["verification"]["improved"] is True
        assert action["before"]["workload_cpu_percent"] >= 20
        assert action["after"]["workload_active"] is False
        assert action["after"]["workload_cpu_percent"] == 0
        assert (await client.get("/api/insights")).json()["verified_actions"] == 1
        assert not (await client.get("/api/actions/available")).json()
        assert not (await client.get(f"/api/preflight/{session['id']}")).json()["snapshot"]["workload"]["active"]
        assert token not in (await client.get("/api/actions/history")).text
        reset = (await client.post("/api/demo/reset")).json()
        assert len(reset["meetings"]) == 3 and not reset["workload"]["active"]
        assert reset["meetings"][0]["id"] != original["id"]
        assert (await client.get("/api/connectivity")).json()["nexthink"]["state"] == "not_configured"
        privacy = (await client.get("/api/privacy")).json()
        assert privacy["external_connections"] == [] and privacy["sync"]["state"] == "not_configured"


@pytest.mark.anyio
async def test_expired_approval_cannot_be_replayed(tmp_path):
    config = settings(tmp_path, action_expiry_seconds=0)
    async with local_client(config, HEADERS) as client:
        assert (await client.post("/api/demo/start")).status_code == 201
        await wait_for(client, "/api/demo/status", lambda x: (x["cpu_percent"] or 0) >= 20)
        session = (await client.post("/api/preflight")).json()
        plan = (await client.post("/api/actions/plan", json={"action_id": "stop_demo_workload", "session_id": session["id"]})).json()
        body = {"approval_token": plan["approval_token"], "approved": True}
        assert (await client.post(f"/api/actions/{plan['id']}/approve", json=body)).status_code == 410
        assert (await client.get("/api/demo/status")).json()["active"]
        assert (await client.post("/api/demo/stop", json={"confirm": True})).status_code == 200
