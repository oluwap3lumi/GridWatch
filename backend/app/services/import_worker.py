"""Dedicated durable import worker, with no uploaded content in logs."""

import json
import logging.config
import time
from pathlib import Path
from threading import Event, Thread

from app.api.dependencies import get_engine
from app.core.uploads import UploadSettings
from app.repositories.import_jobs import cleanup, process_one
from app.services.upload_storage import UploadStorage


def main() -> None:
    logging.config.dictConfig(json.loads(Path("logging.json").read_text()))
    engine, storage = get_engine(), UploadStorage(UploadSettings.from_env())

    def heartbeat() -> None:
        while True:
            Path("/tmp/gridwatch-import-worker").touch()
            Event().wait(5)

    Thread(target=heartbeat, daemon=True).start()
    last_cleanup = 0.0
    while True:
        try:
            if time.monotonic() - last_cleanup > 30:
                cleanup(engine, storage)
                last_cleanup = time.monotonic()
            busy = process_one(engine, storage)
            Path("/tmp/gridwatch-import-worker").touch()
            if not busy:
                time.sleep(1)
        except Exception:
            # Safe retry; database recovery and file-permission errors must not leak data.
            time.sleep(2)


if __name__ == "__main__":
    main()
