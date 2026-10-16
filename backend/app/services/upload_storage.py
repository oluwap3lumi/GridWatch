"""Private bounded staging with UUID-derived paths; clients never choose stored filenames."""

from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from app.core.uploads import UploadSettings


class UploadTooLarge(ValueError):
    """Safe fixed error, with no uploaded filename or content."""


class UploadStorage:
    def __init__(self, settings: UploadSettings) -> None:
        self.settings = settings
        self.root = settings.staging_dir.resolve()

    def path(self, batch_id: UUID) -> Path:
        if not isinstance(batch_id, UUID):
            raise ValueError("Invalid batch identifier")
        target = self.root / f"{batch_id.hex}.upload"
        if target.is_symlink() or target.resolve().parent != self.root:
            raise ValueError("Unsafe staging path")
        return target

    def write(self, batch_id: UUID, chunks: Iterable[bytes]) -> int:
        """Enforce the limit while streaming and remove partial files on every failure."""
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self.path(batch_id)
        size = 0
        # Exclusive creation prevents retries from overwriting a staged upload.
        with target.open("xb") as output:
            try:
                target.chmod(0o600)
                for chunk in chunks:
                    size += len(chunk)
                    if size > self.settings.max_bytes:
                        raise UploadTooLarge("UPLOAD_TOO_LARGE")
                    output.write(chunk)
            except BaseException:
                output.close()
                target.unlink(missing_ok=True)
                raise
        return size

    def delete(self, batch_id: UUID) -> None:
        """Idempotent deletion used by commit, rollback, and TTL cleanup orchestration."""
        self.path(batch_id).unlink(missing_ok=True)
