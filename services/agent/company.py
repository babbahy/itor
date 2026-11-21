"""Company server: each itor sends its daily time and outage logs here; the manager sees the ranking.

Data goes only to the company's own server (ITOR_COMPANY_URL), never to Nexthink.
If the network is down, reports wait in a local outbox and are sent when it comes back.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from .incidents import Incident
from .models import utc_now
from .storage import Store
from .support import Ticket
from .worktime import WorkDay


class DayReport(BaseModel):
    employee: str
    day: date
    active_seconds: float
    idle_seconds: float
    lost_seconds: float
    lost_by_cause: dict[str, float] = Field(default_factory=dict)
    frozen_apps: dict[str, float] = Field(default_factory=dict)
    outages: int = 0
    outage_seconds: float = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    example: bool = False
    received_at: datetime | None = None

    @property
    def paid_seconds(self) -> float:
        return self.active_seconds + self.lost_seconds


class Envelope(BaseModel):
    kind: Literal["day", "incident", "ticket"]
    day: DayReport | None = None
    incident: Incident | None = None
    ticket: Ticket | None = None


class TeamRow(DayReport):
    rank: int
    paid_seconds_total: float
    active_share: float


class TeamReport(BaseModel):
    day: date
    rows: list[TeamRow]
    lost_by_cause: dict[str, float]
    total_lost_seconds: float
    recent_incidents: list[Incident]
    tickets: list[Ticket] = Field(default_factory=list)


# Fake colleagues for the demo, clearly marked as examples.
EXAMPLES = [
    ("Example · Sara", 6.6, 0.5, 0.3, {"offline": 0.2, "frozen_app": 0.1}),
    ("Example · Luca", 5.9, 1.1, 0.8, {"offline": 0.6, "pc_overloaded": 0.2}),
    ("Example · Inès", 7.1, 0.3, 0.2, {"pc_overloaded": 0.2}),
    ("Example · Tom", 4.8, 1.6, 1.2, {"offline": 0.9, "blocked": 0.3}),
]


def example_rows(day: date) -> list[DayReport]:
    hour = 3600
    return [DayReport(employee=name, day=day, active_seconds=active * hour, idle_seconds=idle * hour,
                      lost_seconds=lost * hour, lost_by_cause={k: v * hour for k, v in causes.items()},
                      outages=1 if "offline" in causes else 0,
                      outage_seconds=causes.get("offline", 0) * hour, example=True)
            for name, active, idle, lost, causes in EXAMPLES]


class CompanySender:
    """Runs on each employee PC: keeps an outbox and sends it to the company server."""

    def __init__(self, store: Store, url: str | None, key: str, transport: httpx.AsyncBaseTransport | None = None):
        self.store = store
        self.url = url.rstrip("/") if url else None
        self.key = key
        self.transport = transport
        self.last_error: str | None = None
        self.last_sent_at: datetime | None = None

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def queue_day(self, work: WorkDay, incidents: list[Incident]) -> None:
        mine = [item for item in incidents if item.ended_at and item.started_at.astimezone().date() == work.day]
        report = DayReport(
            employee=work.employee, day=work.day, active_seconds=work.active_seconds, idle_seconds=work.idle_seconds,
            lost_seconds=work.lost_seconds, lost_by_cause=work.lost_by_cause, frozen_apps=work.frozen_apps,
            outages=len(mine), outage_seconds=sum(item.duration_seconds for item in mine),
            first_seen=work.first_seen, last_seen=work.last_seen,
        )
        self.store.put("company_outbox", f"day:{work.day.isoformat()}", Envelope(kind="day", day=report))

    def queue_incident(self, incident: Incident) -> None:
        self.store.put("company_outbox", f"incident:{incident.id}", Envelope(kind="incident", incident=incident))

    def queue_ticket(self, ticket: Ticket) -> None:
        self.store.put("company_outbox", f"ticket:{ticket.id}", Envelope(kind="ticket", ticket=ticket))

    def is_waiting(self, key: str) -> bool:
        return self.store.get("company_outbox", key, Envelope) is not None

    def pending(self) -> int:
        return len(self.store.list("company_outbox", Envelope, limit=1000))

    async def flush(self) -> int:
        """Send what is waiting. Returns how many were sent. Failures stay in the outbox for next time."""
        if not self.configured:
            return 0
        sent = 0
        with self.store.connect() as db:
            rows = db.execute("SELECT id, payload FROM records WHERE bucket='company_outbox' ORDER BY created_at").fetchall()
        try:
            async with httpx.AsyncClient(timeout=5, transport=self.transport, trust_env=False) as client:
                for key, payload in rows:
                    response = await client.post(f"{self.url}/api/company/reports", content=payload,
                                                 headers={"Content-Type": "application/json", "X-Itor-Company-Key": self.key})
                    response.raise_for_status()
                    self.store.delete("company_outbox", key)
                    sent += 1
            self.last_error = None
            if sent:
                self.last_sent_at = utc_now()
        except httpx.HTTPError as error:
            self.last_error = type(error).__name__
        return sent


class CompanyServer:
    """Runs on the manager's side: stores reports and builds the ranking."""

    def __init__(self, store: Store, show_examples: bool = True):
        self.store = store
        self.show_examples = show_examples

    def receive(self, envelope: Envelope) -> None:
        if envelope.kind == "day" and envelope.day:
            report = envelope.day.model_copy(update={"received_at": utc_now(), "example": False})
            self.store.put("company_report", f"{report.employee}|{report.day.isoformat()}", report)
        elif envelope.kind == "incident" and envelope.incident:
            self.store.put("company_incident", envelope.incident.id, envelope.incident)
        elif envelope.kind == "ticket" and envelope.ticket:
            self.store.put("company_ticket", envelope.ticket.id, envelope.ticket.model_copy(update={"sent": True}))

    def team(self, day: date | None = None) -> TeamReport:
        day = day or utc_now().astimezone().date()
        reports = [item for item in self.store.list("company_report", DayReport, limit=1000) if item.day == day]
        if self.show_examples:
            reports += example_rows(day)
        reports.sort(key=lambda item: item.active_seconds, reverse=True)
        rows = []
        for rank, item in enumerate(reports, start=1):
            total = item.active_seconds + item.idle_seconds + item.lost_seconds
            rows.append(TeamRow(**item.model_dump(), rank=rank, paid_seconds_total=item.paid_seconds,
                                active_share=round(item.active_seconds / total, 3) if total else 0))
        causes: dict[str, float] = {}
        for item in reports:
            for cause, seconds in item.lost_by_cause.items():
                causes[cause] = causes.get(cause, 0) + seconds
        return TeamReport(day=day, rows=rows, lost_by_cause=causes,
                          total_lost_seconds=sum(item.lost_seconds for item in reports),
                          recent_incidents=self.store.list("company_incident", Incident, limit=10),
                          tickets=self.store.list("company_ticket", Ticket, limit=20))
