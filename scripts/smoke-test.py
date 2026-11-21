#!/usr/bin/env python3
"""Verify itor through the local web server and its authenticated agent proxy."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from local import environment, origin

OPENER = build_opener(ProxyHandler({}))


def request(base: str, path: str, data: dict | None = None, *, timeout: float = 10):
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        headers.update(Origin=base, **{"Content-Type": "application/json"})
        body = json.dumps(data).encode()
    with OPENER.open(Request(base + path, data=body, headers=headers), timeout=timeout) as result:
        return json.load(result) if path.startswith("/api/") else result.read().decode()


def require(condition: object, detail: str) -> None:
    if not condition:
        raise RuntimeError(detail)


def eventually(get: Callable, ready: Callable, detail: str, timeout: float = 15):
    end = time.monotonic() + timeout
    while True:
        value = get()
        if ready(value):
            return value
        if time.monotonic() >= end:
            raise RuntimeError(detail)
        time.sleep(0.25)


def check(base: str) -> dict:
    page = request(base, "/", timeout=30)
    require("itor" in page, "The local Next.js page did not include itor.")
    health = request(base, "/api/health")
    status = request(base, "/api/status")
    snapshot = request(base, "/api/device/snapshot")
    require(snapshot["source"] == "local", "Live agent reported an unexpected telemetry source.")
    require(snapshot["cpu_percent"] is not None, "The agent did not return host CPU telemetry.")
    print(f"Web and device agent OK · CPU {snapshot['cpu_percent']}% · {snapshot['captured_at']}")
    require(health.get("status") == "ok", "The device agent did not pass its health check.")
    services = status["connectivity"]
    print(f"Device agent {services['agent']['state']} · Local AI {services['ollama']['state']} · "
          f"Internet {services['internet']['state']} · Nexthink {services['nexthink']['state']}")
    return status


def flow(base: str, cloud_outage: bool, skip_diagnosis: bool, expect_ollama: bool) -> None:
    demo = request(base, "/api/demo/status")
    active = demo.get("workload", demo).get("active")
    require(active is False, "Stop the current demo workload before running the smoke test.")
    meeting = request(base, "/api/meetings/next")
    require(meeting and meeting["id"], "No upcoming meeting. Run make demo-reset to seed the schedule.")
    workload_started = False
    cloud_changed = False
    try:
        if cloud_outage:
            before_cloud = request(base, "/api/connectivity")
            cloud = request(base, "/api/demo/cloud", {"enabled": True})
            cloud_changed = not before_cloud["simulated_cloud_outage"]
            require(cloud["simulated_cloud_outage"] and cloud["offline_rescue"], "The demo cloud outage did not activate.")
            require(cloud["agent"]["state"] == "connected", "Cloud simulation interrupted the local agent.")
            print("Simulated cloud adapter outage enabled.")
        request(base, "/api/demo/start", {})
        workload_started = True
        eventually(
            lambda: request(base, "/api/device/snapshot"),
            lambda sample: sample["workload"]["active"] and (sample["workload"]["cpu_percent"] or 0) >= 20,
            "No measured CPU activity from the agent-owned workload.",
        )
        prepared = request(base, "/api/preflight", {"meeting_id": meeting["id"]})
        require(prepared["meeting_id"] == meeting["id"], "Preflight did not retain the meeting.")
        require(prepared["readiness"] in {"attention", "not_ready"}, "Preflight did not surface the workload.")
        require(
            any("stop_demo_workload" in item["recommended_action_ids"] for item in prepared["findings"]),
            "The workload finding did not offer the allowlisted action.",
        )
        session = {"session_id": prepared["id"]}
        if not skip_diagnosis:
            diagnosis = request(base, "/api/diagnose", session, timeout=150)
            require(diagnosis.get("explanation"), "The agent did not return an explanation.")
            provider = diagnosis.get("provider")
            if expect_ollama:
                require(provider == "ollama", f"Expected validated local Ollama inference, received {provider}.")
                require(diagnosis.get("model"), "The Ollama result did not identify the model.")
            print(f"Diagnosis provider · {provider or 'unspecified'} {diagnosis.get('model') or ''}".rstrip())
        plan = request(base, "/api/actions/plan", {**session, "action_id": "stop_demo_workload"})
        require(plan["status"] == "awaiting_approval", "The action did not wait for approval.")
        action_path = f"/api/actions/{plan['id']}"
        before_approval = request(base, "/api/demo/status")
        require(before_approval.get("workload", before_approval)["active"], "Workload stopped before approval.")
        approval = {"approval_token": plan["approval_token"], "approved": True}
        request(base, action_path + "/approve", approval)
        finished = eventually(
            lambda: request(base, action_path),
            lambda action: action["status"] in {"succeeded", "failed", "expired", "canceled"},
            "Action verification did not complete.",
        )
        require(finished["status"] == "succeeded",
                f"Action ended with {finished['status']}. {finished.get('message') or ''}".rstrip())
        require(finished["verification"]["process_exited"], "Verification did not confirm process exit.")
        require(finished["before"]["workload_active"] and not finished["after"]["workload_active"],
                "The before/after workload state was inconsistent.")
        try:
            repeated = request(base, action_path + "/approve", approval)
        except HTTPError as error:
            require(error.code in {403, 409, 410}, f"Unexpected approval replay result: HTTP {error.code}.")
        else:
            require(repeated["id"] == plan["id"] and repeated["status"] == "succeeded",
                    "Repeated approval changed the action state.")
        print(f"Verified workload stopped · {finished['before']['workload_cpu_percent']}% of one core before")
    finally:
        original_failure = sys.exception()
        cleanup_failure = None
        try:
            if workload_started:
                demo = request(base, "/api/demo/status")
                if demo.get("workload", demo)["active"]:
                    request(base, "/api/demo/stop", {"confirm": True})
        except (HTTPError, URLError) as error:
            cleanup_failure = error
        try:
            if cloud_changed:
                request(base, "/api/demo/cloud", {"enabled": False})
        except (HTTPError, URLError) as error:
            cleanup_failure = cleanup_failure or error
        if cleanup_failure:
            if original_failure is None:
                raise cleanup_failure
            print(f"Demo cleanup also encountered an error. {cleanup_failure}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "flow", "reset"])
    parser.add_argument("--cloud-outage", action="store_true", help="Exercise the simulated cloud outage in a flow.")
    parser.add_argument("--expect-offline", action="store_true", help="Require observed network loss and Offline Rescue before the live flow.")
    diagnosis = parser.add_mutually_exclusive_group()
    diagnosis.add_argument("--expect-ollama", action="store_true", help="Require a validated answer from the installed model.")
    diagnosis.add_argument("--skip-diagnosis", action="store_true", help="Skip inference when only testing approval and verification.")
    args = parser.parse_args()
    try:
        _, _, base = origin(environment()["ITOR_WEB_ORIGIN"])
        if args.command == "check":
            check(base)
        elif args.command == "reset":
            print(json.dumps(request(base, "/api/demo/reset", {"confirm": True}), indent=2))
        else:
            check(base)
            if args.expect_offline:
                eventually(
                    lambda: request(base, "/api/connectivity"),
                    lambda report: report["offline_rescue"] and (
                        report["network_interface"]["state"] == "disconnected"
                        or report["internet"]["state"] in {"disconnected", "unreachable"}
                    ),
                    "The device agent did not observe network loss. A simulated cloud outage alone is insufficient.",
                )
                print("Offline Rescue active after observed network loss.")
            flow(base, args.cloud_outage, args.skip_diagnosis, args.expect_ollama)
    except (HTTPError, URLError, RuntimeError, ValueError, OSError) as error:
        if isinstance(error, HTTPError):
            print(error.read().decode(errors="replace"), file=sys.stderr)
        print(f"Smoke test failed. {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
