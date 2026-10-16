import { useEffect, useRef, useState } from 'react';
import { Map as MapLibreMap, LngLatBounds, setWorkerUrl } from 'maplibre-gl';
import type { ExpressionSpecification } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { AssetGeometry, PreviewRow } from '../api/generated';
import { blankMapStyle } from './mapStyle';

setWorkerUrl(workerUrl);
export function positions(geometry: AssetGeometry) {
  return geometry.type === 'Point' ? [geometry.coordinates] : geometry.type === 'MultiLineString' ? geometry.coordinates.flat() : geometry.coordinates;
}

export function ImportPreviewMap({ rows }: { rows: PreviewRow[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState('Loading preview map…');
  useEffect(() => {
    const features = rows.flatMap((row) => row.geometry ? [{ type: 'Feature' as const, geometry: row.geometry, properties: { invalid: row.errors.length > 0 } }] : []);
    if (!container.current || !features.length) return;
    let map: MapLibreMap | undefined;
    let observer: ResizeObserver | undefined;
    try {
      map = new MapLibreMap({ container: container.current, style: blankMapStyle, center: [0, 20], zoom: 1 });
      map.on('load', () => {
        if (!map) return;
        map.addSource('preview', { type: 'geojson', data: { type: 'FeatureCollection', features } });
        const color: ExpressionSpecification = ['case', ['get', 'invalid'], '#cc493e', '#3388bb'];
        map.addLayer({ id: 'lines', type: 'line', source: 'preview', filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-width': 3, 'line-color': color } });
        map.addLayer({ id: 'points', type: 'circle', source: 'preview', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': 6, 'circle-color': color } });
        const bounds = new LngLatBounds();
        for (const feature of features) for (const point of positions(feature.geometry)) bounds.extend(point);
        map.fitBounds(bounds, { padding: 35, maxZoom: 14, duration: 0 });
        setMessage('Preview only · blue: valid rows · red: rows with errors');
      });
      map.on('error', () => setMessage('Map unavailable. Review the preview table instead.'));
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(() => map?.resize()); observer.observe(container.current); }
    } catch { setMessage('Map unavailable. Review the preview table instead.'); }
    return () => { observer?.disconnect(); map?.remove(); };
  }, [rows]);
  if (!rows.some((row) => row.geometry)) return <p>No validated geometry to preview yet.</p>;
  return <figure><div className="import-mini-map" ref={container} aria-label="Upload geometry preview" /><figcaption>{message}</figcaption></figure>;
}
