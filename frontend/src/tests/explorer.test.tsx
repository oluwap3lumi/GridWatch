import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Dashboard } from '../pages/Dashboard';
import { rankedAssets, defaultFilters } from '../components/risk';
import { fleetFixture } from './fixtures';
vi.mock('../components/Map', () => ({ Map: ({ assets, hotspots, onSelect }: { assets: { id: number }[]; hotspots: unknown[]; onSelect: (id: number) => void }) => <div aria-label="Infrastructure map"><span>{assets.length} map assets / {hotspots.length} map hotspots</span><button onClick={() => onSelect(assets[0].id)}>Select map asset</button></div> }));
afterEach(() => vi.unstubAllGlobals());
function showFleet() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const id = Number(url.match(/assets\/(\d+)/)?.[1]);
    return new Response(JSON.stringify({ asset: fleetFixture.assets.find((asset) => asset.id === id), outages: { type: 'FeatureCollection', features: [], pagination: { total: 0, limit: 10, offset: 0, next_offset: null } } }));
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(['fleet'], fleetFixture);
  render(<QueryClientProvider client={client}><Dashboard /></QueryClientProvider>);
}
describe('risk explorer', () => {
  it('ranks the whole fleet deterministically and excludes unscored transformers from the top ten', () => {
    const ranked = rankedAssets(fleetFixture.assets, defaultFilters, true);
    expect(ranked).toHaveLength(10);
    expect(ranked[0].id).toBe(13);
    expect(ranked.every((asset) => asset.properties.type === 'transformer' && asset.properties.risk)).toBe(true);
    const ties = [fleetFixture.assets[0], { ...fleetFixture.assets[0], id: 1 }];
    expect(rankedAssets(ties, defaultFilters, false).map(({ id }) => id)).toEqual([1, 2]);
  });
  it('finds the top ten in one click', async () => {
    showFleet();
    await userEvent.click(screen.getByRole('button', { name: /Top 10 transformers/ }));
    expect(screen.getByRole('heading', { name: 'Top 10 transformers' })).toBeInTheDocument();
    const list = screen.getByRole('region', { name: 'Ranked assets' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(10);
    expect(within(list).getAllByRole('button')[0]).toHaveTextContent('transformer #13');
  });
  it('selects an asset and shows its explanation and history', async () => {
    showFleet();
    const row = screen.getByRole('button', { name: /transformer #13/ });
    await userEvent.click(row);
    expect(row).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: 'Why this score?' })).toBeInTheDocument();
    expect(screen.getByText('Load above 75% (fraction)')).toBeInTheDocument();
    expect(await screen.findByText('No outage events recorded for this asset.')).toBeInTheDocument();
  });
  it('combines type, band, threshold filters, handles emptiness, and toggles hotspots', async () => {
    showFleet();
    await userEvent.selectOptions(screen.getByLabelText('Asset type'), 'pole');
    await userEvent.selectOptions(screen.getByLabelText('Risk band'), 'critical');
    expect(screen.getByText('1 map assets / 1 map hotspots')).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('Hotspots'));
    expect(screen.getByText('1 map assets / 0 map hotspots')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('slider', { name: 'Minimum risk' }), { target: { value: '100' } });
    expect(screen.getByText('No matching assets')).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: 'Reset filters' })[0]);
    expect(screen.getByText('14 map assets / 0 map hotspots')).toBeInTheDocument();
  });
});
