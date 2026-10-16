"""Offline CRS interpretation; never infer missing Shapefile CRS from coordinates."""

import re
import warnings

from pyproj import CRS, Transformer

# Public runtime API is omitted from pyproj 3.8's exported typing declarations.
from pyproj.network import set_network_enabled  # type: ignore[attr-defined]

from app.services.import_records import ParseFailure


def read_prj(value: str) -> str | None:
    if len(value) > 4096:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            crs = CRS.from_wkt(value)
        authority = crs.to_authority()
        return f"EPSG:{authority[1]}" if authority and authority[0] == "EPSG" else value
    except Exception:
        return None


def source_crs(value: str) -> CRS:
    """Accept EPSG identifiers or WKT, never file paths, URLs or PROJ pipelines."""
    if len(value) > 4096:
        raise ParseFailure("INVALID_CRS")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            crs = (
                CRS.from_epsg(int(value.split(":")[1]))
                if re.fullmatch(r"EPSG:\d{1,6}", value, re.IGNORECASE)
                else CRS.from_wkt(value)
            )
        if not (crs.is_projected or crs.is_geographic):
            raise ParseFailure("INVALID_CRS")
        return crs
    except Exception:
        raise ParseFailure("INVALID_CRS") from None


def transformer(value: str | None) -> Transformer:
    if not value:
        raise ParseFailure("CRS_REQUIRED")
    try:
        set_network_enabled(False)
        return Transformer.from_crs(
            source_crs(value), "EPSG:4326", always_xy=True, allow_ballpark=False, only_best=True
        )
    except ParseFailure:
        raise
    except Exception:
        raise ParseFailure("INVALID_CRS") from None
