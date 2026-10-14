import { bands, riskColors } from './risk';
const thresholds = { low: '<5%', medium: '5–<8%', high: '8–<10%', critical: '≥10%' };
export function RiskLegend() {
  return <div className="legend" aria-label="Risk legend">
    <span className="legend-title">30-day risk</span>{bands.map((band) => <span key={band}><i style={{ background: riskColors[band] }} />{band} <small>{thresholds[band]}</small></span>)}
    <span><i style={{ background: riskColors.unscored }} />unscored</span>
  </div>;
}
