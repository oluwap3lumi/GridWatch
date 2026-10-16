import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, get, loadFleet, SnapshotChangedError } from '../api/client';
import type { AssetFeature, RiskSummary } from '../api/generated';

const summary: RiskSummary = { total_assets: 2, scored_assets: 0, unscored_assets: 2,
  counts_by_band: { low: 0, medium: 0, high: 0, critical: 0 }, by_feeder: [], scoring: null };
function asset(id: number): AssetFeature {
  return { type: 'Feature', id, geometry: { type: 'Point', coordinates: [3.4, 6.5] }, properties: {
    external_id: null, pole_id: null, batch_id: null, type: 'transformer', feeder_id: null, install_date: '2000-01-01', capacity_kva: 100, load_factor: 0.8,
    material: 'steel', vegetation_index: 0.5, last_maintenance_date: '2025-01-01', risk: null } };
}
function respond(body: unknown) { return new Response(JSON.stringify(body), { status: 200 }); }
afterEach(() => vi.unstubAllGlobals());

describe('typed fleet client', () => {
  it('loads subsequent pages before returning the fleet and forwards cancellation', async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValueOnce(respond(summary))
      .mockResolvedValueOnce(respond({ features: [asset(1)], pagination: { total: 2, offset: 0, next_offset: 1 } }))
      .mockResolvedValueOnce(respond({ features: [asset(2)], pagination: { total: 2, offset: 1, next_offset: null } }))
      .mockResolvedValueOnce(respond({ features: [], pagination: { total: 0, offset: 0, next_offset: null } }))
      .mockResolvedValueOnce(respond(summary));
    vi.stubGlobal('fetch', fetchMock);
    const fleet = await loadFleet(controller.signal);
    expect(fleet.assets.map(({ id }) => id)).toEqual([1, 2]);
    expect(fetchMock.mock.calls[2][0]).toContain('offset=1');
    expect(fetchMock.mock.calls.every((call) => call[1].signal === controller.signal)).toBe(true);
  });

  it('rejects a duplicate page rather than returning an incomplete ranking', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(respond(summary))
      .mockResolvedValueOnce(respond({ features: [asset(1)], pagination: { total: 2, offset: 0, next_offset: 1 } }))
      .mockResolvedValueOnce(respond({ features: [asset(1)], pagination: { total: 2, offset: 1, next_offset: null } })));
    await expect(loadFleet()).rejects.toBeInstanceOf(SnapshotChangedError);
  });

  it('rejects a scoring batch changed during pagination', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(respond(summary))
      .mockResolvedValueOnce(respond({ features: [asset(1), asset(2)], pagination: { total: 2, offset: 0, next_offset: null } }))
      .mockResolvedValueOnce(respond({ features: [], pagination: { total: 0, offset: 0, next_offset: null } }))
      .mockResolvedValueOnce(respond({ ...summary, scored_assets: 1 })));
    await expect(loadFleet()).rejects.toBeInstanceOf(SnapshotChangedError);
  });

  it('preserves server error details and abort failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Database unavailable' }), { status: 503 })));
    await expect(get('GET /api/v1/risk/summary', {}, {})).rejects.toEqual(new ApiError(503, 'Database unavailable'));
    const aborted = new DOMException('Aborted', 'AbortError');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(aborted));
    await expect(loadFleet()).rejects.toBe(aborted);
  });
});
