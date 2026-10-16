"""Pure mapping and row validation; errors never interpolate private source values."""

import math
import re
import warnings
from collections import Counter
from datetime import date, datetime
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import JsonValue, RootModel
from pyproj import Transformer
from shapely import force_2d, from_wkt, get_coordinates, transform
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

from app.schemas.imports import LayerType, RowIssue, ValidateImport
from app.schemas.spatial import AssetGeometry
from app.services.import_crs import transformer
from app.services.import_records import ParsedUpload, ParseFailure, SourceRow, ValidatedRow

ALIASES = {
    "external_id": ("external_id", "externalid", "asset_id", "assetid", "id", "objectid", "fid"),
    "latitude": ("latitude", "lat", "y", "northing"),
    "longitude": ("longitude", "lon", "lng", "long", "x", "easting"),
    "geometry": ("geometry", "wkt", "geom", "shape"),
    "capacity_kva": ("capacity_kva", "capacity_k", "kva", "capacity"),
    "load_factor": ("load_factor", "load_facto", "loadfactor", "load"),
    "install_date": ("install_date", "install_da", "installed", "inst_date", "commissioned"),
    "last_maintenance_date": ("last_maintenance_date", "maint_date", "last_maint"),
    "feeder_id": ("feeder_id", "feederid", "feeder"),
    "pole_id": ("pole_id", "poleid", "pole"),
    "material": ("material",),
    "vegetation_index": ("vegetation_index", "vegetation", "vegetationindex"),
}


def key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def suggest_mapping(columns: tuple[str, ...]) -> dict[str, str]:
    result = {}
    for target, aliases in ALIASES.items():
        # Ambiguous matches require a deliberate user choice, never positional guessing.
        matches = [column for column in columns if key(column) in {key(a) for a in aliases}]
        if len(matches) == 1:
            result[target] = matches[0]
    return result


def column_mapping(columns: tuple[str, ...], overrides: dict[str, str]) -> dict[str, str]:
    result = suggest_mapping(columns)
    for target, source in overrides.items():
        if target not in ALIASES or (source and source not in columns):
            raise ParseFailure("INVALID_COLUMN_MAPPING")
        if source:
            result[target] = source
        else:
            result.pop(target, None)
    if len(set(result.values())) != len(result):
        raise ParseFailure("DUPLICATE_COLUMN_MAPPING")
    return result


def identifier(value: JsonValue) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise ValueError
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer() or abs(value) > 2**53:
            raise ValueError
        value = int(value)
    result = str(value).strip()
    if len(result) > 255 or any(ord(c) < 32 for c in result):
        raise ValueError
    return result or None


def number(value: JsonValue) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise ValueError
    try:
        result = float(value)
    except OverflowError:
        raise ValueError from None
    if not math.isfinite(result):
        raise ValueError
    return result


