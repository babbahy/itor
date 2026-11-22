import asyncio
import time
import sqlite3
from contextlib import asynccontextmanager, suppress
from hmac import compare_digest
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .company import CompanySender, CompanyServer, Envelope, TeamReport
from .config import Settings
from .connectivity import ConnectivityManager, ConnectivityReport, ServiceState, ServiceStatus
from .incidents import Incident, IncidentLog, failed_checks, is_offline
from .support import Ticket, TicketInput
from .network_fixes import FixId, FixRun, NetworkFix, NetworkFixes
from .diagnosis import GeminiDiagnosisProvider, DiagnosisResult, OllamaDiagnosisProvider
from .models import (
    Action, ActionInput, Activity, Approval, AvailableAction, ChatInput, Consent, DemoStop, DeviceSnapshot,
    DiagnoseInput, PreflightSession, Readiness, ReadinessReport,
    SimulateInput, WorkloadStatus, new_id, utc_now,
)
from .readiness import ReadinessEngine
from .remediation import ActionError, LocalSafeRemediationProvider
from .storage import Store
from .sync import LocalSyncService, SyncStatus
from .telemetry import LocalTelemetryProvider
from .workload import WorkloadError, WorkloadManager
from .worktime import WorkDay, WorkDayView, WorktimeTracker


class ServiceReport(BaseModel):
    agent: Literal["connected"] = "connected"
    telemetry: Literal["local"] = "local"
    remediation: Literal["local"] = "local"
    mode: Literal["live_local"] = "live_local"
    connectivity: ConnectivityReport
    demo: WorkloadStatus
    model: str


class DemoReset(BaseModel):
    workload: WorkloadStatus


class PrivacyReport(BaseModel):
    inference_location: str = "This device"
    model: str
    retention_days: int
    telemetry_sources: list[str]
    stored_data: list[str]
    external_connections: list[str]
    sync: SyncStatus


class Insights(BaseModel):
    preflights: int
    findings: int
    verified_actions: int
    recent_readiness: Readiness | None


class IncidentReport(BaseModel):
    current: Incident | None
    history: list[Incident]


class CompanyStatus(BaseModel):
    configured: bool
    employee: str
    pending: int
    last_sent_at: datetime | None
    last_error: str | None


class BlockedInput(BaseModel):
    blocked: bool


class DiagnosisRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    session_id: str | None = None
    result: DiagnosisResult


