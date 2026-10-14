import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { AssetPanel } from '../components/AssetPanel';
import { fixtureAsset, stamp } from './fixtures';
import type { AssetDetail } from '../api/generated';

const asset = fixtureAsset(2, 0.12);
function detail(offset = 0): AssetDetail {
  return { asset, outages: { type: 'FeatureCollection', features: Array.from({ length: offset ? 1 : 10 }, (_, index) => ({
    type: 'Feature', id: offset + index, geometry: { type: 'Point', coordinates: [3.4, 6.5] },
    properties: { asset_id: 2, cause: offset ? 'vegetation_contact' : 'storm', duration_min: 120, started_at: '2025-12-01T12:00:00Z' },
  })), pagination: { total: 11, limit: 10, offset, next_offset: offset ? null : 10 } } };
}
function show(refresh = vi.fn(), selected = asset) {
  render(<QueryClientProvider client={new QueryClient()}><AssetPanel asset={selected} stamp={selected.properties.risk ? stamp : null} close={vi.fn()} refresh={refresh} /></QueryClientProvider>);
}
afterEach(() => vi.unstubAllGlobals());

it('shows signed explanations immediately, loads history, and paginates older and newer outages', async () => {
  const fetchMock = vi.fn(async (url: string) => new Response(JSON.stringify(detail(url.includes('offset=10') ? 10 : 0))));
  vi.stubGlobal('fetch', fetchMock);
  show();
  expect(screen.getByText('+0.400')).toBeInTheDocument();
  expect(screen.getByText('-0.200')).toBeInTheDocument();
  expect(screen.getByText(/not probability changes or causes/)).toBeInTheDocument();
  expect(screen.getByText('Loading outage history…')).toBeInTheDocument();
  expect(await screen.findByText('1–10 of 11')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Newer' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Older' }));
  expect(await screen.findByText('vegetation contact')).toBeInTheDocument();
  expect(screen.getByText('11–11 of 11')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Older' })).toBeDisabled();
  expect(fetchMock.mock.calls[1][0]).toContain('offset=10');
  await userEvent.click(screen.getByRole('button', { name: 'Newer' }));
  expect(await screen.findByText('1–10 of 11')).toBeInTheDocument();
});
it('offers a history retry after a server error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'History unavailable' }), { status: 503 }))
    .mockResolvedValue(new Response(JSON.stringify(detail()))));
  show();
  expect(await screen.findByRole('alert')).toHaveTextContent('History unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Retry history' }));
  expect(await screen.findByText('1–10 of 11')).toBeInTheDocument();
});
it('rejects changed score batches and asks for a network refresh', async () => {
  const changed = detail();
  changed.asset = { ...asset, properties: { ...asset.properties, risk: { ...asset.properties.risk!, model_version: 'new-batch' } } };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(changed))));
  const refresh = vi.fn();
  show(refresh);
  expect(await screen.findByRole('alert')).toHaveTextContent('network changed');
  expect(screen.queryByText('storm')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Refresh network' }));
  expect(refresh).toHaveBeenCalledOnce();
});
it('distinguishes an unscored asset from a zero-risk prediction and empty history', async () => {
  const unscored = fixtureAsset(2, null);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ asset: unscored, outages: { type: 'FeatureCollection', features: [], pagination: { total: 0, limit: 10, offset: 0, next_offset: null } } }))));
  show(vi.fn(), unscored);
  expect(screen.getByText('This asset has not been scored.')).toBeInTheDocument();
  expect(screen.getByText('Unscored')).toBeInTheDocument();
  expect(await screen.findByText('No outage events recorded for this asset.')).toBeInTheDocument();
});
