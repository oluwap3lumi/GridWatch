"""Lazy connection dependencies; read requests use a consistent read-only snapshot."""

from collections.abc import Iterator
from functools import lru_cache
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
