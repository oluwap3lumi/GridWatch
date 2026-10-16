"""Database-independent import records and safe error codes."""

from dataclasses import dataclass, field

from pydantic import JsonValue

from app.schemas.imports import ImportFormat, RowIssue
from app.schemas.spatial import AssetGeometry


class ParseFailure(ValueError):
    """Never include filenames, row values, native exception text, or coordinates."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SourceRow:
    number: int
    properties: dict[str, JsonValue]
    geometry: dict[str, JsonValue] | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedUpload:
    format: ImportFormat
    columns: tuple[str, ...]
    rows: tuple[SourceRow, ...]
    crs_detected: str | None
    warnings: tuple[str, ...] = ()


@dataclass
class ValidatedRow:
    number: int
    attributes: dict[str, JsonValue] = field(default_factory=dict)
    geometry: AssetGeometry | None = None
    errors: list[RowIssue] = field(default_factory=list)
    warnings: list[RowIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors
