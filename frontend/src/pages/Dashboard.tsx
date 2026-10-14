import { Map } from '../components/Map';

export function Dashboard() {
  return (
    <main>
      <header>
        <div className="brand"><span className="brand-mark" aria-hidden="true">G</span>GridWatch</div>
        <span className="badge">M0 · Foundations</span>
      </header>
      <div className="intro">
        <p className="eyebrow">Electricity distribution / Infrastructure intelligence</p>
        <h1>A clearer view of infrastructure risk.</h1>
        <p>The map foundation is ready. Synthetic assets and risk scores will follow in later milestones.</p>
      </div>
      <Map />
      <footer>Synthetic or public data only · Lagos map centre · No assets loaded</footer>
    </main>
  );
}
