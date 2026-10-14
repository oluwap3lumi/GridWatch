import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { Dashboard } from '../pages/Dashboard';
import type { RiskSummary } from '../api/generated';

vi.mock('../components/Map', () => ({ Map: () => <div>Local map</div> }));
afterEach(() => vi.unstubAllGlobals());
const empty: RiskSummary = { total_assets: 0, scored_assets: 0, unscored_assets: 0, counts_by_band: { low: 0, medium: 0, high: 0, critical: 0 }, by_feeder: [], scoring: null };
it('shows a loading state, preserves server errors, and retries into an honest empty network', async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: 'Fleet unavailable' }), { status: 404 }));
  vi.stubGlobal('fetch', fetchMock);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } })}><Dashboard /></QueryClientProvider>);
  expect(screen.getByRole('status')).toHaveTextContent('Loading the complete network');
  expect(await screen.findByRole('alert')).toHaveTextContent('Fleet unavailable');
  fetchMock.mockImplementation(async (...args: unknown[]) => {
    const url = String(args[0]);
    return new Response(JSON.stringify(url.includes('summary') ? empty : { type: 'FeatureCollection', features: [], pagination: { total: 0, limit: 500, offset: 0, next_offset: null } }));
  });
  await userEvent.click(screen.getByRole('button', { name: 'Retry network' }));
  expect(await screen.findByText('No network assets yet. Run make seed to load the synthetic corpus.')).toBeInTheDocument();
  expect(screen.getByText('No matching assets')).toBeInTheDocument();
});
