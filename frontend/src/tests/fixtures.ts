import type { AssetFeature, ModelInfo, ScoringStamp } from '../api/generated';
import type { FleetSnapshot } from '../api/client';
export const stamp: ScoringStamp = { model_version: 'synthetic-test', scored_at: '2026-10-14T10:00:00Z', prediction_cutoff: '2026-01-01T00:00:00Z', horizon_days: 30, provenance: null };
export const modelFixture: ModelInfo = { model_version: 'new-model', trained_at: '2026-01-01T00:00:00Z', scored_model_version: 'old-model', data_hash: 'a'.repeat(64), git_sha: 'b'.repeat(40), features: ['asset_age_years'], metrics: { quality_gate_passed: 1, pr_auc_lift: 0.01, baseline_pr_auc: 0.1, xgboost_pr_auc: 0.11, xgboost_rows: 100 }, feature_importance: [{ feature: 'asset_age_years', mean_absolute_contribution: 0.2 }], explanation_space: 'uncalibrated XGBoost log-odds', horizon_days: 30 };
export function fixtureAsset(id: number, score: number | null, kind: AssetFeature['properties']['type'] = 'transformer'): AssetFeature {
  return { type: 'Feature', id, geometry: { type: 'Point', coordinates: [3.4, 6.5] }, properties: {
    external_id: null, pole_id: null, batch_id: null, type: kind, feeder_id: 1, install_date: '2000-01-01', capacity_kva: 100, load_factor: 0.8,
    material: 'steel', vegetation_index: 0.5, last_maintenance_date: '2025-01-01', risk: score === null ? null : {
      ...stamp, imputed_fields: [], imputed_values: {}, warnings: [], score, band: score >= 0.1 ? 'critical' : score >= 0.08 ? 'high' : score >= 0.05 ? 'medium' : 'low',
      top_factors: [{ feature: 'load_stress', feature_value: 0.05, contribution: 0.4, contribution_unit: 'log_odds' },
        { feature: 'asset_age_years', feature_value: 26, contribution: -0.2, contribution_unit: 'log_odds' }] } } };
}
export const fleetFixture: FleetSnapshot = {
  assets: [...Array.from({ length: 12 }, (_, index) => fixtureAsset(index + 2, 0.05 + index * 0.01)), fixtureAsset(90, 0.9, 'pole'), fixtureAsset(91, null)],
  hotspots: [{ type: 'Feature', id: 1, geometry: { type: 'Point', coordinates: [3.4, 6.5] }, properties: { asset_count: 3, asset_ids: [8, 9, 10], mean_score: 0.12, max_score: 0.13, counts_by_band: { low: 0, medium: 0, high: 0, critical: 3 } } }],
  summary: { total_assets: 14, scored_assets: 13, unscored_assets: 1, scoring: stamp, by_feeder: [], counts_by_band: { low: 0, medium: 3, high: 2, critical: 8 } },
};
