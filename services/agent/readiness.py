from statistics import mean
from threading import RLock

from .models import Check, DeviceSnapshot, Finding, ReadinessReport


class ReadinessEngine:
    def __init__(self, cpu_threshold: float = 80, cpu_window: float = 6):
        self.cpu_threshold = cpu_threshold
        self.cpu_window = cpu_window
        self.cpu_elevated = False
        self.lock = RLock()

    def cpu_result(self, snapshot: DeviceSnapshot, history: list[DeviceSnapshot]) -> tuple[bool, float]:
        recent = [item for item in history if item.cpu_percent is not None and
                  0 <= (snapshot.captured_at - item.captured_at).total_seconds() <= self.cpu_window]
        span = (recent[-1].captured_at - recent[0].captured_at).total_seconds() if recent else 0
        with self.lock:
            if len(recent) >= 3 and span >= 0.6 * self.cpu_window:
                threshold = self.cpu_threshold - 10 if self.cpu_elevated else self.cpu_threshold
                self.cpu_elevated = mean(item.cpu_percent for item in recent) >= threshold
            return self.cpu_elevated, span

    def evaluate(self, snapshot: DeviceSnapshot, history: list[DeviceSnapshot],
                 internet_unavailable: bool = False) -> ReadinessReport:
        findings: list[Finding] = []
        checks: list[Check] = []

        def record(check_id, label, state, detail):
            checks.append(Check(id=check_id, label=label, state=state, detail=detail))

        def finding(category, severity, title, evidence, impact, limitations, actions=None, window=0):
            findings.append(Finding(category=category, severity=severity, title=title, evidence=evidence,
                                    potential_impact=impact, limitations=limitations, source=snapshot.source,
                                    recommended_action_ids=actions or [], window_seconds=round(window, 1)))

        high_cpu, window = self.cpu_result(snapshot, history)
        pressure = [
            ("cpu", "Processor load", snapshot.cpu_percent, high_cpu,
             "Sustained CPU activity", "High processor demand can make video or screen sharing less responsive.", window),
            ("memory", "Memory availability", snapshot.memory_percent,
             snapshot.memory_percent is not None and snapshot.memory_percent >= 87,
             "Memory pressure", "Applications may respond more slowly when little memory is available.", 0),
            ("disk", "Storage capacity", snapshot.disk_percent,
             snapshot.disk_percent is not None and snapshot.disk_percent >= 92,
             "Low available storage", "A full disk can interfere with updates or temporary files your apps need.", 0),
        ]
        for key, label, percent, warning, title, impact, seconds in pressure:
            if percent is None:
                record(key, label, "unknown", "A current reading is unavailable.")
                finding(key, "unknown", f"{label} could not be checked", "The operating system returned no reading.",
                        "Readiness for this check is unknown.", "Measurements may be unavailable on this device.")
            elif warning:
                detail = f"{percent:.1f}% used in the latest sample." if key != "cpu" else (
                    f"CPU demand stayed elevated over {seconds:.1f} seconds. Latest sample: {percent:.1f}%."
                )
                record(key, label, "warning", detail)
                finding(key, "warning", title, detail, impact, "The exact effect on your work was not measured.",
                        window=seconds)
            else:
                record(key, label, "passed", f"{percent:.1f}% used in the latest sample.")

        work = snapshot.workload
        if work.active and work.cpu_percent is not None and work.cpu_percent >= 20:
            evidence = f"itor's temporary workload is using {work.cpu_percent:.1f}% of one CPU core."
            record("workload", "Background workload", "warning", evidence)
            finding("workload", "warning", "Background workload using CPU", evidence,
                    "The workload may leave less processor time for your work apps.",
                    "This is an app-owned demonstration. Overall device impact depends on available cores.",
                    actions=["stop_demo_workload"] if snapshot.source == "local" else [])
        elif work.active:
            record("workload", "Background workload", "unknown", "Waiting for a current workload CPU sample.")
        else:
            record("workload", "Background workload", "passed", "The itor demonstration workload is idle.")

        if snapshot.network_up is False or internet_unavailable:
            evidence = ("The approved internet check did not reach its configured endpoint." if internet_unavailable
                        else "No active non-loopback network interface with an address was detected.")
            record("network", "Network connection", "warning", evidence)
            finding("network", "critical", "Connection needs attention", evidence,
                    "Online apps and calls may not work.", "This check does not test any specific app.")
        elif snapshot.network_up is None:
            record("network", "Network connection", "unknown", "Interface status was unavailable.")
            finding("network", "unknown", "Network status unavailable", "No interface reading was returned.",
                    "Network readiness is unknown.", "Internet access cannot be confirmed.")
        else:
            record("network", "Network connection", "passed", "A local network interface is active.")

        record("audio", "Audio and camera", "unsupported", "Check your microphone and camera in your call app.")

        if any(item.severity == "critical" for item in findings):
            outcome = "not_ready"
        elif any(item.severity == "warning" for item in findings):
            outcome = "attention"
        elif any(item.severity == "unknown" for item in findings) or (work.active and work.cpu_percent is None):
            outcome = "unknown"
        else:
            outcome = "ready"
        return ReadinessReport(readiness=outcome, findings=findings, snapshot=snapshot, checks=checks)
