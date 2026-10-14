import type { AssetFeature, AssetKind, RiskBand } from '../api/generated';

export const riskColors = { low: '#2d9b79', medium: '#d8ae38', high: '#ef8848', critical: '#de526b', unscored: '#82949d' };
export const bands = ['low', 'medium', 'high', 'critical'] as const;
export const percent = (score: number) => `${(score * 100).toFixed(1)}%`;
export const date = (value: string) => new Date(value).toLocaleDateString('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric' });
export interface FilterState { type: AssetKind | 'all'; band: RiskBand | 'all' | 'unscored'; minimum: number }
export const defaultFilters: FilterState = { type: 'all', band: 'all', minimum: 0 };
export function rankedAssets(assets: AssetFeature[], filters: FilterState, topTen: boolean): AssetFeature[] {
  const filtered = assets.filter(({ properties: p }) => {
    if (topTen) return p.type === 'transformer' && p.risk !== null;
    return (filters.type === 'all' || p.type === filters.type)
      && (filters.band === 'all' || (p.risk?.band ?? 'unscored') === filters.band)
      && (filters.minimum === 0 || (p.risk !== null && p.risk.score >= filters.minimum / 100));
  }).sort((a, b) => (b.properties.risk?.score ?? -1) - (a.properties.risk?.score ?? -1) || a.id - b.id);
  return topTen ? filtered.slice(0, 10) : filtered;
}

export function RiskBadge({ asset }: { asset: AssetFeature }) {
  const risk = asset.properties.risk;
  return <span className={`risk-badge ${risk?.band ?? 'unscored'}`}>{risk ? `${risk.band} · ${percent(risk.score)}` : 'Unscored'}</span>;
}
