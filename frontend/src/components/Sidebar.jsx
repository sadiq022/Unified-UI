import React, { useState, useMemo, useEffect, useRef } from 'react';
import { searchConversations } from '../api.js';

function formatDateGroup(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / 86400000);

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  return date.toLocaleDateString([], { month: 'long', day: 'numeric', year: 'numeric' });
}

function groupByDate(conversations) {
  const groups = [];
  const indexByLabel = new Map();
  for (const conv of conversations) {
    const label = formatDateGroup(conv.created_at);
    if (!indexByLabel.has(label)) {
      indexByLabel.set(label, groups.length);
      groups.push({ label, items: [] });
    }
    groups[indexByLabel.get(label)].items.push(conv);
  }
  return groups;
}

const COLLAPSED_KEY = 'unifiedui:sidebarCollapsed';

export default function Sidebar({
  conversations, activeId, onSelect, onCreate, onDelete, onOpenSettings, userEmail, onLogout,
  view, onChangeView,
}) {
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null); // null = no active search
  const [searching, setSearching] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null); // { id, title } | null
  // Persisted so it survives a reload, same as the theme preference — a
  // deliberate "I want more room" choice shouldn't reset itself every visit.
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const debounceRef = useRef(null);
  const searchSeq = useRef(0);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(COLLAPSED_KEY, String(next));
      } catch {
        // Private browsing / storage blocked — collapse still works for this session.
      }
      return next;
    });
  };

  const confirmDelete = () => {
    if (!pendingDelete) return;
    onDelete(pendingDelete.id);
    setPendingDelete(null);
  };

  // Debounced full-text search across conversation titles AND message content.
  useEffect(() => {
    const q = query.trim();
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!q) {
      setSearchResults(null);
      setSearching(false);
      return;
    }

    setSearching(true);
    const seq = ++searchSeq.current;
    debounceRef.current = setTimeout(async () => {
      try {
        const results = await searchConversations(q);
        if (seq === searchSeq.current) setSearchResults(results);
      } catch (err) {
        console.error('Search failed:', err);
        if (seq === searchSeq.current) setSearchResults([]);
      } finally {
        if (seq === searchSeq.current) setSearching(false);
      }
    }, 300);

    return () => clearTimeout(debounceRef.current);
  }, [query]);

  const filtered = query.trim() ? (searchResults || []) : conversations;

  const groups = useMemo(() => groupByDate(filtered), [filtered]);

  return (
    <div className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      <button
        type="button"
        className="sidebar-collapse-toggle"
        onClick={toggleCollapsed}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        id="sidebar-collapse-btn"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: collapsed ? 'rotate(180deg)' : 'none' }}>
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>

      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">U</div>
          <h1 className="sidebar-label">Unified UI</h1>
        </div>

        <div className="sidebar-search">
          <span className="sidebar-search-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </span>
          <input
            type="text"
            name="conversation-search"
            placeholder="Search conversations"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
            data-lpignore="true"
            data-1p-ignore
          />
        </div>
      </div>

      <div className="view-switch">
        <button
          type="button"
          className={`view-switch-tab${view !== 'ocr' ? ' active' : ''}`}
          onClick={() => onChangeView('chat')}
        >
          Chat
        </button>
        <button
          type="button"
          className={`view-switch-tab${view === 'ocr' ? ' active' : ''}`}
          onClick={() => onChangeView('ocr')}
          id="ocr-tab-btn"
        >
          Document OCR
        </button>
      </div>

      {view === 'ocr' ? (
        <div className="sidebar-conversations sidebar-ocr-note">
          Reading scanned forms with your local vision model. Switch back to Chat to compare models.
        </div>
      ) : (
      <>
      <div className="sidebar-nav">
        <button className="sidebar-nav-item primary" onClick={onCreate} id="new-chat-btn" title="New Comparison">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9" />
            <line x1="12" y1="8" x2="12" y2="16" />
            <line x1="8" y1="12" x2="16" y2="12" />
          </svg>
          <span className="sidebar-label">New Comparison</span>
        </button>
      </div>

      <div className="sidebar-conversations">
        {searching ? (
          <div style={{ padding: '20px 12px', textAlign: 'center' }}>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Searching...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '20px 12px', textAlign: 'center' }}>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {query ? 'No matches found.' : <>No conversations yet.<br />Start a new comparison!</>}
            </p>
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.label}>
              <div className="sidebar-section-label">{group.label}</div>
              {group.items.map((conv) => (
                <div
                  key={conv.id}
                  className={`conversation-item ${conv.id === activeId ? 'active' : ''}`}
                  onClick={() => onSelect(conv.id)}
                >
                  <span className="conversation-item-title">{conv.title}</span>
                  <button
                    className="conversation-item-delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      setPendingDelete({ id: conv.id, title: conv.title });
                    }}
                    title="Delete conversation"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
      </>
      )}

      <div className="sidebar-footer">
        {userEmail && <div className="sidebar-user-email sidebar-label" title={userEmail}>{userEmail}</div>}
        <button className="sidebar-nav-item" onClick={() => onOpenSettings('apikeys')} id="open-settings-btn" title="Settings">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          <span className="sidebar-label">Settings</span>
        </button>
        <button className="sidebar-nav-item" onClick={onLogout} id="logout-btn" title="Log out">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          <span className="sidebar-label">Log out</span>
        </button>
      </div>

      {pendingDelete && (
        <div className="modal-overlay" onClick={() => setPendingDelete(null)}>
          <div className="modal confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Delete conversation?</h2>
              <button className="modal-close" onClick={() => setPendingDelete(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p className="confirm-dialog-text">
                This will permanently delete <strong>&ldquo;{pendingDelete.title}&rdquo;</strong> and every
                message in it. This can't be undone.
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
