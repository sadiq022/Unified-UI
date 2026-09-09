import React, { useState, useEffect } from 'react';
import { getApiKeys, saveApiKey, deleteApiKey } from '../api.js';

const PROVIDERS = [
  { id: 'openai', name: 'OpenAI', placeholder: 'sk-...' },
  { id: 'anthropic', name: 'Anthropic', placeholder: 'sk-ant-...' },
  { id: 'gemini', name: 'Gemini', placeholder: 'AIza...' },
  { id: 'groq', name: 'Groq', placeholder: 'gsk_...' },
  { id: 'deepseek', name: 'DeepSeek', placeholder: 'sk-...' },
  { id: 'openrouter', name: 'OpenRouter', placeholder: 'sk-or-...' },
  { id: 'nvidia', name: 'NVIDIA', placeholder: 'nvapi-...' },
  { id: 'cerebras', name: 'Cerebras', placeholder: 'csk-...' },
  { id: 'local', name: 'Local', placeholder: 'http://localhost:8000', isUrl: true },
];

// The "API Keys" tab content inside the unified Settings modal — no modal
// chrome of its own, that's owned by SettingsModal now.
export default function ApiKeysTab({ onKeysChange }) {
  const [keys, setKeys] = useState({});         // provider -> { preview, configured }
  const [inputs, setInputs] = useState({});       // provider -> input value
  const [saving, setSaving] = useState({});       // provider -> boolean

  useEffect(() => {
    loadKeys();
  }, []);

  const loadKeys = async () => {
    try {
      const data = await getApiKeys();
      const map = {};
      data.forEach((k) => {
        map[k.provider] = { preview: k.key_preview, configured: true };
      });
      setKeys(map);
      onKeysChange?.(Object.keys(map));
    } catch (err) {
      console.error('Failed to load keys:', err);
    }
  };

  const handleSave = async (provider) => {
    const value = inputs[provider];
    if (!value?.trim()) return;

    setSaving((p) => ({ ...p, [provider]: true }));
    try {
      await saveApiKey(provider, value.trim());
      setInputs((p) => ({ ...p, [provider]: '' }));
      await loadKeys();
    } catch (err) {
      alert(`Failed to save: ${err.message}`);
    } finally {
      setSaving((p) => ({ ...p, [provider]: false }));
    }
  };

  const handleDelete = async (provider) => {
    try {
      await deleteApiKey(provider);
      await loadKeys();
    } catch (err) {
      alert(`Failed to delete: ${err.message}`);
    }
  };

  return (
    <div className="settings-pane-body">
      {PROVIDERS.map((p) => {
        const isConfigured = keys[p.id]?.configured;
        return (
          <div key={p.id} className="api-key-row">
            <div className="api-key-row-header">
              <div className="api-key-row-label">
                <span className={`provider-badge ${p.id}`}>{p.id}</span>
                <span>{p.name}</span>
              </div>
              <span className={`api-key-status ${isConfigured ? 'configured' : 'not-configured'}`}>
                {isConfigured ? `✓ ${keys[p.id].preview}` : 'Not configured'}
              </span>
            </div>

            {p.isUrl && (
              <div className="api-key-row-hint">
                Address of your local OpenAI-compatible server (no key needed)
              </div>
            )}

            <div className="api-key-input-row">
              <input
                type={p.isUrl ? 'text' : 'password'}
                className="api-key-input"
                placeholder={p.placeholder}
                value={inputs[p.id] || ''}
                onChange={(e) => setInputs((prev) => ({ ...prev, [p.id]: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && handleSave(p.id)}
                id={`api-key-input-${p.id}`}
                name={`api-key-${p.id}`}
                autoComplete="new-password"
                data-lpignore="true"
                data-1p-ignore
              />
              <button
                className="api-key-save-btn"
                onClick={() => handleSave(p.id)}
                disabled={saving[p.id]}
              >
                {saving[p.id] ? '...' : isConfigured ? 'Update' : 'Save'}
              </button>
              {isConfigured && (
                <button
                  className="api-key-delete-btn"
                  onClick={() => handleDelete(p.id)}
                >
                  🗑
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
