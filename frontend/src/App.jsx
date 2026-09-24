import React, { useState, useEffect, useCallback, useRef } from 'react';
import Sidebar from './components/Sidebar.jsx';
import ChatPanel from './components/ChatPanel.jsx';
import SettingsModal from './components/SettingsModal.jsx';
import SourcePanel from './components/SourcePanel.jsx';
import Auth from './components/Auth.jsx';
import PresetsMenu from './components/PresetsMenu.jsx';
import DocumentOcrTab from './components/DocumentOcrTab.jsx';
import { PROVIDERS } from './constants.js';
import {
  getConversations,
  getConversation,
  createConversation,
  deleteConversation,
  getHistory,
  getCompactions,
  getApiKeys,
  getModels,
  getVisionModels,
  addCustomModel,
  extractFileText,
  sendMessageStream,
  retryMessage,
  editMessage,
  updatePanelLayout,
  getPanelPresets,
  savePanelPreset,
  deletePanelPreset,
  getToken,
  setToken,
  getTokenExpiryMs,
  getMe,
  AUTH_LOGOUT_EVENT,
} from './api.js';

const MAX_PANELS = 4;
const ACTIVE_CONV_STORAGE_KEY = 'unifiedui:activeConvId';
const DEFAULT_PANELS = [
  { panel_id: 'panel-a', provider: '', model: '', seenModels: [], visibleSinceTurn: 0 },
  { panel_id: 'panel-b', provider: '', model: '', seenModels: [], visibleSinceTurn: 0 },
];

