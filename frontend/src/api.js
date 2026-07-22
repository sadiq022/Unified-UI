const BASE = '';
const TOKEN_KEY = 'unifiedui:token';

let authToken = localStorage.getItem(TOKEN_KEY) || null;

export function getToken() {
  return authToken;
}

export function setToken(token) {
  authToken = token;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

// Fired whenever a request comes back 401 (expired/invalid token) so the app
// can immediately drop to the login screen instead of leaving stale, broken UI up.
export const AUTH_LOGOUT_EVENT = 'unifiedui:auth-logout';

// Reads the `exp` claim out of a JWT without verifying it (verification is the
// server's job) — used only to schedule a client-side auto-logout timer.
export function getTokenExpiryMs(token) {
  try {
    let payloadB64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    while (payloadB64.length % 4) payloadB64 += '=';
    const payload = JSON.parse(atob(payloadB64));
    return payload.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Auth ───────────────────────────────────────────────────
export const signup = (email, password) =>
  request('/api/auth/signup', { method: 'POST', body: JSON.stringify({ email, password }) });
export const login = (email, password) =>
  request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
export const getMe = () => request('/api/auth/me');

// ── API Keys ───────────────────────────────────────────────
export const getApiKeys = () => request('/api/keys');
export const saveApiKey = (provider, api_key) =>
  request('/api/keys', { method: 'POST', body: JSON.stringify({ provider, api_key }) });
export const deleteApiKey = (provider) =>
  request(`/api/keys/${provider}`, { method: 'DELETE' });
export const getModels = (provider) =>
  request(`/api/keys/models/${provider}`);
export const getVisionModels = () => request('/api/keys/vision-models');

// ── Custom Models ──────────────────────────────────────────
export const addCustomModel = (provider, model) =>
  request('/api/custom-models', { method: 'POST', body: JSON.stringify({ provider, model }) });

// ── Conversations ──────────────────────────────────────────
export const getConversations = () => request('/api/conversations');
export const getConversation = (id) => request(`/api/conversations/${id}`);
export const searchConversations = (q) =>
  request(`/api/conversations/search?q=${encodeURIComponent(q)}`);
export const createConversation = (title = 'New Chat') =>
  request('/api/conversations', { method: 'POST', body: JSON.stringify({ title }) });
export const deleteConversation = (id) =>
  request(`/api/conversations/${id}`, { method: 'DELETE' });
export const updateConversationTitle = (id, title) =>
  request(`/api/conversations/${id}/title`, { method: 'PUT', body: JSON.stringify({ title }) });
export const updatePanelLayout = (id, panels) =>
  request(`/api/conversations/${id}/panels`, { method: 'PUT', body: JSON.stringify({ panels }) });

// ── Panel Presets ────────────────────────────────────────────
export const getPanelPresets = () => request('/api/panel-presets');
export const savePanelPreset = (name, panels) =>
  request('/api/panel-presets', { method: 'POST', body: JSON.stringify({ name, panels }) });
export const deletePanelPreset = (id) =>
  request(`/api/panel-presets/${id}`, { method: 'DELETE' });

// ── Files ────────────────────────────────────────────────────
// Uploads a document (PDF/DOCX/text) and gets back its extracted text
// (truncated to 32k characters server-side). Bypasses request() since it
// needs a multipart body, not JSON.
export async function extractFileText(file) {
  const formData = new FormData();
  formData.append('file', file);

  const headers = {};
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const res = await fetch(`${BASE}/api/files/extract-text`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Chat ───────────────────────────────────────────────────
export const sendMessage = (conversation_id, message, targets, image = null) =>
  request('/api/chat/send', {
    method: 'POST',
    body: JSON.stringify({ conversation_id, message, targets, image }),
  });

// Streams SSE events from /api/chat/send-stream, calling onEvent(payload) for
// each one. Doesn't use the request() helper since it needs the raw response
// body reader instead of a single parsed JSON result.
export async function sendMessageStream(
  conversation_id, message, targets, image, attachedFileName, attachedFileContent, onEvent
) {
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const res = await fetch(`${BASE}/api/chat/send-stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      conversation_id, message, targets, image,
      attached_file_name: attachedFileName,
      attached_file_content: attachedFileContent,
    }),
  });

  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const line = rawEvent.split('\n').find((l) => l.startsWith('data:'));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch (err) {
        console.error('Failed to parse stream event:', err);
      }
    }
  }
}

export const getHistory = (conversation_id) =>
  request(`/api/chat/history/${conversation_id}`);
export const retryMessage = (conversation_id, turn_number, provider, model) =>
  request('/api/chat/retry', {
    method: 'POST',
    body: JSON.stringify({ conversation_id, turn_number, provider, model }),
  });
export const editMessage = (
  conversation_id, message_id, content, targets, image = null, attachedFileName = null, attachedFileContent = null
) =>
  request('/api/chat/edit', {
    method: 'POST',
    body: JSON.stringify({
      conversation_id, message_id, content, targets, image,
      attached_file_name: attachedFileName,
      attached_file_content: attachedFileContent,
    }),
  });
