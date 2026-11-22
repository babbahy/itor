"""Bounded CPU-only demonstration. This file only runs as a child process."""

from sys import argv
from time import monotonic, sleep


def burn(seconds: int) -> None:
    deadline = monotonic() + min(180, max(1, int(seconds)))
    while monotonic() < deadline:
        busy_until = min(deadline, monotonic() + 0.055)
        while monotonic() < busy_until:
            pass
        sleep(min(0.045, max(0.0, deadline - monotonic())))


if __name__ == "__main__":
    burn(int(argv[1]))
