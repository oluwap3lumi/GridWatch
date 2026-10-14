import { useEffect, useRef, useState } from 'react';
import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
import { blankMapStyle } from './mapStyle';

setWorkerUrl(workerUrl);

export function Map() {
  const container = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState('Loading map…');

  useEffect(() => {
    if (!container.current) return;
    let map: MapLibreMap | undefined;
    try {
      map = new MapLibreMap({
        container: container.current,
        style: blankMapStyle,
        center: [3.3792, 6.5244],
        zoom: 10,
      });
      map.addControl(new NavigationControl(), 'top-right');
      map.on('load', () => setStatus('Map ready · asset data arrives in M1'));
      map.on('error', (event) => {
        console.error('MapLibre error:', event.error);
        setStatus('Map could not load. Check browser WebGL support.');
      });
    } catch (error) {
      console.error('MapLibre initialization failed:', error);
      setStatus('Map could not load. Check browser WebGL support.');
    }
    return () => map?.remove();
  }, []);

  return (
    <section className="map-panel" aria-label="Infrastructure map">
      <div ref={container} className="map" aria-label="MapLibre map of Lagos" />
      <p className="map-status" role="status">{status}</p>
    </section>
  );
}
