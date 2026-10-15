import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ModelInfo } from '../pages/ModelInfo';
import type { ModelHistory } from '../api/generated';
import { modelFixture } from './fixtures';

function history(offset = 0): ModelHistory {
  return { items: [{ model_version: offset ? 'failed-model' : 'new-model', trained_at: modelFixture.trained_at, git_sha: modelFixture.git_sha, data_hash: modelFixture.data_hash, features: modelFixture.features, metrics: modelFixture.metrics, quality_gate_passed: offset === 0 }], pagination: { total: 11, limit: 10, offset, next_offset: offset ? null : 10 } };
}
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  render(<QueryClientProvider client={client}><ModelInfo /></QueryClientProvider>);
  return client;
}
afterEach(() => vi.unstubAllGlobals());
it('shows metric comparison, global SHAP, provenance, and a distinct scored model', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.includes('history') ? history() : modelFixture))));
  show();
  expect(screen.getByText('Loading model information…')).toBeInTheDocument();
  expect(await screen.findByText('A newer passing model is available')).toBeInTheDocument();
  expect(screen.getByText('old-model')).toBeInTheDocument();
  const comparison = screen.getByRole('region', { name: 'Validation comparison' });
  expect(within(comparison).getByText('0.1000')).toBeInTheDocument();
  expect(within(comparison).getByText('0.1100')).toBeInTheDocument();
  const importance = screen.getByRole('region', { name: 'Global feature importance' });
  expect(within(importance).getByText('asset age years')).toBeInTheDocument();
  expect(within(importance).getByText(/not direction or causal effect/)).toBeInTheDocument();
  expect(screen.getByText(modelFixture.data_hash)).toBeInTheDocument();
});
it('paginates to older failed runs and refreshes newly registered models', async () => {
  let current = modelFixture;
  const fetchMock = vi.fn(async (url: string) => new Response(JSON.stringify(url.includes('history') ? history(url.includes('offset=10') ? 10 : 0) : current)));
  vi.stubGlobal('fetch', fetchMock);
  show();
  await screen.findByText('A newer passing model is available');
  await userEvent.click(await screen.findByRole('button', { name: 'Older versions' }));
  expect(await screen.findByText('failed-model')).toBeInTheDocument();
  expect(screen.getByText('Failed')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Older versions' })).toBeDisabled();
  current = { ...modelFixture, model_version: 'newest-model' };
  await userEvent.click(screen.getByRole('button', { name: 'Refresh models' }));
  expect(await screen.findByText('newest-model')).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => url.includes('offset=10'))).toBe(true);
});
it('shows no-model and empty-history states independently and retries errors', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.includes('history')
    ? new Response(JSON.stringify({ items: [], pagination: { total: 0, offset: 0, limit: 10, next_offset: null } }))
    : new Response(JSON.stringify({ detail: 'No passing trained model is available' }), { status: 404 })));
  show();
  expect(await screen.findByText('No passing model available')).toBeInTheDocument();
  expect(await screen.findByText('No training runs registered.')).toBeInTheDocument();
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.includes('history') ? history() : { ...modelFixture, scored_model_version: 'new-model' }))));
  await userEvent.click(screen.getByRole('button', { name: 'Retry model' }));
  expect(await screen.findByText('Scored model matches available model')).toBeInTheDocument();
});
