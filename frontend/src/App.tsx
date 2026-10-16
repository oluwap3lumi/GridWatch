import { useEffect, useState } from 'react';
import { Dashboard } from './pages/Dashboard';
import { ModelInfo } from './pages/ModelInfo';
import { RescoreControl } from './components/RescoreControl';
import { Upload } from './pages/Upload';

export function App() {
  const [route, setRoute] = useState(() => window.location.hash);
  const page = route.split('?')[0] === '#upload' ? 'upload' : route === '#model' ? 'model' : 'map';
  const params = new URLSearchParams(route.split('?')[1]);
  const batchId = params.get('batch');
  const focusId = params.get('import');
  useEffect(() => {
    const navigate = () => setRoute(window.location.hash);
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  return <main>
    <header><div className="brand"><span className="brand-mark" aria-hidden="true">G</span>GridWatch<span className="brand-divider" /><small>Network intelligence</small></div>
      <nav className="page-nav" aria-label="Main navigation"><a href="#map" aria-current={page === 'map' ? 'page' : undefined}>Risk map</a><a href="#upload" aria-current={page === 'upload' ? 'page' : undefined}>Upload</a><a href="#model" aria-current={page === 'model' ? 'page' : undefined}>Model</a></nav>
      <span className="badge"><span className="live-dot" />Synthetic demo</span>
    </header>
    {page !== 'upload' && <RescoreControl />}
    {page === 'upload' ? <Upload batchId={batchId} onSelect={(id) => { window.location.hash = id ? `#upload?batch=${encodeURIComponent(id)}` : '#upload'; }} /> : page === 'map' ? <Dashboard focusBatchId={focusId} /> : <ModelInfo />}
    <footer><span>GRIDWATCH / Private uploads stay on your deployment</span><span>Scores use synthetic demo context</span></footer>
  </main>;
}
