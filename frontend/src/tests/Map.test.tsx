import { act, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { Map } from '../components/Map';
import { fixtureAsset, fleetFixture } from './fixtures';

const adapter = vi.hoisted(() => ({ callbacks: new globalThis.Map<string, (event?: unknown) => void>(),
  sources: new globalThis.Map<string, { setData: ReturnType<typeof vi.fn> }>(), layers: [] as { id: string; paint: Record<string, unknown> }[],
  remove: vi.fn(), fit: vi.fn(), onSelect: vi.fn() }));
vi.mock('maplibre-gl', () => ({
  setWorkerUrl: vi.fn(), NavigationControl: class {}, LngLatBounds: class { extend() { return this; } },
  Map: class {
    addControl() {} on(event: string, callback: (event?: unknown) => void) { adapter.callbacks.set(event, callback); }
    addSource(id: string) { adapter.sources.set(id, { setData: vi.fn() }); }
    addLayer(layer: { id: string; paint: Record<string, unknown> }) { adapter.layers.push(layer); }
    getSource(id: string) { return adapter.sources.get(id); }
    fitBounds = adapter.fit; remove = adapter.remove;
    isStyleLoaded() { return true; } queryRenderedFeatures() { return [{ id: 2 }]; }
    getCanvas() { return { style: {} }; }
  },
}));
beforeEach(() => { adapter.callbacks.clear(); adapter.sources.clear(); adapter.layers.length = 0; vi.clearAllMocks(); });
it('renders risk layers, updates filters and selection, routes map clicks, and removes the map', () => {
  const asset = fixtureAsset(2, 0.12);
  const view = render(<Map assets={[asset]} hotspots={fleetFixture.hotspots} selected={null} onSelect={adapter.onSelect} />);
  act(() => adapter.callbacks.get('load')?.());
  expect(screen.getByRole('status')).toHaveTextContent('Map ready');
  expect(adapter.layers.map(({ id }) => id)).toEqual(['hotspot-halo', 'feeder-lines', 'asset-points', 'selected-line', 'selected-point']);
  expect(adapter.layers.find(({ id }) => id === 'asset-points')?.paint['circle-color']).toContain('critical');
  view.rerender(<Map assets={[asset]} hotspots={[]} selected={asset} onSelect={adapter.onSelect} />);
  expect(adapter.sources.get('selection')?.setData).toHaveBeenLastCalledWith(expect.objectContaining({ features: [expect.objectContaining({ id: 2 })] }));
  expect(adapter.sources.get('hotspots')?.setData).toHaveBeenLastCalledWith({ type: 'FeatureCollection', features: [] });
  act(() => adapter.callbacks.get('click')?.({ point: { x: 1, y: 1 } }));
  expect(adapter.onSelect).toHaveBeenCalledWith(2);
  view.unmount();
  expect(adapter.remove).toHaveBeenCalledOnce();
});
