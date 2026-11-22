"""Bounded demo processes that really slow the PC. This file only runs as a child process.

Kinds (all stop by themselves after `seconds`, at most 180 s):
- cpu:    keeps one processor core busy (a stuck video export)
- memory: grows to about 1.2 GB of memory, a little at a time (a memory leak)
- sync:   keeps one core busy and rewrites a small temp file (a sync loop)
"""

import os
import tempfile
from sys import argv
from time import monotonic, sleep

MEMORY_LIMIT = 1200 * 1024 * 1024
MEMORY_STEP = 40 * 1024 * 1024
SYNC_FILE = os.path.join(tempfile.gettempdir(), "itor-demo-sync.tmp")
SYNC_SIZE = 8 * 1024 * 1024


def busy(until: float, duty: float = 0.55) -> None:
    """Busy loop for `duty` of each 100 ms slice."""
    while monotonic() < until:
        busy_until = min(until, monotonic() + 0.1 * duty)
        while monotonic() < busy_until:
            pass
        sleep(min(0.1 * (1 - duty), max(0.0, until - monotonic())))


def burn(seconds: int, kind: str = "cpu") -> None:
    deadline = monotonic() + min(180, max(1, int(seconds)))
    if kind == "memory":
        leak: list[bytearray] = []
        while monotonic() < deadline:
            if len(leak) * MEMORY_STEP < MEMORY_LIMIT:
                leak.append(bytearray(MEMORY_STEP))  # zero-filled pages: really counted by the OS
            busy(min(deadline, monotonic() + 0.5), duty=0.1)
        return
    if kind == "sync":
        block = os.urandom(1024 * 1024)
        try:
            while monotonic() < deadline:
                with open(SYNC_FILE, "wb") as file:  # same small file, rewritten: disk busy, never fills it
                    for _ in range(SYNC_SIZE // len(block)):
                        file.write(block)
                    file.flush()
                    os.fsync(file.fileno())
                busy(min(deadline, monotonic() + 0.4), duty=0.5)
        finally:
            try:
                os.remove(SYNC_FILE)
            except OSError:
                pass
        return
    busy(deadline)


if __name__ == "__main__":
    burn(int(argv[1]), argv[2] if len(argv) > 2 else "cpu")
