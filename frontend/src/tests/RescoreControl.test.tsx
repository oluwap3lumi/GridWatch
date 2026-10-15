import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { RescoreControl } from '../components/RescoreControl';
import { Dashboard } from '../pages/Dashboard';
import { useModel } from '../api/hooks';
import { fleetFixture, modelFixture, stamp } from './fixtures';
import type { FleetSnapshot } from '../api/client';

vi.mock('../components/Map', () => ({ Map: () => <div>Local map</div> }));
afterEach(() => vi.unstubAllGlobals());
const nextStamp = { ...stamp, model_version: 'rescored-model', scored_at: '2026-10-15T12:00:00Z' };
const nextFleet: FleetSnapshot = { ...fleetFixture, summary: { ...fleetFixture.summary, scoring: nextStamp }, assets: fleetFixture.assets.map((asset) => ({ ...asset, properties: { ...asset.properties, risk: asset.properties.risk ? { ...asset.properties.risk, ...nextStamp, top_factors: [{ feature: 'load_stress', feature_value: 0.05, contribution: 0.9, contribution_unit: 'log_odds' }] } : null } })) };
const scored = { ...nextStamp, scored_assets: nextFleet.summary.scored_assets, unscored_assets: nextFleet.summary.unscored_assets, counts_by_band: nextFleet.summary.counts_by_band };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function read(url: string, fleet: FleetSnapshot): Response {
  if (url.includes('/risk/summary')) return response(fleet.summary);
  if (url.includes('/risk/hotspots')) return response({ type: 'FeatureCollection', features: fleet.hotspots, pagination: { total: fleet.hotspots.length, limit: 500, offset: 0, next_offset: null } });
  if (url.includes('/assets/')) return response({ asset: fleet.assets.find((asset) => asset.id === Number(url.match(/assets\/(\d+)/)?.[1])), outages: { type: 'FeatureCollection', features: [], pagination: { total: 0, offset: 0, limit: 10, next_offset: null } } });
  if (url.includes('/assets')) return response({ type: 'FeatureCollection', features: fleet.assets, pagination: { total: fleet.assets.length, limit: 500, offset: 0, next_offset: null } });
  if (url.includes('/model/history')) return response({ items: [], pagination: { total: 0, offset: 0, limit: 10, next_offset: null } });
  if (url.includes('/model')) return response({ ...modelFixture, model_version: fleet.summary.scoring?.model_version, scored_model_version: fleet.summary.scoring?.model_version });
  throw new Error(`Unexpected test URL ${url}`);
}
function ModelProbe() { const model = useModel(); return <output aria-label="Available model">{model.data?.model_version}</output>; }
function show(dashboard = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  client.setQueryData(['fleet'], fleetFixture);
  render(<QueryClientProvider client={client}><RescoreControl />{dashboard && <><ModelProbe /><Dashboard /></>}</QueryClientProvider>);
  return client;
}

it('updates the selected explanation and model cache after one POST', async () => {
  let active = fleetFixture;
  let finish: (() => void) | undefined;
  const fetchMock = vi.fn((url: string, options?: RequestInit) => options?.method === 'POST'
    ? new Promise<Response>((resolve) => { finish = () => { active = nextFleet; resolve(response(scored)); }; })
    : Promise.resolve(read(url, active)));
  vi.stubGlobal('fetch', fetchMock);
  const client = show(true);
  await userEvent.click(screen.getByRole('button', { name: /transformer #13/ }));
  expect(screen.getByText('+0.400')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Rescore network' }));
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
  act(() => finish?.());
  expect(await screen.findByText('+0.900')).toBeInTheDocument();
  expect(await screen.findByText(/Scores saved for 13 assets. Views refreshed./)).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Asset detail 13' })).toBeInTheDocument();
  expect(screen.getByLabelText('Available model')).toHaveTextContent('rescored-model');
  expect(client.getQueryData<FleetSnapshot>(['fleet'])?.summary.scoring?.model_version).toBe('rescored-model');
});

it('blocks repeated clicks while the POST is pending', async () => {
  let finish: (() => void) | undefined;
  const fetchMock = vi.fn((url: string, options?: RequestInit) => options?.method === 'POST'
    ? new Promise<Response>((resolve) => { finish = () => resolve(response(scored)); })
    : Promise.resolve(read(url, nextFleet)));
  vi.stubGlobal('fetch', fetchMock);
  show();
  await userEvent.click(screen.getByRole('button', { name: 'Rescore network' }));
  const pending = screen.getByRole('button', { name: 'Rescoring and refreshing…' });
  expect(pending).toBeDisabled();
  await userEvent.click(pending);
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
  act(() => finish?.());
  expect(await screen.findByText(/Scores saved for 13 assets. Views refreshed./)).toBeInTheDocument();
});

it('does not retry a conflicting POST or replace the displayed snapshot', async () => {
  const fetchMock = vi.fn(async () => response({ detail: 'Another scoring request is running' }, 409));
  vi.stubGlobal('fetch', fetchMock);
  const client = show();
  await userEvent.click(screen.getByRole('button', { name: 'Rescore network' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Another scoring request is running');
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(client.getQueryData(['fleet'])).toEqual(fleetFixture);
  expect(screen.getByRole('button', { name: 'Rescore network' })).toBeEnabled();
});

it('distinguishes saved scores from failed GET refreshes and retries reads without another POST', async () => {
  let broken = true;
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => options?.method === 'POST' ? response(scored)
    : broken ? response({ detail: 'Read unavailable' }, 404) : read(url, nextFleet));
  vi.stubGlobal('fetch', fetchMock);
  const client = show();
  await userEvent.click(screen.getByRole('button', { name: 'Rescore network' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Scores saved; view refresh failed.');
  expect(client.getQueryData(['fleet'])).toEqual(fleetFixture);
  broken = false;
  await userEvent.click(screen.getByRole('button', { name: 'Refresh views' }));
  expect(await screen.findByText(/Scores saved for 13 assets. Views refreshed./)).toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
  expect(client.getQueryData(['fleet'])).toEqual(nextFleet);
});
