import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { post, uploadFile } from '../api/client';
import { busy, importError, useImportBatch, useImportHistory } from '../api/imports';
import type { ImportBatchDetail, LayerType, ValidateImport } from '../api/generated';
import { ImportPreviewMap } from '../components/ImportPreviewMap';

const fields = ['external_id', 'latitude', 'longitude', 'geometry', 'capacity_kva', 'install_date', 'load_factor', 'pole_id', 'feeder_id', 'last_maintenance_date', 'material', 'vegetation_index'];
export function duplicateMappings(mapping: Record<string, string>): boolean {
  const selected = Object.values(mapping).filter(Boolean);
  return new Set(selected).size !== selected.length;
}
function ErrorMessage({ error }: { error: Error | null }) { return error ? <p className="error" role="alert">{/^[A-Z_]+$/.test(error.message) ? importError(error.message) : error.message}</p> : null; }
function Report({ batch }: { batch: ImportBatchDetail }) { return <a href={`/api/v1/imports/${batch.id}/errors.csv`} download>Download error CSV</a>; }

export function Upload({ batchId, onSelect }: { batchId: string | null; onSelect: (id: string | null) => void }) {
  const client = useQueryClient();
  const [offset, setOffset] = useState(0);
  const history = useImportHistory(offset);
  const [undo, setUndo] = useState<ImportBatchDetail | null>(null);
  const rollback = useMutation({ retry: false, mutationFn: (id: string) => post('POST /api/v1/imports/{batch_id}/rollback', { batch_id: id }, undefined),
    onSuccess: (batch) => { client.setQueryData(['import', batch.id], batch); void client.invalidateQueries({ queryKey: ['imports'] }); setUndo(null); onSelect(batch.id); } });
  return <div className="upload-page">
    <div className="intro"><div><p className="eyebrow">Your network / Data imports</p><h1>Bring your assets onto the map.</h1><p>Preview and validate before saving. Uploaded data stays on your deployment.</p></div></div>
    <ol className="upload-steps" aria-label="Import steps">{['Upload', 'Map columns', 'Preview & validate', 'Commit', 'Result'].map((step) => <li key={step}>{step}</li>)}</ol>
    {batchId ? <BatchWorkspace key={batchId} id={batchId} close={() => onSelect(null)} onRollback={setUndo} /> : <UploadForm onUploaded={(batch) => { client.setQueryData(['import', batch.id], batch); void client.invalidateQueries({ queryKey: ['imports'] }); onSelect(batch.id); }} />}
    <section className="state-card import-history"><h2>Import history</h2>
      {history.isPending && <p role="status">Loading import history…</p>}
      {history.isError && <div role="alert"><p>Could not load import history.</p><button onClick={() => void history.refetch()}>Retry history</button></div>}
      {history.data && <>{!history.data.items.length ? <p>No imports on this page yet.</p> : <div className="table-scroll"><table><thead><tr><th>File</th><th>Layer / format</th><th>Status</th><th>Inserted / updated / skipped</th><th>Actions</th></tr></thead><tbody>{history.data.items.map((batch) => <tr key={batch.id}><td>{batch.filename}<small>{new Date(batch.created_at).toLocaleString()}</small></td><td>{batch.layer_type} / {batch.format ?? 'Detecting'}</td><td>{batch.status}{busy(batch) && ` · ${batch.job?.operation}`}</td><td>{batch.row_counts.inserted} / {batch.row_counts.updated} / {batch.row_counts.invalid}</td><td><button onClick={() => onSelect(batch.id)}>Open</button>{batch.status === 'imported' && <button disabled={busy(batch)} onClick={() => { rollback.reset(); setUndo(batch); }}>Rollback</button>}</td></tr>)}</tbody></table></div>}
        <div className="import-actions"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous imports</button><span>{history.data.total} batches</span><button disabled={offset + 20 >= history.data.total} onClick={() => setOffset(offset + 20)}>Next imports</button></div></>}
    </section>
    {undo && <section className="state-card rollback-confirm" role="alertdialog" aria-modal="true" aria-labelledby="rollback-title"><h2 id="rollback-title">Roll back this batch?</h2><p>This removes inserted assets, restores updated assets, and clears network risk scores. Later dependent batches must be rolled back first.</p><ErrorMessage error={rollback.error} /><button disabled={rollback.isPending} onClick={() => rollback.mutate(undo.id)}>Confirm rollback</button><button disabled={rollback.isPending} onClick={() => { setUndo(null); rollback.reset(); }}>Keep batch</button></section>}
  </div>;
}

