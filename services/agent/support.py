"""Ask IT: a ticket with the employee's words plus what itor measured and already tried.

Tickets go to the company server through the same outbox as daily time, so they also
work offline: they wait on the PC and leave when the connection is back.
(Later, the same ticket could go to Nexthink.)
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .models import Input, new_id, utc_now


class TicketInput(Input):
    message: str = Field(min_length=1, max_length=1000)
    diagnosis: str | None = Field(default=None, max_length=300)


class Ticket(BaseModel):
    id: str = Field(default_factory=new_id)
    employee: str
    created_at: datetime = Field(default_factory=utc_now)
    message: str
    diagnosis: str | None = None
    pc_status: str = "unknown"
    findings: list[str] = Field(default_factory=list)
    connection: list[str] = Field(default_factory=list)
    tried: list[str] = Field(default_factory=list)
    outage_id: str | None = None
    sent: bool = False
