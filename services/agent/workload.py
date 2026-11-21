import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from time import monotonic

import psutil

from .models import WorkloadStatus, new_id, utc_now


class WorkloadError(Exception):
    pass


@dataclass(frozen=True)
class ProcessIdentity:
    parent_pid: int
    start: int | float


def process_identity(pid: int) -> ProcessIdentity:
    if sys.platform.startswith("linux"):
        # Kernel start ticks do not change when WSL or Linux adjusts wall time.
        # The command name can contain parentheses, so split at its last ')'.
        _, delimiter, fields = Path(f"/proc/{pid}/stat").read_bytes().rpartition(b")")
        fields = fields.split()
        if not delimiter or len(fields) < 20:
            raise WorkloadError("The demo process identity could not be read.")
        return ProcessIdentity(parent_pid=int(fields[1]), start=int(fields[19]))
    process = psutil.Process(pid)
    return ProcessIdentity(parent_pid=process.ppid(), start=process.create_time())


def open_pidfd(pid: int) -> int | None:
    if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
        try:
            return os.pidfd_open(pid)
        except ProcessLookupError:
            raise
        except OSError:
            # Older kernels and restricted environments can lack pidfd support.
            pass
    return None


@dataclass
class OwnedProcess:
    id: str
    handle: subprocess.Popen
    process: psutil.Process
    identity: ProcessIdentity
    started_at: datetime
    expires_at: datetime
    pidfd: int | None = None
    last_sample: tuple[float, float] | None = None
    cpu_percent: float | None = None

    def release_pidfd(self) -> None:
        if self.pidfd is not None:
            os.close(self.pidfd)
            self.pidfd = None

    def is_active(self) -> bool:
        if self.handle.poll() is None:
            return True
        self.release_pidfd()
        return False


class WorkloadManager:
    def __init__(self, duration_seconds: int = 180):
        self.duration = min(180, max(1, duration_seconds))
        self.lock = RLock()
        self.current: OwnedProcess | None = None

    def start(self) -> WorkloadStatus:
        with self.lock:
            if self.status().active:
                raise WorkloadError("A demo workload is already running.")
            script = Path(__file__).with_name("demo_worker.py").resolve()
            env = {"SystemRoot": os.environ["SystemRoot"]} if sys.platform == "win32" and "SystemRoot" in os.environ else {}
            try:
                handle = subprocess.Popen(
                    [sys.executable, "-I", "-S", str(script), str(self.duration)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                )
            except OSError as exc:
                raise WorkloadError("The demo workload could not be started.") from exc
            try:
                process = psutil.Process(handle.pid)
                identity = process_identity(handle.pid)
                if identity.parent_pid != os.getpid() or handle.poll() is not None:
                    raise WorkloadError("The demo process is no longer an active child.")
                pidfd = open_pidfd(handle.pid)
            except (OSError, psutil.Error, ValueError, WorkloadError) as exc:
                self._discard(handle)
                raise WorkloadError("The demo process identity could not be established.") from exc

            now = utc_now()
            self.current = OwnedProcess(new_id(), handle, process, identity, now,
                                        now + timedelta(seconds=self.duration), pidfd=pidfd)
            return self.status()

    @staticmethod
    def _discard(handle: subprocess.Popen) -> None:
        # An unregistered child can only be cleaned up using its original handle.
        if handle.poll() is None:
            try:
                handle.terminate()
                handle.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def status(self) -> WorkloadStatus:
        with self.lock:
            record = self.current
            if record is None or not record.is_active():
                return WorkloadStatus()
            memory = None
            try:
                times = record.process.cpu_times()
                memory = record.process.memory_info().rss
                current = (monotonic(), times.user + times.system)
                if record.last_sample is None:
                    record.last_sample = current
                else:
                    elapsed = current[0] - record.last_sample[0]
                    if elapsed >= 0.2:
                        cpu_seconds = current[1] - record.last_sample[1]
                        record.cpu_percent = round(100 * cpu_seconds / elapsed, 1)
                        record.last_sample = current
            except psutil.Error:
                record.cpu_percent = None
            return WorkloadStatus(active=True, id=record.id, cpu_percent=record.cpu_percent, memory_bytes=memory,
                                  started_at=record.started_at, expires_at=record.expires_at)

    def stop(self, expected_id: str) -> bool:
        with self.lock:
            record = self.current
            if record is None or record.id != expected_id or not record.is_active():
                return False
            try:
                current = process_identity(record.handle.pid)
                if current != record.identity or current.parent_pid != os.getpid():
                    raise WorkloadError("The demo process identity has changed. No signal was sent.")
                if record.pidfd is not None:
                    signal.pidfd_send_signal(record.pidfd, signal.SIGTERM)
                else:
                    # This lock serializes all polls and waits on our own child.
                    # On POSIX its PID cannot be reused while it remains unreaped.
                    record.handle.terminate()
                exit_code = record.handle.wait(timeout=3)
                record.release_pidfd()
                # The worker returns 0 on timeout. A coincident natural exit is not an applied action.
                return os.name != "posix" or exit_code == -signal.SIGTERM
            except (FileNotFoundError, ProcessLookupError, psutil.NoSuchProcess) as exc:
                if record.is_active():
                    raise WorkloadError("The demo process identity could not be confirmed. No signal was sent.") from exc
                return False
            except (psutil.AccessDenied, OSError, ValueError, subprocess.TimeoutExpired) as exc:
                raise WorkloadError("The demo process could not be safely stopped and verified.") from exc

    def close(self) -> None:
        with self.lock:
            if self.current is not None:
                try:
                    self.stop(self.current.id)
                except WorkloadError:
                    # The child also has its own independent hard deadline.
                    pass
                finally:
                    self.current.release_pidfd()
