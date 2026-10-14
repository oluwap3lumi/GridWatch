import { useEffect, useRef, useState } from 'react';
import { Map as MapLibreMap, NavigationControl, setWorkerUrl, LngLatBounds } from 'maplibre-gl';
import type { GeoJSONSource, ExpressionSpecification } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { AssetFeature, HotspotFeature } from '../api/generated';
import { blankMapStyle } from './mapStyle';
import { riskColors } from './risk';

setWorkerUrl(workerUrl);
interface MapProps { assets: AssetFeature[]; hotspots: HotspotFeature[]; selected: AssetFeature | null; onSelect: (id: number) => void }
const colors: ExpressionSpecification = ['match', ['get', 'band'], 'low', riskColors.low, 'medium', riskColors.medium, 'high', riskColors.high, 'critical', riskColors.critical, riskColors.unscored];
function data(assets: AssetFeature[]) {
  return { type: 'FeatureCollection' as const, features: assets.map((asset) => ({ ...asset, properties: { kind: asset.properties.type, band: asset.properties.risk?.band ?? 'unscored' } })) };
}
function fit(map: MapLibreMap, assets: AssetFeature[], maxZoom = 12) {
  if (!assets.length) return;
  const bounds = new LngLatBounds();
  for (const asset of assets) {
    const coords = asset.geometry.type === 'Point' ? [asset.geometry.coordinates] : asset.geometry.coordinates;
    for (const coord of coords) bounds.extend(coord);
  }
  map.fitBounds(bounds, { padding: 65, maxZoom, duration: 0 });
}
export function Map(props: MapProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const latest = useRef(props);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState('Loading map…');
  useEffect(() => { latest.current = props; });
  useEffect(() => {
    if (!container.current) return;
    let map: MapLibreMap | undefined;
    let observer: ResizeObserver | undefined;
    try {
      map = new MapLibreMap({ container: container.current, style: blankMapStyle, center: [3.3792, 6.5244], zoom: 10 });
      mapRef.current = map;
      map.addControl(new NavigationControl(), 'top-right');
      map.on('load', () => {
        if (!map) return;
        map.addSource('assets', { type: 'geojson', data: data(latest.current.assets) });
        map.addSource('selection', { type: 'geojson', data: data([]) });
        map.addSource('hotspots', { type: 'geojson', data: { type: 'FeatureCollection', features: latest.current.hotspots } });
        map.addLayer({ id: 'hotspot-halo', type: 'circle', source: 'hotspots', paint: { 'circle-radius': ['interpolate', ['linear'], ['get', 'asset_count'], 3, 15, 30, 35], 'circle-color': '#e98166', 'circle-opacity': 0.13, 'circle-stroke-width': 1, 'circle-stroke-color': '#e98166', 'circle-stroke-opacity': 0.5 } });
        map.addLayer({ id: 'feeder-lines', type: 'line', source: 'assets', filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-color': colors, 'line-width': 2.5, 'line-opacity': 0.8 } });
        map.addLayer({ id: 'asset-points', type: 'circle', source: 'assets', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-color': colors, 'circle-radius': ['match', ['get', 'kind'], 'transformer', 6, 3.5], 'circle-stroke-color': '#122e32', 'circle-stroke-width': 1 } });
        map.addLayer({ id: 'selected-line', type: 'line', source: 'selection', filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-color': '#ffffff', 'line-width': 5 } });
        map.addLayer({ id: 'selected-point', type: 'circle', source: 'selection', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': 10, 'circle-color': colors, 'circle-stroke-width': 3, 'circle-stroke-color': '#ffffff' } });
        fit(map, latest.current.assets);
        setStatus('Map ready · select an asset to inspect');
        setReady(true);
      });
      map.on('click', (event) => {
        if (!map?.isStyleLoaded()) return;
        const id = map.queryRenderedFeatures(event.point, { layers: ['asset-points', 'feeder-lines'] })[0]?.id;
        if (typeof id === 'number') latest.current.onSelect(id);
      });
      map.on('mousemove', (event) => {
        if (map?.isStyleLoaded()) map.getCanvas().style.cursor = map.queryRenderedFeatures(event.point, { layers: ['asset-points', 'feeder-lines'] }).length ? 'pointer' : '';
      });
      map.on('error', (event) => { console.error('MapLibre error:', event.error); setStatus('Map unavailable. Use the asset list to explore the network.'); });
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(() => map?.resize()); observer.observe(container.current); }
    } catch { setStatus('Map unavailable. Use the asset list to explore the network.'); }
    return () => { observer?.disconnect(); map?.remove(); mapRef.current = null; };
  }, []);
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    (mapRef.current.getSource('assets') as GeoJSONSource).setData(data(props.assets));
    (mapRef.current.getSource('hotspots') as GeoJSONSource).setData({ type: 'FeatureCollection', features: props.hotspots });
  }, [ready, props.assets, props.hotspots]);
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    (mapRef.current.getSource('selection') as GeoJSONSource).setData(data(props.selected ? [props.selected] : []));
    if (props.selected) fit(mapRef.current, [props.selected], 15);
  }, [ready, props.selected]);
  return <section className="map-panel" aria-label="Infrastructure map">
    <div className="map-caption"><span className="live-dot" />LAGOS AREA <small>Synthetic network · EPSG:4326</small></div>
    <div ref={container} className="map" aria-label="MapLibre map of Lagos" />
    <button className="fit-map" disabled={!ready || !props.assets.length} onClick={() => mapRef.current && fit(mapRef.current, props.assets)}>Fit visible assets</button>
    <p className="map-status" role="status">{status}</p>
  </section>;
}
