from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value.strip() else default


def _int_env(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _float_env(name: str, default: float) -> float:
    return float(_env(name, str(default)))


@dataclass(frozen=True)
class Settings:
    database_url: str
    factory_execute_url: str
    factory_token: str | None
    app_timezone: str
    poll_interval_seconds: float
    max_concurrency: int
    processing_lease_seconds: int
    http_timeout_seconds: float
    max_retries: int
    shutdown_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = _env(
            "DATABASE_URL",
            "postgresql+psycopg2://payments:payments@localhost:5432/payments",
        )
        return cls(
            database_url=database_url,
            factory_execute_url=_env(
                "FACTORY_EXECUTE_URL", "http://localhost:8080/api/v1/payments/execute"
            ),
            factory_token=os.getenv("FACTORY_TOKEN") or None,
            app_timezone=_env("APP_TIMEZONE", "Europe/Moscow"),
            poll_interval_seconds=_float_env("POLL_INTERVAL_SECONDS", 30.0),
            max_concurrency=_int_env("MAX_CONCURRENCY", 10),
            processing_lease_seconds=_int_env("PROCESSING_LEASE_SECONDS", 900),
            http_timeout_seconds=_float_env("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_int_env("MAX_RETRIES", 5),
            shutdown_timeout_seconds=_float_env("SHUTDOWN_TIMEOUT_SECONDS", 30.0),
        )


settings = Settings.from_env()

