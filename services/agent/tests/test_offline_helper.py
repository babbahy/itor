import asyncio
from datetime import date

import httpx
import pytest

from services.agent.company import CompanySender, CompanyServer, Envelope
from services.agent.connectivity import ConnectivityManager
from services.agent.incidents import IncidentLog
from services.agent.network_fixes import NetworkFixes
from services.agent.storage import Store
from services.agent.tests.test_core import HEADERS, local_client, settings
from services.agent.worktime import WorkDay


def fixes(ok=True):
    ran = []

    async def internet():
        return "connected"

    def runner(command):
        ran.append(command)
        return ok, "done"
    return NetworkFixes(internet, runner=runner, windows=True), ran


def test_fix_runs_only_after_approval():
    async def verify():
        tool, ran = fixes()
        plan = tool.plan("flush_dns")
        assert plan.status == "awaiting_approval" and ran == []
        with pytest.raises(PermissionError):
            await tool.approve(plan.id, "wrong-token-1234567")
        done = await tool.approve(plan.id, plan.approval_token)
        assert done.status == "succeeded" and ran == [["ipconfig", "/flushdns"]]
        with pytest.raises(PermissionError):
            await tool.approve(plan.id, plan.approval_token)
    asyncio.run(verify())


def test_declined_fix_runs_nothing():
    tool, ran = fixes()
    plan = tool.plan("restart_wifi")
    assert tool.cancel(plan.id, plan.approval_token).status == "canceled"
    assert ran == []


def test_fixes_refuse_off_windows():
    tool = NetworkFixes(lambda: None, windows=False)
    assert not tool.available()[0].supported
    with pytest.raises(ValueError):
        tool.plan("flush_dns")


def test_outage_log_opens_and_closes(tmp_path):
    async def verify():
        store = Store(tmp_path / "s.sqlite", 7)
        closed = []
        log = IncidentLog(store, "alex", on_closed=closed.append)
        manager = ConnectivityManager(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
        try:
            down = await manager.simulate_cloud(True)
            log.update(down)
            log.note_help("Local AI: Check your Wi-Fi")
            log.note_fix("Clear the DNS cache: succeeded")
            assert log.current and log.current.simulated
            up = await manager.simulate_cloud(False)
            done = log.update(up)
            assert done and closed == [done] and log.current is None
            assert done.help_given == ["Local AI: Check your Wi-Fi"] and done.fixes
            assert log.history()[0].id == done.id
        finally:
            await manager.close()
    asyncio.run(verify())


def test_sender_waits_offline_then_sends(tmp_path):
    async def verify():
        store = Store(tmp_path / "s.sqlite", 7)
        received = []
        online = {"up": False}

        def handler(request):
            if not online["up"]:
                raise httpx.ConnectError("offline", request=request)
            assert request.headers["X-Itor-Company-Key"] == "team-key"
            received.append(Envelope.model_validate_json(request.content))
            return httpx.Response(204)

        sender = CompanySender(store, "http://127.0.0.1:8765", "team-key", transport=httpx.MockTransport(handler))
        sender.queue_day(WorkDay(day=date(2026, 11, 21), employee="alex", active_seconds=3600), [])
        assert await sender.flush() == 0 and sender.pending() == 1 and sender.last_error
        online["up"] = True
        assert await sender.flush() == 1 and sender.pending() == 0
        assert received[0].day.employee == "alex"
    asyncio.run(verify())


def test_ranking_orders_by_active_time(tmp_path):
    server = CompanyServer(Store(tmp_path / "s.sqlite", 7), show_examples=True)
    today = date.today()
    for name, hours in (("alex", 7.5), ("sam", 2.0)):
        server.receive(Envelope.model_validate({"kind": "day", "day": {
            "employee": name, "day": today.isoformat(), "active_seconds": hours * 3600,
            "idle_seconds": 600, "lost_seconds": 900, "lost_by_cause": {"offline": 900}}}))
    team = server.team(today)
    assert team.rows[0].employee == "alex" and team.rows[0].rank == 1
    assert len(team.rows) == 6 and any(row.example for row in team.rows)
    assert team.rows[0].paid_seconds_total == 7.5 * 3600 + 900
    assert team.lost_by_cause["offline"] >= 1800


@pytest.mark.anyio
async def test_company_routes_need_the_team_key(tmp_path):
    config = settings(tmp_path, company_key="team-key", employee_name="alex", demo_team=False)
    async with local_client(config, HEADERS) as client:
        body = {"kind": "day", "day": {"employee": "alex", "day": date.today().isoformat(),
                                       "active_seconds": 60, "idle_seconds": 0, "lost_seconds": 0}}
        assert (await client.post("/api/company/reports", json=body)).status_code == 401
        sent = await client.post("/api/company/reports", json=body, headers={"X-Itor-Company-Key": "team-key"})
        assert sent.status_code == 204
        team = (await client.get("/api/company/team")).json()
        assert [row["employee"] for row in team["rows"]] == ["alex"]
        assert len((await client.get("/api/fixes")).json()) == 2
        assert (await client.get("/api/incidents")).json()["current"] is None
        assert (await client.get("/api/company/status")).json()["configured"] is False
