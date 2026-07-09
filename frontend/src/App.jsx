import React, { useState, useEffect, useCallback, useRef } from 'react';
import Sidebar from './components/Sidebar.jsx';
import ChatPanel from './components/ChatPanel.jsx';
import ApiKeyManager from './components/ApiKeyManager.jsx';
import {
  getConversations,
  createConversation,
  deleteConversation,
  getHistory,
  getApiKeys,
  sendMessage,
} from './api.js';

const DEFAULT_PANELS = [
  { provider: '', model: '' },
  { provider: '', model: '' },
];

export default function App() {
  // ── State ──────────────────────────────────────────────────
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [panels, setPanels] = useState(DEFAULT_PANELS);
  const [panelCount, setPanelCount] = useState(2);
  const [isLoading, setIsLoading] = useState(false);
  const [panelErrors, setPanelErrors] = useState({});
  const [showSettings, setShowSettings] = useState(false);
  const [configuredProviders, setConfiguredProviders] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const textareaRef = useRef(null);

  // ── Load conversations on mount ────────────────────────────
  useEffect(() => {
    loadConversations();
    loadConfiguredProviders();
  }, []);

  // ── Load messages when conversation changes ────────────────
  useEffect(() => {
    if (activeConvId) {
      loadHistory(activeConvId);
    } else {
      setMessages([]);
    }
  }, [activeConvId]);

  const loadConversations = async () => {
    try {
      const data = await getConversations();
      setConversations(data);
    } catch (err) {
      console.error('Failed to load conversations:', err);
    }
  };

  const loadConfiguredProviders = async () => {
    try {
      const keys = await getApiKeys();
      setConfiguredProviders(keys.map((k) => k.provider));
    } catch (err) {
      console.error('Failed to load API keys:', err);
    }
  };

  const loadHistory = async (convId) => {
    try {
      const data = await getHistory(convId);
      setMessages(data);
    } catch (err) {
      console.error('Failed to load history:', err);
    }
  };

  // ── Conversation actions ───────────────────────────────────
  const handleCreateConversation = async () => {
    try {
      const conv = await createConversation();
      setConversations((prev) => [conv, ...prev]);
      setActiveConvId(conv.id);
      setMessages([]);
      setPanelErrors({});
    } catch (err) {
      console.error('Failed to create conversation:', err);
    }
  };

  const handleDeleteConversation = async (id) => {
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConvId === id) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  };

  // ── Panel management ───────────────────────────────────────
  const handlePanelCountChange = (count) => {
    setPanelCount(count);
    setPanels((prev) => {
      const updated = [...prev];
      while (updated.length < count) {
        updated.push({ provider: '', model: '' });
      }
      return updated.slice(0, count);
    });
  };

  const handleProviderChange = (index, provider) => {
    setPanels((prev) => {
      const updated = [...prev];
      updated[index] = { provider, model: '' };
      return updated;
    });
  };

  const handleModelChange = (index, model) => {
    setPanels((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], model };
      return updated;
    });
  };

  // ── Send message ───────────────────────────────────────────
  const handleSend = async () => {
    const msg = inputValue.trim();
    if (!msg || isLoading) return;

    // Validate: need at least one panel with provider + model
    const activePanels = panels.filter((p) => p.provider && p.model);
    if (activePanels.length === 0) {
      alert('Please select at least one provider and model.');
      return;
    }

    // Auto-create conversation if none active
    let convId = activeConvId;
    if (!convId) {
      try {
        const conv = await createConversation();
        setConversations((prev) => [conv, ...prev]);
        setActiveConvId(conv.id);
        convId = conv.id;
      } catch (err) {
        console.error('Failed to create conversation:', err);
        return;
      }
    }

    setInputValue('');
    setIsLoading(true);
    setPanelErrors({});

    try {
      const targets = activePanels.map((p) => ({
        provider: p.provider,
        model: p.model,
      }));

      const result = await sendMessage(convId, msg, targets);

      // Add user message + all responses to local state
      const newMessages = [result.user_message];
      for (const resp of result.responses) {
        if (resp.error) {
          setPanelErrors((prev) => ({
            ...prev,
            [`${resp.provider}:${resp.model}`]: resp.error,
          }));
        } else {
          newMessages.push({
            id: Date.now() + Math.random(), // temp ID
            conversation_id: convId,
            turn_number: result.turn_number,
            role: 'assistant',
            content: resp.content,
            provider: resp.provider,
            model: resp.model,
            response_time_ms: resp.response_time_ms,
            token_count: resp.token_count,
            created_at: new Date().toISOString(),
          });
        }
      }

      setMessages((prev) => [...prev, ...newMessages]);

      // Reload conversations to get updated title
      loadConversations();
    } catch (err) {
      console.error('Send failed:', err);
      setPanelErrors({ global: err.message });
    } finally {
      setIsLoading(false);
    }
  };

  // ── Auto-resize textarea ──────────────────────────────────
  const handleTextareaChange = (e) => {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Render ─────────────────────────────────────────────────
  return (
    <div className="app-layout">
      <Sidebar
        conversations={conversations}
        activeId={activeConvId}
        onSelect={setActiveConvId}
        onCreate={handleCreateConversation}
        onDelete={handleDeleteConversation}
        onOpenSettings={() => setShowSettings(true)}
      />

      <div className="main-content">
        {/* Panel count controls */}
        <div className="panel-controls">
          <span className="panel-controls-label">Panels</span>
          <button 
            className="panel-count-btn" 
            onClick={() => handlePanelCountChange(Math.max(1, panelCount - 1))}
            disabled={panelCount <= 1}
            style={{ opacity: panelCount <= 1 ? 0.5 : 1 }}
          >
            -
          </button>
          <span style={{ fontSize: '14px', fontWeight: 'bold', margin: '0 8px' }}>{panelCount}</span>
          <button 
            className="panel-count-btn" 
            onClick={() => handlePanelCountChange(Math.min(4, panelCount + 1))}
            disabled={panelCount >= 4}
            style={{ opacity: panelCount >= 4 ? 0.5 : 1 }}
          >
            +
          </button>
        </div>

        {/* Side-by-side comparison */}
        <div className="comparison-view">
          {panels.slice(0, panelCount).map((panel, i) => (
            <ChatPanel
              key={i}
              panelIndex={i}
              provider={panel.provider}
              model={panel.model}
              messages={messages}
              isLoading={isLoading}
              error={panelErrors[`${panel.provider}:${panel.model}`] || (i === 0 ? panelErrors.global : null)}
              onProviderChange={(p) => handleProviderChange(i, p)}
              onModelChange={(m) => handleModelChange(i, m)}
              configuredProviders={configuredProviders}
            />
          ))}
        </div>

        {/* Shared input area */}
        <div className="input-area">
          {panelErrors.global && (
            <div className="error-banner" style={{ marginBottom: '10px' }}>
              ⚠️ {panelErrors.global}
            </div>
          )}
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder="Type a message to send to all models..."
              rows={1}
              id="chat-input"
            />
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={isLoading || !inputValue.trim()}
              id="send-btn"
            >
              ▶
            </button>
          </div>
        </div>
      </div>

      <ApiKeyManager
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
        onKeysChange={setConfiguredProviders}
      />
    </div>
  );
}
