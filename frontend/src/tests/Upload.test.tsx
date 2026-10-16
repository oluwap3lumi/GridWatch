import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { Upload, duplicateMappings } from '../pages/Upload';
import type { ImportBatchDetail } from '../api/generated';

vi.mock('../components/ImportPreviewMap', () => ({ ImportPreviewMap: () => <div>Geometry preview</div> }));
const batch: ImportBatchDetail = {
  id: '00000000-0000-0000-0000-000000000001', filename: 'synthetic.csv', format: 'csv', layer_type: 'transformer', status: 'uploaded',
  row_counts: { total: 2, valid: 1, invalid: 1, inserted: 0, updated: 0 }, detected_columns: ['ID', 'lat', 'lon'], column_mapping: { external_id: 'ID', latitude: 'lat', longitude: 'lon' },
  crs_detected: 'EPSG:4326', crs_selected: null, created_at: '2026-01-01T00:00:00Z', completed_at: null, expires_at: '2026-01-02T00:00:00Z',
  preview: [{ row_number: 1, properties: { ID: 'synthetic-1', lat: 6.5, lon: 3.3 }, geometry: { type: 'Point', coordinates: [3.3, 6.5] }, errors: [], warnings: [] },
    { row_number: 2, properties: { ID: 'synthetic-2', lat: 0, lon: 0 }, geometry: null, errors: [{ row_number: 2, field: 'latitude', code: 'INVALID_COORDINATES', reason: 'Coordinates cannot be zero.' }], warnings: [] }],
  job: null, errors: [], extent: [3.3, 6.5, 3.3, 6.5], error_code: null, warnings: [],
};
function show(current: ImportBatchDetail | null = batch) {
  const select = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><Upload batchId={current?.id ?? null} onSelect={select} /></QueryClientProvider>);
  return { select, client };
}
function mock(current: ImportBatchDetail) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.includes('?limit=')) return new Response(JSON.stringify({ items: [], total: 0 }));
    if (init?.method === 'POST') return new Response(JSON.stringify({ ...current, job: { id: 'job', operation: url.endsWith('/validate') ? 'validate' : 'commit', status: 'queued', processed: 0, total: 2 } }));
    return new Response(JSON.stringify(current));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}
afterEach(() => { vi.unstubAllGlobals(); });

it('uploads multipart with the chosen layer and provides templates without trusting MIME', async () => {
  const fetchMock = mock(batch);
  const { select } = show(null);
  expect(screen.getByRole('link', { name: 'Synthetic GeoJSON example' })).toHaveAttribute('href', '/api/v1/imports/templates/transformer.geojson');
  await userEvent.selectOptions(screen.getByLabelText('Layer type'), 'pole');
  await userEvent.upload(screen.getByLabelText('Drop a file here or choose a file'), new File(['synthetic'], 'poles.json', { type: 'application/json' }));
  await userEvent.click(screen.getByRole('button', { name: 'Upload and inspect' }));
  await waitFor(() => expect(select).toHaveBeenCalledWith(batch.id));
  const upload = fetchMock.mock.calls.find(([url]) => url === '/api/v1/imports');
  expect(upload?.[1]?.body).toBeInstanceOf(FormData);
  expect((upload?.[1]?.body as FormData).get('layer_type')).toBe('pole');
  expect(upload?.[1]?.headers).toBeUndefined();
});

it('prefills server mappings, prevents duplicate mappings and submits explicit CRS/date choices', async () => {
  const fetchMock = mock({ ...batch, crs_detected: null });
  show();
  expect(await screen.findByLabelText('external_id')).toHaveValue('ID');
  expect(screen.getByLabelText('Source CRS')).toBeRequired();
  await userEvent.selectOptions(screen.getByLabelText('longitude'), 'lat');
  expect(screen.getByRole('button', { name: 'Validate all rows' })).toBeDisabled();
  expect(duplicateMappings({ a: '', b: '' })).toBe(false);
  await userEvent.selectOptions(screen.getByLabelText('longitude'), 'lon');
  await userEvent.type(screen.getByLabelText('Source CRS'), 'EPSG:32631');
  await userEvent.selectOptions(screen.getByLabelText('Date convention'), 'day_first');
  await userEvent.click(screen.getByRole('button', { name: 'Validate all rows' }));
  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/validate'))).toBe(true));
  const call = fetchMock.mock.calls.find(([url]) => url.endsWith('/validate'));
  expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ column_mapping: { external_id: 'ID', longitude: 'lon' }, source_crs: 'EPSG:32631', date_format: 'day_first' });
});

