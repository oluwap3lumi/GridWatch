import { Map } from '../components/Map';
import { useFleet } from '../api/hooks';

export function Dashboard() {
  const fleet = useFleet();
  return (
    <main>
      <header>
        <div className="brand"><span className="brand-mark" aria-hidden="true">G</span>GridWatch</div>
        <span className="badge">Synthetic demo</span>
      </header>
      <div className="intro">
        <p className="eyebrow">Electricity distribution / Infrastructure intelligence</p>
        <h1>A clearer view of infrastructure risk.</h1>
        <p>Explore electricity-distribution assets and their predicted 30-day failure risk.</p>
      </div>
      <Map />
      {fleet.isPending && <p role="status">Loading the complete network…</p>}
      {fleet.isError && <p role="alert">{fleet.error.message} <button onClick={() => void fleet.refetch()}>Retry network</button></p>}
      {fleet.data && <p role="status">{fleet.data.assets.length.toLocaleString()} assets loaded · {fleet.data.hotspots.length} hotspots</p>}
      <footer>Synthetic or public data only · Lagos area</footer>
    </main>
  );
}
