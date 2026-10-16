"""Synthetic byte-level parser, reprojection, row-validation and archive adversarial cases."""

import io
import json
import stat
import struct
import warnings
import zipfile
from dataclasses import replace

import pytest
import shapefile
from pyproj import CRS

from app.core.uploads import UploadSettings
from app.schemas.imports import ValidateImport
from app.services.import_archive import shapefile_members
from app.services.import_parsing import parse_upload
from app.services.import_records import ParseFailure
from app.services.import_validation import (
    column_mapping,
    parse_date,
    suggest_mapping,
    validate_upload,
)

LIMITS = UploadSettings()


def packed(members: dict[str, bytes], *, compressed: bool = False) -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(
        result, "w", compression=zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
    ) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return result.getvalue()


def shape_members(
    *,
    encoding: str = "utf-8",
    prj: bytes | None = None,
    cpg: bytes | None = None,
    null: bool = False,
    lines: bool = False,
) -> dict[str, bytes]:
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    with shapefile.Writer(
        shp=shp,
        shx=shx,
        dbf=dbf,
        encoding=encoding,
        shapeType=shapefile.POLYLINE if lines else shapefile.POINT,
    ) as writer:
        writer.field("externalid", "C", size=30)
        writer.field("material", "C", size=30)
        if lines:
            writer.line([[(500000, 0), (500010, 10)], [(500100, 0), (500110, 10)]])
        else:
            writer.point(500000, 0)
        writer.record("001", "pôle")
        if null:
            writer.null()
            writer.record("002", "steel")
    result = {
        "network.shp": shp.getvalue(),
        "network.shx": shx.getvalue(),
        "network.dbf": dbf.getvalue(),
    }
    if prj is not None:
        result["network.prj"] = prj
    if cpg is not None:
        result["network.cpg"] = cpg
    return result


def validate(data: bytes, filename: str = "assets.csv", **kwargs):
    return validate_upload(
        parse_upload(data, filename, LIMITS), "transformer", ValidateImport(**kwargs)
    )


@pytest.mark.parametrize("delimiter", [",", ";"])
def test_csv_bom_delimiters_quoted_fields_and_leading_zero_ids(delimiter: str) -> None:
    output = io.StringIO(newline="")
    import csv

    writer = csv.writer(output, delimiter=delimiter)
    writer.writerow(["ID", "Y", "X", "material"])
    writer.writerow(["0001", "6.5", "3.3", 'steel, painted; "new"'])
    row = validate(output.getvalue().encode("utf-8-sig"))[0]
    assert row.valid and row.attributes["external_id"] == "0001"
    assert row.attributes["material"] == 'steel, painted; "new"'
    assert row.geometry.coordinates == (3.3, 6.5)


def test_csv_partial_success_duplicates_malformed_rows_and_private_errors() -> None:
    rows = validate(
        b"id,lat,lon,capacity_kva\n001,6.5,3.3,50\n002,6.5,3.3,-5\n003,6.5,3.3,50,extra\n001,6.5,3.4,50\n"
    )
    assert not any(row.valid for row in rows)
    assert any(e.code == "DUPLICATE_ID" for e in rows[0].errors)
    assert any(e.code == "INVALID_NUMBER" for e in rows[1].errors)
    assert any(e.code == "COLUMN_COUNT_MISMATCH" for e in rows[2].errors)
    assert all("3.3" not in e.reason and "-5" not in e.reason for row in rows for e in row.errors)
    assert [r.valid for r in validate(b"id,lat,lon\na,6.5,3.3\nb,bad,3.3\nc,6.5,3.4\n")] == [
        True,
        False,
        True,
    ]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2020-12-31", "2020-12-31"),
        ("2020/12/31", "2020-12-31"),
        ("31/12/2020", "2020-12-31"),
        ("12/31/2020", "2020-12-31"),
        ("31 Dec 2020", "2020-12-31"),
    ],
)
def test_common_dates(value: str, expected: str) -> None:
    assert parse_date(value, "auto").isoformat() == expected