// A stable identity for a panel, independent of its array position — needed
// because two panels can end up targeting the same provider+model, and
// messages must be attributed to the panel that actually asked for them, not
// just matched by (provider, model), which is ambiguous once that overlap happens.
function makePanelId() {
  return `panel-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

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

// Keeps messages in chronological turn order (stable sort preserves relative
// order of same-turn entries), needed after retrying/editing an older turn.
function sortMessages(msgs) {
  return [...msgs].sort((a, b) => {
    if (a.turn_number !== b.turn_number) return (a.turn_number || 0) - (b.turn_number || 0);
    if (a.role !== b.role) return a.role === 'user' ? -1 : 1;
    return 0;
  });
}

const THEME_STORAGE_KEY = 'unifiedui:theme';

export default function App() {
  // ── Theme ──────────────────────────────────────────────────
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_STORAGE_KEY) || 'dark');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  // ── Auth state ─────────────────────────────────────────────
  const [authChecked, setAuthChecked] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const logoutTimerRef = useRef(null);

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
  const [retryingKey, setRetryingKey] = useState(null); // "provider:model:turnNumber"
  const [showSettings, setShowSettings] = useState(false);
  const [view, setView] = useState('chat'); // 'chat' | 'ocr'
  const [settingsTab, setSettingsTab] = useState('account');
  const [configuredProviders, setConfiguredProviders] = useState([]);
  const [modelsByProvider, setModelsByProvider] = useState({});
  const [visionModels, setVisionModels] = useState({});
  const [presets, setPresets] = useState([]);
  const [attachedImage, setAttachedImage] = useState(null); // { dataUrl, name }
  const [attachedFile, setAttachedFile] = useState(null); // { name, content, truncated }
  const [webSearch, setWebSearch] = useState(false); // stays on across messages until switched off
  const [withSources, setWithSources] = useState(false); // "generate with sources" toggle, only meaningful with a file attached
  const [extractingFile, setExtractingFile] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [compactions, setCompactions] = useState([]); // [{provider, model, covers_through_turn}]
  const [sourcePanel, setSourcePanel] = useState(null); // { sentences, highlightIds, label } | null
  const textareaRef = useRef(null);
  const activeConvIdRef = useRef(null);
  const fileInputRef = useRef(null);

  // ── Restore session from a stored token on mount ───────────
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setAuthChecked(true);
      return;
    }
    const expMs = getTokenExpiryMs(token);
    if (expMs && expMs <= Date.now()) {
      setToken(null);
      setAuthChecked(true);
      return;
    }
    getMe()
      .then((user) => {
        setCurrentUser(user);
        if (expMs) scheduleAutoLogout(expMs);
      })
      .catch(() => {})
      .finally(() => setAuthChecked(true));
  }, []);

  // ── Force logout the moment the token expires, or on any 401 ──
  const handleLogout = useCallback(() => {
    setToken(null);
    setCurrentUser(null);
    if (logoutTimerRef.current) {
      clearTimeout(logoutTimerRef.current);
      logoutTimerRef.current = null;
    }
    setConversations([]);
    setActiveConvId(null);
    setMessages([]);
    setPanels(DEFAULT_PANELS);
    setClosedPanels([]);
    setPanelErrors({});
    setConfiguredProviders([]);
    setModelsByProvider({});
    setVisionModels({});
    setPresets([]);
    setAttachedImage(null);
    setInputValue('');
  }, []);

  const scheduleAutoLogout = (expiryMs) => {
    if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current);
    const msUntilExpiry = expiryMs - Date.now();
    if (msUntilExpiry <= 0) {
      handleLogout();
      return;
    }
    logoutTimerRef.current = setTimeout(handleLogout, msUntilExpiry);
  };

  useEffect(() => {
    window.addEventListener(AUTH_LOGOUT_EVENT, handleLogout);
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, handleLogout);
  }, [handleLogout]);

  const handleAuthenticated = (user, expiresAt) => {
    setCurrentUser(user);
    scheduleAutoLogout(new Date(expiresAt).getTime());
  };

  // ── Load app data once logged in ───────────────────────────
  useEffect(() => {
    if (!currentUser) return;
    loadConversations();
    loadConfiguredProviders();
    loadAllModels();
    loadVisionModels();
    loadPanelPresets();
  }, [currentUser]);

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

  // Re-fetches the model list whenever configured keys change — needed for the
  // "local" provider, whose model list comes live from the server rather than
  // a fixed default list, so saving/updating its base URL should refresh it.
  const handleKeysChange = (providers) => {
    setConfiguredProviders(providers);
    loadAllModels();
  };

  const loadVisionModels = async () => {
    try {
      const data = await getVisionModels();
      setVisionModels(data || {});
    } catch (err) {
      console.error('Failed to load vision models:', err);
    }
  };

  const loadPanelPresets = async () => {
    try {
      const data = await getPanelPresets();
      setPresets(data || []);
    } catch (err) {
      console.error('Failed to load panel presets:', err);
    }
  };

  const handleApplyPreset = (preset) => {
    let config;
    try {
      config = JSON.parse(preset.config);
    } catch (err) {
      console.error('Failed to parse preset config:', err);
      return;
    }
    if (!Array.isArray(config) || config.length === 0) return;

    const nextPanels = config.slice(0, MAX_PANELS).map((p) => ({
      panel_id: makePanelId(),
      provider: p.provider || '',
      model: p.model || '',
      seenModels: p.provider && p.model ? [{ provider: p.provider, model: p.model }] : [],
      visibleSinceTurn: 0,
    }));
    setPanels(nextPanels);
    setClosedPanels([]);
    savePanelLayout(activeConvId, nextPanels);
  };

  const handleSavePreset = async (name) => {
    try {
      const config = panels
        .filter((p) => p.provider && p.model)
        .map((p) => ({ provider: p.provider, model: p.model }));
      if (config.length === 0) {
        alert('Select at least one provider and model before saving a preset.');
        return;
      }
      const saved = await savePanelPreset(name, config);
      setPresets((prev) => {
        const withoutOld = prev.filter((p) => p.id !== saved.id);
        return [...withoutOld, saved];
      });
    } catch (err) {
      console.error('Failed to save preset:', err);
      alert(`Failed to save preset: ${err.message}`);
    }
  };

  const handleDeletePreset = async (id) => {
    try {
      await deletePanelPreset(id);
      setPresets((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      console.error('Failed to delete preset:', err);
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

  // Refetches which (provider, model) targets have compacted history for the
  // active conversation, so panels can show a "context compacted" divider.
  const refreshCompactions = async (convId) => {
    if (!convId) return;
    try {
      const data = await getCompactions(convId);
      if (activeConvIdRef.current === convId) setCompactions(data);
    } catch (err) {
      console.error('Failed to load compactions:', err);
    }
  };

  const loadHistory = async (convId) => {
    try {
      const [data, conv] = await Promise.all([
        getHistory(convId),
        getConversation(convId).catch(() => null),
      ]);

      // Ignore responses for a conversation we've since navigated away from
      // (e.g. clicking a chat then immediately hitting "New Comparison").
      if (activeConvIdRef.current !== convId) return;

      setMessages(data);
      setClosedPanels([]);
      refreshCompactions(convId);

      // Restore the exact panel layout the user last configured for this
      // conversation (added/removed panels, model choices) if one was saved.
      if (conv?.panel_layout) {
        try {
          const savedPanels = JSON.parse(conv.panel_layout);
          if (Array.isArray(savedPanels) && savedPanels.length > 0) {
            // Backfill a panel_id for layouts saved before panel identity existed,
            // so this conversation starts getting correctly-attributed messages
            // from its very next turn instead of only new conversations.
            let backfilled = false;
            const withIds = savedPanels.map((p) => {
              if (p.panel_id) return p;
              backfilled = true;
              return { ...p, panel_id: makePanelId() };
            });
            setPanels(withIds);
            if (backfilled) savePanelLayout(convId, withIds);
            return;
          }
        } catch (err) {
          console.error('Failed to parse saved panel layout:', err);
        }
      }

      // Legacy fallback for conversations saved before panel layout persistence
      // existed: reconstruct panels from which models actually answered.
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
                panel_id: makePanelId(),
                provider: msg.provider,
                model: msg.model,
                seenModels: [{ provider: msg.provider, model: msg.model }],
                visibleSinceTurn: 0,
              });
            }
          }
          if (uniquePanels.length === 4) break;
        }

        if (uniquePanels.length > 0) {
          const reconstructed = uniquePanels.reverse();
          setPanels(reconstructed);
          // Persist it so this reconstruction (and the panel_ids it just minted)
          // only happens once — future loads restore this exact layout instead
          // of re-deriving fresh (and different) panel_ids from history each time.
          savePanelLayout(convId, reconstructed);
        }
      }
    } catch (err) {
      console.error('Failed to load history:', err);
    }
  };

  // Persist the panel layout instantly whenever it changes, so switching
  // conversations and coming back doesn't lose added/removed panels or model picks.
  const savePanelLayout = (convId, panelsToSave) => {
    if (!convId) return;
    updatePanelLayout(convId, panelsToSave).catch((err) => {
      console.error('Failed to save panel layout:', err);
    });
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
      setCompactions([]);
      // Same reasoning as the auto-create path in handleSend: without this,
      // the conversation's panel_layout stays unset until something else
      // happens to save it, and a refresh in that window would reconstruct
      // fresh panel_ids that don't match whatever gets sent in the meantime.
      savePanelLayout(conv.id, panels);
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
    let nextPanels;
    if (closedPanels.length > 0) {
      const restored = closedPanels[closedPanels.length - 1];
      setClosedPanels((prev) => prev.slice(0, -1));
      nextPanels = [...panels, restored];
    } else {
      // A brand-new panel shouldn't see any messages that predate it — only
      // turns sent after it joins. Mark the current latest turn as its cutoff.
      const currentMaxTurn = messages.reduce((max, m) => Math.max(max, m.turn_number || 0), 0);
      nextPanels = [
        ...panels,
        { panel_id: makePanelId(), provider: '', model: '', seenModels: [], visibleSinceTurn: currentMaxTurn },
      ];
    }
    setPanels(nextPanels);
    savePanelLayout(activeConvId, nextPanels);
  };

  const handleClosePanel = (index) => {
    if (panels.length <= 1) return;
    const panelToClose = panels[index];
    setClosedPanels((prev) => [...prev, panelToClose]);
    const nextPanels = panels.filter((_, i) => i !== index);
    setPanels(nextPanels);
    savePanelLayout(activeConvId, nextPanels);
  };

  const handleSelect = (index, provider, model) => {
    const seenModels = withSeenModel(panels[index].seenModels, provider, model);
    const nextPanels = [...panels];
    nextPanels[index] = { ...nextPanels[index], provider, model, seenModels };
    setPanels(nextPanels);
    savePanelLayout(activeConvId, nextPanels);
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
        // Save the panel layout (with its panel_ids) right away — otherwise
        // this conversation has messages stamped with a panel_id that was
        // never persisted anywhere else. Refreshing before anything else
        // triggers a save (e.g. switching a model) would then fall back to
        // reconstructing the layout from scratch with brand-new panel_ids,
        // permanently orphaning the messages already tagged with the old ones.
        savePanelLayout(convId, panels);
      } catch (err) {
        console.error('Failed to create conversation:', err);
        return;
      }
    }

    const imageToSend = attachedImage?.dataUrl || null;
    const fileNameToSend = attachedFile?.name || null;
    const fileContentToSend = attachedFile?.content || null;
    const withSourcesToSend = withSources && !!fileContentToSend;

    setInputValue('');
    setAttachedImage(null);
    setAttachedFile(null);
    setWithSources(false);
    setIsLoading(true);
    setPanelErrors({});

    const targets = activePanels.map((p) => ({ provider: p.provider, model: p.model, panel_id: p.panel_id }));
    let turnNumber = null;
    const streamingIds = {}; // panel_id -> temp message id for the in-progress bubble

    try {
      await sendMessageStream(convId, msg, targets, imageToSend, fileNameToSend, fileContentToSend, (event) => {
        if (event.type === 'start') {
          turnNumber = event.turn_number;
          setMessages((prev) => [...prev, event.user_message]);
        } else if (event.type === 'delta') {
          const key = event.panel_id;
          setMessages((prev) => {
            const existingId = streamingIds[key];
            if (!existingId) {
              const id = `streaming-${key}-${Date.now()}`;
              streamingIds[key] = id;
              return [...prev, {
                id,
                conversation_id: convId,
                turn_number: turnNumber,
                role: 'assistant',
                content: event.content,
                provider: event.provider,
                model: event.model,
                panel_id: event.panel_id,
                created_at: new Date().toISOString(),
              }];
            }
            return prev.map((m) => (m.id === existingId ? { ...m, content: m.content + event.content } : m));
          });
        } else if (event.type === 'done') {
          const key = event.panel_id;
          const existingId = streamingIds[key];
          setMessages((prev) => {
            // No delta ever arrived for this panel (e.g. the model produced
            // nothing but reasoning that only got recovered as a single
            // fallback chunk at the very end) — there's no placeholder bubble
            // to update, so create one now instead of silently dropping it.
            if (!existingId) {
              return [...prev, {
                id: `streaming-${key}-${Date.now()}`,
                conversation_id: convId,
                turn_number: turnNumber,
                role: 'assistant',
                content: event.content,
                provider: event.provider,
                model: event.model,
                panel_id: event.panel_id,
                response_time_ms: event.response_time_ms,
                token_count: event.token_count,
                context_usage_pct: event.context_usage_pct,
                content_format: event.content_format,
                created_at: new Date().toISOString(),
              }];
            }
            return prev.map((m) => (m.id === existingId ? {
              ...m,
              content: event.content,
              response_time_ms: event.response_time_ms,
              token_count: event.token_count,
              context_usage_pct: event.context_usage_pct,
              content_format: event.content_format,
            } : m));
          });
        } else if (event.type === 'error') {
          setPanelErrors((prev) => ({
            ...prev,
            [event.panel_id]: { message: event.error, detail: event.error_detail, turnNumber },
          }));
        } else if (event.type === 'end') {
          loadConversations();
          refreshCompactions(convId);
        }
      }, withSourcesToSend, webSearch);
    } catch (err) {
      console.error('Send failed:', err);
      setPanelErrors({ global: err.message });
    } finally {
      setIsLoading(false);
    }
  };

  // ── Retry a single panel's response ─────────────────────────
  const handleRetry = async ({ provider, model, turn_number, panel_id }) => {
    if (!activeConvId) return;
    const key = `${panel_id}:${turn_number}`;
    if (retryingKey) return; // one retry at a time keeps things simple
    setRetryingKey(key);
    setPanelErrors((prev) => {
      const next = { ...prev };
      delete next[panel_id];
      return next;
    });

    try {
      const resp = await retryMessage(activeConvId, turn_number, provider, model, panel_id);

      if (resp.error) {
        setPanelErrors((prev) => ({
          ...prev,
          [panel_id]: { message: resp.error, detail: resp.error_detail, turnNumber: turn_number },
        }));
        return;
      }

      setMessages((prev) => {
        const idx = prev.findIndex(
          (m) => m.role === 'assistant' && m.turn_number === turn_number
            && (panel_id ? m.panel_id === panel_id : m.provider === provider && m.model === model)
        );
        const updated = {
          id: idx >= 0 ? prev[idx].id : Date.now() + Math.random(),
          conversation_id: activeConvId,
          turn_number,
          role: 'assistant',
          content: resp.content,
          provider: resp.provider,
          model: resp.model,
          panel_id: resp.panel_id,
          response_time_ms: resp.response_time_ms,
          token_count: resp.token_count,
          context_usage_pct: resp.context_usage_pct,
          created_at: new Date().toISOString(),
        };
        const next = idx >= 0
          ? [...prev.slice(0, idx), updated, ...prev.slice(idx + 1)]
          : [...prev, updated];
        return sortMessages(next);
      });
      refreshCompactions(activeConvId);
    } catch (err) {
      console.error('Retry failed:', err);
      setPanelErrors((prev) => ({
        ...prev,
        [panel_id]: { message: err.message, turnNumber: turn_number },
      }));
    } finally {
      setRetryingKey(null);
    }
  };

  // ── Edit + resend a user message ────────────────────────────
  const handleEditMessage = async (message, newContent) => {
    if (!activeConvId || isLoading) return;

    const activePanels = panels.filter((p) => p.provider && p.model);
    if (activePanels.length === 0) {
      alert('Please select at least one provider and model.');
      return;
    }

    setIsLoading(true);
    setPanelErrors({});

    try {
      const targets = activePanels.map((p) => ({ provider: p.provider, model: p.model, panel_id: p.panel_id }));
      const result = await editMessage(
        activeConvId, message.id, newContent, targets,
        message.image || null, message.attached_file_name || null, message.attached_file_content || null,
        webSearch
      );

      const newMessages = [result.user_message];
      const newErrors = {};
      for (const resp of result.responses) {
        if (resp.error) {
          newErrors[resp.panel_id] = { message: resp.error, detail: resp.error_detail, turnNumber: result.turn_number };
        } else {
          newMessages.push({
            id: Date.now() + Math.random(),
            conversation_id: activeConvId,
            turn_number: result.turn_number,
            role: 'assistant',
            content: resp.content,
            provider: resp.provider,
            model: resp.model,
            panel_id: resp.panel_id,
            response_time_ms: resp.response_time_ms,
            token_count: resp.token_count,
            context_usage_pct: resp.context_usage_pct,
            created_at: new Date().toISOString(),
          });
        }
      }

      // Discard the stale answers/turns that followed the pre-edit question,
      // then splice in the edited message and its fresh responses.
      setMessages((prev) => {
        const kept = prev.filter((m) => m.turn_number < result.turn_number);
        return sortMessages([...kept, ...newMessages]);
      });
      if (Object.keys(newErrors).length > 0) setPanelErrors(newErrors);

      loadConversations();
      refreshCompactions(activeConvId);
    } catch (err) {
      console.error('Edit failed:', err);
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

  // ── Attachments (image or text document) ────────────────────
  const DOCUMENT_EXTENSIONS = [
    'pdf', 'docx', 'txt', 'md', 'markdown', 'csv', 'json', 'log', 'yaml', 'yml',
    'py', 'js', 'jsx', 'ts', 'tsx', 'html', 'css', 'xml', 'ini', 'cfg',
  ];

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file later
    if (!file) return;

    if (file.type.startsWith('image/')) {
      setAttachedFile(null);
      const reader = new FileReader();
      reader.onload = () => {
        setAttachedImage({ dataUrl: reader.result, name: file.name });
      };
      reader.readAsDataURL(file);
      return;
    }

    const ext = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : '';
    if (!DOCUMENT_EXTENSIONS.includes(ext)) {
      alert(`Unsupported file type: .${ext || 'unknown'}`);
      return;
    }

    setAttachedImage(null);
    setExtractingFile(true);
    try {
      const result = await extractFileText(file);
      setAttachedFile({ name: result.filename, content: result.content, truncated: result.truncated });
    } catch (err) {
      console.error('Failed to extract file text:', err);
      alert(`Failed to read file: ${err.message}`);
    } finally {
      setExtractingFile(false);
    }
  };

  const handleRemoveImage = () => {
    setAttachedImage(null);
  };

  const handleRemoveFile = () => {
    setAttachedFile(null);
    setWithSources(false);
  };

  // One shared source panel for the whole conversation — whichever citation
  // was last clicked, in any panel, from any model's MoM output, is what it
  // shows. Not spawned per panel/model.
  const handleCitationClick = (sourceIds, label, sentences, message) => {
    if (!sentences) return;
    setSourcePanel({
      sentences,
      highlightIds: sourceIds,
      label: message?.model ? `${message.model} — ${label}` : label,
    });
  };

  // ── Render ─────────────────────────────────────────────────
  if (!authChecked) return null;
  if (!currentUser) return <Auth onAuthenticated={handleAuthenticated} />;

  // Keep showing the welcome hero only while truly idle — once the first
  // message is in flight, switch to the panel view so the loading indicator
  // (and eventually the response) is visible instead of looking like nothing happened.
  const showWelcome = messages.length === 0 && !isLoading;

  return (
    <div className="app-layout">
      <Sidebar
        conversations={conversations}
        activeId={activeConvId}
        onSelect={setActiveConvId}
        onCreate={handleCreateConversation}
        onDelete={handleDeleteConversation}
        onOpenSettings={(tab) => { setSettingsTab(tab || 'account'); setShowSettings(true); }}
        userEmail={currentUser.email}
        onLogout={handleLogout}
        view={view}
        onChangeView={setView}
      />

      {view === 'ocr' ? (
        <DocumentOcrTab />
      ) : (
      <div className="main-content">
        {/* Panel controls */}
        <div className="panel-controls">
          <div className="panel-controls-left">
            <span className="panel-controls-label">{panels.length} Panel{panels.length !== 1 ? 's' : ''}</span>
            <button
              className="add-panel-btn"
              onClick={handleAddPanel}
              disabled={panels.length >= MAX_PANELS}
            >
              + Add panel
            </button>
            <PresetsMenu
              presets={presets}
              onApply={handleApplyPreset}
              onSave={handleSavePreset}
              onDelete={handleDeletePreset}
            />
          </div>

          <div className="panel-controls-right">
            <div className="theme-toggle">
              <button
                type="button"
                className={`theme-toggle-btn${theme === 'light' ? ' active' : ''}`}
                onClick={() => setTheme('light')}
                title="Light mode"
                id="theme-toggle-light"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="4" />
                  <line x1="12" y1="2" x2="12" y2="4" />
                  <line x1="12" y1="20" x2="12" y2="22" />
                  <line x1="4.93" y1="4.93" x2="6.34" y2="6.34" />
                  <line x1="17.66" y1="17.66" x2="19.07" y2="19.07" />
                  <line x1="2" y1="12" x2="4" y2="12" />
                  <line x1="20" y1="12" x2="22" y2="12" />
                  <line x1="4.93" y1="19.07" x2="6.34" y2="17.66" />
                  <line x1="17.66" y1="6.34" x2="19.07" y2="4.93" />
                </svg>
              </button>
              <button
                type="button"
                className={`theme-toggle-btn${theme === 'dark' ? ' active' : ''}`}
                onClick={() => setTheme('dark')}
                title="Dark mode"
                id="theme-toggle-dark"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Side-by-side comparison */}
        <div className={`comparison-view${showWelcome ? ' comparison-view-collapsed' : ''}`}>
          {panels.map((panel, i) => (
            <ChatPanel
              key={panel.panel_id || i}
              panelIndex={i}
              panelId={panel.panel_id}
              provider={panel.provider}
              model={panel.model}
              seenModels={panel.seenModels || []}
              visibleSinceTurn={panel.visibleSinceTurn ?? 0}
              compactions={compactions}
              messages={messages}
              isLoading={isLoading}
              error={
                panelErrors[panel.panel_id] ||
                (i === 0 && panelErrors.global ? { message: panelErrors.global, turnNumber: null } : null)
              }
              onRetry={handleRetry}
              retryingKey={retryingKey}
              onEdit={handleEditMessage}
              modelsByProvider={modelsByProvider}
              onSelect={(provider, model) => handleSelect(i, provider, model)}
              onAddCustomModel={handleAddCustomModel}
              onClose={() => handleClosePanel(i)}
              canClose={panels.length > 1}
              configuredProviders={configuredProviders}
              hideBody={showWelcome}
              visionModels={visionModels}
              restrictToVision={!!attachedImage}
              onCitationClick={handleCitationClick}
            />
          ))}
        </div>

        <SourcePanel panel={sourcePanel} onClose={() => setSourcePanel(null)} />

        {showWelcome && (
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
            accept="image/*,.pdf,.docx,.txt,.md,.csv,.json,.log,.yaml,.yml,.py,.js,.jsx,.ts,.tsx,.html,.css,.xml,.ini,.cfg"
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <div className="input-wrapper">
            <button
              type="button"
              className="attach-btn"
              onClick={handleAttachClick}
              title="Attach an image or document"
              id="attach-btn"
              disabled={extractingFile}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>

            <button
              type="button"
              className={`web-search-btn${webSearch ? ' active' : ''}`}
              onClick={() => setWebSearch((v) => !v)}
              title={webSearch
                ? 'Web search is ON — each message is answered using live results from DuckDuckGo. Click to turn off.'
                : 'Turn on web search — answer using live results from the web'}
              aria-pressed={webSearch}
              id="web-search-btn"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              </svg>
              Web
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

            {extractingFile && (
              <div className="attached-file-chip attached-file-chip-loading">
                <span className="attached-image-name">Reading file...</span>
              </div>
            )}

            {attachedFile && (
              <div className="attached-file-chip" title={attachedFile.truncated ? 'Truncated to 32,000 characters' : undefined}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <span className="attached-image-name">
                  {attachedFile.name}{attachedFile.truncated ? ' (truncated)' : ''}
                </span>
                <button type="button" className="attached-image-remove" onClick={handleRemoveFile} title="Remove file">
                  ✕
                </button>
              </div>
            )}

            {attachedFile && (
              <label className="with-sources-toggle" title="Ask for a structured summary (e.g. meeting minutes) with every point traceable back to the exact sentence in this document">
                <input
                  type="checkbox"
                  checked={withSources}
                  onChange={(e) => setWithSources(e.target.checked)}
                />
                Generate with sources
              </label>
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
      )}

      <SettingsModal
        isOpen={showSettings}
        initialTab={settingsTab}
        onClose={() => setShowSettings(false)}
        onKeysChange={handleKeysChange}
        userEmail={currentUser.email}
        onLogout={handleLogout}
      />
    </div>
  );
}
