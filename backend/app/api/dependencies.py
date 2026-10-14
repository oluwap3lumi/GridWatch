"""Lazy connection dependencies; read requests use a consistent read-only snapshot."""

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.session import make_engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine(Settings.from_env())


def get_session(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[Session]:
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        yield session


type ReadSession = Annotated[Session, Depends(get_session)]


def get_artifact_root() -> Path:
    return Path(os.environ.get("MODEL_ARTIFACT_DIR", "/app/ml/artifacts"))


type ArtifactRoot = Annotated[Path, Depends(get_artifact_root)]
type DatabaseEngine = Annotated[Engine, Depends(get_engine)]
