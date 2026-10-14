"""Typed GeoJSON geometry and validated EPSG:4326 bounding boxes."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

type Position = tuple[FiniteFloat, FiniteFloat]


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: Position


class LineGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[Position] = Field(min_length=2)


type AssetGeometry = Annotated[PointGeometry | LineGeometry, Field(discriminator="type")]


class BoundingBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    west: FiniteFloat = Field(ge=-180, le=180)
    south: FiniteFloat = Field(ge=-90, le=90)
    east: FiniteFloat = Field(ge=-180, le=180)
    north: FiniteFloat = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def ordered(self) -> "BoundingBox":
        if self.west >= self.east or self.south >= self.north:
            raise ValueError(
                "bbox must be ordered west,south,east,north without antimeridian wrapping"
            )
        return self

    @classmethod
    def parse(cls, value: str) -> "BoundingBox":
        parts = value.split(",")
        if len(parts) != 4:
            raise ValueError("bbox requires four comma-separated coordinates")
        west, south, east, north = (float(part) for part in parts)
        return cls(west=west, south=south, east=east, north=north)
