"""Independent local and optional external connectivity observations."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from ipaddress import ip_address
from pathlib import Path
import re
import socket
import sys
import threading
import subprocess
from time import monotonic
from typing import Protocol
from urllib.parse import urlsplit

import httpx
import psutil
from pydantic import BaseModel, ConfigDict


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNREACHABLE = "unreachable"
    AUTHENTICATION_ERROR = "authentication_error"
    DEGRADED = "degraded"
    CHECKING = "checking"
    UNKNOWN = "unknown"
    NOT_CONFIGURED = "not_configured"


class ServiceStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    state: ServiceState
    configured: bool = True
    explanation: str
    last_success_at: datetime | None = None
    last_checked_at: datetime | None = None
    duration_ms: int | None = None
    error_category: str | None = None


class ConnectivityReport(BaseModel):
    agent: ServiceStatus
    ollama: ServiceStatus
    ollama_loading: bool
    network_interface: ServiceStatus
    gateway: ServiceStatus
    dns_resolver: ServiceStatus
    dns: ServiceStatus
    internet: ServiceStatus
    nexthink: ServiceStatus
    nexthink_reachability: ServiceStatus
    nexthink_auth: ServiceStatus
    offline_rescue: bool
    simulated_cloud_outage: bool
    updated_at: datetime
    cloud_data_stale: bool
    cloud_last_updated_at: datetime | None


@dataclass(frozen=True)
class Observation:
    state: ServiceState
    explanation: str
    error_category: str | None = None


@dataclass(frozen=True)
class CloudProbeResult:
    """A future, documented tenant adapter supplies both observations."""

    reachability: Observation
    authentication: Observation


class CloudProbe(Protocol):
    async def __call__(self) -> CloudProbeResult: ...


def normalize_local_ollama(base_url: str) -> str:
    """Prevent local inference traffic reaching a non-loopback destination."""
    parsed = urlsplit(base_url)
    host = parsed.hostname
    try:
        is_loopback = host == "localhost" or bool(host and ip_address(host).is_loopback)
    except ValueError:
        is_loopback = False
    if (
        parsed.scheme != "http" or not is_loopback or parsed.username is not None
        or parsed.password is not None or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment
    ):
        raise ValueError("OLLAMA_BASE_URL must be an HTTP origin on the local loopback interface")
    # Accessing .port also validates an explicitly configured port.
    port = parsed.port
    if host == "localhost":
        return f"http://127.0.0.1:{port}" if port is not None else "http://127.0.0.1"
    return base_url.rstrip("/")


def local_model_name(model: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)?", model) or "cloud" in model.lower():
        raise ValueError("OLLAMA_MODEL must name a downloaded local model")
    return model if ":" in model else f"{model}:latest"


def normalize_probe_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.query or parsed.fragment
    ):
        raise ValueError("ITOR_INTERNET_PROBE_URL must be an HTTPS URL without credentials, query or fragment")
    if parsed.port is not None and parsed.port < 1:
        raise ValueError("ITOR_INTERNET_PROBE_URL must use a valid HTTPS port")
    return url


# Virtual adapters (VirtualBox, VMware, Hyper-V, WSL, VPN taps...) stay "up" when Wi-Fi is off,
# so they must not count as being connected.
VIRTUAL_WORDS = ("virtualbox", "vmware", "vethernet", "hyper-v", "wsl", "loopback", "pseudo", "tap-", "tunnel",
                 "bluetooth", "docker", "npcap", "zerotier", "tailscale")
_physical_cache: tuple[float, set[str] | None] = (0.0, None)
_physical_refreshing = threading.Lock()


def _refresh_physical() -> None:
    global _physical_cache
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-NetAdapter -Physical | ForEach-Object { $_.Name }"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        names = {line.strip() for line in done.stdout.splitlines() if line.strip()} if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        names = None
    _physical_cache = (monotonic(), names if names is not None else _physical_cache[1])
    _physical_refreshing.release()


def physical_adapters() -> set[str] | None:
    """Names of physical network adapters on Windows. None when not known yet (or not Windows).

    Never blocks: the list (from PowerShell, ~1 s) is refreshed in the background every 60 s.
    """
    if sys.platform != "win32":
        return None
    checked, names = _physical_cache
    if (names is None or monotonic() - checked >= 60) and _physical_refreshing.acquire(blocking=False):
        threading.Thread(target=_refresh_physical, daemon=True).start()
    return names


def counts_as_network(name: str, address: str, physical: set[str] | None) -> bool:
    """A real connection: a physical (or not obviously virtual) adapter with a routable address."""
    lowered = name.lower()
    if physical is not None and name not in physical:
        return False
    if any(word in lowered for word in VIRTUAL_WORDS):
        return False
    ip = ip_address(address.split("%")[0])
    # 169.254.x.x / fe80:: are self-assigned when there is no network: not connected.
    return not (ip.is_loopback or ip.is_unspecified or ip.is_link_local)


def check_interface() -> Observation:
    try:
        addresses = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        physical = physical_adapters()
        connected = any(
            stats.get(name) and stats[name].isup
            and address.family in (socket.AF_INET, socket.AF_INET6)
            and counts_as_network(name, address.address, physical)
            for name, entries in addresses.items()
            for address in entries
        )
    except (OSError, psutil.Error, ValueError):
        return Observation(ServiceState.UNKNOWN, "The OS did not provide usable adapter data.", "unsupported")
    if not connected:
        return Observation(
            ServiceState.DISCONNECTED,
            "No active network adapter with a non-loopback IP address was observed.",
            "no_active_adapter",
        )
    return Observation(
        ServiceState.CONNECTED,
        "An active adapter has a non-loopback IP address. This does not test Wi-Fi or internet access.",
    )


def check_gateway() -> Observation:
    paths = (Path("/proc/net/route"), Path("/proc/net/ipv6_route"))
    available = False
    for path in paths:
        try:
            rows = path.read_text().splitlines()
        except OSError:
            continue
        available = True
        for row in rows:
            fields = row.split()
            try:
                if path.name == "route":
                    is_default = fields[1] == "00000000" and int(fields[3], 16) & 1 and fields[7] == "00000000"
                else:
                    # The IPv6 route table can contain an unreachable loopback catchall.
                    is_default = (
                        fields[0] == "0" * 32 and fields[1] == "00"
                        and int(fields[8], 16) & 1 and not int(fields[8], 16) & 0x200
                        and fields[9] != "lo"
                    )
            except (IndexError, ValueError):
                continue
            if is_default:
                return Observation(ServiceState.CONNECTED, "The OS reports an active default route.")
    if available:
        return Observation(ServiceState.DISCONNECTED, "No active default route was observed.", "missing_route")
    return Observation(ServiceState.UNKNOWN, "Default-route visibility is unavailable on this OS.", "unsupported")


def check_resolver() -> Observation:
    try:
        rows = Path("/etc/resolv.conf").read_text().splitlines()
    except OSError:
        return Observation(ServiceState.UNKNOWN, "Resolver configuration is unavailable on this OS.", "unsupported")
    for row in rows:
        fields = row.split()
        if len(fields) >= 2 and fields[0] == "nameserver":
            try:
                ip_address(fields[1].split("%")[0])
            except ValueError:
                continue
            return Observation(ServiceState.CONNECTED, "The OS lists a DNS resolver. It may be a local forwarder.")
    return Observation(ServiceState.UNKNOWN, "No resolver was found in the supported OS configuration.", "resolver_unknown")


def check_local_network() -> dict[str, Observation]:
    return {
        "network_interface": check_interface(),
        "gateway": check_gateway(),
        "dns_resolver": check_resolver(),
    }


def pending(name: str, explanation: str, configured: bool = True) -> ServiceStatus:
    return ServiceStatus(
        name=name,
        state=ServiceState.UNKNOWN if configured else ServiceState.NOT_CONFIGURED,
        explanation=explanation,
        configured=configured,
    )


class ConnectivityManager:
    def __init__(
        self, *,
        ollama_base_url: str = "http://127.0.0.1:11434",
        ollama_model: str = "qwen3.5:4b",
        ollama_loading: Callable[[], bool] | None = None,
        internet_probe_url: str | None = None,
        internet_expected_status: int = 204,
        nexthink_probe: CloudProbe | None = None,
        probe_interval: float = 30.0,
        timeout: float = 3.0,
        stability_seconds: float = 5.0,
        on_change: Callable[[ServiceStatus, ServiceStatus], None] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.ollama_base_url = normalize_local_ollama(ollama_base_url)
        self.ollama_model = local_model_name(ollama_model)
        self.ollama_loading = ollama_loading or (lambda: False)
        self.internet_probe_url = normalize_probe_url(internet_probe_url) if internet_probe_url else None
        self.internet_expected_status = internet_expected_status
        if not 200 <= internet_expected_status < 300:
            raise ValueError("ITOR_INTERNET_EXPECTED_STATUS must be a successful 2xx response code")
        self.nexthink_probe = nexthink_probe
        self.probe_interval = max(probe_interval, 1)
        self.timeout = max(timeout, 0.1)
        self.stability_seconds = max(stability_seconds, 0)
        self.on_change = on_change
        self.transport = transport
        self._updated_at = utc_now()
        self._states = {
            "agent": ServiceStatus(name="Device agent", state=ServiceState.CONNECTED,
                                    explanation="The local device agent responded.", last_success_at=self._updated_at,
                                    last_checked_at=self._updated_at),
            "ollama": pending("Local AI", "Waiting for the local runtime check."),
            "network_interface": pending("Network adapter", "Waiting for the adapter check."),
            "gateway": pending("Default route", "Waiting for the default-route check."),
            "dns_resolver": pending("DNS resolver", "Waiting for the resolver check."),
            "internet": pending("Internet", "Waiting for the approved HTTPS check." if self.internet_probe_url
                                else "No approved HTTPS connectivity endpoint is configured.", bool(self.internet_probe_url)),
            "dns": pending("DNS test", "Run a connection investigation to test the approved host." if self.internet_probe_url
                           else "No approved hostname is configured for an active DNS check.", bool(self.internet_probe_url)),
            "nexthink": pending("Nexthink", "Waiting for the tenant adapter." if self.nexthink_probe
                                else "Nexthink integration is not configured.", bool(self.nexthink_probe)),
            "nexthink_reachability": pending("Nexthink reachability", "Waiting for the tenant adapter." if self.nexthink_probe
                                             else "No Nexthink endpoint is configured.", bool(self.nexthink_probe)),
            "nexthink_auth": pending("Nexthink authentication", "Waiting for the tenant adapter." if self.nexthink_probe
                                      else "No Nexthink credentials are configured.", bool(self.nexthink_probe)),
        }
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._last_attempts: dict[str, float] = {}
        self._simulated = False
        self._simulation_changed_at: datetime | None = None
        self._offline_rescue = False
        self._recovery_since: float | None = None
        self._cloud_last_updated_at: datetime | None = None
        self._cloud_context_invalidated = False
        self._awaiting_nexthink_recovery = False
        self._closed = False

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=False, trust_env=False, transport=self.transport,
        )

    def _record(self, key: str, value: Observation, started: float) -> None:
        old = self._states[key]
        now = utc_now()
        self._updated_at = now
        new = old.model_copy(update={
            "state": value.state,
            "explanation": value.explanation,
            "last_success_at": now if value.state == ServiceState.CONNECTED else old.last_success_at,
            "last_checked_at": now,
            "duration_ms": max(0, round((monotonic() - started) * 1000)),
            "error_category": value.error_category,
        })
        self._states[key] = new
        if key == "nexthink":
            self._awaiting_nexthink_recovery = False
            if new.state != ServiceState.CONNECTED:
                self._cloud_context_invalidated = True
        if self.on_change and old.state != new.state:
            self.on_change(old, new)
        self._update_recovery()

    def _nexthink_state(self) -> ServiceStatus:
        current = self._states["nexthink"]
        if self._simulated:
            return current.model_copy(update={
                "state": ServiceState.UNREACHABLE,
                "error_category": "simulated_outage",
                "explanation": "Simulated cloud outage. The device network is unchanged.",
                "last_checked_at": self._simulation_changed_at,
                "duration_ms": None,
            })
        return current

    def _update_recovery(self) -> None:
        offline_now = (
            self._states["network_interface"].state == ServiceState.DISCONNECTED
            or self._states["internet"].state in (ServiceState.DISCONNECTED, ServiceState.UNREACHABLE)
            or self._nexthink_state().state == ServiceState.UNREACHABLE
            or self._awaiting_nexthink_recovery
        )
        if offline_now:
            self._offline_rescue = True
            self._recovery_since = None
        elif self._offline_rescue:
            if self._recovery_since is None:
                self._recovery_since = monotonic()
            if monotonic() - self._recovery_since >= self.stability_seconds:
                self._offline_rescue = False
                self._recovery_since = None

    def mark_cloud_context_updated(self, captured_at: datetime) -> None:
        """Future context providers call this only after a successful data fetch."""
        if captured_at.utcoffset() is None:
            raise ValueError("Cloud context timestamps must be timezone-aware")
        self._cloud_last_updated_at = captured_at
        self._cloud_context_invalidated = False

    def _report(self) -> ConnectivityReport:
        self._update_recovery()
        states = dict(self._states)
        now = utc_now()
        states["agent"] = states["agent"].model_copy(update={"last_success_at": now, "last_checked_at": now})
        for key in ("ollama", "dns", "internet", "nexthink"):
            task = self._tasks.get(key)
            if states[key].state == ServiceState.UNKNOWN and task and not task.done():
                states[key] = states[key].model_copy(update={"state": ServiceState.CHECKING})
        ollama_loading = self.ollama_loading()
        if ollama_loading and states["ollama"].state in (ServiceState.CONNECTED, ServiceState.CHECKING):
            states["ollama"] = states["ollama"].model_copy(update={
                "explanation": "The local model is loading or generating a diagnosis.",
            })
        if self._simulated:
            states["nexthink"] = self._nexthink_state()
            states["nexthink_reachability"] = states["nexthink_reachability"].model_copy(update={
                "state": ServiceState.UNREACHABLE, "explanation": "Simulated cloud outage.",
                "error_category": "simulated_outage", "last_checked_at": self._simulation_changed_at,
                "duration_ms": None,
            })
            states["nexthink_auth"] = states["nexthink_auth"].model_copy(update={
                "state": ServiceState.UNKNOWN, "explanation": "Authentication was not checked during the simulation.",
                "error_category": None,
            })
        context_age = (now - self._cloud_last_updated_at).total_seconds() if self._cloud_last_updated_at else None
        return ConnectivityReport(
            **states, ollama_loading=ollama_loading, offline_rescue=self._offline_rescue,
            simulated_cloud_outage=self._simulated,
            updated_at=self._updated_at, cloud_last_updated_at=self._cloud_last_updated_at,
            cloud_data_stale=context_age is not None and (
                self._cloud_context_invalidated or states["nexthink"].state != ServiceState.CONNECTED or context_age > 180
            ),
        )

    def _schedule(self, key: str, check: Callable[[], Awaitable[None]], interval: float) -> asyncio.Task[None] | None:
        task = self._tasks.get(key)
        if task and not task.done():
            return task
        start = monotonic()
        if self._closed or start - self._last_attempts.get(key, float("-inf")) < interval:
            return None
        self._last_attempts[key] = start
        task = asyncio.create_task(check())
        self._tasks[key] = task
        # A status-only caller can leave checks running in the background.
        task.add_done_callback(self._report_task_error)
        return task

    @staticmethod
    def _report_task_error(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            asyncio.get_running_loop().call_exception_handler(
                {"message": "itor connectivity update failed", "exception": error}
            )

    def _start_checks(self, include_dns: bool = False) -> list[asyncio.Task[None]]:
        checks = [
            self._schedule("local", self._check_passive, 2.0),
            self._schedule("ollama", self._check_ollama, min(10.0, self.probe_interval)),
        ]
        if self.internet_probe_url:
            checks.append(self._schedule("internet", self._check_internet, self.probe_interval))
            if include_dns:
                checks.append(self._schedule("dns", self._check_dns, self.probe_interval))
        if self.nexthink_probe and not self._simulated:
            checks.append(self._schedule("nexthink", self._check_nexthink, self.probe_interval))
        return [check for check in checks if check is not None]

    async def status(self) -> ConnectivityReport:
        self._start_checks()
        return self._report()

    async def inspect(self, probe: bool = False) -> ConnectivityReport:
        if probe:
            tasks = self._start_checks(include_dns=True)
            if tasks:
                await asyncio.gather(*(asyncio.shield(task) for task in tasks))
        else:
            self._start_checks()
            local = self._tasks.get("local")
            if local and not local.done():
                await asyncio.shield(local)
        return self._report()

    async def simulate_cloud(self, enabled: bool) -> ConnectivityReport:
        if self._simulated != enabled:
            old = self._nexthink_state()
            self._simulated = enabled
            self._simulation_changed_at = self._updated_at = utc_now()
            if enabled:
                self._cloud_context_invalidated = True
                task = self._tasks.get("nexthink")
                if task and not task.done():
                    task.cancel()
            if not enabled:
                self._last_attempts.pop("nexthink", None)
                if self.nexthink_probe:
                    self._awaiting_nexthink_recovery = True
                    self._states["nexthink"] = self._states["nexthink"].model_copy(update={
                        "state": ServiceState.UNKNOWN,
                        "explanation": "Rechecking the configured Nexthink adapter after simulation.",
                        "error_category": None,
                    })
            if self.on_change:
                self.on_change(old, self._nexthink_state())
        return await self.status()

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_passive(self) -> None:
        start = monotonic()
        observations = await asyncio.to_thread(check_local_network)
        for name, observation in observations.items():
            self._record(name, observation, start)

    async def _check_ollama(self) -> None:
        start = monotonic()
        try:
            async with self._client() as client:
                response = await asyncio.wait_for(client.get(f"{self.ollama_base_url}/api/tags"), self.timeout)
            response.raise_for_status()
            models = response.json()["models"]
            names = {entry.get("name", entry.get("model")) for entry in models}
            observation = (
                Observation(ServiceState.CONNECTED, f"{self.ollama_model} is available on this device.")
                if self.ollama_model in names else
                Observation(ServiceState.DEGRADED, f"Ollama is running. Download {self.ollama_model} to enable local AI.",
                            "model_missing")
            )
        except (httpx.TransportError, TimeoutError, asyncio.TimeoutError):
            observation = Observation(ServiceState.UNREACHABLE, "Ollama did not respond. Local rules remain available.",
                                      "runtime_unreachable")
        except (httpx.HTTPStatusError, ValueError, KeyError, TypeError, AttributeError):
            observation = Observation(ServiceState.DEGRADED, "Ollama returned an unexpected response.", "runtime_response")
        self._record("ollama", observation, start)

    async def _check_internet(self) -> None:
        start = monotonic()

        async def probe() -> int:
            async with self._client() as client:
                async with client.stream("GET", str(self.internet_probe_url), headers={"Cache-Control": "no-cache"}) as response:
                    return response.status_code

        try:
            code = await asyncio.wait_for(probe(), self.timeout)
            observation = (
                Observation(ServiceState.CONNECTED, "The approved HTTPS endpoint returned the expected response.")
                if code == self.internet_expected_status else
                Observation(ServiceState.DEGRADED, f"The endpoint returned HTTP {code}; broader internet access is uncertain.",
                            "unexpected_http_status")
            )
        except (httpx.HTTPError, TimeoutError, asyncio.TimeoutError):
            observation = Observation(
                ServiceState.UNREACHABLE,
                "The approved HTTPS endpoint could not be reached. Access to other services is uncertain.",
                "endpoint_unreachable",
            )
        self._record("internet", observation, start)

    async def _check_dns(self) -> None:
        start = monotonic()
        host = urlsplit(str(self.internet_probe_url)).hostname
        try:
            ip_address(str(host))
        except ValueError:
            pass
        else:
            self._record("dns", Observation(ServiceState.UNKNOWN, "The approved endpoint uses an IP address.", "no_hostname"), start)
            return
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM), self.timeout)
            observation = Observation(ServiceState.CONNECTED, "The system resolver returned an address for the approved hostname.")
        except (OSError, TimeoutError, asyncio.TimeoutError):
            observation = Observation(
                ServiceState.UNREACHABLE,
                "The system resolver could not resolve the approved hostname. This does not identify the failing network component.",
                "dns_resolution",
            )
        self._record("dns", observation, start)

    async def _check_nexthink(self) -> None:
        start = monotonic()
        if self.nexthink_probe is None:
            return
        try:
            result = await asyncio.wait_for(self.nexthink_probe(), self.timeout)
        except httpx.HTTPStatusError as error:
            unauthorized = error.response.status_code in (401, 403)
            result = CloudProbeResult(
                reachability=Observation(ServiceState.CONNECTED, "The configured Nexthink endpoint responded."),
                authentication=Observation(
                    ServiceState.AUTHENTICATION_ERROR if unauthorized else ServiceState.DEGRADED,
                    "The configured Nexthink endpoint rejected authentication." if unauthorized
                    else "The configured Nexthink endpoint did not return the expected response.",
                    "authentication" if unauthorized else "unexpected_http_status",
                ),
            )
        except (httpx.HTTPError, OSError, TimeoutError, asyncio.TimeoutError):
            result = CloudProbeResult(
                reachability=Observation(ServiceState.UNREACHABLE, "The configured Nexthink adapter did not respond.", "endpoint_unreachable"),
                authentication=Observation(ServiceState.UNKNOWN, "Tenant authentication could not be checked."),
            )
        self._record("nexthink_reachability", result.reachability, start)
        self._record("nexthink_auth", result.authentication, start)
        combined = result.reachability if result.reachability.state != ServiceState.CONNECTED else result.authentication
        self._record("nexthink", combined, start)
