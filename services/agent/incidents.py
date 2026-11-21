"""Outage log: opens when internet (or the cloud) drops, closes when it comes back."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, Field

from .connectivity import ConnectivityReport, ServiceState
from .models import new_id, utc_now
from .storage import Store


class Incident(BaseModel):
    id: str = Field(default_factory=new_id)
    employee: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float = 0
    simulated: bool = False
    what_failed: list[str] = Field(default_factory=list)
    help_given: list[str] = Field(default_factory=list)
    fixes: list[str] = Field(default_factory=list)


def is_offline(report: ConnectivityReport | None) -> bool:
    if report is None:
        return False
    return report.simulated_cloud_outage or report.internet.state in (
        ServiceState.DISCONNECTED, ServiceState.UNREACHABLE,
    ) or report.network_interface.state == ServiceState.DISCONNECTED


def failed_checks(report: ConnectivityReport) -> list[str]:
    names = {"network_interface": "Network card", "gateway": "Router", "dns": "Website names (DNS)",
             "internet": "Internet", "nexthink": "Company cloud"}
    failed = [label for key, label in names.items()
              if getattr(report, key).state in (ServiceState.DISCONNECTED, ServiceState.UNREACHABLE)]
    if report.simulated_cloud_outage:
        failed.append("Company cloud (demo outage)")
    return failed


class IncidentLog:
    def __init__(self, store: Store, employee: str, on_closed: Callable[[Incident], None] | None = None):
        self.store = store
        self.employee = employee
        self.on_closed = on_closed
        self.current: Incident | None = None

    def update(self, report: ConnectivityReport | None) -> Incident | None:
        """Call after each connection check. Returns the incident that just closed, if any."""
        offline = is_offline(report)
        if offline and self.current is None:
            self.current = Incident(employee=self.employee, started_at=utc_now(),
                                    simulated=bool(report and report.simulated_cloud_outage))
            self.store.event("outage_started", "Connection lost", "itor switched to local help and started an outage log.")
        if self.current is not None and report is not None:
            for item in failed_checks(report):
                if item not in self.current.what_failed:
                    self.current.what_failed.append(item)
            self.save()
        if not offline and self.current is not None:
            closed = self.current
            closed.ended_at = utc_now()
            closed.duration_seconds = round((closed.ended_at - closed.started_at).total_seconds(), 1)
            self.current = None
            self.store.put("incident", closed.id, closed)
            minutes = max(1, round(closed.duration_seconds / 60))
            self.store.event("outage_ended", "Connection back", f"The outage lasted about {minutes} min. The log will be sent to your company.")
            if self.on_closed:
                self.on_closed(closed)
            return closed
        return None

    def note_help(self, text: str) -> None:
        if self.current is not None and text not in self.current.help_given:
            self.current.help_given.append(text[:200])
            self.save()

    def note_fix(self, text: str) -> None:
        if self.current is not None:
            self.current.fixes.append(text[:200])
            self.save()

    def save(self) -> None:
        if self.current is not None:
            self.current.duration_seconds = round((utc_now() - self.current.started_at).total_seconds(), 1)
            self.store.put("incident", self.current.id, self.current)

    def history(self, limit: int = 20) -> list[Incident]:
        return self.store.list("incident", Incident, limit=limit)
