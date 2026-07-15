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
];

export default function ApiKeyManager({ isOpen, onClose, onKeysChange }) {
  const [keys, setKeys] = useState({});         // provider -> { preview, configured }
  const [inputs, setInputs] = useState({});       // provider -> input value
  const [saving, setSaving] = useState({});       // provider -> boolean

  useEffect(() => {
    if (isOpen) loadKeys();
  }, [isOpen]);

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

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>🔑 API Key Management</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
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

                <div className="api-key-input-row">
                  <input
                    type="password"
                    className="api-key-input"
                    placeholder={p.placeholder}
                    value={inputs[p.id] || ''}
                    onChange={(e) => setInputs((prev) => ({ ...prev, [p.id]: e.target.value }))}
                    onKeyDown={(e) => e.key === 'Enter' && handleSave(p.id)}
                    id={`api-key-input-${p.id}`}
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
      </div>
    </div>
  );
}
