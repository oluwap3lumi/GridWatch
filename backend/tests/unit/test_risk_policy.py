"""Probability boundaries and deterministic graph clustering for the approved demo policy."""

import pytest

from app.services.risk_policy import connected_groups, risk_band


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "low"),
        (0.049999, "low"),
        (0.05, "medium"),
        (0.079999, "medium"),
        (0.08, "high"),
        (0.099999, "high"),
        (0.10, "critical"),
        (1, "critical"),
    ],
)
def test_risk_band_boundaries(score: float, expected: str) -> None:
    assert risk_band(score).value == expected


@pytest.mark.parametrize("score", [-0.01, 1.01, float("nan"), float("inf")])
def test_nonprobabilities_are_rejected(score: float) -> None:
    with pytest.raises(ValueError):
        risk_band(score)


def test_connected_groups_are_transitive_stable_and_drop_small_groups() -> None:
    ids = [9, 8, 7, 6, 5, 4, 3, 2, 1]
    edges = [(3, 2), (1, 2), (4, 5), (7, 8), (9, 8)]
    assert connected_groups(ids, edges) == [(1, 2, 3), (7, 8, 9)]
    assert connected_groups(list(reversed(ids)), list(reversed(edges))) == [(1, 2, 3), (7, 8, 9)]
    with pytest.raises(ValueError, match="unknown"):
        connected_groups([1], [(1, 2)])
