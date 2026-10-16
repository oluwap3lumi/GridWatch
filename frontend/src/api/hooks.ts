import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryClient } from '@tanstack/react-query';
import { ApiError, get, loadFleet, rescore, SnapshotChangedError, stampKey } from './client';
import type { ScoringStamp, RescoreRequest } from './generated';

export function useFleet() {
  return useQuery({ queryKey: ['fleet'], queryFn: ({ signal }) => loadFleet(signal), staleTime: 30_000,
    retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status >= 500) });
}

const retryRead = (count: number, error: Error) => count < 1 && (!(error instanceof ApiError) || error.status >= 500);
export function useModel() {
  return useQuery({ queryKey: ['model'], queryFn: ({ signal }) => get('GET /api/v1/model', {}, {}, signal), staleTime: 15_000, retry: retryRead });
}
export function useModelHistory(offset: number) {
  return useQuery({ queryKey: ['model-history', offset], queryFn: ({ signal }) => get('GET /api/v1/model/history', {}, { limit: 10, offset }, signal), staleTime: 15_000, retry: retryRead });
}

export async function refreshViews(client: QueryClient): Promise<boolean> {
  // Cancel reads begun before scoring, then replace the fleet cache as one snapshot.
  await client.cancelQueries({ predicate: ({ queryKey }) => ['fleet', 'model', 'model-history'].includes(String(queryKey[0])) });
  const results = await Promise.allSettled([
    client.fetchQuery({ queryKey: ['fleet'], queryFn: ({ signal }) => loadFleet(signal), staleTime: 0, retry: retryRead }),
    client.invalidateQueries({ queryKey: ['model'] }, { throwOnError: true }),
    client.invalidateQueries({ queryKey: ['model-history'] }, { throwOnError: true }),
  ]);
  // Old detail keys include their scoring stamp; they cannot overwrite the new batch.
  await client.invalidateQueries({ queryKey: ['asset'], refetchType: 'none' });
  return results.every((result) => result.status === 'fulfilled');
}

export function useRescore() {
  const client = useQueryClient();
  return useMutation({ mutationKey: ['rescore'], retry: false, mutationFn: async (options: RescoreRequest) => {
    const scored = await rescore(options);
    // A failed GET must never turn a committed POST into an invitation to retry it.
    let refreshed = false;
    try { refreshed = await refreshViews(client); } catch { /* Scores were already saved. */ }
    return { scored, refreshed };
  } });
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
