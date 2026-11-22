import asyncio
from dataclasses import dataclass
from datetime import timedelta
from hmac import compare_digest
from secrets import token_urlsafe
from statistics import mean
from typing import Callable, Protocol

from .models import (
    Action, ActionMeasurement, ActionState, AvailableAction, DeviceSnapshot, PreflightSession, ReadinessReport,
    Verification, utc_now,
)
from .storage import Store
from .telemetry import NotConfigured, TelemetryProvider
from .workload import WorkloadError, WorkloadManager


class ActionError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class RemediationProvider(Protocol):
    def available(self) -> list[AvailableAction]: ...
    def plan(self, session: PreflightSession) -> Action: ...
    def approve(self, action_id: str, token: str) -> Action: ...
    def get(self, action_id: str) -> Action: ...


class NexthinkRemoteActionProvider:
    def available(self) -> list[AvailableAction]:
        return []

    def plan(self, session: PreflightSession) -> Action:
        raise NotConfigured("Nexthink Remote Actions require an authenticated tenant and reviewed action definitions.")

    def approve(self, action_id: str, token: str) -> Action:
        raise NotConfigured("Nexthink Remote Actions are not configured.")

    def get(self, action_id: str) -> Action:
        raise NotConfigured("Nexthink Remote Actions are not configured.")


@dataclass
class Plan:
    action: Action
    workload_id: str
    token: str


TRANSITIONS: dict[ActionState, set[ActionState]] = {
    "proposed": {"awaiting_approval"},
    "awaiting_approval": {"approved", "canceled", "expired"},
    "approved": {"executing", "failed"},
    "executing": {"executing", "verifying", "failed"},
    "verifying": {"succeeded", "failed"},
}


