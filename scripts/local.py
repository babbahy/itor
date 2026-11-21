#!/usr/bin/env python3
"""Install or launch the two loopback services using one local environment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit
import venv

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
NEXT = WEB / "node_modules" / "next" / "dist" / "bin" / "next"
DEFAULT_WEB_ORIGIN = "http://127.0.0.1:3000"
DEFAULT_AGENT_URL = "http://127.0.0.1:8765"


def origin(value: str) -> tuple[str, int, str]:
    parsed = urlsplit(value)
    host = parsed.hostname
    if (
        parsed.scheme != "http"
        or host not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Spark Ready endpoints must be HTTP loopback origins.")
    port = parsed.port if parsed.port is not None else 80
    if port == 0:
        raise ValueError("Choose a fixed nonzero port for each Spark Ready endpoint.")
    authority = host if port == 80 else f"{host}:{port}"
    return host, port, f"http://{authority}"


def environment() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not separator or not key.replace("_", "").isalnum():
                raise ValueError("Use NAME=value entries in .env.")
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values[key] = value
    values.update(os.environ)
    values.setdefault("SPARK_WEB_ORIGIN", DEFAULT_WEB_ORIGIN)
    values.setdefault("SPARK_AGENT_URL", DEFAULT_AGENT_URL)
    values.setdefault("SPARK_AGENT_KEY", secrets.token_urlsafe(32))
    values["NEXT_TELEMETRY_DISABLED"] = "1"
    return values


def executable(name: str) -> str:
    path = shutil.which(f"{name}.cmd" if name == "npm" and os.name == "nt" else name)
    if not path:
        raise ValueError(f"{name} is required. Install Node.js 22.12 or newer.")
    return path


def setup() -> None:
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required. Set SPARK_PYTHON to the executable path.")
    node, npm = executable("node"), executable("npm")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    if tuple(map(int, version.removeprefix("v").split(".")[:2])) < (22, 12):
        raise ValueError("Install Node.js 22.12 or newer.")
    if not PYTHON.is_file():
        venv.EnvBuilder(with_pip=True).create(VENV)
    values = environment()
    subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "-r", "services/agent/requirements-dev.txt"],
        cwd=ROOT,
        env=values,
        check=True,
    )
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=WEB, env=values, check=True)
    print("Local dependencies installed. Run the launcher when you are ready to start.", flush=True)


def stop_children(children: list[subprocess.Popen]) -> None:
    for process in reversed(children):
        if process.poll() is None:
            process.terminate()
    for process in reversed(children):
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def launch(production: bool) -> int:
    if not NEXT.is_file() or not PYTHON.is_file():
        raise ValueError("Run the setup script to install the local dependencies.")
    if production and not (WEB / ".next" / "BUILD_ID").is_file():
        raise ValueError("Run make build (or npm --prefix apps/web run build) first.")
    values = environment()
    web_host, web_port, web_url = origin(values["SPARK_WEB_ORIGIN"])
    agent_host, agent_port, agent_url = origin(values["SPARK_AGENT_URL"])
    values.update(SPARK_WEB_ORIGIN=web_url, SPARK_AGENT_URL=agent_url)
    if web_port == agent_port:
        raise ValueError("Use different ports for the web app and the device agent.")
    if not values["SPARK_AGENT_KEY"].strip():
        raise ValueError("Remove the empty SPARK_AGENT_KEY to let the launcher generate a key.")
    node = executable("node")
    # Prefer a concrete IPv4 binding for the default localhost aliases.
    web_bind = "127.0.0.1" if web_host == "localhost" else web_host
    agent_bind = "127.0.0.1" if agent_host == "localhost" else agent_host
    if agent_host == "localhost":
        values["SPARK_AGENT_URL"] = f"http://127.0.0.1:{agent_port}"
    children: list[subprocess.Popen] = []

    def stop(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    try:
        children.append(subprocess.Popen([
            str(PYTHON), "-m", "uvicorn", "services.agent.main:app",
            "--host", agent_bind, "--port", str(agent_port), "--no-proxy-headers",
        ], cwd=ROOT, env=values))
        children.append(subprocess.Popen([
            node, str(NEXT), "start" if production else "dev",
            "--hostname", web_bind, "--port", str(web_port),
        ], cwd=WEB, env=values))
        print(f"Spark Ready  {web_url}", flush=True)
        while all(process.poll() is None for process in children):
            time.sleep(0.25)
        return next((code for process in children if (code := process.poll()) is not None), 1)
    except KeyboardInterrupt:
        return 0
    finally:
        stop_children(children)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "dev", "start"])
    selected = parser.parse_args().command
    try:
        if selected == "setup":
            setup()
            return 0
        return launch(production=selected == "start")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Spark Ready could not start or finish setup. {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
