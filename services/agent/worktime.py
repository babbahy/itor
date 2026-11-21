"""Time clock: counts active, idle and lost time (time lost because of tools).

Only two things are read from the computer:
- how long since the last mouse or keyboard action (never which keys),
- the name of the front app, and only when Windows says it is frozen.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Literal

import psutil
from pydantic import BaseModel, Field

from .models import utc_now
from .storage import Store

Cause = Literal["blocked", "offline", "pc_overloaded", "frozen_app"]

CAUSE_LABELS: dict[str, str] = {
    "blocked": "Employee said they were blocked",
    "offline": "Internet or cloud down",
    "pc_overloaded": "PC overloaded",
    "frozen_app": "App not responding",
}

# One tick never counts more than this. If the PC slept, the gap is not counted.
MAX_TICK_SECONDS = 60.0


class WorkDay(BaseModel):
    day: date
    employee: str
    active_seconds: float = 0
    idle_seconds: float = 0
    lost_seconds: float = 0
    lost_by_cause: dict[str, float] = Field(default_factory=dict)
    frozen_apps: dict[str, float] = Field(default_factory=dict)
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    demo: bool = False

    @property
    def paid_seconds(self) -> float:
        """Hours to pay = time working, including time lost because of tools."""
        return self.active_seconds + self.lost_seconds


class WorkDayView(WorkDay):
    paid_seconds_total: float
    state: Literal["active", "idle", "lost", "unknown"]
    blocked: bool
    causes_now: list[str]


def windows_idle_seconds() -> float | None:
    """Seconds since the last mouse or keyboard action, from Windows."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    info = LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000


def windows_frozen_app() -> str | None:
    """Name of the front app if Windows says it is not responding, otherwise None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    window = user32.GetForegroundWindow()
    if not window or not user32.IsHungAppWindow(window):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name()
    except psutil.Error:
        return "Unknown app"


class WorktimeTracker:
    def __init__(
        self, store: Store, employee: str, idle_limit: float = 120,
        idle_reader: Callable[[], float | None] = windows_idle_seconds,
        frozen_reader: Callable[[], str | None] = windows_frozen_app,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.store = store
        self.employee = employee
        self.idle_limit = idle_limit
        self.idle_reader = idle_reader
        self.frozen_reader = frozen_reader
        self.clock = clock
        self.blocked = False
        self.state: Literal["active", "idle", "lost", "unknown"] = "unknown"
        self.causes_now: list[str] = []
        self._lock = Lock()

    def day(self, day: date | None = None) -> WorkDay:
        day = day or self.clock().astimezone().date()
        return self.store.get("worktime", day.isoformat(), WorkDay) or WorkDay(day=day, employee=self.employee)

    def save(self, work: WorkDay) -> None:
        self.store.put("worktime", work.day.isoformat(), work)

    def tick(self, elapsed: float, causes: list[str]) -> WorkDay:
        """Add `elapsed` seconds to today. `causes` are the tool problems seen right now."""
        elapsed = max(0.0, min(elapsed, MAX_TICK_SECONDS))
        idle = self.idle_reader()
        frozen = self.frozen_reader()
        causes = list(dict.fromkeys(causes))
        if frozen:
            causes.append("frozen_app")
        if self.blocked:
            causes.insert(0, "blocked")
        now = self.clock()
        with self._lock:
            work = self.day(now.astimezone().date())
            work.first_seen = work.first_seen or now
            work.last_seen = now
            is_idle = idle is not None and idle >= self.idle_limit
            if self.blocked or (causes and not is_idle):
                # Lost time: the person is working but a tool is in the way.
                work.lost_seconds += elapsed
                share = elapsed / len(causes)
                for cause in causes:
                    work.lost_by_cause[cause] = work.lost_by_cause.get(cause, 0) + share
                if frozen:
                    work.frozen_apps[frozen] = work.frozen_apps.get(frozen, 0) + elapsed
                self.state = "lost"
            elif is_idle:
                work.idle_seconds += elapsed
                self.state = "idle"
            else:
                work.active_seconds += elapsed
                self.state = "active"
            self.causes_now = causes
            self.save(work)
            return work

    def view(self, work: WorkDay | None = None) -> WorkDayView:
        work = work or self.day()
        return WorkDayView(**work.model_dump(), paid_seconds_total=work.paid_seconds, state=self.state,
                           blocked=self.blocked, causes_now=self.causes_now)

    def week(self) -> list[WorkDay]:
        today = self.clock().astimezone().date()
        return [self.day(today - timedelta(days=offset)) for offset in range(6, -1, -1)]

    def fill_demo_day(self) -> WorkDay:
        """Demo: add a realistic morning so the numbers are not empty on stage."""
        with self._lock:
            work = self.day()
            now = self.clock()
            work.first_seen = work.first_seen or now - timedelta(hours=3)
            work.last_seen = now
            work.active_seconds += 2 * 3600 + 35 * 60
            work.idle_seconds += 22 * 60
            for cause, minutes in (("offline", 14), ("pc_overloaded", 6), ("frozen_app", 4)):
                work.lost_seconds += minutes * 60
                work.lost_by_cause[cause] = work.lost_by_cause.get(cause, 0) + minutes * 60
            work.frozen_apps["Teams.exe"] = work.frozen_apps.get("Teams.exe", 0) + 4 * 60
            work.demo = True
            self.save(work)
            return work
