from datetime import datetime, timezone

import pytest

from services.agent.storage import Store
from services.agent.worktime import MAX_TICK_SECONDS, WorktimeTracker

from services.agent.tests.test_core import HEADERS, local_client, settings

NOON = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def tracker(tmp_path, idle=0.0, frozen=None):
    state = {"idle": idle, "frozen": frozen}
    clock = WorktimeTracker(
        Store(tmp_path / "work.sqlite", 7), "alex", idle_limit=120,
        idle_reader=lambda: state["idle"], frozen_reader=lambda: state["frozen"], clock=lambda: NOON,
    )
    return clock, state


def test_active_idle_and_lost_time(tmp_path):
    clock, state = tracker(tmp_path)
    clock.tick(30, [])
    state["idle"] = 300
    clock.tick(20, [])
    state["idle"] = 5
    work = clock.tick(10, ["offline"])
    assert (work.active_seconds, work.idle_seconds, work.lost_seconds) == (30, 20, 10)
    assert work.lost_by_cause == {"offline": 10}
    assert work.paid_seconds == 40
    assert clock.view().state == "lost"


def test_tool_problem_while_away_counts_as_idle_not_lost(tmp_path):
    clock, _ = tracker(tmp_path, idle=600)
    work = clock.tick(15, ["offline"])
    assert work.idle_seconds == 15 and work.lost_seconds == 0


def test_blocked_counts_as_lost_even_without_input(tmp_path):
    clock, _ = tracker(tmp_path, idle=600)
    clock.blocked = True
    work = clock.tick(15, [])
    assert work.lost_seconds == 15 and work.lost_by_cause == {"blocked": 15}


def test_frozen_app_is_named_and_long_gaps_are_capped(tmp_path):
    clock, _ = tracker(tmp_path, frozen="Teams.exe")
    work = clock.tick(3600, [])
    assert work.lost_seconds == MAX_TICK_SECONDS
    assert work.frozen_apps == {"Teams.exe": MAX_TICK_SECONDS}


def test_unknown_idle_counts_as_active(tmp_path):
    clock, _ = tracker(tmp_path, idle=None)
    assert clock.tick(15, []).active_seconds == 15


def test_day_is_saved(tmp_path):
    clock, _ = tracker(tmp_path)
    clock.tick(15, [])
    again, _ = tracker(tmp_path)
    assert again.day().active_seconds == 15
    assert len(again.week()) == 7


@pytest.mark.anyio
async def test_worktime_routes(tmp_path):
    async with local_client(settings(tmp_path, employee_name="alex"), HEADERS) as client:
        today = (await client.get("/api/worktime/today")).json()
        assert today["employee"] == "alex" and today["blocked"] is False
        blocked = (await client.post("/api/worktime/blocked", json={"blocked": True})).json()
        assert blocked["blocked"] is True
        demo = (await client.post("/api/demo/worktime")).json()
        assert demo["demo"] and demo["active_seconds"] > 3600 and demo["lost_by_cause"]["offline"] > 0
        assert demo["paid_seconds_total"] == demo["active_seconds"] + demo["lost_seconds"]
        assert len((await client.get("/api/worktime/week")).json()) == 7
        activity = (await client.get("/api/activity")).json()
        assert any(item["kind"] == "blocked" for item in activity)