class Agent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = Store(settings.db_path, settings.retention_days)
        self.sync = LocalSyncService(db_path=settings.db_path, retention_days=settings.retention_days)
        self.workload = WorkloadManager(settings.demo_seconds)
        self.telemetry = LocalTelemetryProvider(self.workload)
        self.engine = ReadinessEngine(settings.cpu_threshold, settings.cpu_window)
        self.local_ai = OllamaDiagnosisProvider(base_url=settings.ollama_url, model=settings.ollama_model,
                                                timeout=settings.ollama_timeout)
        self.diagnosis = GeminiDiagnosisProvider(self.local_ai, model=settings.gemini_model)
        self.connectivity = ConnectivityManager(
            ollama_base_url=settings.ollama_url, ollama_model=settings.ollama_model,
            ollama_loading=lambda: self.diagnosis.is_loading,
            internet_probe_url=settings.internet_probe_url, internet_expected_status=settings.internet_expected_status,
            probe_interval=settings.connectivity_interval, timeout=settings.connectivity_timeout,
            stability_seconds=settings.connectivity_stability, on_change=self.on_connection_change,
        )
        self.remediation = LocalSafeRemediationProvider(
            self.workload, self.telemetry, self.store, self.recheck_action, settings.action_expiry_seconds,
        )
        self.worktime = WorktimeTracker(self.store, settings.employee_name, settings.idle_seconds)
        self.company_sender = CompanySender(self.store, settings.company_url, settings.company_key)
        self.company = CompanyServer(self.store, settings.demo_team)
        self.incidents = IncidentLog(self.store, settings.employee_name, on_closed=self.company_sender.queue_incident)
        self.fixes = NetworkFixes(check_internet=self.internet_state, on_done=self.fix_done)
        self.demo_lock = asyncio.Lock()
        self.ai_quiet_until = 0.0
        self.connectivity_report: ConnectivityReport | None = None
        self.history_generation = 0

    def on_connection_change(self, old: ServiceStatus, new: ServiceStatus) -> None:
        self.store.event("connectivity_changed", f"{new.name} status changed", f"{old.state.value} → {new.state.value}. {new.explanation}")

    async def connectivity_status(self) -> ConnectivityReport:
        self.connectivity_report = await self.connectivity.status()
        return self.connectivity_report

    def readiness(self, snapshot: DeviceSnapshot) -> ReadinessReport:
        internet = self.connectivity_report.internet if self.connectivity_report else None
        internet_unavailable = internet is not None and internet.state in {
            ServiceState.DISCONNECTED, ServiceState.UNREACHABLE,
        }
        return self.engine.evaluate(snapshot, self.telemetry.history(), internet_unavailable,
                                    ignore_cpu=self.ai_busy())

    async def internet_state(self) -> str:
        self.connectivity_report = await self.connectivity.inspect(probe=True)
        report = self.connectivity_report
        return "cloud down (demo)" if report.simulated_cloud_outage else report.internet.state.value

    def fix_done(self, run: FixRun) -> None:
        self.incidents.note_fix(f"{run.title}: {run.status}")
        self.store.event("network_fix", f"{run.title}: {run.status}", run.message or "")

    async def send_to_company(self) -> int:
        await asyncio.to_thread(self.company_sender.queue_day, self.worktime.day(), self.incidents.history(50))
        return await self.company_sender.flush()

    def ai_busy(self) -> bool:
        """True while the local AI runs (and 15 s after): its CPU use must not count as the PC being slow."""
        return self.diagnosis.is_loading or time.monotonic() < self.ai_quiet_until

    def lost_time_causes(self) -> list[str]:
        """Tool problems right now that make active time count as lost time."""
        causes: list[str] = []
        report = self.connectivity_report
        if report and (report.simulated_cloud_outage or report.internet.state in {
            ServiceState.DISCONNECTED, ServiceState.UNREACHABLE,
        }):
            causes.append("offline")
        latest = self.telemetry.latest()
        if latest and not self.ai_busy() and self.engine.cpu_result(latest, self.telemetry.history())[0]:
            causes.append("pc_overloaded")
        return causes

    async def worktime_tick(self, elapsed: float) -> WorkDay:
        return await asyncio.to_thread(self.worktime.tick, elapsed, self.lost_time_causes())

    def recheck_action(self, snapshot: DeviceSnapshot, session: PreflightSession) -> ReadinessReport:
        return self.readiness(snapshot)

    def require_session(self, session_id: str) -> PreflightSession:
        session = self.store.get("preflight", session_id, PreflightSession)
        if session is None:
            raise HTTPException(404, "Preflight session not found. Run the device checks again.")
        return session

    async def sample_loop(self) -> None:
        cycles = 0
        last_tick = time.monotonic()
        ticks = 0
        while True:
            await asyncio.sleep(self.settings.sample_interval)
            await asyncio.to_thread(self.telemetry.capture)
            await self.connectivity_status()
            if self.incidents.update(self.connectivity_report):
                await self.company_sender.flush()
            now = time.monotonic()
            if now - last_tick >= self.settings.worktime_interval:
                await self.worktime_tick(now - last_tick)
                last_tick = now
                ticks += 1
                if ticks % 4 == 0:  # about once a minute
                    await self.send_to_company()
            cycles += 1
            if cycles % 60 == 0:
                await asyncio.to_thread(self.store.prune)

    async def explain(self, session_id: str | None, question: str | None = None) -> DiagnosisResult:
        generation = self.history_generation
        if session_id:
            findings = self.require_session(session_id).findings
        else:
            latest = self.telemetry.latest()
            findings = self.readiness(latest).findings if latest else []
        try:
            result = await self.diagnosis.explain([item.model_dump(mode="json") for item in findings],
                                                  question=question, network=await self.connectivity_status())
        finally:
            self.ai_quiet_until = time.monotonic() + 15
        if generation == self.history_generation:
            diagnosis = DiagnosisRecord(session_id=session_id, result=result)
            self.store.put("diagnosis", diagnosis.id, diagnosis)
            provider = {"gemini": "Gemini", "ollama": "Local AI"}.get(result.provider, "Simple rules")
            self.store.event("diagnosis", "Device explanation prepared", f"{provider}. {result.headline}")
            self.incidents.note_help(f"{provider}: {result.headline}")
        return result

    def check_demo_idle(self) -> None:
        if self.remediation.busy:
            raise HTTPException(409, "An approved action is still running.")

    async def stop_demo(self) -> WorkloadStatus:
        self.check_demo_idle()
        current = self.workload.status()
        if current.active and current.id:
            stopped = await asyncio.to_thread(self.workload.stop, current.id)
            if not stopped and self.workload.status().active:
                raise WorkloadError("The demo workload could not be stopped.")
            await asyncio.to_thread(self.telemetry.capture)
            self.store.event("demo_stopped", "Demo workload stopped", "The demo control ended the itor-owned workload.")
        return self.workload.status()


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = Agent(settings or Settings.from_env())
        app.state.agent = service
        await asyncio.to_thread(service.telemetry.capture)
        await service.connectivity_status()
        sampling = asyncio.create_task(service.sample_loop())
        try:
            yield
        finally:
            sampling.cancel()
            with suppress(asyncio.CancelledError):
                await sampling
            await service.connectivity.close()
            try:
                await service.remediation.close()
            finally:
                await asyncio.to_thread(service.workload.close)

    app = FastAPI(title="itor Device Agent", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.middleware("http")
    async def local_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    async def authorized(request: Request, x_itor_key: Annotated[str | None, Header()] = None) -> Agent:
        service: Agent = request.app.state.agent
        if (not service.settings.api_key or x_itor_key is None or
                not compare_digest(service.settings.api_key.encode(), x_itor_key.encode())):
            raise HTTPException(401, "A valid local agent key is required.")
        if request.method not in {"GET", "HEAD"} and "origin" in request.headers:
            raise HTTPException(403, "Send browser requests through the itor application.")
        return service

    LocalAgent = Annotated[Agent, Depends(authorized)]

    @app.exception_handler(ActionError)
    async def action_error(_, error: ActionError):
        return JSONResponse({"detail": str(error)}, error.status_code)

    @app.exception_handler(WorkloadError)
    async def demo_error(_, error: WorkloadError):
        return JSONResponse({"detail": str(error)}, 409)

    @app.exception_handler(sqlite3.Error)
    async def database_error(_, _error):
        return JSONResponse({"detail": "The local database is unavailable. Check access and try again."}, 503)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, error: RequestValidationError):
        problems = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in error.errors()]
        return JSONResponse({"detail": problems}, 422)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    async def status(service: LocalAgent) -> ServiceReport:
        return ServiceReport(connectivity=await service.connectivity_status(), demo=service.workload.status(),
                             model=service.local_ai.model)

    @app.get("/api/device/snapshot")
    async def snapshot(service: LocalAgent) -> DeviceSnapshot:
        return service.telemetry.latest() or await asyncio.to_thread(service.telemetry.capture)

    @app.get("/api/device/history")
    async def history(service: LocalAgent) -> list[DeviceSnapshot]:
        return service.telemetry.history()

    @app.get("/api/device/capabilities")
    async def capabilities(service: LocalAgent) -> dict[str, str]:
        return service.telemetry.capabilities()

    @app.get("/api/device/readiness")
    async def readiness(service: LocalAgent) -> ReadinessReport:
        await service.connectivity_status()
        return service.readiness(await snapshot(service))

    @app.post("/api/preflight", status_code=201)
    async def preflight(service: LocalAgent) -> PreflightSession:
        started = utc_now()
        reading = await asyncio.to_thread(service.telemetry.capture)
        await service.connectivity_status()
        result = service.readiness(reading)
        session = PreflightSession(**result.model_dump(), started_at=started)
        service.store.put("preflight", session.id, session)
        count = len(session.findings)
        service.store.event("preflight", "Device check completed", f"{session.readiness.replace('_', ' ').capitalize()}. {count} finding(s).")
        for item in session.findings:
            service.store.event("finding", item.title, item.evidence)
        return session

    @app.get("/api/preflight/latest")
    async def latest_preflight(service: LocalAgent) -> PreflightSession | None:
        return next(iter(service.store.list("preflight", PreflightSession, limit=1)), None)

    @app.get("/api/preflight/{session_id}")
    async def get_preflight(session_id: str, service: LocalAgent) -> PreflightSession:
        return service.require_session(session_id)

    @app.post("/api/diagnose")
    async def diagnose(body: DiagnoseInput, service: LocalAgent) -> DiagnosisResult:
        return await service.explain(body.session_id)

    @app.post("/api/diagnosis/chat")
    async def chat(body: ChatInput, service: LocalAgent) -> DiagnosisResult:
        return await service.explain(body.session_id, body.question)

    @app.get("/api/actions/available")
    async def available_actions(service: LocalAgent) -> list[AvailableAction]:
        return service.remediation.available()

    @app.post("/api/actions/plan", status_code=201)
    async def plan_action(body: ActionInput, service: LocalAgent) -> Action:
        return service.remediation.plan(service.require_session(body.session_id))

    @app.post("/api/actions/{action_id}/approve", status_code=202)
    async def approve_action(action_id: str, body: Approval, service: LocalAgent) -> Action:
        if service.demo_lock.locked():
            raise HTTPException(409, "Wait for the demo control to finish.")
        return service.remediation.approve(action_id, body.approval_token)

    @app.post("/api/actions/{action_id}/cancel")
    async def cancel_action(action_id: str, body: Consent, service: LocalAgent) -> Action:
        return service.remediation.cancel(action_id, body.approval_token)

    @app.get("/api/actions/history")
    async def action_history(service: LocalAgent) -> list[Action]:
        return service.remediation.history()

    @app.get("/api/actions/{action_id}")
    async def get_action(action_id: str, service: LocalAgent) -> Action:
        return service.remediation.get(action_id)

    @app.get("/api/demo/status")
    async def demo_status(service: LocalAgent) -> WorkloadStatus:
        return service.workload.status()

    @app.post("/api/demo/start", status_code=201)
    async def start_demo(service: LocalAgent) -> WorkloadStatus:
        async with service.demo_lock:
            service.check_demo_idle()
            service.workload.start()
            await asyncio.to_thread(service.telemetry.capture)
            service.store.event("demo_started", "Demo workload started", "A time-limited itor child process was started.")
            return service.workload.status()

    @app.post("/api/demo/stop")
    async def stop_demo(body: DemoStop, service: LocalAgent) -> WorkloadStatus:
        async with service.demo_lock:
            return await service.stop_demo()

    @app.post("/api/demo/reset")
    async def reset_demo(service: LocalAgent, body: DemoStop | None = None) -> DemoReset:
        async with service.demo_lock:
            service.check_demo_idle()
            if service.workload.status().active and not body:
                raise HTTPException(409, "Confirm stopping the active demo workload before resetting.")
            workload = await service.stop_demo()
            service.connectivity_report = await service.connectivity.simulate_cloud(False)
            service.store.event("demo_reset", "Demo reset", "The demo was restored to its starting state.")
            return DemoReset(workload=workload)

    @app.post("/api/demo/cloud")
    async def simulate_cloud(body: SimulateInput, service: LocalAgent) -> ConnectivityReport:
        service.connectivity_report = await service.connectivity.simulate_cloud(body.enabled)
        return service.connectivity_report

    @app.get("/api/connectivity")
    async def connectivity(service: LocalAgent) -> ConnectivityReport:
        return await service.connectivity_status()

    @app.post("/api/connectivity/check")
    async def check_connection(service: LocalAgent) -> ConnectivityReport:
        service.connectivity_report = await service.connectivity.inspect(probe=True)
        return service.connectivity_report

    @app.get("/api/worktime/today")
    async def worktime_today(service: LocalAgent) -> WorkDayView:
        return service.worktime.view()

    @app.get("/api/worktime/week")
    async def worktime_week(service: LocalAgent) -> list[WorkDay]:
        return service.worktime.week()

    @app.post("/api/worktime/blocked")
    async def worktime_blocked(body: BlockedInput, service: LocalAgent) -> WorkDayView:
        if body.blocked != service.worktime.blocked:
            service.worktime.blocked = body.blocked
            title = "Marked as blocked" if body.blocked else "No longer blocked"
            service.store.event("blocked", title, "This time counts as lost because of tools." if body.blocked else "Time counts as active again.")
        return service.worktime.view(await service.worktime_tick(0))

    @app.post("/api/demo/worktime")
    async def demo_worktime(service: LocalAgent) -> WorkDayView:
        work = await asyncio.to_thread(service.worktime.fill_demo_day)
        service.store.event("demo_worktime", "Demo day added", "A sample morning was added to today's time.")
        return service.worktime.view(work)

    @app.get("/api/fixes")
    async def fixes(service: LocalAgent) -> list[NetworkFix]:
        return service.fixes.available()

    @app.post("/api/fixes/{fix_id}/plan", status_code=201)
    async def plan_fix(fix_id: FixId, service: LocalAgent) -> FixRun:
        try:
            return service.fixes.plan(fix_id)
        except ValueError as error:
            raise HTTPException(400, str(error))

    @app.get("/api/fixes/runs/{run_id}")
    async def get_fix(run_id: str, service: LocalAgent) -> FixRun:
        try:
            return service.fixes.get(run_id)
        except KeyError:
            raise HTTPException(404, "Fix not found.")

    @app.post("/api/fixes/runs/{run_id}/approve")
    async def approve_fix(run_id: str, body: Approval, service: LocalAgent) -> FixRun:
        try:
            return await service.fixes.approve(run_id, body.approval_token)
        except KeyError:
            raise HTTPException(404, "Fix not found.")
        except PermissionError as error:
            raise HTTPException(409, str(error))

    @app.post("/api/fixes/runs/{run_id}/cancel")
    async def cancel_fix(run_id: str, body: Consent, service: LocalAgent) -> FixRun:
        try:
            return service.fixes.cancel(run_id, body.approval_token)
        except KeyError:
            raise HTTPException(404, "Fix not found.")
        except PermissionError as error:
            raise HTTPException(409, str(error))

    @app.get("/api/incidents")
    async def incidents(service: LocalAgent) -> IncidentReport:
        return IncidentReport(current=service.incidents.current, history=service.incidents.history())

    @app.post("/api/support/ticket", status_code=201)
    async def support_ticket(body: TicketInput, service: LocalAgent) -> Ticket:
        report = await service.connectivity_status()
        reading = service.readiness(await snapshot(service))
        since = utc_now() - timedelta(hours=2)
        tried = list(dict.fromkeys(  # recent attempts only, short titles, no duplicates
            item.title[:120] for item in service.store.list("activity", Activity, limit=40)
            if item.created_at >= since and item.kind in {"network_fix", "action_verified", "action_failed"}))[:5]
        ticket = Ticket(
            employee=service.settings.employee_name, message=body.message, diagnosis=body.diagnosis,
            pc_status=reading.readiness, findings=[item.title for item in reading.findings],
            connection=(failed_checks(report) or ["Connection looks normal"]) if report else [],
            tried=tried, outage_id=service.incidents.current.id if service.incidents.current else None,
        )
        service.company_sender.queue_ticket(ticket)
        if not is_offline(report):
            await service.company_sender.flush()
        ticket.sent = not service.company_sender.is_waiting(f"ticket:{ticket.id}")
        service.store.put("ticket", ticket.id, ticket)
        service.store.event("ticket", "Sent to IT" if ticket.sent else "Saved for IT",
                            "IT has your message and what itor found." if ticket.sent
                            else "It will be sent to IT when the connection is back.")
        return ticket

    @app.get("/api/support/tickets")
    async def support_tickets(service: LocalAgent) -> list[Ticket]:
        tickets = service.store.list("ticket", Ticket, limit=20)
        return [item.model_copy(update={"sent": not service.company_sender.is_waiting(f"ticket:{item.id}")})
                for item in tickets]

    @app.get("/api/company/status")
    async def company_status(service: LocalAgent) -> CompanyStatus:
        sender = service.company_sender
        return CompanyStatus(configured=sender.configured, employee=service.settings.employee_name,
                             pending=sender.pending(), last_sent_at=sender.last_sent_at, last_error=sender.last_error)

    @app.post("/api/company/send")
    async def company_send(service: LocalAgent) -> CompanyStatus:
        await service.send_to_company()
        return await company_status(service)

    @app.get("/api/company/team")
    async def company_team(service: LocalAgent) -> TeamReport:
        return service.company.team()

    @app.post("/api/company/reports", status_code=204)
    async def company_receive(body: Envelope, request: Request,
                              x_itor_company_key: Annotated[str | None, Header()] = None) -> Response:
        service: Agent = request.app.state.agent
        key = service.settings.company_key
        if not key or x_itor_company_key is None or not compare_digest(key.encode(), x_itor_company_key.encode()):
            raise HTTPException(401, "A valid company key is required.")
        if "origin" in request.headers:
            raise HTTPException(403, "Reports are sent by itor, not by a browser.")
        service.company.receive(body)
        return Response(status_code=204)

    @app.get("/api/activity")
    async def activity(service: LocalAgent) -> list[Activity]:
        return service.store.list("activity", Activity)

    @app.get("/api/insights")
    async def insights(service: LocalAgent) -> Insights:
        with service.store.connect() as db:
            counts = dict(db.execute("SELECT bucket, COUNT(*) FROM records GROUP BY bucket"))
            findings = db.execute("SELECT COUNT(*) FROM records WHERE bucket='activity' AND json_extract(payload, '$.kind')='finding'").fetchone()[0]
            verified = db.execute("SELECT COUNT(*) FROM records WHERE bucket='action' AND json_extract(payload, '$.status')='succeeded'").fetchone()[0]
        latest = await latest_preflight(service)
        return Insights(preflights=counts.get("preflight", 0), findings=findings, verified_actions=verified,
                        recent_readiness=latest.readiness if latest else None)

    @app.get("/api/privacy")
    async def privacy(service: LocalAgent) -> PrivacyReport:
        external = ["One approved HTTPS connectivity endpoint and its DNS hostname"] if service.settings.internet_probe_url else []
        return PrivacyReport(model=service.settings.ollama_model, retention_days=service.settings.retention_days,
                             telemetry_sources=["Operating system CPU, memory, disk and network summaries", "itor-owned demo workload"],
                             stored_data=["Preflight findings and diagnostic summaries", "Action approvals, outcomes and connectivity changes"],
                             external_connections=external, sync=service.sync.status())

    @app.delete("/api/privacy/history", status_code=204)
    async def clear_history(service: LocalAgent) -> Response:
        service.check_demo_idle()
        service.store.clear_history()
        service.sync.clear()
        service.telemetry.clear_history()
        service.remediation.plans.clear()
        service.history_generation += 1
        return Response(status_code=204)

    return app


app = create_app()
