import { useMemo, useState } from 'react';
import { Map } from '../components/Map';
import { useFleet } from '../api/hooks';
import { Filters } from '../components/Filters';
import { RiskLegend } from '../components/RiskLegend';
import { SummaryCards } from '../components/SummaryCards';
import { date, defaultFilters, rankedAssets, RiskBadge } from '../components/risk';
import type { FilterState } from '../components/risk';
export function Dashboard() {
  const fleet = useFleet();
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [topTen, setTopTen] = useState(false);
  const [showHotspots, setShowHotspots] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState(20);
  const assets = useMemo(() => rankedAssets(fleet.data?.assets ?? [], filters, topTen), [fleet.data, filters, topTen]);
  const selected = assets.find((asset) => asset.id === selectedId) ?? null;
  function changeFilters(value: FilterState) { setFilters(value); setTopTen(false); setSelectedId(null); setVisibleCount(20); }
  return <main>
    <header><div className="brand"><span className="brand-mark" aria-hidden="true">G</span>GridWatch<span className="brand-divider" /><small>Network intelligence</small></div><span className="badge"><span className="live-dot" />Synthetic demo</span></header>
    <div className="intro"><div><p className="eyebrow">Electricity distribution / Risk explorer</p><h1>A clearer view of infrastructure risk.</h1><p>Find the assets that need a closer look. Explore 30-day failure probabilities across the synthetic network.</p></div><button className="secondary" disabled={fleet.isFetching} onClick={() => void fleet.refetch()}>{fleet.isFetching ? 'Loading network…' : 'Refresh network'}</button></div>
    {fleet.isPending && <div className="state-card" role="status">Loading the complete network…</div>}
    {fleet.isError && <div className="state-card error" role="alert"><strong>Network could not refresh</strong><p>{fleet.error.message}</p><button onClick={() => void fleet.refetch()}>Retry network</button>{fleet.data && <p>The previous snapshot remains visible below.</p>}</div>}
    {fleet.data && <>
      <SummaryCards fleet={fleet.data} />
      <div className="snapshot-note">{fleet.data.summary.scoring ? <>Prediction cutoff <strong>{fleet.data.summary.scoring.prediction_cutoff ? date(fleet.data.summary.scoring.prediction_cutoff) : 'Unknown'} UTC</strong> · 30-day horizon · Scored {date(fleet.data.summary.scoring.scored_at)} UTC</> : 'Assets have not been scored. Train and rescore through the API to explore risk.'}<span>Demo thresholds · No operational guidance</span></div>
      <Filters value={filters} onChange={changeFilters} topTen={topTen} onTopTen={() => { setFilters({ ...defaultFilters, type: 'transformer' }); setTopTen(true); setSelectedId(null); }} reset={() => changeFilters(defaultFilters)} hotspots={showHotspots} onHotspots={setShowHotspots} />
      <div className="workspace"><div className="map-column"><Map assets={assets} hotspots={showHotspots ? fleet.data.hotspots : []} selected={selected} onSelect={setSelectedId} /><RiskLegend /><p className="map-help">Points: transformers & poles · Lines: feeders · Halos: connected hotspot centres, not distance boundaries. Hotspots describe the whole fleet.</p></div>
        <section className="asset-list" aria-label="Ranked assets"><div className="list-heading"><p className="eyebrow">Priority queue</p><h2>{topTen ? 'Top 10 transformers' : 'Assets by risk'}</h2><p>{assets.length.toLocaleString()} {topTen ? 'scored transformers' : 'matching assets'} · Highest risk first</p></div>
          {!assets.length && <div className="empty-state"><strong>{topTen ? 'No scored transformers' : 'No matching assets'}</strong><p>{topTen ? 'This network needs scores before it can be ranked.' : 'Try another band or lower the risk threshold.'}</p><button onClick={() => changeFilters(defaultFilters)}>Reset filters</button></div>}
          <ol>{assets.slice(0, visibleCount).map((asset, index) => <li key={asset.id}><button className={`asset-row ${selectedId === asset.id ? 'selected' : ''}`} aria-pressed={selectedId === asset.id} onClick={() => setSelectedId(asset.id)}><span className="rank">{String(index + 1).padStart(2, '0')}</span><span><strong>{asset.properties.type} #{asset.id}</strong><small>{asset.properties.feeder_id ? `Feeder #${asset.properties.feeder_id}` : 'Feeder asset'}</small></span><RiskBadge asset={asset} /></button></li>)}</ol>
          {assets.length > visibleCount && <button className="load-more" onClick={() => setVisibleCount((value) => value + 20)}>Show 20 more</button>}
          {selected && <div className="selection-preview" role="status">Selected {selected.properties.type} #{selected.id}. Asset explanations arrive in the next M4 slice.</div>}
        </section>
      </div>
      {!fleet.data.assets.length && <p role="status">No network assets yet. Run make seed to load the synthetic corpus.</p>}
    </>}
    <footer><span>GRIDWATCH / Synthetic or public data only</span><span>Historical demo · Lagos area</span></footer>
  </main>;
}
