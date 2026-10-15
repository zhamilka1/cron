from app.config import Settings


def test_settings_read_executor_configuration(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://user:password@db:5432/payments")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "5")
    monkeypatch.setenv("MAX_CONCURRENCY", "3")

    settings = Settings.from_env()

    assert settings.database_url.endswith("@db:5432/payments")
    assert settings.poll_interval_seconds == 5
    assert settings.max_concurrency == 3

