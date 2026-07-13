import React, { useRef, useEffect } from 'react';
import ModelSelector from './ModelSelector.jsx';
import MessageBubble from './MessageBubble.jsx';

export default function ChatPanel({
  panelIndex,
  provider,
  model,
  seenModels,
  messages,
  isLoading,
  error,
  modelsByProvider,
  onSelect,
  onAddCustomModel,
  onClose,
  canClose,
  configuredProviders,
}) {
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Show user messages, and assistant replies from any model this panel has ever used
  // (not just the currently selected one) so switching models doesn't hide prior answers.
  const filteredMessages = messages.filter((msg) => {
    if (msg.role === 'user') return true;
    if (msg.role === 'assistant') {
      return seenModels.some((pm) => pm.provider === msg.provider && pm.model === msg.model);
    }
    return false;
  });

  return (
    <div className="chat-panel">
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
      />

      <div className="messages-area">
        {filteredMessages.length === 0 && !isLoading ? (
          <div className="empty-state">
            <div className="empty-state-icon">💬</div>
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
      </div>
    </div>
  );
}
