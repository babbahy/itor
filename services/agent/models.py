from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkloadStatus(BaseModel):
    active: bool = False
    id: str | None = None
    scenario: str | None = None
    kind: str | None = None
    app: str | None = None
    story: str | None = None
    cpu_percent: float | None = None
    memory_bytes: int | None = None
    started_at: datetime | None = None
    expires_at: datetime | None = None


class DeviceSnapshot(BaseModel):
    id: str = Field(default_factory=new_id)
    captured_at: datetime = Field(default_factory=utc_now)
    source: Literal["local", "fixture"] = "local"
    cpu_percent: float | None = None
    cpu_logical: int | None = None
    cpu_physical: int | None = None
    memory_percent: float | None = None
    memory_total: int | None = None
    memory_available: int | None = None
    disk_percent: float | None = None
    disk_total: int | None = None
    disk_free: int | None = None
    workload: WorkloadStatus = Field(default_factory=WorkloadStatus)
    network_up: bool | None = None
    errors: list[str] = Field(default_factory=list)


Readiness = Literal["ready", "attention", "not_ready", "unknown"]


class Finding(BaseModel):
    id: str = Field(default_factory=new_id)
    category: str
    severity: Literal["warning", "critical", "unknown"]
    title: str
    evidence: str
    window_seconds: float = 0
    potential_impact: str
    recommended_action_ids: list[str] = Field(default_factory=list)
    source: Literal["local", "fixture"] = "local"
    limitations: str


class Check(BaseModel):
    id: str
    label: str
    state: Literal["passed", "warning", "unknown", "unsupported"]
    detail: str


class ReadinessReport(BaseModel):
    readiness: Readiness
    findings: list[Finding]
    snapshot: DeviceSnapshot
    checks: list[Check]


class PreflightSession(ReadinessReport):
    id: str = Field(default_factory=new_id)
    started_at: datetime
    completed_at: datetime = Field(default_factory=utc_now)
    status: Literal["completed"] = "completed"


class DiagnoseInput(Input):
    session_id: str = Field(min_length=1, max_length=64)


class ChatInput(Input):
    question: str = Field(min_length=1, max_length=400)
    session_id: str | None = Field(default=None, max_length=64)


class ActionInput(DiagnoseInput):
    action_id: Literal["stop_demo_workload"]


class Consent(Input):
    approval_token: str = Field(min_length=16, max_length=256)


class Approval(Consent):
    approved: StrictBool

    @field_validator("approved")
    @classmethod
    def require_approval(cls, approved: bool) -> bool:
        if not approved:
            raise ValueError("Approval must be explicit.")
        return approved


class DemoStop(Input):
    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def require_confirmation(cls, confirm: bool) -> bool:
        if not confirm:
            raise ValueError("Confirm stopping the demo workload.")
        return confirm


class SimulateInput(Input):
    enabled: StrictBool


ActionState = Literal[
    "proposed", "awaiting_approval", "approved", "executing", "verifying",
    "succeeded", "failed", "canceled", "expired",
]


class ActionMeasurement(BaseModel):
    captured_at: datetime
    system_cpu_percent: float | None
    workload_cpu_percent: float | None
    workload_active: bool
    readiness: Readiness


class Verification(BaseModel):
    process_exited: bool
    system_cpu_delta: float | None
    improved: bool


class AvailableAction(BaseModel):
    action_id: Literal["stop_demo_workload"] = "stop_demo_workload"
    title: str = "Stop demo workload"
    scope: str = "Stop the temporary background workload started by itor."
    expected_result: str = "Release the CPU time used by this workload and recheck device readiness."
    side_effects: str = "Ends the current demo run. Other applications and network settings are unaffected."


class Action(AvailableAction):
    id: str = Field(default_factory=new_id)
    session_id: str
    status: ActionState = "proposed"
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    approval_token: str | None = None
    before: ActionMeasurement | None = None
    after: ActionMeasurement | None = None
    verification: Verification | None = None
    message: str | None = None


class Activity(BaseModel):
    id: str = Field(default_factory=new_id)
    kind: str
    created_at: datetime = Field(default_factory=utc_now)
    title: str
    detail: str
