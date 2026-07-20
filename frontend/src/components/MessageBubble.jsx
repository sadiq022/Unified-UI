import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function MessageBubble({ message, onRetry, isRetrying, onEdit }) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(message.content);
  const time = message.created_at
    ? new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.error('Failed to copy message:', err);
    }
  };

  const startEdit = () => {
    setEditValue(message.content);
    setEditing(true);
  };

  const submitEdit = () => {
    const trimmed = editValue.trim();
    if (!trimmed || trimmed === message.content) {
      setEditing(false);
      return;
    }
    onEdit(message, trimmed);
    setEditing(false);
  };

  if (isUser) {
    return (
      <div className={`message-bubble ${message.role}`}>
        {editing ? (
          <div className="message-edit-box">
            {message.image && (
              <img src={message.image} alt="attached" className="message-image" />
            )}
            <textarea
              className="message-edit-textarea"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  submitEdit();
                } else if (e.key === 'Escape') {
                  setEditing(false);
                }
              }}
              autoFocus
              rows={3}
            />
            <div className="message-edit-actions">
              <button type="button" className="message-edit-cancel" onClick={() => setEditing(false)}>
                Cancel
              </button>
              <button type="button" className="message-edit-save" onClick={submitEdit}>
                Save & Resend
              </button>
            </div>
          </div>
        ) : (
          <div className="message-bubble-user-row">
            {onEdit && (
              <button
                type="button"
                className="message-edit-btn"
                onClick={startEdit}
                title="Edit and resend"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </button>
            )}
            <div className={`message-content ${message.role}`}>
              {message.image && (
                <img src={message.image} alt="attached" className="message-image" />
              )}
              <p>{message.content}</p>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={`message-bubble ${message.role}`}>
      <div className="assistant-message-row">
        <div className="assistant-avatar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2l1.8 5.6L19.4 9.4 13.8 11.2 12 16.8 10.2 11.2 4.6 9.4 10.2 7.6 12 2z" />
          </svg>
        </div>

        <div className="assistant-message-col">
          <div className={`message-content ${message.role}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>

          <div className="message-meta">
          {message.model && (
            <span className="meta-chip meta-chip-model">
              <span className="meta-chip-value">{message.model}</span>
            </span>
          )}
          {message.response_time_ms && (
            <span className="meta-chip">
              <span className="meta-chip-value">{(message.response_time_ms / 1000).toFixed(1)}s</span>
            </span>
          )}
          {message.token_count && (
            <span className="meta-chip">
              <span className="meta-chip-value">{message.token_count} tokens</span>
            </span>
          )}
          <button
            type="button"
            className="meta-chip meta-chip-copy"
            onClick={handleCopy}
            title="Copy message"
          >
            {copied ? (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            )}
            <span className="meta-chip-value">{copied ? 'Copied' : 'Copy'}</span>
          </button>
          {onRetry && (
            <button
              type="button"
              className="meta-chip meta-chip-retry"
              onClick={() => onRetry(message)}
              disabled={isRetrying}
              title="Regenerate this response"
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={isRetrying ? 'spin' : ''}
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              <span className="meta-chip-value">{isRetrying ? 'Retrying...' : 'Retry'}</span>
            </button>
          )}
          </div>
        </div>
      </div>
    </div>
  );
}