def test_dates_ambiguous_invalid_and_order() -> None:
    rows = validate(
        b"id,lat,lon,install_date,last_maintenance_date\na,6.5,3.3,03/04/2020,2021-01-01\n"
    )
    assert rows[0].errors[0].code == "AMBIGUOUS_DATE"
    assert (
        validate(b"id,lat,lon,install_date\na,6.5,3.3,03/04/2020\n", date_format="day_first")[
            0
        ].attributes["install_date"]
        == "2020-04-03"
    )
    for value in ("2020-02-30", "31/02/2020", "not-a-date"):
        with pytest.raises(ValueError):
            parse_date(value, "auto")
    assert any(
        e.code == "DATE_ORDER"
        for e in validate(
            b"id,lat,lon,install_date,last_maintenance_date\na,6.5,3.3,2020-01-01,2019-01-01\n"
        )[0].errors
    )


def test_mapping_ambiguity_override_and_unknown_references() -> None:
    columns = ("id", "lat", "latitude", "X", "feeder")
    assert "latitude" not in suggest_mapping(columns)
    assert column_mapping(columns, {"latitude": "lat"})["latitude"] == "lat"
    with pytest.raises(ParseFailure, match="INVALID_COLUMN_MAPPING"):
        column_mapping(columns, {"latitude": "missing"})
    with pytest.raises(ParseFailure, match="DUPLICATE_COLUMN_MAPPING"):
        column_mapping(columns, {"latitude": "X"})
    parsed = parse_upload(b"id,lat,lon,pole_id,feeder_id\na,6.5,3.3,P-1,F-1\n", "x.csv", LIMITS)
    row = validate_upload(parsed, "transformer", ValidateImport())[0]
    assert row.valid and len(row.warnings) == 2
    assert row.attributes["external_pole_id"] == "P-1"
    assert not validate_upload(
        parsed,
        "transformer",
        ValidateImport(),
        known_poles=frozenset({"P-1"}),
        known_feeders=frozenset({"F-1"}),
    )[0].warnings


@pytest.mark.parametrize(
    "latitude,longitude", [("0", "0"), ("91", "3"), ("6", "181"), ("nan", "3"), ("inf", "3")]
)
def test_coordinate_ranges(latitude: str, longitude: str) -> None:
    assert not validate(f"id,lat,lon\na,{latitude},{longitude}\n".encode())[0].valid


def test_wkt_and_json_records() -> None:
    assert validate(b'id,wkt\na,"POINT (3.3 6.5)"\n')[0].valid
    row = validate(
        json.dumps([{"external_id": "0001", "lat": 6.5, "lon": 3.3}]).encode(), "x.json"
    )[0]
    assert row.valid and row.attributes["external_id"] == "0001"


def test_geojson_geometry_types_invalid_empty_and_z() -> None:
    def document(geometry):
        return json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"external_id": "a"}, "geometry": geometry}
                ],
            }
        ).encode()

    row = validate(document({"type": "Point", "coordinates": [3.3, 6.5, 10]}), "x.geojson")[0]
    assert row.valid and row.geometry.coordinates == (3.3, 6.5)
    assert row.warnings[0].code == "Z_DROPPED"
    for geometry in (
        None,
        {"type": "Point", "coordinates": []},
        {"type": "LineString", "coordinates": [[3.3, 6.5], [3.4, 6.5]]},
    ):
        assert not validate(document(geometry), "x.geojson")[0].valid
    parsed = parse_upload(
        document({"type": "LineString", "coordinates": [[3.3, 6.5], [3.3, 6.5]]}),
        "x.geojson",
        LIMITS,
    )
    assert not validate_upload(parsed, "feeder_line", ValidateImport())[0].valid


def test_projected_shapefile_reprojection_null_shape_and_multipart() -> None:
    prj = CRS.from_epsg(32631).to_wkt().encode()
    parsed = parse_upload(packed(shape_members(prj=prj, null=True)), "synthetic.zip", LIMITS)
    rows = validate_upload(parsed, "pole", ValidateImport())
    assert parsed.crs_detected == "EPSG:32631"
    assert rows[0].valid and rows[0].geometry.coordinates == pytest.approx((3, 0), abs=1e-8)
    assert not rows[1].valid and rows[1].errors[0].code == "NULL_GEOMETRY"
    parsed = parse_upload(packed(shape_members(prj=prj, lines=True)), "synthetic.zip", LIMITS)
    row = validate_upload(parsed, "feeder_line", ValidateImport())[0]
    assert (
        row.valid and row.geometry.type == "MultiLineString" and len(row.geometry.coordinates) == 2
    )


