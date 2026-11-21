from dataclasses import dataclass
from os import getenv
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    db_path: Path = Path(".spark-ready/local.sqlite3")
    retention_days: int = 7
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:4b"
    ollama_timeout: float = 60.0
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

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            api_key=getenv("SPARK_AGENT_KEY", ""),
            db_path=Path(getenv("SPARK_DB_PATH", ".spark-ready/local.sqlite3")),
            retention_days=int(getenv("SPARK_RETENTION_DAYS", "7")),
            ollama_url=getenv("SPARK_OLLAMA_URL", "http://127.0.0.1:11434"),
            ollama_model=getenv("SPARK_OLLAMA_MODEL", "qwen3.5:4b"),
            ollama_timeout=float(getenv("SPARK_OLLAMA_TIMEOUT_SECONDS", "60")),
            internet_probe_url=getenv("SPARK_INTERNET_PROBE_URL") or None,
            internet_expected_status=int(getenv("SPARK_INTERNET_EXPECTED_STATUS", "204")),
            connectivity_interval=float(getenv("SPARK_CONNECTIVITY_INTERVAL_SECONDS", "30")),
            connectivity_timeout=float(getenv("SPARK_CONNECTIVITY_TIMEOUT_SECONDS", "3")),
            connectivity_stability=float(getenv("SPARK_CONNECTIVITY_STABILITY_SECONDS", "5")),
            cpu_threshold=float(getenv("SPARK_CPU_WARNING_PERCENT", "80")),
            cpu_window=float(getenv("SPARK_CPU_WINDOW_SECONDS", "6")),
            demo_seconds=int(getenv("SPARK_DEMO_WORKLOAD_SECONDS", "180")),
            sample_interval=float(getenv("SPARK_TELEMETRY_INTERVAL_SECONDS", "2")),
        )
        if not settings.api_key:
            raise RuntimeError("Set SPARK_AGENT_KEY before starting the device agent.")
        if not 1 <= settings.retention_days <= 365:
            raise ValueError("SPARK_RETENTION_DAYS must be between 1 and 365.")
        if not 20 <= settings.cpu_threshold <= 100 or not 2 <= settings.cpu_window <= 60:
            raise ValueError("CPU warning must be 20–100 percent over 2–60 seconds.")
        if not 1 <= settings.sample_interval <= 30:
            raise ValueError("SPARK_TELEMETRY_INTERVAL_SECONDS must be between 1 and 30.")
        if not 1 <= settings.demo_seconds <= 180:
            raise ValueError("SPARK_DEMO_WORKLOAD_SECONDS must be between 1 and 180.")
        return settings
