"""Settings validate connection inputs without exposing credentials."""

import pytest

from app.core.settings import Settings


def test_missing_settings_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        Settings.from_env()


def test_url_encodes_special_password_and_hides_it(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "synthetic:p@ss/word%",
        "POSTGRES_DB": "gridwatch_test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
    }.items():
        monkeypatch.setenv(name, value)
    settings = Settings.from_env()
    assert settings.database_url.password == "synthetic:p@ss/word%"
    assert "synthetic" not in str(settings.database_url)
    assert settings.database_url.drivername == "postgresql+psycopg"


def test_port_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST"):
        monkeypatch.setenv(name, "test")
    monkeypatch.setenv("POSTGRES_PORT", "65536")
    with pytest.raises(ValueError, match="POSTGRES_PORT"):
        Settings.from_env()