it('highlights validation errors and requires explicit partial success and scoring consent', async () => {
  const current = { ...batch, status: 'validated' as const };
  const fetchMock = mock(current);
  show(current);
  const button = await screen.findByRole('button', { name: 'Commit import' });
  expect(button).toBeDisabled();
  expect(screen.getByText('0', { selector: 'td.invalid-cell' })).toBeInTheDocument();
  expect(screen.getByText('latitude: Coordinates cannot be zero.')).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText('Import valid rows only; skip 1 invalid rows'));
  await userEvent.click(screen.getByLabelText('Rescore the network after import'));
  expect(screen.getByLabelText('Allow training medians for missing model attributes')).not.toBeChecked();
  await userEvent.click(screen.getByLabelText('Allow training medians for missing model attributes'));
  await userEvent.click(button);
  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/commit'))).toBe(true));
  const call = fetchMock.mock.calls.find(([url]) => url.endsWith('/commit'));
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ valid_rows_only: true, rescore: true, accept_scoring_defaults: true });
});

it('keeps an import saved when scoring fails and requires rollback confirmation', async () => {
  const current: ImportBatchDetail = { ...batch, status: 'imported', job: { id: 'job', operation: 'rescore', status: 'failed', processed: 0, total: 0, error_code: 'SCORING_DEFAULTS_REQUIRED' } };
  const fetchMock = mock(current);
  show(current);
  expect(await screen.findByRole('heading', { name: 'Import saved' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'View on map' })).toHaveAttribute('href', `#map?import=${batch.id}`);
  expect(screen.queryByRole('button', { name: 'Commit import' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Rollback' }));
  expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/rollback'))).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Keep batch' }));
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
});

it('retries a failed batch read and shows empty history independently', async () => {
  let failed = true;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.includes('?limit=') ? new Response(JSON.stringify({ items: [], total: 0 })) : failed ? new Response('{}', { status: 503 }) : new Response(JSON.stringify(batch))));
  show();
  expect(await screen.findByText('No imports on this page yet.')).toBeInTheDocument();
  await screen.findByRole('button', { name: 'Retry batch' });
  failed = false;
  await userEvent.click(screen.getByRole('button', { name: 'Retry batch' }));
  expect(await screen.findByLabelText('external_id')).toHaveValue('ID');
});

it('polls a queued job into validation and never permits committing while work runs', async () => {
  const current: ImportBatchDetail = { ...batch, job: { id: 'job', operation: 'validate', status: 'running', processed: 1, total: 2, error_code: null } };
  let reads = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('?limit=')) return new Response(JSON.stringify({ items: [], total: 0 }));
    reads += 1;
    return new Response(JSON.stringify(reads === 1 ? current : { ...batch, status: 'validated' }));
  }));
  const { client } = show(current);
  expect(await screen.findByRole('progressbar')).toHaveAttribute('value', '1');
  expect(screen.queryByRole('button', { name: 'Commit import' })).not.toBeInTheDocument();
  expect(await screen.findByRole('button', { name: 'Commit import' }, { timeout: 2500 })).toBeDisabled();
  client.clear();
});

it('retains the saved import on rollback conflict and shows the server response', async () => {
  const current: ImportBatchDetail = { ...batch, status: 'imported' };
  const fetchMock = mock(current);
  const { client } = show(current);
  await screen.findByRole('heading', { name: 'Import saved' });
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => init?.method === 'POST'
    ? new Response(JSON.stringify({ detail: 'ROLLBACK_CONFLICT' }), { status: 409 })
    : new Response(JSON.stringify(url.includes('?limit=') ? { items: [], total: 0 } : current)));
  await userEvent.click(screen.getByRole('button', { name: 'Rollback' }));
  await userEvent.click(screen.getByRole('button', { name: 'Confirm rollback' }));
  expect(await screen.findByText('Later changes depend on this batch. Roll back newer batches first.')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Import saved' })).toBeInTheDocument();
  expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  client.clear();
});
