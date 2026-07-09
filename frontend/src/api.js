const BASE = '';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── API Keys ───────────────────────────────────────────────
export const getApiKeys = () => request('/api/keys');
export const saveApiKey = (provider, api_key) =>
  request('/api/keys', { method: 'POST', body: JSON.stringify({ provider, api_key }) });
export const deleteApiKey = (provider) =>
  request(`/api/keys/${provider}`, { method: 'DELETE' });
export const getModels = (provider) =>
  request(`/api/keys/models/${provider}`);

// ── Conversations ──────────────────────────────────────────
export const getConversations = () => request('/api/conversations');
export const createConversation = (title = 'New Chat') =>
  request('/api/conversations', { method: 'POST', body: JSON.stringify({ title }) });
export const deleteConversation = (id) =>
  request(`/api/conversations/${id}`, { method: 'DELETE' });
export const updateConversationTitle = (id, title) =>
  request(`/api/conversations/${id}/title`, { method: 'PUT', body: JSON.stringify({ title }) });

// ── Chat ───────────────────────────────────────────────────
export const sendMessage = (conversation_id, message, targets) =>
  request('/api/chat/send', {
    method: 'POST',
    body: JSON.stringify({ conversation_id, message, targets }),
  });
export const getHistory = (conversation_id) =>
  request(`/api/chat/history/${conversation_id}`);
