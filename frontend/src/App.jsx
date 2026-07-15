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
  getVisionModels,
  addCustomModel,
  sendMessage,
} from './api.js';

const MAX_PANELS = 4;
const ACTIVE_CONV_STORAGE_KEY = 'unifiedui:activeConvId';
const DEFAULT_PANELS = [
  { provider: '', model: '', seenModels: [] },
  { provider: '', model: '', seenModels: [] },
];

const EXAMPLE_PROMPTS = [
  'Explain quantum computing in simple terms',
  'Write a Python function to reverse a linked list',
  'What are the pros and cons of remote work?',
  'Give me 5 creative names for a coffee shop',
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
  const [activeConvId, setActiveConvId] = useState(() => {
    const saved = Number(localStorage.getItem(ACTIVE_CONV_STORAGE_KEY));
    return saved || null;
  });
  const [messages, setMessages] = useState([]);
  const [panels, setPanels] = useState(DEFAULT_PANELS);
  const [closedPanels, setClosedPanels] = useState([]); // stash of {provider, model}, most-recently-closed last
  const [isLoading, setIsLoading] = useState(false);
  const [panelErrors, setPanelErrors] = useState({});
  const [showSettings, setShowSettings] = useState(false);
  const [configuredProviders, setConfiguredProviders] = useState([]);
  const [modelsByProvider, setModelsByProvider] = useState({});
  const [visionModels, setVisionModels] = useState({});
  const [attachedImage, setAttachedImage] = useState(null); // { dataUrl, name }
  const [inputValue, setInputValue] = useState('');
  const textareaRef = useRef(null);
  const activeConvIdRef = useRef(null);
  const fileInputRef = useRef(null);

  // ── Load conversations on mount ────────────────────────────
  useEffect(() => {
    loadConversations();
    loadConfiguredProviders();
    loadAllModels();
    loadVisionModels();
  }, []);

  // ── Persist the active conversation so a page refresh reopens it ──
  useEffect(() => {
    if (activeConvId) {
      localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, String(activeConvId));
    } else {
      localStorage.removeItem(ACTIVE_CONV_STORAGE_KEY);
    }
  }, [activeConvId]);

  // ── Load messages when conversation changes ────────────────
  useEffect(() => {
    activeConvIdRef.current = activeConvId;
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

      // Clear the restored conversation if it no longer exists (e.g. deleted elsewhere)
      setActiveConvId((current) => {
        if (current && !data.some((c) => c.id === current)) return null;
        return current;
      });
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

  const loadVisionModels = async () => {
    try {
      const data = await getVisionModels();
      setVisionModels(data || {});
    } catch (err) {
      console.error('Failed to load vision models:', err);
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

      // Ignore responses for a conversation we've since navigated away from
      // (e.g. clicking a chat then immediately hitting "New Comparison").
      if (activeConvIdRef.current !== convId) return;

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

    const imageToSend = attachedImage?.dataUrl || null;

    setInputValue('');
    setAttachedImage(null);
    setIsLoading(true);
    setPanelErrors({});

    try {
      const targets = activePanels.map((p) => ({
        provider: p.provider,
        model: p.model,
      }));

      const result = await sendMessage(convId, msg, targets, imageToSend);

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

  const handleExampleClick = (text) => {
    setInputValue(text);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus();
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 120) + 'px';
      }
    });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Image attachment ───────────────────────────────────────
  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file later
    if (!file || !file.type.startsWith('image/')) return;

    const reader = new FileReader();
    reader.onload = () => {
      setAttachedImage({ dataUrl: reader.result, name: file.name });
    };
    reader.readAsDataURL(file);
  };

  const handleRemoveImage = () => {
    setAttachedImage(null);
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
        <div className={`comparison-view${messages.length === 0 ? ' comparison-view-collapsed' : ''}`}>
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
              hideBody={messages.length === 0}
              visionModels={visionModels}
              restrictToVision={!!attachedImage}
            />
          ))}
        </div>

        {messages.length === 0 && (
          <div className="welcome-hero">
            <div className="welcome-hero-icon">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="7" height="16" rx="1.5" />
                <rect x="14" y="4" width="7" height="16" rx="1.5" />
              </svg>
            </div>
            <h2 className="welcome-hero-title">Unified UI</h2>
            <p className="welcome-hero-subtitle">
              Compare responses from multiple AI models side by side, in real time.
            </p>
            <div className="example-prompts">
              {EXAMPLE_PROMPTS.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  className="example-prompt-card"
                  onClick={() => handleExampleClick(ex)}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Shared input area */}
        <div className="input-area">
          {panelErrors.global && (
            <div className="error-banner" style={{ marginBottom: '10px' }}>
              ⚠️ {panelErrors.global}
            </div>
          )}
          {attachedImage && (
            <div className="vision-warning">
              ⚠️ Only vision-capable models can read images:{' '}
              {Object.entries(visionModels)
                .filter(([, models]) => models.length > 0)
                .map(([provider, models]) => {
                  const providerName = PROVIDERS.find((p) => p.id === provider)?.name || provider;
                  return `${providerName} (${models.join(', ')})`;
                })
                .join(' · ') || 'none currently configured'}
              . Other selected models will show an error for this message.
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <div className="input-wrapper">
            <button
              type="button"
              className="attach-btn"
              onClick={handleAttachClick}
              title="Attach an image"
              id="attach-btn"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>

            {attachedImage && (
              <div className="attached-image-chip">
                <img src={attachedImage.dataUrl} alt={attachedImage.name} />
                <span className="attached-image-name">{attachedImage.name}</span>
                <button type="button" className="attached-image-remove" onClick={handleRemoveImage} title="Remove image">
                  ✕
                </button>
              </div>
            )}

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
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 2 2" />
              </svg>
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
