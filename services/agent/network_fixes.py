"""Two quick network fixes. Each one shows its exact command and runs only after Approve."""
from __future__ import annotations

import asyncio
import base64
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
OFFLINE_STATES = {"unreachable", "disconnected", "cloud down (demo)"}

# Turns the Wi-Fi *radio* off then on through Windows (Windows.Devices.Radios), like the Wi-Fi button in the
# taskbar. Works when Wi-Fi was switched off or airplane mode is on, and needs no admin rights.
WIFI_RADIO_CYCLE = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$wifi = $radios | Where-Object { $_.Kind -eq 'WiFi' } | Select-Object -First 1
if (-not $wifi) { Write-Output 'No Wi-Fi radio found.'; exit 2 }
Await ($wifi.SetStateAsync('Off')) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
Start-Sleep -Seconds 2
$status = Await ($wifi.SetStateAsync('On')) ([Windows.Devices.Radios.RadioAccessStatus])
Write-Output "Wi-Fi radio: $($wifi.State) ($status)"
if ($status -ne 'Allowed') { exit 3 }
"""


def encoded(script: str) -> str:
    """PowerShell -EncodedCommand value: no quoting can change the script."""
    return base64.b64encode(script.encode("utf-16-le")).decode()


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
        "Switches the Wi-Fi radio off and back on, like the Wi-Fi button in the taskbar. "
        "Also turns Wi-Fi back on if it was switched off. Then itor waits for the internet to come back.",
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(WIFI_RADIO_CYCLE)],
        "Windows.Devices.Radios: Wi-Fi radio Off, then On", False,
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
            after = await self.check_internet()
            if ok and run.fix_id == "restart_wifi":
                # Wi-Fi needs a few seconds to reconnect: wait up to 25 s for the internet to come back.
                for _ in range(10):
                    if after not in OFFLINE_STATES:
                        break
                    await asyncio.sleep(2.5)
                    after = await self.check_internet()
            # Only "succeeded" when it really worked: the command ran, and for the Wi-Fi fix, internet is back.
            fixed = ok and not (run.fix_id == "restart_wifi" and after in OFFLINE_STATES)
            if fixed:
                message = "Done. " + (output or "")
            elif ok:
                message = "The command ran, but the internet is still unreachable. Ask IT if it stays like this."
            else:
                message = "The command failed. " + (output or "")
            run = run.model_copy(update={"status": "succeeded" if fixed else "failed", "internet_after": after,
                                         "message": message.strip()})
            self.runs[run_id] = (run, token)
        if self.on_done:
            self.on_done(run)
        return run
