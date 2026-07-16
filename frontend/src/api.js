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
export const createConversation = (title = 'New Chat') =>
  request('/api/conversations', { method: 'POST', body: JSON.stringify({ title }) });
export const deleteConversation = (id) =>
  request(`/api/conversations/${id}`, { method: 'DELETE' });
export const updateConversationTitle = (id, title) =>
  request(`/api/conversations/${id}/title`, { method: 'PUT', body: JSON.stringify({ title }) });
export const updatePanelLayout = (id, panels) =>
  request(`/api/conversations/${id}/panels`, { method: 'PUT', body: JSON.stringify({ panels }) });

// ── Chat ───────────────────────────────────────────────────
export const sendMessage = (conversation_id, message, targets, image = null) =>
  request('/api/chat/send', {
    method: 'POST',
    body: JSON.stringify({ conversation_id, message, targets, image }),
  });
export const getHistory = (conversation_id) =>
  request(`/api/chat/history/${conversation_id}`);
