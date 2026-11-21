"""Two quick network fixes. Each one shows its exact command and runs only after Approve."""
from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from hmac import compare_digest
from secrets import token_urlsafe
from typing import Literal

from pydantic import BaseModel

from .models import new_id, utc_now

FixId = Literal["flush_dns", "restart_wifi"]

RESTART_WIFI = (
    "Get-NetAdapter -Physical | Where-Object { $_.Status -ne 'Disabled' -and "
    "($_.InterfaceDescription -match 'Wireless|Wi-?Fi|WLAN' -or $_.Name -match 'Wi-?Fi|WLAN') } | "
    "Restart-NetAdapter -Confirm:$false"
)


class NetworkFix(BaseModel):
    id: FixId
    title: str
    what_it_does: str
    command: str
    needs_admin: bool
    supported: bool


class FixRun(BaseModel):
    id: str
    fix_id: FixId
    title: str
    status: Literal["awaiting_approval", "running", "succeeded", "failed", "canceled", "expired"]
    created_at: datetime
    expires_at: datetime
    approval_token: str | None = None
    internet_before: str | None = None
    internet_after: str | None = None
    message: str | None = None


@dataclass
class FixSpec:
    title: str
    what_it_does: str
    command: list[str]
    shown: str
    needs_admin: bool


FIXES: dict[str, FixSpec] = {
    "flush_dns": FixSpec(
        "Clear the DNS cache",
        "Forgets old website addresses. Helps when websites stop loading after a network change. Instant, nothing is lost.",
        ["ipconfig", "/flushdns"], "ipconfig /flushdns", False,
    ),
    "restart_wifi": FixSpec(
        "Turn Wi-Fi off and on",
        "Restarts the Wi-Fi card, like switching it off and on. The connection drops for about 10 seconds.",
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", RESTART_WIFI],
        f"powershell -Command \"{RESTART_WIFI}\"", True,
    ),
}


def run_command(command: list[str]) -> tuple[bool, str]:
    try:
        # Windows tools print in the console code page ("oem"), e.g. French accents.
        done = subprocess.run(command, capture_output=True, text=True, timeout=60, errors="replace",
                              encoding="oem" if sys.platform == "win32" else None,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)[:300]
    output = (done.stdout or done.stderr or "").strip()[-300:]
    return done.returncode == 0, output


class NetworkFixes:
    def __init__(self, check_internet, on_done=None, runner=run_command, expires_in: int = 90,
                 windows: bool = sys.platform == "win32"):
        self.check_internet = check_internet  # async () -> state string
        self.on_done = on_done                # (FixRun) -> None
        self.runner = runner
        self.expires_in = expires_in
        self.windows = windows
        self.runs: dict[str, tuple[FixRun, str]] = {}
        self.lock = asyncio.Lock()

    def available(self) -> list[NetworkFix]:
        return [NetworkFix(id=key, title=spec.title, what_it_does=spec.what_it_does, command=spec.shown,
                           needs_admin=spec.needs_admin, supported=self.windows)
                for key, spec in FIXES.items()]

    def plan(self, fix_id: FixId) -> FixRun:
        if not self.windows:
            raise ValueError("These fixes only work on Windows.")
        now = utc_now()
        token = token_urlsafe(24)
        run = FixRun(id=new_id(), fix_id=fix_id, title=FIXES[fix_id].title, status="awaiting_approval",
                     created_at=now, expires_at=now + timedelta(seconds=self.expires_in))
        self.runs[run.id] = (run, token)
        return run.model_copy(update={"approval_token": token})

    def get(self, run_id: str) -> FixRun:
        if run_id not in self.runs:
            raise KeyError(run_id)
        run, token = self.runs[run_id]
        if run.status == "awaiting_approval" and utc_now() >= run.expires_at:
            run = run.model_copy(update={"status": "expired", "message": "Approval expired. Ask again."})
            self.runs[run_id] = (run, token)
        return run

    def cancel(self, run_id: str, token: str) -> FixRun:
        run = self._pending(run_id, token)
        run = run.model_copy(update={"status": "canceled", "message": "You declined. Nothing was run."})
        self.runs[run_id] = (run, self.runs[run_id][1])
        return run

    def _pending(self, run_id: str, token: str) -> FixRun:
        run = self.get(run_id)
        if run.status != "awaiting_approval":
            raise PermissionError(f"This fix is {run.status}.")
        if not compare_digest(self.runs[run_id][1].encode(), token.encode()):
            raise PermissionError("Approval does not match.")
        return run

    async def approve(self, run_id: str, token: str) -> FixRun:
        run = self._pending(run_id, token)
        async with self.lock:
            spec = FIXES[run.fix_id]
            run = run.model_copy(update={"status": "running", "internet_before": await self.check_internet()})
            self.runs[run_id] = (run, token)
            ok, output = await asyncio.to_thread(self.runner, spec.command)
            if ok and run.fix_id == "restart_wifi":
                await asyncio.sleep(10)  # give Wi-Fi time to reconnect before measuring again
            after = await self.check_internet()
            message = ("Done. " if ok else "The command failed. ") + (output or "")
            if not ok and spec.needs_admin:
                message += " (This fix needs itor to run as administrator.)"
            run = run.model_copy(update={"status": "succeeded" if ok else "failed", "internet_after": after,
                                         "message": message.strip()})
            self.runs[run_id] = (run, token)
        if self.on_done:
            self.on_done(run)
        return run