@pytest.mark.parametrize("prj", [None, b"broken private CRS text"])
def test_missing_or_unparseable_prj_requires_choice(prj: bytes | None) -> None:
    parsed = parse_upload(packed(shape_members(prj=prj)), "synthetic.zip", LIMITS)
    assert parsed.crs_detected is None and "CRS_REQUIRED" in parsed.warnings
    assert validate_upload(parsed, "pole", ValidateImport())[0].errors[0].code == "CRS_REQUIRED"
    assert validate_upload(parsed, "pole", ValidateImport(source_crs="EPSG:32631"))[0].valid


@pytest.mark.parametrize(
    "encoding,cpg", [("utf-8", b"1252"), ("cp1252", b"1252"), ("latin-1", b"invalid-codec")]
)
def test_dbf_encoding_order(encoding: str, cpg: bytes) -> None:
    parsed = parse_upload(
        packed(shape_members(encoding=encoding, cpg=cpg)), "synthetic.zip", LIMITS
    )
    assert parsed.rows[0].properties["material"] == "pôle"
    assert ("DBF_ENCODING_FALLBACK" in parsed.warnings) == (encoding != "utf-8")


@pytest.mark.parametrize(
    "name", ["../network.shp", "/network.shp", "C:/network.shp", "a\\network.shp"]
)
def test_zip_slip(name: str) -> None:
    # ZipInfo on Windows normalises backslashes while writing; exercise raw archive names.
    data = packed({name: b"synthetic"})
    if "\\" in name:
        data = data.replace(name.replace("\\", "/").encode(), name.encode())
    with pytest.raises(ParseFailure, match="UNSAFE_ZIP"):
        shapefile_members(data, LIMITS)


def test_zip_symlink_bombs_missing_components_and_multiple_layers() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        info = zipfile.ZipInfo("network.shp")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "outside")
    with pytest.raises(ParseFailure, match="UNSAFE_ZIP"):
        shapefile_members(output.getvalue(), LIMITS)
    for data, limits, code in (
        (packed({"bomb.txt": b"0" * 10000}, compressed=True), LIMITS, "ZIP_RATIO_LIMIT"),
        (packed({"file.txt": b"123"}), replace(LIMITS, max_expanded_bytes=2), "ZIP_EXPANDED_LIMIT"),
        (
            packed({"a.txt": b"", "b.txt": b""}),
            replace(LIMITS, max_zip_files=1),
            "ZIP_TOO_MANY_FILES",
        ),
        (packed({"network.shp": b""}), LIMITS, "SHAPEFILE_COMPONENTS_REQUIRED"),
        (packed({**shape_members(), **{"second.shp": b""}}), LIMITS, "MULTIPLE_SHAPEFILE_LAYERS"),
    ):
        with pytest.raises(ParseFailure, match=code):
            shapefile_members(data, limits)


def test_declared_shapefile_sizes_cannot_allocate_unbounded_records() -> None:
    members = shape_members()
    malicious = bytearray(members["network.dbf"])
    struct.pack_into("<I", malicious, 4, 2**31)
    members["network.dbf"] = bytes(malicious)
    with pytest.raises(ParseFailure, match="FEATURE_LIMIT"):
        parse_upload(packed(members), "synthetic.zip", LIMITS)


@pytest.mark.parametrize(
    "data,filename,code",
    [
        (b"{}", "x.csv", "FORMAT_MISMATCH"),
        (b"bad", "x.zip", "FORMAT_MISMATCH"),
        (b"{bad}", "x.json", "INVALID_JSON"),
        (b"[]", "x.json", "EMPTY_FILE"),
        (b'{"type":"FeatureCollection","features":[],"x":NaN}', "x.json", "NONFINITE_JSON"),
        (b'{"x":1,"x":2}', "x.json", "DUPLICATE_JSON_PROPERTY"),
        (b"id,id\na,b\n", "x.csv", "INVALID_CSV_HEADER"),
    ],
)
def test_detection_and_safe_errors(data: bytes, filename: str, code: str) -> None:
    with pytest.raises(ParseFailure, match=f"^{code}$"):
        parse_upload(data, filename, LIMITS)


