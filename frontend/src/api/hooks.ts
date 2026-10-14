import { useQuery } from '@tanstack/react-query';
import { ApiError, get, loadFleet, SnapshotChangedError, stampKey } from './client';
import type { ScoringStamp } from './generated';

export function useFleet() {
  return useQuery({ queryKey: ['fleet'], queryFn: ({ signal }) => loadFleet(signal), staleTime: 30_000,
    retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status >= 500) });
}

export function useAssetDetail(id: number | null, offset: number, stamp: ScoringStamp | null) {
  return useQuery({ queryKey: ['asset', id, offset, stampKey(stamp)], enabled: id !== null,
    queryFn: async ({ signal }) => {
      if (id === null) throw new Error('Select an asset first.');
      const detail = await get('GET /api/v1/assets/{asset_id}', { asset_id: id }, { limit: 10, offset }, signal);
      if (stampKey(detail.asset.properties.risk) !== stampKey(stamp)) throw new SnapshotChangedError();
      return detail;
    }, staleTime: 30_000, retry: false });
}
