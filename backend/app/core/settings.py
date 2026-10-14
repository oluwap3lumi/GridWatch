"""Database configuration supplied entirely by environment variables."""

import os
from dataclasses import dataclass

from sqlalchemy.engine import URL


@dataclass(frozen=True)
class Settings:
    """Connection settings; creating a URL does not open a database connection."""

    database_url: URL

    @classmethod
    def from_env(cls) -> "Settings":
        required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError("Missing database environment variables: " + ", ".join(missing))
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        if not 1 <= port <= 65535:
            raise ValueError("POSTGRES_PORT must be between 1 and 65535")
        return cls(
            URL.create(
                "postgresql+psycopg",
                username=os.environ["POSTGRES_USER"],
                password=os.environ["POSTGRES_PASSWORD"],
                host=os.environ["POSTGRES_HOST"],
                port=port,
                database=os.environ["POSTGRES_DB"],
            )
        )