def test_upload_feature_limits_across_formats() -> None:
    with pytest.raises(ParseFailure, match="UPLOAD_TOO_LARGE"):
        parse_upload(b"id,lat,lon\na,6,3\n", "x.csv", replace(LIMITS, max_bytes=4))
    with pytest.raises(ParseFailure, match="FEATURE_LIMIT"):
        parse_upload(b"id,lat,lon\na,6,3\nb,6,4\n", "x.csv", replace(LIMITS, max_features=1))
    with pytest.raises(ParseFailure, match="FEATURE_LIMIT"):
        parse_upload(b"[{},{}]", "x.json", replace(LIMITS, max_features=1))
    with pytest.raises(ParseFailure, match="FEATURE_LIMIT"):
        parse_upload(packed(shape_members(null=True)), "x.zip", replace(LIMITS, max_features=1))


@pytest.mark.parametrize(
    "field,value",
    [
        ("load_factor", "0"),
        ("load_factor", "1.51"),
        ("capacity_kva", "0"),
        ("capacity_kva", "1000000"),
        ("vegetation_index", "1.1"),
    ],
)
def test_numeric_limits(field: str, value: str) -> None:
    row = validate(f"id,lat,lon,{field}\na,6.5,3.3,{value}\n".encode())[0]
    assert not row.valid and any(e.code == "INVALID_NUMBER" for e in row.errors)


def test_json_nonfinite_overflow_and_invalid_text_stay_safe() -> None:
    with pytest.raises(ParseFailure, match="NONFINITE_JSON"):
        parse_upload(b'[{"id":"a","x":1e999}]', "x.json", LIMITS)
    data = json.dumps(
        [
            {"id": "a", "lat": 6.5, "lon": 3.3, "capacity_kva": 10**1000},
            {"id": "b", "lat": 6.5, "lon": 3.3, "extra": "bad\x00text"},
            {"id": "c", "lat": 6.5, "lon": 3.3},
        ]
    ).encode()
    rows = validate(data, "x.json")
    assert [r.valid for r in rows] == [False, False, True]
    assert rows[1].errors[0].code == "INVALID_TEXT"
    parsed = parse_upload(data, "x.json", LIMITS)
    assert "\x00" not in json.dumps(parsed.rows[1].properties, ensure_ascii=False)


def test_safe_crs_inputs_unknown_declared_crs_and_date_time() -> None:
    for crs in ("https://example.invalid/private.prj", "/private/file.prj", "EPSG:999999"):
        row = validate(b"id,x,y\na,3.3,6.5\n", source_crs=crs)[0]
        assert not row.valid and any(e.code == "INVALID_CRS" for e in row.errors)
    doc = {
        "type": "FeatureCollection",
        "crs": {"properties": {"name": "unknown"}},
        "features": [
            {
                "type": "Feature",
                "id": "a",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": [3.3, 6.5]},
            }
        ],
    }
    data = json.dumps(doc).encode()
    assert validate(data, "x.geojson")[0].errors[0].code == "CRS_REQUIRED"
    assert validate(data, "x.geojson", source_crs="EPSG:4326")[0].valid
    assert parse_date("2020-01-01T12:30:00Z", "auto").isoformat() == "2020-01-01"


def test_native_parser_warnings_are_not_emitted(monkeypatch: pytest.MonkeyPatch) -> None:
    original = shapefile.Reader.iterShapeRecords

    def noisy(self, *args, **kwargs):
        warnings.warn("synthetic-private-row-content", UserWarning, stacklevel=2)
        yield from original(self, *args, **kwargs)

    monkeypatch.setattr(shapefile.Reader, "iterShapeRecords", noisy)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        parse_upload(packed(shape_members()), "x.zip", LIMITS)
    assert not captured


def test_dbf_control_text_is_row_local_and_safe_for_staging() -> None:
    members = shape_members(prj=CRS.from_epsg(32631).to_wkt().encode())
    members["network.dbf"] = members["network.dbf"].replace("pôle".encode(), b"p\x00le ")
    parsed = parse_upload(packed(members), "x.zip", LIMITS)
    assert parsed.rows[0].errors == ("INVALID_TEXT",)
    assert "\x00" not in str(parsed.rows[0].properties)
    assert not validate_upload(parsed, "pole", ValidateImport())[0].valid


def test_optional_whitespace_fields_stay_missing() -> None:
    row = validate(b"id,lat,lon,capacity_kva,install_date,material\na,6.5,3.3,  ,  ,  \n")[0]
    assert row.valid and row.attributes == {"external_id": "a"}
