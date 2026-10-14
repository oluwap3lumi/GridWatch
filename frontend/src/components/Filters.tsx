import type { FilterState } from './risk';
import { bands } from './risk';

export function Filters({ value, onChange, topTen, onTopTen, reset, hotspots, onHotspots }: {
  value: FilterState; onChange: (value: FilterState) => void; topTen: boolean; onTopTen: () => void;
  reset: () => void; hotspots: boolean; onHotspots: (value: boolean) => void;
}) {
  return <section className="filters" aria-label="Asset filters">
    <label>Asset type<select value={value.type} onChange={(e) => onChange({ ...value, type: e.target.value as FilterState['type'] })}>
      <option value="all">All assets</option><option value="transformer">Transformers</option><option value="feeder">Feeders</option><option value="pole">Poles</option>
    </select></label>
    <label>Risk band<select value={value.band} onChange={(e) => onChange({ ...value, band: e.target.value as FilterState['band'] })}>
      <option value="all">All bands</option>{bands.map((band) => <option key={band} value={band}>{band[0].toUpperCase() + band.slice(1)}</option>)}<option value="unscored">Unscored</option>
    </select></label>
    <label className="threshold">Minimum risk <strong>{value.minimum}%</strong><input aria-label="Minimum risk" type="range" min="0" max="100" step="1" value={value.minimum} onChange={(e) => onChange({ ...value, minimum: Number(e.target.value) })} /></label>
    <button className={`primary ${topTen ? 'active' : ''}`} aria-pressed={topTen} onClick={onTopTen}>Top 10 transformers <span aria-hidden="true">↗</span></button>
    <button className="text-button" onClick={reset}>Reset filters</button>
    <label className="toggle"><input type="checkbox" checked={hotspots} onChange={(e) => onHotspots(e.target.checked)} />Hotspots</label>
  </section>;
}