function UploadForm({ onUploaded }: { onUploaded: (batch: ImportBatchDetail) => void }) {
  const [layer, setLayer] = useState<LayerType>('transformer');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');
  const upload = useMutation({ retry: false, mutationFn: () => { if (!file) throw new Error('Choose a file.'); return uploadFile(file, layer); }, onSuccess: onUploaded });
  function choose(files: FileList | null) { setFileError(files && files.length > 1 ? 'Choose one file at a time.' : ''); setFile(files?.length === 1 ? files[0] : null); }
  return <form className="state-card" onSubmit={(event) => { event.preventDefault(); upload.mutate(); }}>
    <h2>Upload a layer</h2><label>Layer type<select value={layer} disabled={upload.isPending} onChange={(event) => setLayer(event.target.value as LayerType)}><option value="transformer">Transformers</option><option value="pole">Poles</option><option value="feeder_line">Feeder lines</option></select></label>
    <div className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (!upload.isPending) choose(event.dataTransfer.files); }}><label>Drop a file here or choose a file<input type="file" accept=".csv,.zip,.geojson,.json" disabled={upload.isPending} onChange={(event) => choose(event.target.files)} /></label><p>CSV, GeoJSON/JSON, or a zipped Shapefile (.shp, .shx, .dbf; include .prj).</p><p>Points for transformers/poles; LineString or MultiLineString for feeder lines. CSV feeder geometry uses WKT.</p>{file && <strong>{file.name}</strong>}</div>
    <p>Default limits: 25 MB and 100,000 features; your deployment can configure these. Staged files expire automatically and are deleted after commit or rollback.</p>
    <div className="import-actions"><a href={`/api/v1/imports/templates/${layer}.csv`} download>CSV template</a><a href={`/api/v1/imports/templates/${layer}.geojson`} download>Synthetic GeoJSON example</a></div>
    {fileError && <p role="alert">{fileError}</p>}<ErrorMessage error={upload.error} /><button disabled={!file || !!fileError || upload.isPending}>{upload.isPending ? 'Uploading…' : 'Upload and inspect'}</button>
  </form>;
}

function BatchWorkspace({ id, close, onRollback }: { id: string; close: () => void; onRollback: (batch: ImportBatchDetail) => void }) {
  const query = useImportBatch(id);
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ValidateImport | null>(null);
  const [partial, setPartial] = useState(false);
  const [rescore, setRescore] = useState(false);
  const [defaults, setDefaults] = useState(false);
  function saved(batch: ImportBatchDetail) { client.setQueryData(['import', id], batch); void client.invalidateQueries({ queryKey: ['imports'] }); }
  const validate = useMutation({ retry: false, mutationFn: (options: ValidateImport) => post('POST /api/v1/imports/{batch_id}/validate', { batch_id: id }, options), onSuccess: (batch) => { saved(batch); setEditing(false); setPartial(false); } });
  const commit = useMutation({ retry: false, mutationFn: () => post('POST /api/v1/imports/{batch_id}/commit', { batch_id: id }, { valid_rows_only: partial, rescore, accept_scoring_defaults: rescore && defaults }), onSuccess: saved });
  const batch = query.data;
  return <section className="state-card import-workspace"><div className="import-actions"><h2>{batch?.filename ?? 'Import batch'}</h2><button onClick={close}>Close / new upload</button></div>
    {query.isPending && <p role="status">Loading batch…</p>}{query.isError && <div role="alert"><p>Could not refresh the batch. Saved work is retained.</p><button onClick={() => void query.refetch()}>Retry batch</button></div>}
    {batch && <><p>{batch.layer_type} · {batch.format ?? 'Detecting format'} · {batch.status}</p>
      {busy(batch) ? <div role="status"><p>{batch.status === 'imported' ? 'Import saved. ' : ''}{batch.job?.operation} {batch.job?.status} — {batch.job?.processed} / {batch.job?.total} rows</p><progress value={batch.job?.total ? batch.job.processed : undefined} max={batch.job?.total || undefined} /></div> : <>
        {(batch.error_code || batch.job?.status === 'failed') && <div role="alert"><p>{importError(batch.job?.error_code ?? batch.error_code)}</p><Report batch={batch} />{batch.job?.operation === 'rescore' && <p><a href="#model">Review scoring on the Model page</a></p>}</div>}
        {batch.warnings.length > 0 && <p>Warnings: {batch.warnings.join(', ')}</p>}
        {(['uploaded', 'validated'].includes(batch.status) || (batch.status === 'failed' && batch.detected_columns.length > 0)) && <>
          {(batch.status !== 'validated' || editing) ? <MappingForm batch={batch} draft={draft} pending={validate.isPending} onValidate={(options) => { setDraft(options); validate.mutate(options); }} /> : <>
            <p><strong>{batch.row_counts.total} total · {batch.row_counts.valid} valid · {batch.row_counts.invalid} invalid</strong></p>
            <button onClick={() => { commit.reset(); setEditing(true); }}>Edit column mapping</button>
            <Preview batch={batch} />
            {batch.row_counts.invalid > 0 && <label><input type="checkbox" checked={partial} onChange={(event) => setPartial(event.target.checked)} />Import valid rows only; skip {batch.row_counts.invalid} invalid rows</label>}
            <label><input type="checkbox" checked={rescore} onChange={(event) => setRescore(event.target.checked)} />Rescore the network after import</label>
            {rescore && <><p>Scores use historical synthetic weather/outage context and are demo estimates. Assets installed after the prediction cutoff remain unscored.</p><label><input type="checkbox" checked={defaults} onChange={(event) => setDefaults(event.target.checked)} />Allow training medians for missing model attributes</label></>}
            <button disabled={commit.isPending || query.isError || batch.row_counts.valid === 0 || (batch.row_counts.invalid > 0 && !partial)} onClick={() => commit.mutate()}>{commit.isPending ? 'Saving…' : 'Commit import'}</button>
            <p>Closing without committing leaves real assets unchanged. Staged data expires {new Date(batch.expires_at).toLocaleString()}.</p>
          </>}
          <ErrorMessage error={validate.error} /><ErrorMessage error={commit.error} />
        </>}
        {batch.status === 'imported' && <div className="import-result"><h3>Import saved</h3><p>{batch.row_counts.inserted} inserted · {batch.row_counts.updated} updated · {batch.row_counts.invalid} skipped</p><div className="import-actions"><Report batch={batch} /><a href={`#map?import=${batch.id}`}>View on map</a><button onClick={() => onRollback(batch)}>Rollback</button></div></div>}
        {batch.status === 'rolled_back' && <p role="status">Batch rolled back. Insertions were removed and updates restored. Rescore the network to refresh risk estimates.</p>}
      </>}
    </>}
  </section>;
}

