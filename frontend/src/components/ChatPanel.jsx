import React, { useRef, useEffect } from 'react';
import ModelSelector from './ModelSelector.jsx';
import MessageBubble from './MessageBubble.jsx';

export default function ChatPanel({
  panelIndex,
  provider,
  model,
  seenModels,
  visibleSinceTurn,
  messages,
  isLoading,
  error,
  modelsByProvider,
  onSelect,
  onAddCustomModel,
  onClose,
  canClose,
  configuredProviders,
  hideBody,
  visionModels,
  restrictToVision,
}) {
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Show user messages, and assistant replies from any model this panel has ever used
  // (not just the currently selected one) so switching models doesn't hide prior answers.
  // A panel added mid-conversation never shows turns that predate it joining.
  const filteredMessages = messages.filter((msg) => {
    if ((msg.turn_number || 0) <= visibleSinceTurn) return false;
    if (msg.role === 'user') return true;
    if (msg.role === 'assistant') {
      return seenModels.some((pm) => pm.provider === msg.provider && pm.model === msg.model);
    }
    return false;
  });

  return (
    <div className={`chat-panel${hideBody ? ' chat-panel-header-only' : ''}`}>
      <ModelSelector
        panelIndex={panelIndex}
        provider={provider}
        model={model}
        modelsByProvider={modelsByProvider}
        onSelect={onSelect}
        onAddCustomModel={onAddCustomModel}
        onClose={onClose}
        canClose={canClose}
        configuredProviders={configuredProviders}
        visionModels={visionModels}
        restrictToVision={restrictToVision}
      />

      {hideBody ? null : <div className="messages-area">
        {filteredMessages.length === 0 && !isLoading ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
              </svg>
            </div>
            <div className="empty-state-text">
              {provider && model
                ? 'Send a message to start comparing'
                : 'Select a provider and model above'}
            </div>
          </div>
        ) : (
          filteredMessages.map((msg, i) => (
            <MessageBubble key={msg.id || `temp-${i}`} message={msg} />
          ))
        )}

        {isLoading && (
          <div className="message-bubble">
            <div className="message-header">
              <span className={`provider-badge ${provider}`}>{provider}</span>
              <span className="role-label assistant">Thinking...</span>
            </div>
            <div className="message-content assistant">
              <div className="loading-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="error-banner">⚠️ {error}</div>
        )}

        <div ref={messagesEndRef} />
      </div>}
    </div>
  );
}
