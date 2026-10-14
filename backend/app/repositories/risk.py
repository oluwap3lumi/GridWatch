"""Transactional scoring persistence and geography-based risk queries."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Engine, delete, insert, select, text
from sqlalchemy.orm import Session

from app.core.errors import ScoringConflict
from app.db.models import RiskScore
from app.repositories.assets import page_metadata
from app.repositories.model_runs import latest_passing_run
from app.repositories.seed import data_fingerprint
from app.schemas.risk import (
    BandCounts,
    FeederSummary,
    HotspotCollection,
    HotspotFeature,
    HotspotProperties,
    RiskSummary,
    ScoringStamp,
)
from app.schemas.spatial import BoundingBox, PointGeometry
from app.services.risk_policy import connected_groups, risk_band

if TYPE_CHECKING:
    from ml.predict import AssetPrediction

SCORING_LOCK = 5139241308840342596
CORPUS_LOCK = 5139241308840342595


@contextmanager
def scoring_lock(engine: Engine) -> Iterator[None]:
    """A dedicated connection holds a session advisory lock across read/compute/write."""
    with engine.connect() as connection:
        acquired = bool(
            connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": SCORING_LOCK})
        )
        connection.commit()
        if not acquired:
            raise ScoringConflict("Another rescore is running; retry after it completes")
        try:
            yield
        finally:
            try:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SCORING_LOCK})
                connection.commit()
            except Exception:
                # Do not return a connection with a held session lock to the pool.
                connection.invalidate()
                raise


def replace_scores(
    session: Session,
    *,
    predictions: tuple["AssetPrediction", ...],
    version: str,
    data_hash: str,
    cutoff: datetime,
    scored_at: datetime,
) -> None:
    if not session.in_transaction():
        raise ValueError("Score persistence requires an explicit transaction")
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CORPUS_LOCK})
    if data_fingerprint(session) != data_hash:
        raise ScoringConflict(
            "Source data changed while scoring; retry with a matching trained model"
        )
    latest = latest_passing_run(session)
    if latest is None or latest.model_version != version:
        raise ScoringConflict("A newer passing model became available while scoring; retry")
    rows: list[dict[str, object]] = []
    for prediction in predictions:
        rows.append(
            {
                "asset_id": prediction.asset_id,
                "score": prediction.score,
                "band": risk_band(prediction.score).value,
                "model_version": version,
                "scored_at": scored_at,
                "prediction_cutoff": cutoff,
                "top_factors": [
                    {
                        "feature": factor.feature,
                        "feature_value": factor.feature_value,
                        "contribution": factor.contribution,
                        "contribution_unit": "log_odds",
                    }
                    for factor in prediction.factors
                ],
            }
        )
    session.execute(delete(RiskScore))
    for offset in range(0, len(rows), 1000):
        session.execute(insert(RiskScore), rows[offset : offset + 1000])


def scoring_stamp(session: Session) -> ScoringStamp | None:
    stamps = session.execute(
        select(RiskScore.model_version, RiskScore.scored_at, RiskScore.prediction_cutoff).distinct()
    ).all()
    if not stamps:
        return None
    if len(stamps) != 1:
        raise ScoringConflict(
            "Risk scores contain mixed batches; run rescore to restore a consistent batch"
        )
    return ScoringStamp.model_validate(stamps[0]._mapping)


def risk_summary(session: Session) -> RiskSummary:
    records = session.execute(
        text(
            "SELECT coalesce(a.feeder_id,a.id) AS feeder_id,count(*) AS total_assets,"
            "count(r.asset_id) AS scored_assets,"
            "count(*) FILTER (WHERE r.band='low') AS low,"
            "count(*) FILTER (WHERE r.band='medium') AS medium,"
            "count(*) FILTER (WHERE r.band='high') AS high,"
            "count(*) FILTER (WHERE r.band='critical') AS critical "
            "FROM assets a LEFT JOIN risk_scores r ON r.asset_id=a.id "
            "GROUP BY coalesce(a.feeder_id,a.id) ORDER BY feeder_id"
        )
    )
    feeders = [
        FeederSummary(
            feeder_id=int(row.feeder_id),
            total_assets=int(row.total_assets),
            scored_assets=int(row.scored_assets),
            unscored_assets=int(row.total_assets - row.scored_assets),
            counts_by_band=BandCounts(
                low=row.low, medium=row.medium, high=row.high, critical=row.critical
            ),
        )
        for row in records
    ]
    total = sum(feeder.total_assets for feeder in feeders)
    scored = sum(feeder.scored_assets for feeder in feeders)
    return RiskSummary(
        total_assets=total,
        scored_assets=scored,
        unscored_assets=total - scored,
        by_feeder=feeders,
        counts_by_band=BandCounts(
            low=sum(feeder.counts_by_band.low for feeder in feeders),
            medium=sum(feeder.counts_by_band.medium for feeder in feeders),
            high=sum(feeder.counts_by_band.high for feeder in feeders),
            critical=sum(feeder.counts_by_band.critical for feeder in feeders),
        ),
        scoring=scoring_stamp(session),
    )


def hotspots(
    session: Session,
    *,
    limit: int,
    offset: int,
    bbox: BoundingBox | None = None,
) -> HotspotCollection:
    # Feeders use the same line midpoint as feature engineering, not the whole line extent.
    cte = (
        "WITH high_assets AS (SELECT a.id,r.score,r.band,"
        "CASE WHEN a.type='feeder' THEN ST_LineInterpolatePoint(a.geom,0.5) "
        "ELSE a.geom END AS point FROM assets a JOIN risk_scores r ON r.asset_id=a.id "
        "WHERE r.band IN ('high','critical')"
    )
    params: dict[str, object] = {}
    if bbox is not None:
        cte += " AND ST_Intersects(a.geom,ST_MakeEnvelope(:west,:south,:east,:north,4326))"
        params.update(bbox.model_dump())
    cte += ") "
    ids = list(session.scalars(text(cte + "SELECT id FROM high_assets ORDER BY id"), params))
    edges = [
        (int(row[0]), int(row[1]))
        for row in session.execute(
            text(
                cte + "SELECT a.id,b.id FROM high_assets a JOIN high_assets b ON a.id<b.id "
                "AND ST_DWithin(a.point::geography,b.point::geography,500)"
            ),
            params,
        )
    ]
    groups = connected_groups(ids, edges)
    page = groups[offset : offset + limit]
    if not page:
        return HotspotCollection(features=[], pagination=page_metadata(len(groups), limit, offset))
    params["asset_ids"] = [asset_id for group in page for asset_id in group]
    params["cluster_ids"] = [group[0] for group in page for _ in group]
    records = session.execute(
        text(
            cte + "SELECT m.cluster_id, count(*) AS asset_count,"
            "array_agg(h.id ORDER BY h.id) AS asset_ids,avg(h.score) AS mean_score,"
            "max(h.score) AS max_score,"
            "count(*) FILTER (WHERE h.band='high') AS high,"
            "count(*) FILTER (WHERE h.band='critical') AS critical,"
            "ST_AsGeoJSON(ST_Centroid(ST_Collect(h.point)::geography)::geometry) AS geometry "
            "FROM high_assets h JOIN unnest(CAST(:asset_ids AS bigint[]),"
            "CAST(:cluster_ids AS bigint[])) AS m(asset_id,cluster_id) ON m.asset_id=h.id "
            "GROUP BY m.cluster_id ORDER BY m.cluster_id"
        ),
        params,
    )
    features = [
        HotspotFeature(
            id=row.cluster_id,
            geometry=PointGeometry.model_validate_json(row.geometry),
            properties=HotspotProperties(
                asset_count=row.asset_count,
                asset_ids=row.asset_ids,
                mean_score=row.mean_score,
                max_score=row.max_score,
                counts_by_band=BandCounts(high=row.high, critical=row.critical),
            ),
        )
        for row in records
    ]
    return HotspotCollection(
        features=features, pagination=page_metadata(len(groups), limit, offset)
    )
