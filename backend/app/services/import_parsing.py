"""Bounded CSV, GeoJSON/JSON and Shapefile readers with safe failure messages."""

import codecs
import csv
import io
import json
import math
import struct
import warnings
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import cast

import shapefile
from pydantic import JsonValue, TypeAdapter

from app.core.uploads import UploadSettings
from app.services.import_archive import shapefile_members
from app.services.import_crs import read_prj, source_crs
from app.services.import_records import ParsedUpload, ParseFailure, SourceRow

JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


def object_value(value: object) -> dict[str, JsonValue]:
    return JSON_OBJECT.validate_python(value)


def reject_constant(value: str) -> None:
    raise ParseFailure("NONFINITE_JSON")


def finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ParseFailure("NONFINITE_JSON")
    return result


def clean_object(value: dict[str, JsonValue]) -> tuple[dict[str, JsonValue], tuple[str, ...]]:
    """Keep malformed text row-local and JSONB-safe without losing valid sibling rows."""
    problems: set[str] = set()

    def clean(item: JsonValue) -> JsonValue:
        if isinstance(item, str):
            normalized = item.encode("utf-8", errors="replace").decode().replace("\x00", "\ufffd")
            if normalized != item:
                problems.add("INVALID_TEXT")
            return normalized
        if isinstance(item, float) and not math.isfinite(item):
            problems.add("INVALID_NUMBER")
            return None
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, dict):
            return {str(clean(key)): clean(child) for key, child in item.items()}
        return item

    result = object_value(clean(value))
    return result, tuple(sorted(problems))


def unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ParseFailure("DUPLICATE_JSON_PROPERTY")
        result[key] = value
    return result


def columns(rows: list[SourceRow]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(key for row in rows for key in row.properties))


def read_csv(data: bytes, limits: UploadSettings) -> ParsedUpload:
    try:
        content = data.decode("utf-8-sig")
        if "\x00" in content:
            raise ParseFailure("INVALID_CSV")
        try:
            delimiter = csv.Sniffer().sniff(content[:8192], delimiters=",;").delimiter
        except csv.Error:
            delimiter = ";" if content.partition("\n")[0].count(";") else ","
        reader = csv.reader(io.StringIO(content, newline=""), delimiter=delimiter, strict=True)
        header = [name.strip() for name in next(reader)]
        if not header or any(not name for name in header) or len(set(header)) != len(header):
            raise ParseFailure("INVALID_CSV_HEADER")
        rows: list[SourceRow] = []
        for values in reader:
            if not values or all(not value.strip() for value in values):
                continue
            if len(rows) >= limits.max_features:
                raise ParseFailure("FEATURE_LIMIT")
            rows.append(
                SourceRow(
                    len(rows) + 1,
                    dict(zip(header, values, strict=False)),
                    errors=(() if len(values) == len(header) else ("COLUMN_COUNT_MISMATCH",)),
                )
            )
        return ParsedUpload("csv", tuple(header), tuple(rows), "EPSG:4326")
    except ParseFailure:
        raise
    except (UnicodeError, csv.Error, StopIteration):
        raise ParseFailure("INVALID_CSV") from None