function MappingForm({ batch, draft, pending, onValidate }: { batch: ImportBatchDetail; draft: ValidateImport | null; pending: boolean; onValidate: (options: ValidateImport) => void }) {
  const [mapping, setMapping] = useState<Record<string, string>>(() => Object.fromEntries(fields.map((field) => [field, (draft?.column_mapping ?? batch.column_mapping)[field] ?? ''])));
  const [crs, setCrs] = useState(draft?.source_crs ?? batch.crs_selected ?? batch.crs_detected ?? '');
  const [dates, setDates] = useState<NonNullable<ValidateImport['date_format']>>(draft?.date_format ?? 'auto');
  const duplicates = duplicateMappings(mapping);
  return <form onSubmit={(event) => { event.preventDefault(); if (!duplicates) onValidate({ column_mapping: mapping, source_crs: crs.trim() || null, date_format: dates }); }}>
    <h3>Map columns</h3><p>Suggested matches come from your file. External ID is required. Map latitude/longitude or WKT geometry for tabular points; embedded spatial geometry is used automatically. Parent IDs match external IDs and unresolved references produce warnings.</p>
    <div className="mapping-grid">{fields.map((field) => <label key={field}>{field}<select required={field === 'external_id'} value={mapping[field]} disabled={pending} onChange={(event) => setMapping({ ...mapping, [field]: event.target.value })}><option value="">Not mapped</option>{batch.detected_columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></label>)}</div>
    {duplicates && <p role="alert">Each source column can map to only one field.</p>}
    <label>Source CRS<input required={!batch.crs_detected} maxLength={4096} value={crs} disabled={pending} placeholder="EPSG:4326" onChange={(event) => setCrs(event.target.value)} /></label><p>Detected: {batch.crs_detected ?? 'Unknown — choose a CRS. Missing or unreadable .prj is never guessed.'} · Geometry is reprojected to EPSG:4326.</p>
    <label>Date convention<select value={dates} disabled={pending} onChange={(event) => setDates(event.target.value as NonNullable<ValidateImport['date_format']>)}><option value="auto">Automatic (reject ambiguous dates)</option><option value="day_first">Day first</option><option value="month_first">Month first</option></select></label>
    <button disabled={pending || duplicates}>{pending ? 'Scheduling validation…' : 'Validate all rows'}</button><p>Validation does not write to the asset tables.</p>
  </form>;
}

function Preview({ batch }: { batch: ImportBatchDetail }) {
  const columns = batch.detected_columns.slice(0, 12);
  return <section><h3>Preview & validation</h3><p>First {batch.preview.length} rows. All {batch.row_counts.total} rows were validated. The CSV contains the full error report.</p><Report batch={batch} /><ImportPreviewMap rows={batch.preview} />
    <div className="table-scroll"><table><thead><tr><th>Row</th>{columns.map((column) => <th key={column}>{column}</th>)}<th>Errors / warnings</th></tr></thead><tbody>{batch.preview.map((row) => <tr key={row.row_number} className={row.errors.length ? 'invalid-row' : ''}><th>{row.row_number}</th>{columns.map((column) => <td key={column} className={row.errors.some((issue) => (batch.column_mapping[issue.field] ?? issue.field) === column) ? 'invalid-cell' : ''}>{String(typeof row.properties[column] === 'object' ? JSON.stringify(row.properties[column]) : row.properties[column] ?? '').slice(0, 160)}</td>)}<td>{[...row.errors, ...row.warnings].map((issue, index) => <p key={index}>{issue.field}: {issue.reason}</p>)}</td></tr>)}</tbody></table></div>
  </section>;
}
