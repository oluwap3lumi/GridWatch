import { useEffect, useState } from 'react';
import { Dashboard } from './pages/Dashboard';
import { ModelInfo } from './pages/ModelInfo';
import { RescoreControl } from './components/RescoreControl';

export function App() {
  const [page, setPage] = useState(() => window.location.hash === '#model' ? 'model' : 'map');
  useEffect(() => {
    const navigate = () => setPage(window.location.hash === '#model' ? 'model' : 'map');
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  return <main>
    <header><div className="brand"><span className="brand-mark" aria-hidden="true">G</span>GridWatch<span className="brand-divider" /><small>Network intelligence</small></div>
      <nav className="page-nav" aria-label="Main navigation"><a href="#map" aria-current={page === 'map' ? 'page' : undefined}>Risk map</a><a href="#model" aria-current={page === 'model' ? 'page' : undefined}>Model</a></nav>
      <span className="badge"><span className="live-dot" />Synthetic demo</span>
    </header>
    <RescoreControl />
    {page === 'map' ? <Dashboard /> : <ModelInfo />}
    <footer><span>GRIDWATCH / Synthetic or public data only</span><span>Historical demo · Lagos area</span></footer>
  </main>;
}
