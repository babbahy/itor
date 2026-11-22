"""Start the itor helper. Used by the desktop app and by the packed itor-helper.exe.

    python -m services.agent.serve            # helper on 127.0.0.1:$ITOR_AGENT_PORT (default 8765)
    itor-helper.exe --demo-worker 180         # demo CPU hog (child process, packed app only)
"""
from __future__ import annotations

import os
import sys


def parse_port(value: str | None) -> int:
    port = int(value or "8765")
    if not 1024 <= port <= 65535:
        raise ValueError("ITOR_AGENT_PORT must be between 1024 and 65535.")
    return port


def main(argv: list[str]) -> None:
    if len(argv) >= 3 and argv[1] == "--demo-worker":
        from services.agent.demo_worker import burn
        burn(int(argv[2]), argv[3] if len(argv) > 3 else "cpu")
        return
    if sys.stdout is None or sys.stderr is None:
        # Packed without a console window: write logs to %LOCALAPPDATA%\itor-data\helper.log instead.
        folder = os.path.join(os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), "itor-data")
        os.makedirs(folder, exist_ok=True)
        log = open(os.path.join(folder, "helper.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    import uvicorn
    from services.agent.main import app
    uvicorn.run(app, host="127.0.0.1", port=parse_port(os.getenv("ITOR_AGENT_PORT")), log_level="warning")


if __name__ == "__main__":
    main(sys.argv)
