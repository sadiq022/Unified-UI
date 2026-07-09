import React from 'react';
import ReactMarkdown from 'react-markdown';

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const time = message.created_at
    ? new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

  return (
    <div className="message-bubble">
      <div className="message-header">
        <span className={`role-label ${message.role}`}>
          <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>{isUser ? 'person' : 'smart_toy'}</span>
        </span>
        <span className="message-time">{time}</span>
      </div>

      <div className={`message-content ${message.role}`}>
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <ReactMarkdown>{message.content}</ReactMarkdown>
        )}
      </div>

      {!isUser && (message.response_time_ms || message.token_count) && (
        <div className="message-meta">
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
        </div>
      )}
    </div>
  );
}
