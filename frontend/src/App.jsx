import React, { useState, useEffect, useCallback, useRef } from 'react';
import Sidebar from './components/Sidebar.jsx';
import ChatPanel from './components/ChatPanel.jsx';
import ApiKeyManager from './components/ApiKeyManager.jsx';
import { PROVIDERS } from './constants.js';
import {
  getConversations,
  createConversation,
  deleteConversation,
  getHistory,
  getApiKeys,
  getModels,
  addCustomModel,
  sendMessage,
} from './api.js';

const MAX_PANELS = 4;
const DEFAULT_PANELS = [
  { provider: '', model: '', seenModels: [] },
  { provider: '', model: '', seenModels: [] },
];

function withSeenModel(seenModels, provider, model) {
  if (seenModels.some((pm) => pm.provider === provider && pm.model === model)) {
    return seenModels;
  }
  return [...seenModels, { provider, model }];
}

export default function App() {
  // ── State ──────────────────────────────────────────────────
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [panels, setPanels] = useState(DEFAULT_PANELS);
  const [closedPanels, setClosedPanels] = useState([]); // stash of {provider, model}, most-recently-closed last
  const [isLoading, setIsLoading] = useState(false);
  const [panelErrors, setPanelErrors] = useState({});
  const [showSettings, setShowSettings] = useState(false);
  const [configuredProviders, setConfiguredProviders] = useState([]);
  const [modelsByProvider, setModelsByProvider] = useState({});
  const [inputValue, setInputValue] = useState('');
  const textareaRef = useRef(null);

  // ── Load conversations on mount ────────────────────────────
  useEffect(() => {
    loadConversations();
    loadConfiguredProviders();
    loadAllModels();
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

  const loadAllModels = async () => {
    try {
      const entries = await Promise.all(
        PROVIDERS.map(async (p) => {
          const data = await getModels(p.id).catch(() => ({ models: [] }));
          return [p.id, data.models || []];
        })
      );
      setModelsByProvider(Object.fromEntries(entries));
    } catch (err) {
      console.error('Failed to load models:', err);
    }
  };

  const handleAddCustomModel = async (provider, model) => {
    await addCustomModel(provider, model);
    setModelsByProvider((prev) => {
      const existing = prev[provider] || [];
      if (existing.includes(model)) return prev;
      return { ...prev, [provider]: [...existing, model] };
    });
  };

  const loadHistory = async (convId) => {
    try {
      const data = await getHistory(convId);
      setMessages(data);
      
      // Auto-restore panels based on history
      if (data && data.length > 0) {
        const uniquePanels = [];
        const seen = new Set();
        for (let i = data.length - 1; i >= 0; i--) {
          const msg = data[i];
          if (msg.role === 'assistant' && msg.provider && msg.model) {
            const key = `${msg.provider}:${msg.model}`;
            if (!seen.has(key)) {
              seen.add(key);
              uniquePanels.push({
                provider: msg.provider,
                model: msg.model,
                seenModels: [{ provider: msg.provider, model: msg.model }],
              });
            }
          }
          if (uniquePanels.length === 4) break;
        }

        if (uniquePanels.length > 0) {
          setPanels(uniquePanels.reverse());
          setClosedPanels([]);
        }
      }
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
      setClosedPanels([]);
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
  // "+ Add panel" restores the most recently closed panel (with its provider/model) first;
  // only creates a blank panel once the closed-panel stash is empty.
  const handleAddPanel = () => {
    if (panels.length >= MAX_PANELS) return;
    if (closedPanels.length > 0) {
      const restored = closedPanels[closedPanels.length - 1];
      setClosedPanels((prev) => prev.slice(0, -1));
      setPanels((prev) => [...prev, restored]);
    } else {
      setPanels((prev) => [...prev, { provider: '', model: '', seenModels: [] }]);
    }
  };

  const handleClosePanel = (index) => {
    if (panels.length <= 1) return;
    const panelToClose = panels[index];
    setClosedPanels((prev) => [...prev, panelToClose]);
    setPanels((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSelect = (index, provider, model) => {
    setPanels((prev) => {
      const updated = [...prev];
      const seenModels = withSeenModel(updated[index].seenModels, provider, model);
      updated[index] = { provider, model, seenModels };
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
        {/* Panel controls */}
        <div className="panel-controls">
          <span className="panel-controls-label">{panels.length} Panel{panels.length !== 1 ? 's' : ''}</span>
          <button
            className="add-panel-btn"
            onClick={handleAddPanel}
            disabled={panels.length >= MAX_PANELS}
          >
            + Add panel
          </button>
        </div>

        {/* Side-by-side comparison */}
        <div className="comparison-view">
          {panels.map((panel, i) => (
            <ChatPanel
              key={i}
              panelIndex={i}
              provider={panel.provider}
              model={panel.model}
              seenModels={panel.seenModels}
              messages={messages}
              isLoading={isLoading}
              error={panelErrors[`${panel.provider}:${panel.model}`] || (i === 0 ? panelErrors.global : null)}
              modelsByProvider={modelsByProvider}
              onSelect={(provider, model) => handleSelect(i, provider, model)}
              onAddCustomModel={handleAddCustomModel}
              onClose={() => handleClosePanel(i)}
              canClose={panels.length > 1}
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
