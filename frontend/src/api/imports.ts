import { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get } from './client';
import type { ImportBatchDetail } from './generated';

export const busy = (batch?: ImportBatchDetail) => batch?.job?.status === 'queued' || batch?.job?.status === 'running';

export function useImportBatch(id: string | null) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['import', id], enabled: id !== null,
    queryFn: ({ signal }) => get('GET /api/v1/imports/{batch_id}', { batch_id: id ?? '' }, { include_errors: false }, signal),
    retry: false, refetchInterval: (q) => q.state.status !== 'error' && busy(q.state.data) ? 750 : false });
  const job = query.data?.job;
  useEffect(() => {
    if (!job || !['commit', 'rollback', 'rescore'].includes(job.operation) || !['completed', 'failed'].includes(job.status)) return;
    for (const key of ['fleet', 'asset', 'model', 'model-history', 'imports']) {
      void client.cancelQueries({ queryKey: [key] }).then(() => client.invalidateQueries({ queryKey: [key] }));
    }
  }, [client, job?.id, job?.operation, job?.status]);
  return query;
}

export function useImportHistory(offset: number) {
  return useQuery({ queryKey: ['imports', offset],
    queryFn: ({ signal }) => get('GET /api/v1/imports', {}, { limit: 20, offset }, signal), retry: false,
    refetchInterval: (q) => q.state.status !== 'error' && q.state.data?.items.some(busy) ? 1500 : false });
}

export function importError(code: string | null | undefined): string {
  const messages: Record<string, string> = {
    SCORING_DEFAULTS_REQUIRED: 'Scoring needs consent to use training medians. The import is saved; review the scoring options on the Model page.',
    MODEL_NOT_FOUND: 'No trained model is available. The import is saved; train a model before rescoring.',
    ROLLBACK_CONFLICT: 'Later changes depend on this batch. Roll back newer batches first.',
    JOB_IN_PROGRESS: 'This batch already has a job running. Wait for it to finish.',
    STAGING_EXPIRED: 'Staged data has expired. Upload the file again to continue.',
    NO_VALID_ROWS: 'No rows passed validation. Fix the source data and upload again.',
    PARTIAL_IMPORT_REQUIRES_CONSENT: 'Choose whether to import valid rows only before committing.',
    BATCH_NOT_FOUND: 'This import batch could not be found.',
    INVALID_BATCH_STATE: 'This action is unavailable in the current batch state. Refresh the batch.',
    CRS_REQUIRED: 'Choose a source CRS before validating.',
    UPLOAD_TOO_LARGE: 'The file exceeds the configured upload size limit.',
    FEATURE_LIMIT: 'The file exceeds the configured feature count limit.',
  };
  return code ? messages[code] ?? `Operation could not complete (${code}). Review the error report.` : 'Operation could not complete. Try refreshing the batch.';
}
