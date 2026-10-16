"""One representative point policy shared by features and hotspot calculations."""

# The alias is fixed in repository SQL. Existing LineString midpoints are unchanged.
ASSET_POINT = (
    "CASE WHEN GeometryType(a.geom)='LINESTRING' THEN ST_LineInterpolatePoint(a.geom,0.5) "
    "WHEN GeometryType(a.geom)='MULTILINESTRING' THEN ST_PointOnSurface(a.geom) ELSE a.geom END"
)
