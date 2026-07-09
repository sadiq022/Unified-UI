import React, { useState, useEffect } from 'react';
import { getModels } from '../api.js';

const PROVIDERS = [
  { id: 'openai', name: 'OpenAI' },
  { id: 'anthropic', name: 'Anthropic' },
  { id: 'gemini', name: 'Gemini' },
  { id: 'groq', name: 'Groq' },
  { id: 'deepseek', name: 'DeepSeek' },
  { id: 'openrouter', name: 'OpenRouter' },
];

export default function ModelSelector({ panelIndex, provider, model, onProviderChange, onModelChange, configuredProviders }) {
  const [models, setModels] = useState([]);

  useEffect(() => {
    if (provider) {
      getModels(provider)
        .then((data) => {
          setModels(data.models || []);
          // Auto-select first model if current model not in list
          if (data.models && data.models.length > 0 && !data.models.includes(model)) {
            onModelChange(data.models[0]);
          }
        })
        .catch(() => setModels([]));
    } else {
      setModels([]);
    }
  }, [provider]);

  return (
    <div className="chat-panel-header">
      <select
        className="model-select"
        value={provider}
        onChange={(e) => onProviderChange(e.target.value)}
        id={`provider-select-${panelIndex}`}
      >
        <option value="">Select Provider</option>
        {PROVIDERS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} {configuredProviders.includes(p.id) ? '✓' : ''}
          </option>
        ))}
      </select>

      {provider && (
        <>
          <select
            className="model-select"
            value={model}
            onChange={(e) => onModelChange(e.target.value)}
            id={`model-select-${panelIndex}`}
          >
            <option value="">Select Model</option>
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}