def read_json(data: bytes, limits: UploadSettings) -> ParsedUpload:
    try:
        document: JsonValue = json.loads(
            data.decode("utf-8-sig"),
            parse_constant=reject_constant,
            parse_float=finite_float,
            object_pairs_hook=unique_object,
        )
        detected: str | None = "EPSG:4326"
        warning: tuple[str, ...] = ()
        plain = isinstance(document, list)
        if isinstance(document, dict) and document.get("type") == "FeatureCollection":
            features = document.get("features")
            if "crs" in document:
                try:
                    declared = cast(dict[str, JsonValue], document["crs"])
                    properties = cast(dict[str, JsonValue], declared["properties"])
                    detected = source_crs(str(properties["name"])).to_wkt()
                except Exception:
                    detected, warning = None, ("CRS_REQUIRED",)
        elif plain:
            features = document
        else:
            raise ParseFailure("FEATURE_COLLECTION_REQUIRED")
        if not isinstance(features, list):
            raise ParseFailure("FEATURE_COLLECTION_REQUIRED")
        if len(features) > limits.max_features:
            raise ParseFailure("FEATURE_LIMIT")
        rows = []
        for index, feature in enumerate(features, 1):
            if not isinstance(feature, dict):
                rows.append(SourceRow(index, {}, errors=("INVALID_RECORD",)))
                continue
            if plain:
                clean, errors_found = clean_object(feature)
                rows.append(SourceRow(index, clean, errors=errors_found))
                continue
            props, geometry = feature.get("properties"), feature.get("geometry")
            errors = []
            if feature.get("type") != "Feature":
                errors.append("INVALID_RECORD")
            if not isinstance(props, dict):
                props = {}
                errors.append("INVALID_PROPERTIES")
            props = dict(props)
            if "external_id" not in props and isinstance(feature.get("id"), str | int):
                props["external_id"] = feature["id"]
            props, errors_found = clean_object(props)
            errors.extend(errors_found)
            if not isinstance(geometry, dict):
                geometry = None
                errors.append("NULL_GEOMETRY")
            else:
                geometry, errors_found = clean_object(geometry)
                errors.extend(errors_found)
            rows.append(SourceRow(index, props, geometry, tuple(errors)))
        return ParsedUpload("geojson", columns(rows), tuple(rows), detected, warning)
    except ParseFailure:
        raise
    except Exception:
        raise ParseFailure("INVALID_JSON") from None


def json_default(value: object) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    raise ParseFailure("INVALID_DBF_VALUE")


def check_shape_headers(members: dict[str, bytes], limits: UploadSettings) -> None:
    """Bound native-reader allocations using actual file sizes, not declared record counts."""
    try:
        for extension in (".shp", ".shx"):
            value = members[extension]
            if (
                len(value) < 100
                or struct.unpack_from(">i", value)[0] != 9994
                or struct.unpack_from(">i", value, 24)[0] * 2 != len(value)
                or struct.unpack_from("<i", value, 28)[0] != 1000
            ):
                raise ParseFailure("INVALID_SHAPEFILE_HEADER")
        shx, dbf, shp = members[".shx"], members[".dbf"], members[".shp"]
        count = (len(shx) - 100) // 8
        if len(dbf) < 33 or (len(shx) - 100) % 8:
            raise ParseFailure("INVALID_SHAPEFILE_HEADER")
        records, header_size, record_size = struct.unpack_from("<IHH", dbf, 4)
        if max(count, records) > limits.max_features:
            raise ParseFailure("FEATURE_LIMIT")
        if (
            records != count
            or header_size < 33
            or record_size < 1
            or header_size + record_size * records > len(dbf)
        ):
            raise ParseFailure("SHAPE_RECORD_MISMATCH")
        cursor = 100
        for index in range(count):
            offset, words = struct.unpack_from(">ii", shx, 100 + index * 8)
            if offset * 2 != cursor or words < 2 or cursor + 8 + words * 2 > len(shp):
                raise ParseFailure("INVALID_SHAPEFILE_HEADER")
            number, actual_words = struct.unpack_from(">ii", shp, cursor)
            if actual_words != words or number != index + 1:
                raise ParseFailure("INVALID_SHAPEFILE_HEADER")
            kind = struct.unpack_from("<i", shp, cursor + 8)[0]
            body = words * 2
            if kind in (3, 5, 13, 15, 23, 25, 31):
                parts, points = struct.unpack_from("<ii", shp, cursor + 8 + 36)
                if parts < 0 or points < 0 or 44 + 4 * parts + 16 * points > body:
                    raise ParseFailure("INVALID_SHAPEFILE_HEADER")
            elif kind in (8, 18, 28):
                points = struct.unpack_from("<i", shp, cursor + 8 + 36)[0]
                if points < 0 or 40 + 16 * points > body:
                    raise ParseFailure("INVALID_SHAPEFILE_HEADER")
            cursor += 8 + words * 2
        if cursor != len(shp):
            raise ParseFailure("INVALID_SHAPEFILE_HEADER")
    except ParseFailure:
        raise
    except Exception:
        raise ParseFailure("INVALID_SHAPEFILE_HEADER") from None