class LocalSafeRemediationProvider:
    def __init__(self, workload: WorkloadManager, telemetry: TelemetryProvider, store: Store,
                 recheck: Callable[[DeviceSnapshot, PreflightSession], ReadinessReport], expires_in: int):
        self.workload = workload
        self.telemetry = telemetry
        self.store = store
        self.recheck = recheck
        self.expires_in = expires_in
        self.plans: dict[str, Plan] = {}
        self.job: asyncio.Task | None = None

    @property
    def busy(self) -> bool:
        return self.job is not None and not self.job.done()

    def save(self, plan: Plan, status: ActionState, **details) -> Action:
        if status not in TRANSITIONS.get(plan.action.status, set()):
            raise ValueError(f"Invalid action transition from {plan.action.status} to {status}.")
        action = Action.model_validate({**plan.action.model_dump(), "status": status, **details})
        self.store.put("action", action.id, action)
        plan.action = action
        return action

    def expire(self) -> None:
        now = utc_now()
        current = self.workload.status().id
        for action_id, plan in list(self.plans.items()):
            if plan.action.status == "awaiting_approval" and (
                    now >= plan.action.expires_at or plan.workload_id != current):
                self.save(plan, "expired", message="This approval is no longer current. Run a new device check.")
            if plan.action.status in {"expired", "succeeded", "failed", "canceled"}:
                del self.plans[action_id]

    def available(self) -> list[AvailableAction]:
        current = self.workload.status()
        return [self.describe(current)] if current.active and not self.busy else []

    @staticmethod
    def describe(current) -> AvailableAction:
        app = current.app or "the background app"
        return AvailableAction(
            title=f"Stop {app}",
            scope=f"Stop {app}, the demo process itor started ({current.story or 'it slows the PC'}). Nothing else is touched.",
            expected_result="Frees the processor and memory it was using, then itor measures again.",
            side_effects=f"{app} closes. Unsaved work in it would be lost (none in this demo).",
        )

    def plan(self, session: PreflightSession) -> Action:
        self.expire()
        current = self.workload.status()
        observed = session.snapshot.workload
        if self.busy or not current.id or current.id != observed.id or not any(
            "stop_demo_workload" in item.recommended_action_ids for item in session.findings
        ):
            raise ActionError("Run a fresh preflight while the controlled workload is active.")
        for plan in self.plans.values():
            if plan.workload_id == current.id and plan.action.session_id == session.id:
                return plan.action.model_copy(update={"approval_token": plan.token})
        if len(self.plans) >= 20:
            raise ActionError("Too many pending approvals. Cancel a plan or let it expire.", 429)
        action = Action(session_id=session.id, expires_at=utc_now() + timedelta(seconds=self.expires_in),
                        **self.describe(current).model_dump(exclude={"action_id"}))
        plan = Plan(action, current.id, token_urlsafe(32))
        planned = self.save(plan, "awaiting_approval")
        self.plans[action.id] = plan
        return planned.model_copy(update={"approval_token": plan.token})

    def get(self, action_id: str) -> Action:
        self.expire()
        if plan := self.plans.get(action_id):
            return plan.action
        action = self.store.get("action", action_id, Action)
        if action is None:
            raise ActionError("Action plan not found.", 404)
        if action.status in {"proposed", "awaiting_approval", "approved", "executing", "verifying"}:
            action = action.model_copy(update={"status": "expired", "message": "The local agent restarted. This action will not run."})
            self.store.put("action", action.id, action)
        return action

    def validate_pending(self, action_id: str, token: str) -> Plan:
        action = self.get(action_id)
        plan = self.plans.get(action_id)
        if action.status == "expired":
            raise ActionError("This approval expired. Run a new preflight.", 410)
        if plan is None or action.status != "awaiting_approval":
            raise ActionError("This approval has already been used or canceled.")
        if not compare_digest(plan.token.encode(), token.encode()):
            raise ActionError("This approval token does not match the plan.", 403)
        return plan

    def cancel(self, action_id: str, token: str) -> Action:
        return self.save(self.validate_pending(action_id, token), "canceled", message="Approval canceled.")

    def approve(self, action_id: str, token: str) -> Action:
        plan = self.validate_pending(action_id, token)
        if self.busy:
            raise ActionError("An approved action is running.")
        session = self.store.get("preflight", plan.action.session_id, PreflightSession)
        if session is None:
            raise ActionError("The originating preflight is unavailable.", 410)
        action = self.save(plan, "approved")
        self.store.event("action_approved", "Demo action approved", "The employee approved stopping the itor workload.")
        self.job = asyncio.create_task(self.execute(plan, session))
        return action

    async def samples(self) -> list[DeviceSnapshot]:
        return [await asyncio.to_thread(self.telemetry.capture) for _ in range(3)]

    def measurement(self, samples: list[DeviceSnapshot], result: ReadinessReport, workload_id: str) -> ActionMeasurement:
        latest = samples[-1]
        system = [sample.cpu_percent for sample in samples if sample.cpu_percent is not None]
        active = latest.workload.id == workload_id and latest.workload.active
        process = [sample.workload.cpu_percent for sample in samples
                   if sample.workload.id == workload_id and sample.workload.cpu_percent is not None]
        return ActionMeasurement(captured_at=latest.captured_at,
                                 system_cpu_percent=round(mean(system), 1) if system else None,
                                 workload_cpu_percent=(round(mean(process), 1) if process else None) if active else 0,
                                 workload_active=active, readiness=result.readiness)

    async def execute(self, plan: Plan, session: PreflightSession) -> None:
        try:
            self.save(plan, "executing")
            before_samples = await self.samples()
            before = self.measurement(before_samples, self.recheck(before_samples[-1], session), plan.workload_id)
            self.save(plan, "executing", before=before)
            if not before.workload_active or not await asyncio.to_thread(self.workload.stop, plan.workload_id):
                raise WorkloadError("The original workload had already exited. No remediation was performed.")
            self.save(plan, "verifying")
            after_samples = await self.samples()
            result = self.recheck(after_samples[-1], session)
            after = self.measurement(after_samples, result, plan.workload_id)
            if after.workload_active:
                raise WorkloadError("The workload is still running after the stop attempt.")
            system_delta = (round(after.system_cpu_percent - before.system_cpu_percent, 1)
                            if after.system_cpu_percent is not None and before.system_cpu_percent is not None else None)
            verification = Verification(process_exited=True, system_cpu_delta=system_delta,
                                        improved=bool(before.workload_cpu_percent and before.workload_cpu_percent > 0))
            self.store.put("preflight", session.id, PreflightSession.model_validate({
                **session.model_dump(), **result.model_dump(), "completed_at": utc_now(),
            }))
            self.save(plan, "succeeded", after=after, verification=verification,
                      message="The original itor workload exited and device checks were rerun.")
        except WorkloadError as error:
            self.save(plan, "failed", message=str(error))
            self.store.event("action_failed", "Demo remediation could not be verified", str(error))
        except Exception:
            self.save(plan, "failed", message="The run could not complete. Check device readiness again.")
            self.store.event("action_failed", "Demo remediation could not be verified", "The local run encountered an error.")
        else:
            self.store.event("action_verified", "Demo workload stopped and verified",
                             "The owned process exited. Fresh processor measurements and readiness were recorded.")

    def history(self) -> list[Action]:
        return [self.get(item.id) for item in self.store.list("action", Action)]

    async def close(self) -> None:
        if self.job is not None:
            await self.job
