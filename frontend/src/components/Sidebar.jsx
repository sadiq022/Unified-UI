import React from 'react';

export default function Sidebar({ conversations, activeId, onSelect, onCreate, onDelete, onOpenSettings }) {
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">U</div>
          <h1>Unified UI</h1>
        </div>
        <button className="new-chat-btn" onClick={onCreate} id="new-chat-btn">
          ＋ New Comparison
        </button>
      </div>

      <div className="sidebar-conversations">
        {conversations.length === 0 ? (
          <div style={{ padding: '20px 12px', textAlign: 'center' }}>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              No conversations yet.<br />Start a new comparison!
            </p>
          </div>
        ) : (
          conversations.map((conv) => (
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
                  onDelete(conv.id);
                }}
                title="Delete conversation"
              >
                ✕
              </button>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-footer">
        <button className="settings-btn" onClick={onOpenSettings} id="open-settings-btn">
          ⚙️ API Keys & Settings
        </button>
      </div>
    </div>
  );
}
