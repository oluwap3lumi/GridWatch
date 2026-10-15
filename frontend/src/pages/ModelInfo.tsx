import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useModel, useModelHistory } from '../api/hooks';
import { ApiError } from '../api/client';
import { date } from '../components/risk';

const metricRows = [
  ['pr_auc', 'PR-AUC (average precision)', 'Higher is better'], ['roc_auc', 'ROC-AUC', 'Higher is better'],
  ['brier_score', 'Brier score', 'Lower is better'], ['expected_calibration_error', 'Calibration error', 'Lower is better'],
  ['precision_at_top_k', 'Precision in highest-risk 5%', 'Higher is better'], ['log_loss', 'Log loss', 'Lower is better'],
] as const;
const number = (value: number | undefined) => value === undefined ? '—' : value.toFixed(4);

export function ModelInfo() {
  const model = useModel();
  const [offset, setOffset] = useState(0);
  const history = useModelHistory(offset);
  const client = useQueryClient();
  const current = model.data;
  const maximum = Math.max(0, ...(current?.feature_importance.map((item) => item.mean_absolute_contribution) ?? []));
  function refresh() {
    void client.invalidateQueries({ queryKey: ['model'] });
    void client.invalidateQueries({ queryKey: ['model-history'] });
  }
  return <>
    <div className="intro"><div><p className="eyebrow">Model registry / Transparent predictions</p><h1>Understand the model behind the map.</h1><p>Compare validation results, inspect global explanations, and trace every registered training run.</p></div><button className="secondary" disabled={model.isFetching || history.isFetching} onClick={refresh}>{model.isFetching || history.isFetching ? 'Loading models…' : 'Refresh models'}</button></div>
    {model.isPending && <p className="state-card" role="status">Loading model information…</p>}
    {model.isError && <div className="state-card error" role="alert"><strong>{model.error instanceof ApiError && model.error.status === 404 ? 'No passing model available' : 'Model information unavailable'}</strong><p>{model.error.message}</p><p>{current ? 'Displaying the previous model information.' : 'Registered history is shown separately below. Train with make train to register a model.'}</p><button onClick={() => void model.refetch()}>Retry model</button></div>}
    {current && <>
      <section className="model-status" aria-label="Model status"><div><p className="eyebrow">Latest passing model</p><code id="model-version">{current.model_version}</code><p>Trained {date(current.trained_at)} UTC · {current.horizon_days}-day prediction horizon</p></div><div><span className="risk-badge low">Quality gate passed</span><p>{current.scored_model_version === current.model_version ? 'Scored model matches available model' : current.scored_model_version ? 'A newer passing model is available' : 'The network has not been scored'}</p><small>Scored version: <code id="scored-model-version">{current.scored_model_version ?? 'None'}</code></small></div></section>
      <section className="summary-grid model-metrics" aria-label="Validation highlights">
        {[['PR-AUC', 'pr_auc'], ['ROC-AUC', 'roc_auc'], ['Brier score', 'brier_score'], ['Precision · top 5%', 'precision_at_top_k']].map(([label, metric]) => <article key={metric}><span>{label}</span><strong>{number(current.metrics[`xgboost_${metric}`])}</strong><small>Calibrated XGBoost · held-out validation</small></article>)}
      </section>
      <div className="model-grid"><section className="model-card" aria-label="Validation comparison"><div className="section-heading"><h2>Validation performance</h2><span>Chronological holdout</span></div><p className="detail-caption">PR-AUC is average precision. Compare against the calibrated logistic baseline on the same validation asset-months. A passing gate requires positive PR-AUC lift.</p>
        <div className="table-scroll"><table><thead><tr><th scope="col">Metric</th><th scope="col">Logistic baseline</th><th scope="col">XGBoost</th></tr></thead><tbody>{metricRows.map(([metric, label, direction]) => <tr key={metric}><th scope="row">{label}<small>{direction}</small></th><td>{number(current.metrics[`baseline_${metric}`])}</td><td>{number(current.metrics[`xgboost_${metric}`])}</td></tr>)}</tbody></table></div>
        <div className="validation-note"><span>PR-AUC lift <strong>{number(current.metrics.pr_auc_lift)}</strong></span><span>Validation asset-months <strong>{current.metrics.xgboost_rows?.toLocaleString() ?? '—'}</strong></span><span>Positive labels <strong>{current.metrics.xgboost_positives?.toLocaleString() ?? '—'}</strong></span></div>
        <p className="detail-caption">Synthetic data only. These metrics do not establish performance on a real distribution network.</p>
      </section><section className="model-card" aria-label="Global feature importance"><div className="section-heading"><h2>Global feature importance</h2><span>Exact TreeSHAP</span></div><p className="detail-caption">Mean absolute contribution in uncalibrated XGBoost log-odds. This measures magnitude, not direction or causal effect; it does not add up to a calibrated probability.</p>
        {current.feature_importance.length ? <ol className="importance-list">{current.feature_importance.map((item) => <li key={item.feature}><div><span>{item.feature.replaceAll('_', ' ')}</span><strong>{item.mean_absolute_contribution.toFixed(4)}</strong></div><div className="importance-track" aria-hidden="true"><i style={{ width: `${maximum ? item.mean_absolute_contribution / maximum * 100 : 0}%` }} /></div></li>)}</ol> : <p>No global explanations available.</p>}
      </section></div>
      <section className="model-card provenance" aria-label="Model provenance"><h2>Run provenance</h2><dl><div><dt>Training data SHA-256</dt><dd><code>{current.data_hash}</code></dd></div><div><dt>Source Git SHA</dt><dd><code>{current.git_sha}</code></dd></div><div><dt>Feature list ({current.features.length})</dt><dd>{current.features.join(', ')}</dd></div></dl></section>
    </>}
    <section className="model-card history-card" aria-label="Registered version history"><div className="section-heading"><h2>Registered version history</h2>{history.data && <span>{history.data.pagination.total} runs</span>}</div><p className="detail-caption">Newest training time first. Failed quality gates remain visible. These are registered evaluation records; a passed gate does not certify current artifact-file availability.</p>
      {history.isPending && <p role="status">Loading version history…</p>}
      {history.isError && <div role="alert"><p>{history.error.message}</p><button onClick={() => void history.refetch()}>Retry history</button>{history.data && <p>Displaying the previous history page.</p>}</div>}
      {history.data && <>{history.data.items.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Version / trained UTC</th><th scope="col">Quality gate</th><th scope="col">PR-AUC / lift</th><th scope="col">Provenance</th></tr></thead><tbody>{history.data.items.map((run) => <tr key={run.model_version}><th scope="row"><code>{run.model_version}</code><small>{new Date(run.trained_at).toISOString()}</small>{run.model_version === current?.model_version && <span className="risk-badge low">Available</span>} {run.model_version === current?.scored_model_version && <span className="risk-badge medium">Scored</span>}</th><td><span className={`risk-badge ${run.quality_gate_passed ? 'low' : 'critical'}`}>{run.quality_gate_passed ? 'Passed' : 'Failed'}</span></td><td>{number(run.metrics.xgboost_pr_auc)}<small>Lift {number(run.metrics.pr_auc_lift)}</small></td><td><small>Git <code title={run.git_sha}>{run.git_sha.slice(0, 12)}</code></small><small>Data <code title={run.data_hash}>{run.data_hash.slice(0, 12)}</code></small></td></tr>)}</tbody></table></div> : <p>No training runs registered.</p>}
        {history.data.pagination.total > 10 && <nav className="history-pagination" aria-label="Version history pagination"><button disabled={offset === 0 || history.isFetching} onClick={() => setOffset((value) => Math.max(0, value - 10))}>Newer versions</button><span>{history.data.items.length ? offset + 1 : 0}–{offset + history.data.items.length} of {history.data.pagination.total}</span><button disabled={history.data.pagination.next_offset === null || history.isFetching} onClick={() => setOffset(history.data?.pagination.next_offset ?? offset)}>Older versions</button></nav>}
      </>}
    </section>
  </>;
}
