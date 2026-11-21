from collections import deque
from pathlib import Path
from threading import RLock
from typing import Protocol

import psutil

from .connectivity import ServiceState, check_interface
from .models import DeviceSnapshot, utc_now
from .workload import WorkloadManager


class TelemetryProvider(Protocol):
    def capture(self) -> DeviceSnapshot: ...
    def latest(self) -> DeviceSnapshot | None: ...
    def history(self) -> list[DeviceSnapshot]: ...
    def capabilities(self) -> dict[str, str]: ...


class NotConfigured(Exception):
    """A provider has no authenticated tenant configuration."""


class NexthinkTelemetryProvider:
    def capture(self) -> DeviceSnapshot:
        raise NotConfigured("Nexthink telemetry requires an authenticated tenant and reviewed NQL queries.")

    def latest(self) -> DeviceSnapshot | None:
        return None

    def history(self) -> list[DeviceSnapshot]:
        return []

    def capabilities(self) -> dict[str, str]:
        return {"source": "not_configured"}


class LocalTelemetryProvider:
    def __init__(self, workload: WorkloadManager, interval: float = 0.25):
        self.workload = workload
        self.cpu_interval = interval
        self.samples: deque[DeviceSnapshot] = deque(maxlen=180)
        self.sample_lock = RLock()
        self.history_lock = RLock()

    def capture(self) -> DeviceSnapshot:
        with self.sample_lock:
            snapshot = DeviceSnapshot()
            try:
                snapshot.cpu_percent = psutil.cpu_percent(interval=self.cpu_interval)
                snapshot.cpu_logical = psutil.cpu_count(logical=True)
                snapshot.cpu_physical = psutil.cpu_count(logical=False)
            except (OSError, psutil.Error, NotImplementedError):
                snapshot.errors.append("CPU measurement unavailable.")
            try:
                memory = psutil.virtual_memory()
                snapshot.memory_percent = memory.percent
                snapshot.memory_total = memory.total
                snapshot.memory_available = memory.available
            except (OSError, psutil.Error, NotImplementedError):
                snapshot.errors.append("Memory measurement unavailable.")
            try:
                disk = psutil.disk_usage(Path.home())
                snapshot.disk_percent = disk.percent
                snapshot.disk_total = disk.total
                snapshot.disk_free = disk.free
            except (OSError, psutil.Error, NotImplementedError):
                snapshot.errors.append("Disk measurement unavailable.")
            try:
                interface = check_interface()
                if interface.state in {ServiceState.CONNECTED, ServiceState.DISCONNECTED}:
                    snapshot.network_up = interface.state == ServiceState.CONNECTED
            except NotImplementedError:
                pass
            if snapshot.network_up is None:
                snapshot.errors.append("Network interface measurement unavailable.")
            snapshot.workload = self.workload.status()
            snapshot.captured_at = utc_now()
            with self.history_lock:
                self.samples.append(snapshot)
            return snapshot

    def latest(self) -> DeviceSnapshot | None:
        with self.history_lock:
            return self.samples[-1] if self.samples else None

    def history(self) -> list[DeviceSnapshot]:
        with self.history_lock:
            return list(self.samples)

    def clear_history(self) -> None:
        with self.history_lock:
            self.samples.clear()

    def capabilities(self) -> dict[str, str]:
        snapshot = self.latest()
        return {
            "source": "local",
            "cpu": "supported" if snapshot and snapshot.cpu_percent is not None else "unavailable",
            "memory": "supported" if snapshot and snapshot.memory_percent is not None else "unavailable",
            "disk": "supported" if snapshot and snapshot.disk_percent is not None else "unavailable",
            "network_interface": "supported" if snapshot and snapshot.network_up is not None else "unavailable",
            "audio": "unsupported",
            "camera": "unsupported",
        }


class FixtureTelemetryProvider:
    def __init__(self, samples: list[DeviceSnapshot]):
        self.samples = [sample.model_copy(update={"source": "fixture"}) for sample in samples]

    def capture(self) -> DeviceSnapshot:
        return self.samples[-1]

    def latest(self) -> DeviceSnapshot | None:
        return self.samples[-1] if self.samples else None

    def history(self) -> list[DeviceSnapshot]:
        return self.samples.copy()

    def capabilities(self) -> dict[str, str]:
        return {"source": "fixture"}
