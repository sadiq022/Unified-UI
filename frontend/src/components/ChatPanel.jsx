import React, { useRef, useEffect } from 'react';
import ModelSelector from './ModelSelector.jsx';
import MessageBubble from './MessageBubble.jsx';

export default function ChatPanel({
  panelIndex,
  panelId,
  provider,
  model,
  seenModels,
  visibleSinceTurn,
  compactions,
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
  onRetry,
  retryingKey,
  onEdit,
}) {
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Show user messages, and assistant replies that belong to this panel. Each
  // assistant message is tagged with the panel_id of whoever requested it, so
  // this matches on identity, not just (provider, model) — two panels can share
  // the same model without one absorbing the other's answers. Older messages
  // saved before panel identity existed have no panel_id, so they fall back to
  // the previous "any model this panel has ever used" heuristic.
  const filteredMessages = messages.filter((msg) => {
    if ((msg.turn_number || 0) <= visibleSinceTurn) return false;
    if (msg.role === 'user') return true;
    if (msg.role === 'assistant') {
      if (msg.panel_id) return msg.panel_id === panelId;
      return seenModels.some((pm) => pm.provider === msg.provider && pm.model === msg.model);
    }
    return false;
  });

  let lastAssistantKey = null;
  const insertedCompactionDivider = new Set();
  const compactionByKey = {};
  for (const c of compactions || []) {
    compactionByKey[`${c.provider}:${c.model}`] = c.covers_through_turn;
  }

  // With streaming, panels finish at different times — only show "Thinking..."
  // for a panel that hasn't started/finished streaming its own answer yet for
  // the latest turn, instead of a blanket indicator on every panel at once.
  const latestTurn = messages.reduce((max, m) => Math.max(max, m.turn_number || 0), 0);
  const hasCurrentTurnResponse = filteredMessages.some(
    (m) => m.role === 'assistant' && m.turn_number === latestTurn
  );

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
          filteredMessages.flatMap((msg, i) => {
            const elements = [];
            if (msg.role === 'assistant') {
              const key = `${msg.provider}:${msg.model}`;
              if (lastAssistantKey !== null && key !== lastAssistantKey) {
                elements.push(
                  <div key={`switch-${msg.id || i}`} className="model-switch-divider">
                    <span>Switched to {msg.model}</span>
                  </div>
                );
              }
              lastAssistantKey = key;

              const coversThroughTurn = compactionByKey[key];
              if (
                coversThroughTurn !== undefined
                && msg.turn_number > coversThroughTurn
                && !insertedCompactionDivider.has(key)
              ) {
                insertedCompactionDivider.add(key);
                elements.push(
                  <div key={`compaction-${msg.id || i}`} className="model-switch-divider">
                    <span>Context compacted for this model — earlier turns summarized</span>
                  </div>
                );
              }
            }
            const isRetrying = msg.role === 'assistant'
              && retryingKey === `${panelId}:${msg.turn_number}`;
            elements.push(
              <MessageBubble
                key={msg.id || `temp-${i}`}
                message={msg}
                onRetry={msg.role === 'assistant' && onRetry
                  ? (m) => onRetry({ provider: m.provider, model: m.model, turn_number: m.turn_number, panel_id: panelId })
                  : undefined}
                isRetrying={isRetrying}
                onEdit={msg.role === 'user' ? onEdit : undefined}
              />
            );
            return elements;
          })
        )}

        {isLoading && !hasCurrentTurnResponse && (
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
          <div className="error-banner">
            ⚠️ {error.message}
            {error.turnNumber != null && onRetry && (
              <button
                type="button"
                className="error-retry-btn"
                onClick={() => onRetry({ provider, model, turn_number: error.turnNumber, panel_id: panelId })}
                disabled={retryingKey === `${panelId}:${error.turnNumber}`}
              >
                {retryingKey === `${panelId}:${error.turnNumber}` ? 'Retrying...' : 'Retry'}
              </button>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>}
    </div>
  );
}
