import { useMutation, useQueryClient } from '@tanstack/react-query';
import { refreshViews, useRescore } from '../api/hooks';

export function RescoreControl() {
  const mutation = useRescore();
  const client = useQueryClient();
  const refresh = useMutation({ mutationFn: () => refreshViews(client), retry: false });
  const pending = mutation.isPending || refresh.isPending;
  const saved = mutation.data;
  const refreshed = refresh.isError ? false : refresh.isSuccess ? refresh.data : saved?.refreshed;
  return <section className="rescore-bar" aria-label="Rescore network">
    <div><strong>Score the network</strong><p>Use the latest passing model and the historical data cutoff. Training is a separate step.</p></div>
    <div className="rescore-actions"><button className="primary rescore-button" disabled={pending} onClick={() => { refresh.reset(); mutation.mutate(); }}>{mutation.isPending ? 'Rescoring and refreshing…' : 'Rescore network'}</button>
      <button disabled={pending} onClick={() => refresh.mutate()}>{refresh.isPending ? 'Refreshing views…' : 'Refresh views'}</button></div>
    <div className="rescore-message" aria-live="polite">
      {mutation.isPending && <p role="status">Computing scores and refreshing views. This may take a moment.</p>}
      {refresh.isPending && <p role="status">Refreshing saved views…</p>}
      {mutation.isError && <div role="alert"><strong>Rescore request failed</strong><p>{mutation.error.message}</p><p>Refresh views to check the latest saved scores before retrying.</p></div>}
      {saved && !pending && (refreshed ? <p role="status">Scores saved for {saved.scored.scored_assets.toLocaleString()} assets. Views refreshed. <span>Model <code>{saved.scored.model_version}</code></span></p> : <div role="alert"><strong>Scores saved; view refresh failed.</strong><p>Use Refresh views to read the saved batch without rescoring again.</p></div>)}
      {refresh.isSuccess && !refresh.data && !saved && <p role="alert">Views could not refresh. The previous data remains visible; try Refresh views again.</p>}
      {refresh.isSuccess && refresh.data && !saved && <p role="status">Views refreshed from the API.</p>}
      {refresh.isError && !saved && <p role="alert">View refresh failed: {refresh.error.message}</p>}
    </div>
  </section>;
}
