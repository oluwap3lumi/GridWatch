import { useEffect, useRef, useState } from 'react';
import type { AssetFeature, RiskFactor, ScoringStamp } from '../api/generated';
import { useAssetDetail } from '../api/hooks';
import { SnapshotChangedError } from '../api/client';
import { date, percent, RiskBadge } from './risk';

const featureLabels: Record<string, string> = {
  asset_age_years: 'Asset age (years)', load_stress: 'Load above 75% (fraction)', vegetation_index: 'Vegetation index',
  capacity_log_kva: 'Log capacity (ln[1 + kVA])', is_feeder: 'Feeder indicator', is_transformer: 'Transformer indicator', is_pole: 'Pole indicator',
  outage_count_365d: 'Outages in prior 365 days', rainfall_mean_30d: 'Mean rainfall, 30 days (mm)', rainfall_max_30d: 'Peak rainfall, 30 days (mm)',
  wind_mean_30d: 'Mean wind, 30 days (km/h)', wind_max_30d: 'Peak wind, 30 days (km/h)', lightning_mean_30d: 'Mean lightning density, 30 days',
  weather_days_30d: 'Weather coverage (days)', nearest_prior_outage_m: 'Nearest prior outage (m)', prior_outage_available: 'Prior outage available',
};
function Factor({ factor, maximum }: { factor: RiskFactor; maximum: number }) {
  const positive = factor.contribution > 0;
  return <li className="factor"><div><strong>{featureLabels[factor.feature] ?? factor.feature.replaceAll('_', ' ')}</strong><span className={positive ? 'factor-positive' : 'factor-negative'}>{factor.contribution > 0 ? '+' : ''}{factor.contribution.toFixed(3)}</span></div>
    <small>Feature value: {Number(factor.feature_value.toFixed(3)).toLocaleString('en-GB')} · {positive ? 'Raises' : factor.contribution < 0 ? 'Lowers' : 'Neutral for'} model risk</small>
    <div className="factor-track" aria-hidden="true"><i className={positive ? 'positive' : 'negative'} style={{ width: `${maximum ? Math.abs(factor.contribution) / maximum * 50 : 0}%` }} /></div>
  </li>;
}

export function AssetPanel({ asset, stamp, close, refresh }: { asset: AssetFeature; stamp: ScoringStamp | null; close: () => void; refresh: () => void }) {
  const [offset, setOffset] = useState(0);
  const detail = useAssetDetail(asset.id, offset, stamp);
  const heading = useRef<HTMLHeadingElement>(null);
  const p = asset.properties;
  const factors = [...(p.risk?.top_factors ?? [])].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  const maximum = Math.max(0, ...factors.map((factor) => Math.abs(factor.contribution)));
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView?.({ block: window.matchMedia?.('(max-width: 1000px)').matches ? 'start' : 'nearest' });
  }, []);
  return <section className="asset-panel" aria-label={`Asset detail ${asset.id}`}>
    <div className="panel-heading"><div><p className="eyebrow">Asset insight</p><h2 ref={heading} tabIndex={-1}>{p.type} #{asset.id}</h2></div><button aria-label="Close asset detail" onClick={close}>×</button></div>
    <div className="panel-body">
      <div className="asset-risk"><strong>{p.risk ? percent(p.risk.score) : '—'}</strong><div><RiskBadge asset={asset} /><small>Predicted failure in 30 days</small></div></div>
      <p className="detail-caption">Historical synthetic forecast · Cutoff {p.risk?.prediction_cutoff ? `${date(p.risk.prediction_cutoff)} UTC` : 'unavailable'}</p>
      {p.risk?.warnings.includes('SYNTHETIC_HISTORY') && <p className="detail-caption" role="note">Demo estimate using synthetic weather and outage history. This model has not been validated for uploaded assets.</p>}
      {!!p.risk?.imputed_fields.length && <p className="detail-caption">Training medians used for scoring: {p.risk.imputed_fields.map((field) => `${field.replaceAll('_', ' ')}: ${p.risk?.imputed_values[field] ?? 'median'}`).join(', ')}.</p>}
      {p.risk?.warnings.includes('OUTSIDE_TRAINING_EXTENT') && <p className="detail-caption">This asset is outside the training network extent.</p>}
      <div className="section-heading"><h3>Why this score?</h3><span>TreeSHAP</span></div>
      <p className="detail-caption">Signed contributions to uncalibrated model log-odds. Positive raises risk; negative lowers it. These are associations, not probability changes or causes.</p>
      {factors.length ? <ul className="factors">{factors.map((factor) => <Factor key={factor.feature} factor={factor} maximum={maximum} />)}</ul> : <p className="empty-detail">{p.risk ? 'No explanation factors available.' : 'This asset has not been scored.'}</p>}
      <div className="section-heading"><h3>Outage history</h3>{detail.data && <span>{detail.data.outages.pagination.total} events</span>}</div>
      {detail.isPending && <p role="status" className="empty-detail">Loading outage history…</p>}
      {detail.isError && <div role="alert" className="detail-error"><p>{detail.error.message}</p>{detail.error instanceof SnapshotChangedError ? <button onClick={refresh}>Refresh network</button> : <button onClick={() => void detail.refetch()}>Retry history</button>}</div>}
      {detail.data && !detail.isError && <>
        {detail.data.outages.features.length ? <ul className="outages">{detail.data.outages.features.map((outage) => <li key={outage.id}><div><strong>{outage.properties.cause.replaceAll('_', ' ')}</strong><span>{outage.properties.duration_min.toLocaleString()} min</span></div><time dateTime={outage.properties.started_at}>{new Date(outage.properties.started_at).toLocaleString('en-GB', { timeZone: 'UTC' })} UTC</time></li>)}</ul> : <p className="empty-detail">No outage events recorded for this asset.</p>}
        {detail.data.outages.pagination.total > 10 && <nav className="history-pagination" aria-label="Outage history pagination"><button disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - 10))}>Newer</button><span>{offset + 1}–{offset + detail.data.outages.features.length} of {detail.data.outages.pagination.total}</span><button disabled={detail.data.outages.pagination.next_offset === null} onClick={() => setOffset(detail.data?.outages.pagination.next_offset ?? offset)}>Older</button></nav>}
      </>}
      <div className="section-heading"><h3>Asset attributes</h3></div>
      <dl className="asset-attributes"><div><dt>Feeder</dt><dd>{p.feeder_id ? `#${p.feeder_id}` : p.type === 'feeder' ? 'This asset' : 'Unassigned'}</dd></div><div><dt>Capacity</dt><dd>{p.capacity_kva === null ? 'Unknown' : `${p.capacity_kva.toLocaleString()} kVA`}</dd></div><div><dt>Load factor</dt><dd>{percent(p.load_factor)}</dd></div><div><dt>Vegetation</dt><dd>{p.vegetation_index?.toFixed(2) ?? 'Unknown'}</dd></div><div><dt>Installed</dt><dd>{date(p.install_date)}</dd></div><div><dt>Material</dt><dd>{p.material ?? 'Unknown'}</dd></div><div><dt>Last maintenance</dt><dd>{date(p.last_maintenance_date)}</dd></div></dl>
      {p.risk && <p className="model-stamp">Scored {date(p.risk.scored_at)} UTC<br />Model <code>{p.risk.model_version}</code></p>}
    </div>
  </section>;
}
