import React, { useState, useEffect } from 'react';
import { getMemories, setMemoryPinned, deleteMemory } from '../api.js';

const CATEGORY_LABELS = {
  identity: 'Identity',
  preference: 'Preference',
  fact: 'Fact',
  contact: 'Contact',
  project: 'Project',
  goal: 'Goal',
};

// The "Memories" tab content inside the unified Settings modal — no modal
// chrome of its own, that's owned by SettingsModal now.
export default function MemoriesTab() {
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null); // memory | null

  useEffect(() => {
    loadMemories();
  }, []);

  const loadMemories = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMemories();
      setMemories(data);
    } catch (err) {
      console.error('Failed to load memories:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleTogglePin = async (memory) => {
    setBusyId(memory.id);
    try {
      const updated = await setMemoryPinned(memory.id, !memory.pinned);
      setMemories((prev) => prev.map((m) => (m.id === memory.id ? updated : m)));
    } catch (err) {
      alert(`Failed to update: ${err.message}`);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (memory) => {
    setPendingDelete(null);
    setBusyId(memory.id);
    try {
      await deleteMemory(memory.id);
      setMemories((prev) => prev.filter((m) => m.id !== memory.id));
    } catch (err) {
      alert(`Failed to delete: ${err.message}`);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="settings-pane-body">
      <p className="memories-intro">
        Durable facts picked up from what you've said, automatically fed back into
        future conversations. Pinned facts (e.g. your name, location) are included in
        every prompt; others are pulled in only when relevant to what you're asking.
      </p>

      {loading ? (
        <div className="memories-empty">Loading…</div>
      ) : error ? (
        <div className="memories-empty">Failed to load: {error}</div>
      ) : memories.length === 0 ? (
        <div className="memories-empty">Nothing remembered yet — it builds up as you chat.</div>
      ) : (
        <div className="memories-list">
          {memories.map((m) => (
            <div key={m.id} className="memory-row">
              <div className="memory-row-main">
                <span className={`memory-category memory-category-${m.category}`}>
                  {CATEGORY_LABELS[m.category] || m.category}
                </span>
                <span className="memory-text">{m.text}</span>
              </div>
              <div className="memory-row-actions">
                {m.uses > 0 && <span className="memory-uses">used {m.uses}×</span>}
                <button
                  type="button"
                  className={`memory-pin-btn${m.pinned ? ' active' : ''}`}
                  onClick={() => handleTogglePin(m)}
                  disabled={busyId === m.id}
                  title={m.pinned ? 'Unpin (only inject when relevant)' : 'Pin (always inject)'}
                >
                  📌
                </button>
                <button
                  type="button"
                  className="memory-delete-btn"
                  onClick={() => setPendingDelete(m)}
                  disabled={busyId === m.id}
                  title="Forget this"
                >
                  🗑
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {pendingDelete && (
        <div
          className="modal-overlay"
          onClick={(e) => {
            e.stopPropagation();
            setPendingDelete(null);
          }}
        >
          <div className="modal confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Forget this memory?</h2>
              <button className="modal-close" onClick={() => setPendingDelete(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p className="confirm-dialog-text">
                This will permanently delete <strong>&ldquo;{pendingDelete.text}&rdquo;</strong>. The
                assistant will no longer remember it. This can't be undone.
              </p>
              <div className="confirm-dialog-actions">
                <button type="button" className="confirm-dialog-cancel" onClick={() => setPendingDelete(null)}>
                  Cancel
                </button>
                <button type="button" className="confirm-dialog-delete" onClick={() => handleDelete(pendingDelete)}>
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