def _read_shapefile(data: bytes, limits: UploadSettings) -> ParsedUpload:
    members = shapefile_members(data, limits)
    check_shape_headers(members, limits)
    encodings = ["utf-8"]
    warning = []
    if ".cpg" in members:
        try:
            cpg = members[".cpg"].decode("ascii").strip()
            cpg = "utf-8" if cpg == "65001" else "cp" + cpg if cpg.isdecimal() else cpg
            encodings.append(codecs.lookup(cpg).name)
        except (LookupError, UnicodeError):
            warning.append("CPG_INVALID")
    encodings.append("latin-1")
    try:
        for encoding in dict.fromkeys(encodings):
            try:
                with shapefile.Reader(
                    shp=io.BytesIO(members[".shp"]),
                    shx=io.BytesIO(members[".shx"]),
                    dbf=io.BytesIO(members[".dbf"]),
                    encoding=encoding,
                ) as reader:
                    if reader.numRecords > limits.max_features:
                        raise ParseFailure("FEATURE_LIMIT")
                    if reader.numShapes != reader.numRecords:
                        raise ParseFailure("SHAPE_RECORD_MISMATCH")
                    rows: list[SourceRow] = []
                    for index, record in enumerate(reader.iterShapeRecords(), 1):
                        if len(rows) >= limits.max_features:
                            raise ParseFailure("FEATURE_LIMIT")
                        props, row_errors = clean_object(
                            object_value(
                                json.loads(
                                    json.dumps(record.record.as_dict(), default=json_default)
                                )
                            )
                        )
                        if record.shape.shapeType == shapefile.NULL:
                            rows.append(
                                SourceRow(index, props, errors=(*row_errors, "NULL_GEOMETRY"))
                            )
                        else:
                            try:
                                geometry = object_value(
                                    json.loads(
                                        json.dumps(record.shape.__geo_interface__, allow_nan=False)
                                    )
                                )
                                rows.append(SourceRow(index, props, geometry, row_errors))
                            except Exception:
                                rows.append(SourceRow(index, props, errors=("INVALID_GEOMETRY",)))
                if encoding != "utf-8":
                    warning.append("DBF_ENCODING_FALLBACK")
                prj = members.get(".prj", b"")
                try:
                    detected = read_prj(prj.decode("utf-8-sig")) if prj else None
                except UnicodeError:
                    detected = None
                if detected is None:
                    warning.append("CRS_REQUIRED")
                return ParsedUpload(
                    "shapefile", columns(rows), tuple(rows), detected, tuple(warning)
                )
            except (UnicodeError, shapefile.ShapefileException):
                continue
        raise ParseFailure("INVALID_DBF_ENCODING")
    except ParseFailure:
        raise
    except Exception:
        raise ParseFailure("INVALID_SHAPEFILE") from None


def read_shapefile(data: bytes, limits: UploadSettings) -> ParsedUpload:
    # PyShp warnings can embed raw DBF bytes. Emit our fixed fallback code instead.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _read_shapefile(data, limits)


def parse_upload(data: bytes, filename: str, limits: UploadSettings) -> ParsedUpload:
    if len(data) > limits.max_bytes:
        raise ParseFailure("UPLOAD_TOO_LARGE")
    if not data.strip():
        raise ParseFailure("EMPTY_FILE")
    extension = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    prefix = data.lstrip(b"\xef\xbb\xbf \r\n\t")[:4]
    if extension == ".zip" and prefix.startswith(b"PK"):
        parsed = read_shapefile(data, limits)
    elif extension in (".json", ".geojson") and prefix[:1] in (b"{", b"["):
        parsed = read_json(data, limits)
    elif extension == ".csv" and not prefix.startswith((b"PK", b"{", b"[")):
        parsed = read_csv(data, limits)
    else:
        raise ParseFailure("FORMAT_MISMATCH")
    if not parsed.rows:
        raise ParseFailure("EMPTY_FILE")
    return parsed
