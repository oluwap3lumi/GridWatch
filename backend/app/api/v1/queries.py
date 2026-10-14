"""Shared validated query parameters, with standard FastAPI validation error shapes."""

from datetime import UTC, datetime
from typing import Annotated, NoReturn

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError

from app.schemas.spatial import BoundingBox

type Limit = Annotated[int, Query(ge=1, le=500, description="Page size (maximum 500)")]
type Offset = Annotated[int, Query(ge=0, description="Zero-based pagination offset")]


def invalid_query(name: str, message: str, value: object) -> NoReturn:
    raise RequestValidationError(
        [{"type": "value_error", "loc": ("query", name), "msg": message, "input": value}]
    )


def parse_bbox(
    bbox: Annotated[str | None, Query(description="EPSG:4326 west,south,east,north")] = None,
) -> BoundingBox | None:
    if bbox is None:
        return None
    try:
        return BoundingBox.parse(bbox)
    except ValueError as exc:
        invalid_query("bbox", str(exc), bbox)


type BBoxQuery = Annotated[BoundingBox | None, Depends(parse_bbox)]


def time_bounds(
    started_after: Annotated[
        datetime | None, Query(description="Inclusive timezone-aware start")
    ] = None,
    started_before: Annotated[
        datetime | None, Query(description="Exclusive timezone-aware end")
    ] = None,
) -> tuple[datetime | None, datetime | None]:
    values = []
    for name, value in (("started_after", started_after), ("started_before", started_before)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            invalid_query(
                name, "Timestamp requires a timezone (Z or an explicit offset)", str(value)
            )
        values.append(value.astimezone(UTC) if value is not None else None)
    start, end = values
    if start is not None and end is not None and start >= end:
        invalid_query("started_before", "Time range must have start before end", str(end))
    return start, end


type TimeBounds = Annotated[tuple[datetime | None, datetime | None], Depends(time_bounds)]
