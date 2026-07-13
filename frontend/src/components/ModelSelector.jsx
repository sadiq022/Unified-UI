import React, { useState } from 'react';
import { PROVIDERS } from '../constants.js';

const CUSTOM_VALUE = '__custom__';

export default function ModelSelector({
  panelIndex,
  provider,
  model,
  modelsByProvider,
  configuredProviders,
  onSelect,
  onAddCustomModel,
  onClose,
  canClose,
}) {
  const [addingProvider, setAddingProvider] = useState(null);
  const [customValue, setCustomValue] = useState('');
  const [saving, setSaving] = useState(false);

  const handleChange = (e) => {
    const [selectedProvider, selectedModel] = e.target.value.split('::');
    if (selectedModel === CUSTOM_VALUE) {
      setAddingProvider(selectedProvider);
      setCustomValue('');
      return;
    }
    onSelect(selectedProvider, selectedModel);
  };

  const handleCustomSubmit = async () => {
    const name = customValue.trim();
    if (!name || saving) return;
    setSaving(true);
    try {
      await onAddCustomModel(addingProvider, name);
      onSelect(addingProvider, name);
      setAddingProvider(null);
      setCustomValue('');
    } finally {
      setSaving(false);
    }
  };

  const handleCustomKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleCustomSubmit();
    } else if (e.key === 'Escape') {
      setAddingProvider(null);
    }
  };

  return (
    <div className="chat-panel-header">
      {provider && <span className={`provider-dot ${provider}`} />}

      {addingProvider ? (
        <div className="custom-model-input-row">
          <input
            autoFocus
            type="text"
            className="custom-model-input"
            placeholder={`Custom ${PROVIDERS.find((p) => p.id === addingProvider)?.name || ''} model name`}
            value={customValue}
            onChange={(e) => setCustomValue(e.target.value)}
            onKeyDown={handleCustomKeyDown}
          />
          <button
            type="button"
            className="custom-model-confirm"
            onClick={handleCustomSubmit}
            disabled={!customValue.trim() || saving}
            title="Add model"
          >
            ✓
          </button>
          <button
            type="button"
            className="custom-model-cancel"
            onClick={() => setAddingProvider(null)}
            title="Cancel"
          >
            ✕
          </button>
        </div>
      ) : (
        <select
          className="model-select"
          value={provider && model ? `${provider}::${model}` : ''}
          onChange={handleChange}
          id={`model-select-${panelIndex}`}
        >
          <option value="">Select Model</option>
          {PROVIDERS.map((p) => (
            <optgroup key={p.id} label={`${p.name}${configuredProviders.includes(p.id) ? ' ✓' : ''}`}>
              {(modelsByProvider[p.id] || []).map((m) => (
                <option key={`${p.id}::${m}`} value={`${p.id}::${m}`}>
                  {m}
                </option>
              ))}
              <option value={`${p.id}::${CUSTOM_VALUE}`}>+ Add custom model</option>
            </optgroup>
          ))}
        </select>
      )}

      <label className="panel-toggle" title={canClose ? 'Turn panel off' : 'At least one panel must stay on'}>
        <input type="checkbox" checked disabled={!canClose} onChange={onClose} />
        <span className="panel-toggle-track">
          <span className="panel-toggle-thumb" />
        </span>
      </label>
    </div>
  );
}
