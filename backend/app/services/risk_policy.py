"""Approved synthetic demo bands and pure connected-component clustering."""

import math

from app.schemas.assets import RiskBand


def risk_band(score: float) -> RiskBand:
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Risk score must be a finite probability")
    if score < 0.05:
        return RiskBand.low
    if score < 0.08:
        return RiskBand.medium
    if score < 0.10:
        return RiskBand.high
    return RiskBand.critical


def connected_groups(asset_ids: list[int], edges: list[tuple[int, int]]) -> list[tuple[int, ...]]:
    """Return deterministic components of at least three assets; edges come from PostGIS."""
    parents = {asset_id: asset_id for asset_id in asset_ids}

    def root(asset_id: int) -> int:
        while parents[asset_id] != asset_id:
            parents[asset_id] = parents[parents[asset_id]]
            asset_id = parents[asset_id]
        return asset_id

    for left, right in edges:
        if left not in parents or right not in parents:
            raise ValueError("Hotspot edge references an unknown asset")
        first, second = root(left), root(right)
        parents[max(first, second)] = min(first, second)
    groups: dict[int, list[int]] = {}
    for asset_id in sorted(parents):
        groups.setdefault(root(asset_id), []).append(asset_id)
    return sorted(tuple(members) for members in groups.values() if len(members) >= 3)
