"""Validated, environment-configured bounds for private upload staging."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UploadSettings:
    staging_dir: Path = Path("uploads/staging")
    max_bytes: int = 25 * 1024 * 1024
    max_features: int = 100_000
    max_expanded_bytes: int = 250 * 1024 * 1024
    max_zip_files: int = 32
    max_zip_ratio: int = 100
    ttl_seconds: int = 86400

    def __post_init__(self) -> None:
        for field in (
            "max_bytes",
            "max_features",
            "max_expanded_bytes",
            "max_zip_files",
            "max_zip_ratio",
            "ttl_seconds",
        ):
            value = getattr(self, field)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"Upload setting {field} must be a positive integer")

    @classmethod
    def from_env(cls) -> "UploadSettings":
        defaults = cls()
        return cls(
            staging_dir=Path(os.getenv("UPLOAD_STAGING_DIR", str(defaults.staging_dir))),
            **{
                name: int(os.getenv("UPLOAD_" + name.upper(), str(getattr(defaults, name))))
                for name in (
                    "max_bytes",
                    "max_features",
                    "max_expanded_bytes",
                    "max_zip_files",
                    "max_zip_ratio",
                    "ttl_seconds",
                )
            },
        )
