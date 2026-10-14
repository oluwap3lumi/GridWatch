import type { FleetSnapshot } from '../api/client';
export function SummaryCards({ fleet }: { fleet: FleetSnapshot }) {
  const summary = fleet.summary;
  const elevated = summary.counts_by_band.high + summary.counts_by_band.critical;
  return <section className="summary-grid" aria-label="Fleet summary">
    <article><span>Network assets</span><strong>{summary.total_assets.toLocaleString()}</strong><small>{summary.by_feeder.length} feeders · {summary.unscored_assets} unscored</small></article>
    <article><span>Elevated risk</span><strong>{elevated.toLocaleString()}<em className="high">High + critical</em></strong><small>{summary.scored_assets ? `${(elevated / summary.scored_assets * 100).toFixed(1)}% of scored assets` : 'No scores available'}</small></article>
    <article><span>Critical assets</span><strong className="critical-number">{summary.counts_by_band.critical.toLocaleString()}</strong><small>30-day probability ≥10%</small></article>
    <article><span>Risk hotspots</span><strong>{fleet.hotspots.length}<em>500 m links</em></strong><small>Connected groups of 3+ elevated-risk assets</small></article>
  </section>;
}
