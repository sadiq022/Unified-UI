import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
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

  return (
    <div className={`message-bubble ${message.role}`}>

      <div className={`message-content ${message.role}`}>
        {isUser ? (
          <>
            {message.image && (
              <img src={message.image} alt="attached" className="message-image" />
            )}
            <p>{message.content}</p>
          </>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        )}
      </div>

      {!isUser && (
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
        </div>
      )}
    </div>
  );
}
