import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  getModels, getApiKeys, getVisionModels, uploadOcrDocument, listOcrDocuments, getOcrDocument, deleteOcrDocument,
  correctOcrField, fetchOcrPageImageUrl,
} from '../api.js';

const STATUS_LABELS = {
  queued: 'Queued',
  processing: 'Reading…',
  done: 'Done',
  failed: 'Failed',
};

// Documents that aren't finished yet get polled for status — there's no
// push channel for background-task progress here, unlike chat's SSE stream.
const POLL_MS = 3000;

function StatusBadge({ status }) {
  return <span className={`ocr-status ocr-status-${status}`}>{STATUS_LABELS[status] || status}</span>;
}

function formatDuration(seconds) {
  if (seconds == null) return null;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

// Backend timestamps are naive UTC (no "Z") — same convention as MessageBubble's
// formatTimestamp, so treat them the same way here.
function toDate(value) {
  const iso = /(Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`;
  return new Date(iso);
}

// Ticks once a second while a document is still queued/processing, so you can
// see it counting up in real time instead of just staring at "Reading…" with
// no feedback. Once it's done, the backend's own measured processing_seconds
// takes over (see the caller) — this is only ever shown before that exists.
function useLiveElapsedSeconds(sinceIso, active) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  if (!active || !sinceIso) return null;
  return Math.max(0, (now - toDate(sinceIso).getTime()) / 1000);
}

// A field with both a row and a column/option label is one cell of a table
// on the page (e.g. "Wickeln" x "Datum" -> "02. Aug 2024"). Showing those as
// a flat list ("Wickeln / Datum" in one cell, repeated per row) loses the
// grid a human would actually want to read — so when there are enough of
// them, pivot them back into a real table instead.
const MIN_FIELDS_FOR_GRID = 4;

function buildGrid(fields) {
  const tableFields = fields.filter((f) => f.row_label && (f.column_label || f.option_label));
  if (tableFields.length < MIN_FIELDS_FOR_GRID) return null;

  const rows = [];
  const rowIndex = new Map();
  const cols = [];
  const colIndex = new Map();
  const cells = new Map(); // "row|col" -> field

  for (const f of tableFields) {
    const r = f.row_label;
    const c = f.column_label
      ? (f.option_label ? `${f.column_label} – ${f.option_label}` : f.column_label)
      : f.option_label;
    if (!rowIndex.has(r)) { rowIndex.set(r, rows.length); rows.push(r); }
    if (!colIndex.has(c)) { colIndex.set(c, cols.length); cols.push(c); }
    cells.set(`${r}|${c}`, f);
  }
  return { rows, cols, cells };
}

function GridCell({ field, onSave }) {
  const [editing, setEditing] = useState(false);
  const [textValue, setTextValue] = useState(field?.text_value || '');
  const [checkboxState, setCheckboxState] = useState(field?.checkbox_state || '');

  if (!field) return <span className="ocr-muted">—</span>;

  if (editing) {
    const save = async () => {
      await onSave(field.id, {
        text_value: field.text_value !== null ? textValue : null,
        checkbox_state: field.checkbox_state !== null ? (checkboxState || 'ambiguous') : null,
      });
      setEditing(false);
    };
    return field.checkbox_state !== null ? (
      <select autoFocus value={checkboxState} onChange={(e) => setCheckboxState(e.target.value)} onBlur={save}>
        <option value="checked">checked</option>
        <option value="unchecked">unchecked</option>
        <option value="ambiguous">ambiguous</option>
      </select>
    ) : (
      <input
        autoFocus value={textValue} onChange={(e) => setTextValue(e.target.value)}
        onBlur={save} onKeyDown={(e) => e.key === 'Enter' && save()}
      />
    );
  }

  return (
    <button
      type="button"
      className={`ocr-grid-cell-btn${field.needs_review && !field.reviewed ? ' ocr-field-review' : ''}`}
      onClick={() => setEditing(true)}
      title="Click to correct"
    >
      {field.checkbox_state !== null
        ? <span className={`ocr-checkbox-state ocr-checkbox-${field.checkbox_state}`}>{field.checkbox_state}</span>
        : (field.text_value || <span className="ocr-muted">—</span>)}
    </button>
  );
}

function FieldGrid({ grid, onSave }) {
  return (
    <div className="ocr-grid-wrap">
      <table className="ocr-fields-grid">
        <thead>
          <tr>
            <th></th>
            {grid.cols.map((c) => <th key={c}>{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {grid.rows.map((r) => (
            <tr key={r}>
              <th>{r}</th>
              {grid.cols.map((c) => (
                <td key={c}><GridCell field={grid.cells.get(`${r}|${c}`)} onSave={onSave} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// A field belongs to a table cell only if it has a row label plus a column
// or option label — that's the signal buildGrid() also uses to pivot a run
// of these into a real grid instead of a flat, order-scrambled dump.
function isTableCell(f) {
  return !!(f.row_label && (f.column_label || f.option_label));
}

// Splits a page's fields into ordered runs — consecutive table-cell fields
// become one 'table' run, everything else becomes one 'plain' run — so the
// page renders in the SAME reading order the fields came back in (a header
// above a table stays above it; a signature block after a table stays
// after it), instead of always yanking every table cell to the top and
// dumping everything else in one pile below.
function splitIntoRuns(fields) {
  const runs = [];
  let current = null;
  for (const f of fields) {
    const type = isTableCell(f) ? 'table' : 'plain';
    if (!current || current.type !== type) {
      current = { type, fields: [] };
      runs.push(current);
    }
    current.fields.push(f);
  }
  return runs;
}

// A plain (non-table) field, rendered as one readable row: its label (the
// question it belongs to, or the option it is, if any) next to its value —
// or, for a bare label/title with no question of its own, the text spans
// the full row instead of sitting next to an empty, confusing "—" label.
function PlainFieldRow({ field, onSave }) {
  const label = field.question || field.option_label || null;
  const reviewClass = field.needs_review && !field.reviewed ? ' ocr-field-review' : '';
  return (
    <tr className={reviewClass}>
      {label && <td className="ocr-plain-label">{label}</td>}
      <td colSpan={label ? 1 : 2}><GridCell field={field} onSave={onSave} /></td>
      <td className="ocr-plain-status">
        {field.reviewed ? (
          <span className="ocr-reviewed-tag">Reviewed</span>
        ) : field.needs_review ? (
          <span className="ocr-review-tag">Needs review</span>
        ) : field.confidence != null ? (
          <span className="ocr-muted">{Math.round(field.confidence * 100)}%</span>
        ) : null}
      </td>
    </tr>
  );
}

function PlainFieldList({ fields, onSave }) {
  return (
    <table className="ocr-fields-table">
      <tbody>
        {fields.map((f) => <PlainFieldRow key={f.id} field={f} onSave={onSave} />)}
      </tbody>
    </table>
  );
}

function DocumentDetail({ documentId, onDeleted }) {
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(null);
  const [activePage, setActivePage] = useState(1);
  const [imageUrl, setImageUrl] = useState(null);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const data = await getOcrDocument(documentId);
      setDoc(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }, [documentId]);

  useEffect(() => {
    let cancelled = false;
    setDoc(null);
    setActivePage(1);
    load();
    pollRef.current = setInterval(async () => {
      const data = await load();
      if (cancelled) return;
      if (data && data.status !== 'queued' && data.status !== 'processing') {
        clearInterval(pollRef.current);
      }
    }, POLL_MS);
    return () => { cancelled = true; clearInterval(pollRef.current); };
  }, [documentId, load]);

  useEffect(() => {
    let objectUrl = null;
    let cancelled = false;
    setImageUrl(null);
    fetchOcrPageImageUrl(documentId, activePage).then((url) => {
      if (cancelled) { URL.revokeObjectURL(url); return; }
      objectUrl = url;
      setImageUrl(url);
    }).catch(() => {});
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [documentId, activePage]);

  const handleSave = async (fieldId, data) => {
    await correctOcrField(fieldId, data);
    load();
  };

  // Every hook must run on every render regardless of doc/error state below —
  // calling this after the early returns made React see a different number
  // of hooks between the "still loading" and "loaded" renders (error #310,
  // a blank page with no visible cause). doc?.created_at/doc?.status are
  // undefined until doc loads, which the hook already treats as "inactive".
  const isActive = doc?.status === 'queued' || doc?.status === 'processing';
  const liveElapsed = useLiveElapsedSeconds(doc?.created_at, isActive);

  if (error) return <div className="ocr-empty">Failed to load: {error}</div>;
  if (!doc) return <div className="ocr-empty">Loading…</div>;

  const page = doc.pages.find((p) => p.page_number === activePage);
  const reviewCount = doc.pages.flatMap((p) => p.fields).filter((f) => f.needs_review && !f.reviewed).length;
  const timeLabel = isActive
    ? (liveElapsed != null ? `${formatDuration(liveElapsed)} so far…` : null)
    : (doc.processing_seconds != null ? `read in ${formatDuration(doc.processing_seconds)}` : null);

  return (
    <div className="ocr-detail">
      <div className="ocr-detail-header">
        <div>
          <h2>{doc.filename}</h2>
          <div className="ocr-detail-meta">
            <StatusBadge status={doc.status} />
            <span>{doc.page_count} page{doc.page_count !== 1 ? 's' : ''}</span>
            <span>{doc.provider}/{doc.model}</span>
            {timeLabel && <span className="ocr-time">{timeLabel}</span>}
            {reviewCount > 0 && <span className="ocr-review-tag">{reviewCount} field{reviewCount !== 1 ? 's' : ''} need review</span>}
          </div>
          {doc.error && <div className="ocr-error-note">{doc.error}</div>}
        </div>
        <button
          type="button"
          className="ocr-delete-btn"
          onClick={() => onDeleted(doc.id)}
        >
          Delete
        </button>
      </div>

      {doc.page_count > 1 && (
        <div className="ocr-page-tabs">
          {doc.pages.map((p) => (
            <button
              key={p.page_number}
              type="button"
              className={`ocr-page-tab${p.page_number === activePage ? ' active' : ''}`}
              onClick={() => setActivePage(p.page_number)}
            >
              Page {p.page_number}
              {p.status !== 'done' && <StatusBadge status={p.status} />}
              {p.status === 'done' && p.processing_seconds != null && (
                <span className="ocr-time">{formatDuration(p.processing_seconds)}</span>
              )}
            </button>
          ))}
        </div>
      )}

      <div className="ocr-page-body">
        <div className="ocr-page-image">
          {imageUrl ? <img src={imageUrl} alt={`Page ${activePage}`} /> : <div className="ocr-empty">Loading page…</div>}
        </div>
        <div className="ocr-page-fields">
          {!page ? (
            <div className="ocr-empty">—</div>
          ) : page.status === 'queued' || page.status === 'processing' ? (
            <div className="ocr-empty">Reading this page with {doc.provider}/{doc.model}…</div>
          ) : page.status === 'failed' ? (
            <div className="ocr-error-note">{page.error || 'This page failed to process.'}</div>
          ) : page.fields.length === 0 ? (
            <div className="ocr-empty">No fields found on this page.</div>
          ) : (() => {
            const runs = splitIntoRuns(page.fields);
            const anyGrid = runs.some((r) => r.type === 'table' && buildGrid(r.fields));
            return (
              <>
                {page.error && <div className="ocr-warning-note">{page.error}</div>}
                {runs.map((run, i) => {
                  if (run.type === 'table') {
                    const grid = buildGrid(run.fields);
                    if (grid) return <FieldGrid key={i} grid={grid} onSave={handleSave} />;
                    // Too few cells in this run to be worth pivoting — show them plainly instead.
                  }
                  return <PlainFieldList key={i} fields={run.fields} onSave={handleSave} />;
                })}
                {anyGrid && <p className="ocr-grid-hint">Click any cell to correct it.</p>}
              </>
            );
          })()}
        </div>
      </div>
    </div>
  );
}

export default function DocumentOcrTab() {
  const [documents, setDocuments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  // { provider, model } pairs the user can actually pick from: every provider
  // they have an API key for, restricted to models known to be vision-capable
  // (see backend/providers/__init__.py) — except "local", which is never
  // restricted, since a local GGUF's capabilities aren't something this app
  // can know in advance (same rule ModelSelector.jsx uses for the chat view).
  const [options, setOptions] = useState([]);
  const [selected, setSelected] = useState(null); // { provider, model } | null
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const loadDocuments = useCallback(async () => {
    try {
      setDocuments(await listOcrDocuments());
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    loadDocuments();

    (async () => {
      try {
        const [keys, visionModels] = await Promise.all([getApiKeys(), getVisionModels()]);
        const configuredProviders = keys.map((k) => k.provider);
        const built = [];
        for (const provider of configuredProviders) {
          const isLocal = provider === 'local';
          const { models: providerModels } = await getModels(provider).catch(() => ({ models: [] }));
          const allowed = isLocal ? providerModels : providerModels.filter((m) => (visionModels[provider] || []).includes(m));
          for (const model of allowed) built.push({ provider, model });
        }
        setOptions(built);
        setSelected(built[0] || null);
      } catch (err) {
        console.error('Failed to load vision-capable models:', err);
        setOptions([]);
      }
    })();
  }, [loadDocuments]);

  // The list only ever reflects the last fetch — nothing pushes it updates
  // when a background extraction finishes, so without this a document could
  // sit showing "Reading…" forever even after it's actually done (the open
  // detail view polls itself, but the list row it came from never does).
  // Keeps polling only while something here is still queued/processing, and
  // stops on its own once everything settles.
  useEffect(() => {
    const hasActive = documents.some((d) => d.status === 'queued' || d.status === 'processing');
    if (!hasActive) return;
    const id = setInterval(loadDocuments, POLL_MS);
    return () => clearInterval(id);
  }, [documents, loadDocuments]);

  const handleUpload = async (file) => {
    if (!file) return;
    if (!selected) {
      setError('No vision-capable model available — add an API key for a provider that supports images (or load one on your local server) under Settings → API Keys.');
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const doc = await uploadOcrDocument(file, selected.provider, selected.model);
      await loadDocuments();
      setSelectedId(doc.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const [pendingDelete, setPendingDelete] = useState(null); // { id, filename } | null

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const id = pendingDelete.id;
    setPendingDelete(null);
    await deleteOcrDocument(id);
    if (selectedId === id) setSelectedId(null);
    loadDocuments();
  };

  return (
    <div className="ocr-tab">
      <div className="ocr-list-pane">
        <div className="ocr-upload-box">
          <label className="ocr-model-picker">
            Model
            <select
              value={selected ? `${selected.provider}::${selected.model}` : ''}
              onChange={(e) => {
                const [provider, model] = e.target.value.split('::');
                setSelected({ provider, model });
              }}
            >
              {options.length === 0 && <option value="">No vision-capable models found</option>}
              {options.map((o) => (
                <option key={`${o.provider}::${o.model}`} value={`${o.provider}::${o.model}`}>
                  {o.provider}/{o.model}
                </option>
              ))}
            </select>
          </label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
            style={{ display: 'none' }}
            onChange={(e) => handleUpload(e.target.files[0])}
          />
          <button
            type="button"
            className="ocr-upload-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? 'Uploading…' : 'Upload scanned form'}
          </button>
          {error && <div className="ocr-error-note">{error}</div>}
        </div>

        <div className="ocr-doc-list">
          {documents.length === 0 ? (
            <div className="ocr-empty">No documents yet. Upload a scanned form to get started.</div>
          ) : (
            documents.map((doc) => (
              <div
                key={doc.id}
                className={`ocr-doc-item${doc.id === selectedId ? ' active' : ''}`}
                onClick={() => setSelectedId(doc.id)}
              >
                <span className="ocr-doc-item-name">{doc.filename}</span>
                <StatusBadge status={doc.status} />
                <button
                  type="button"
                  className="ocr-doc-item-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPendingDelete({ id: doc.id, filename: doc.filename });
                  }}
                  title="Delete document"
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="ocr-main-pane">
        {selectedId ? (
          <DocumentDetail
            documentId={selectedId}
            onDeleted={(id) => {
              const doc = documents.find((d) => d.id === id);
              setPendingDelete({ id, filename: doc?.filename || 'this document' });
            }}
          />
        ) : (
          <div className="ocr-empty ocr-empty-large">
            Select a document, or upload a new scanned form to read it with your local vision model.
          </div>
        )}
      </div>

      {pendingDelete && (
        <div className="modal-overlay" onClick={() => setPendingDelete(null)}>
          <div className="modal confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Delete document?</h2>
              <button className="modal-close" onClick={() => setPendingDelete(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p className="confirm-dialog-text">
                This will permanently delete <strong>&ldquo;{pendingDelete.filename}&rdquo;</strong> and
                everything extracted from it. This can't be undone.
              </p>
              <div className="confirm-dialog-actions">
                <button type="button" className="confirm-dialog-cancel" onClick={() => setPendingDelete(null)}>
                  Cancel
                </button>
                <button type="button" className="confirm-dialog-delete" onClick={confirmDelete}>
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
