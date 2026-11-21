import getpass
from dataclasses import dataclass
from os import getenv
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    db_path: Path = Path(".itor/local.sqlite3")
    retention_days: int = 7
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:4b"
    ollama_timeout: float = 120.0
    gemini_model: str = "gemini-3.5-flash-lite"
    internet_probe_url: str | None = None
    internet_expected_status: int = 204
    connectivity_interval: float = 30.0
    connectivity_timeout: float = 3.0
    connectivity_stability: float = 5.0
    cpu_threshold: float = 80.0
    cpu_window: float = 6.0
    demo_seconds: int = 180
    sample_interval: float = 2.0
    action_expiry_seconds: int = 90
    employee_name: str = "me"
    idle_seconds: float = 120.0
    worktime_interval: float = 15.0
    company_url: str | None = None
    company_key: str = ""
    demo_team: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            api_key=getenv("ITOR_AGENT_KEY", ""),
            db_path=Path(getenv("ITOR_DB_PATH", ".itor/local.sqlite3")),
            retention_days=int(getenv("ITOR_RETENTION_DAYS", "7")),
            ollama_url=getenv("ITOR_OLLAMA_URL", "http://127.0.0.1:11434"),
            ollama_model=getenv("ITOR_OLLAMA_MODEL", "qwen3.5:4b"),
            ollama_timeout=float(getenv("ITOR_OLLAMA_TIMEOUT_SECONDS", "120")),
            gemini_model=getenv("ITOR_GEMINI_MODEL", "gemini-3.5-flash-lite"),
            internet_probe_url=getenv("ITOR_INTERNET_PROBE_URL") or None,
            internet_expected_status=int(getenv("ITOR_INTERNET_EXPECTED_STATUS", "204")),
            connectivity_interval=float(getenv("ITOR_CONNECTIVITY_INTERVAL_SECONDS", "30")),
            connectivity_timeout=float(getenv("ITOR_CONNECTIVITY_TIMEOUT_SECONDS", "3")),
            connectivity_stability=float(getenv("ITOR_CONNECTIVITY_STABILITY_SECONDS", "5")),
            cpu_threshold=float(getenv("ITOR_CPU_WARNING_PERCENT", "80")),
            cpu_window=float(getenv("ITOR_CPU_WINDOW_SECONDS", "6")),
            demo_seconds=int(getenv("ITOR_DEMO_WORKLOAD_SECONDS", "180")),
            sample_interval=float(getenv("ITOR_TELEMETRY_INTERVAL_SECONDS", "2")),
            employee_name=getenv("ITOR_EMPLOYEE_NAME") or getpass.getuser(),
            idle_seconds=float(getenv("ITOR_IDLE_SECONDS", "120")),
            worktime_interval=float(getenv("ITOR_WORKTIME_INTERVAL_SECONDS", "15")),
            company_url=getenv("ITOR_COMPANY_URL") or None,
            company_key=getenv("ITOR_COMPANY_KEY", ""),
            demo_team=getenv("ITOR_DEMO_TEAM", "1") not in ("0", "false", "no"),
        )
        if not settings.api_key:
            raise RuntimeError("Set ITOR_AGENT_KEY before starting the device agent.")
        if not 1 <= settings.retention_days <= 365:
            raise ValueError("ITOR_RETENTION_DAYS must be between 1 and 365.")
        if not 20 <= settings.cpu_threshold <= 100 or not 2 <= settings.cpu_window <= 60:
            raise ValueError("CPU warning must be 20–100 percent over 2–60 seconds.")
        if not 1 <= settings.sample_interval <= 30:
            raise ValueError("ITOR_TELEMETRY_INTERVAL_SECONDS must be between 1 and 30.")
        if not 1 <= settings.demo_seconds <= 180:
            raise ValueError("ITOR_DEMO_WORKLOAD_SECONDS must be between 1 and 180.")
        return settings