def empty(value: JsonValue) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_date(value: str, convention: Literal["auto", "day_first", "month_first"]) -> date:
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]", value):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            raise ValueError("INVALID_DATE") from None
    parts = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value)
    if parts:
        first, second, year = map(int, parts.groups())
        if convention == "auto" and first <= 12 and second <= 12 and first != second:
            raise ValueError("AMBIGUOUS_DATE")
        day_first = convention == "day_first" or (convention == "auto" and first > 12)
        return date(year, second if day_first else first, first if day_first else second)
    for pattern in ("%Y/%m/%d", "%d %b %Y", "%d-%b-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError("INVALID_DATE")


def issue(row: ValidatedRow, field: str, code: str, *, warning: bool = False) -> None:
    reasons = {
        "DUPLICATE_ID": "External ID is repeated within this file; all copies are invalid.",
        "UNKNOWN_REFERENCE": "Reference is unresolved and will be retained for later matching.",
        "CRS_REQUIRED": "Choose a source CRS before validation can complete.",
        "INVALID_CRS": "Source CRS cannot be interpreted or transformed.",
        "AMBIGUOUS_DATE": "Choose day-first or month-first date interpretation.",
        "INVALID_DATE": "Date is invalid or uses an unsupported format.",
        "DATE_ORDER": "Maintenance date precedes installation date.",
        "MISSING_ID": "An external ID is required.",
        "INVALID_ID": "Use a nonempty external ID of at most 255 characters.",
        "INVALID_NUMBER": "Use a finite numeric value within the documented range.",
        "NULL_GEOMETRY": "Geometry is missing or is a null shape.",
        "INVALID_GEOMETRY": "Geometry is invalid, empty, or cannot be parsed.",
        "GEOMETRY_TYPE": "Geometry type does not match the selected layer type.",
        "COORDINATE_RANGE": "Coordinates must be finite WGS84 positions and cannot be (0,0).",
        "Z_DROPPED": "Height coordinates were removed; GridWatch stores two-dimensional geometry.",
        "INVALID_TEXT": "Text exceeds the allowed length or has an unsupported value.",
        "RELATIONSHIP_TYPE": "Reference field is not supported for the selected layer type.",
    }
    item = RowIssue(
        row_number=row.number,
        field=field,
        code=code,
        reason=reasons.get(code, "Source row is malformed and cannot be imported."),
    )
    (row.warnings if warning else row.errors).append(item)


class GeometryValue(RootModel[AssetGeometry]):
    pass


def _validate_geometry(
    source: SourceRow,
    values: dict[str, JsonValue],
    layer: LayerType,
    projection: Transformer | None,
    crs_error: str | None,
    result: ValidatedRow,
) -> None:
    try:
        geometry: BaseGeometry
        if source.geometry is not None:
            geometry = shape(source.geometry)
        elif isinstance(values.get("geometry"), str) and values["geometry"]:
            geometry = from_wkt(str(values["geometry"]))
        elif "latitude" in values and "longitude" in values:
            geometry = Point(number(values["longitude"]), number(values["latitude"]))
        else:
            issue(result, "geometry", "NULL_GEOMETRY")
            return
        expected = ("LineString", "MultiLineString") if layer == "feeder_line" else ("Point",)
        if geometry.geom_type not in expected:
            issue(result, "geometry", "GEOMETRY_TYPE")
            return
        if geometry.is_empty or not geometry.is_valid:
            issue(result, "geometry", "INVALID_GEOMETRY")
            return
        if geometry.has_z:
            issue(result, "geometry", "Z_DROPPED", warning=True)
        if projection is None:
            raise ParseFailure(crs_error or "CRS_REQUIRED")

        def project(coordinates: NDArray[np.float64]) -> NDArray[np.float64]:
            x, y = projection.transform(coordinates[:, 0], coordinates[:, 1], errcheck=True)
            return np.asarray(np.column_stack((x, y)), dtype=np.float64)

        geometry = transform(force_2d(geometry), project)
        positions = get_coordinates(geometry)
        if not len(positions) or any(
            not math.isfinite(lon)
            or not math.isfinite(lat)
            or not -180 <= lon <= 180
            or not -90 <= lat <= 90
            or (lon == 0 and lat == 0)
            for lon, lat in positions
        ):
            issue(result, "geometry", "COORDINATE_RANGE")
            return
        if not geometry.is_valid:
            issue(result, "geometry", "INVALID_GEOMETRY")
            return
        result.geometry = GeometryValue.model_validate(mapping(geometry)).root
    except ParseFailure as error:
        issue(result, "crs", error.code)
    except Exception:
        issue(result, "geometry", "INVALID_GEOMETRY")


def validate_geometry(
    source: SourceRow,
    values: dict[str, JsonValue],
    layer: LayerType,
    projection: Transformer | None,
    crs_error: str | None,
    result: ValidatedRow,
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _validate_geometry(source, values, layer, projection, crs_error, result)


def validate_upload(
    parsed: ParsedUpload,
    layer: LayerType,
    options: ValidateImport,
    *,
    known_poles: frozenset[str] = frozenset(),
    known_feeders: frozenset[str] = frozenset(),
) -> tuple[ValidatedRow, ...]:
    selected = column_mapping(parsed.columns, options.column_mapping)
    projection = None
    crs_error = None
    try:
        projection = transformer(options.source_crs or parsed.crs_detected)
    except ParseFailure as error:
        crs_error = error.code
    rows = []
    for source in parsed.rows:
        row = ValidatedRow(source.number)
        for code in source.errors:
            issue(row, "geometry" if "GEOMETRY" in code else "row", code)
        values = {target: source.properties.get(column) for target, column in selected.items()}
        for field in ("external_id", "pole_id", "feeder_id"):
            try:
                external = identifier(values.get(field))
                if external is not None:
                    if (field == "pole_id" and layer != "transformer") or (
                        field == "feeder_id" and layer == "feeder_line"
                    ):
                        issue(row, field, "RELATIONSHIP_TYPE")
                    row.attributes[field if field == "external_id" else "external_" + field] = (
                        external
                    )
                    known = known_poles if field == "pole_id" else known_feeders
                    if field != "external_id" and external not in known:
                        issue(row, field, "UNKNOWN_REFERENCE", warning=True)
                elif field == "external_id":
                    issue(row, field, "MISSING_ID")
            except ValueError:
                issue(row, field, "INVALID_ID")
        for field in ("capacity_kva", "load_factor", "vegetation_index"):
            value = values.get(field)
            if empty(value):
                continue
            try:
                numeric = number(value)
                low, high = {
                    "capacity_kva": (0, 1_000_000),
                    "load_factor": (0, 1.5),
                    "vegetation_index": (0, 1),
                }[field]
                if (
                    numeric < low
                    or numeric > high
                    or (
                        numeric == 0
                        and (
                            field == "load_factor" or (field == "capacity_kva" and layer != "pole")
                        )
                    )
                    or (field == "capacity_kva" and numeric == high)
                ):
                    raise ValueError
                row.attributes[field] = numeric
            except ValueError:
                issue(row, field, "INVALID_NUMBER")
        for field in ("install_date", "last_maintenance_date"):
            value = values.get(field)
            if empty(value):
                continue
            try:
                if not isinstance(value, str):
                    raise ValueError("INVALID_DATE")
                row.attributes[field] = parse_date(value, options.date_format).isoformat()
            except ValueError as error:
                issue(
                    row,
                    field,
                    "AMBIGUOUS_DATE" if str(error) == "AMBIGUOUS_DATE" else "INVALID_DATE",
                )
        installed, maintained = (
            row.attributes.get("install_date"),
            row.attributes.get("last_maintenance_date"),
        )
        if isinstance(installed, str) and isinstance(maintained, str) and maintained < installed:
            issue(row, "last_maintenance_date", "DATE_ORDER")
        material = values.get("material")
        if not empty(material):
            if (
                not isinstance(material, str)
                or len(material.strip()) > 30
                or any(ord(c) < 32 for c in material)
            ):
                issue(row, "material", "INVALID_TEXT")
            else:
                row.attributes["material"] = material.strip()
        if not any("GEOMETRY" in code for code in source.errors):
            validate_geometry(source, values, layer, projection, crs_error, row)
        rows.append(row)
    counts = Counter(row.attributes.get("external_id") for row in rows)
    for row in rows:
        duplicate_id = row.attributes.get("external_id")
        if duplicate_id is not None and counts[duplicate_id] > 1:
            issue(row, "external_id", "DUPLICATE_ID")
    return tuple(rows)
