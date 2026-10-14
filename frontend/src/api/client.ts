import type { ApiOperations, AssetFeature, HotspotFeature, PageMetadata, RiskSummary, ScoringStamp } from './generated';

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

export class SnapshotChangedError extends Error {
  constructor() { super('The network changed while loading. Refresh to load a consistent snapshot.'); }
}

export async function get<K extends keyof ApiOperations>(
  operation: K,
  path: ApiOperations[K]['path'],
  query: ApiOperations[K]['query'],
  signal?: AbortSignal,
): Promise<ApiOperations[K]['response']> {
  let url = operation.split(' ')[1];
  for (const [key, value] of Object.entries(path)) url = url.replace(`{${key}}`, encodeURIComponent(String(value)));
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (value !== null && value !== undefined) params.set(key, String(value));
  const response = await fetch(`${url}${params.size ? `?${params}` : ''}`, { signal });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') message = body.detail;
    } catch { /* The server may return a non-JSON error. */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<ApiOperations[K]['response']>;
}

async function pages<T extends { id: number }>(load: (offset: number) => Promise<{ features: T[]; pagination: PageMetadata }>): Promise<T[]> {
  const features: T[] = [];
  const ids = new Set<number>();
  let offset = 0;
  let total: number | undefined;
  for (;;) {
    const page = await load(offset);
    total ??= page.pagination.total;
    if (page.pagination.total !== total || page.pagination.offset !== offset) throw new SnapshotChangedError();
    for (const feature of page.features) {
      if (ids.has(feature.id)) throw new SnapshotChangedError();
      ids.add(feature.id);
      features.push(feature);
    }
    const next = page.pagination.next_offset;
    if (next === null) break;
    if (next <= offset || next !== features.length || next >= total) throw new SnapshotChangedError();
    offset = next;
  }
  if (features.length !== total) throw new SnapshotChangedError();
  return features;
}

export function stampKey(stamp: ScoringStamp | null): string {
  return stamp ? JSON.stringify([stamp.model_version, stamp.scored_at, stamp.prediction_cutoff, stamp.horizon_days]) : 'unscored';
}

export interface FleetSnapshot { assets: AssetFeature[]; hotspots: HotspotFeature[]; summary: RiskSummary }

export async function loadFleet(signal?: AbortSignal): Promise<FleetSnapshot> {
  const summary = await get('GET /api/v1/risk/summary', {}, {}, signal);
  const assets = await pages((offset) => get('GET /api/v1/assets', {}, { limit: 500, offset }, signal));
  const hotspots = await pages((offset) => get('GET /api/v1/risk/hotspots', {}, { limit: 500, offset }, signal));
  const after = await get('GET /api/v1/risk/summary', {}, {}, signal);
  if (JSON.stringify(summary) !== JSON.stringify(after) || assets.length !== summary.total_assets
    || assets.some((asset) => asset.properties.risk && stampKey(asset.properties.risk) !== stampKey(summary.scoring))
    || assets.filter((asset) => asset.properties.risk !== null).length !== summary.scored_assets) throw new SnapshotChangedError();
  return { assets, hotspots, summary };
}
