import React, { useState } from 'react';
import { signup, login, setToken } from '../api.js';

export default function Auth({ onAuthenticated }) {
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setError('');
    setLoading(true);
    try {
      const action = mode === 'signup' ? signup : login;
      const result = await action(email.trim(), password);
      setToken(result.access_token);
      onAuthenticated(result.user, result.expires_at);
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-screen">
      <form className="auth-card" onSubmit={handleSubmit}>
        <div className="auth-logo">
          <div className="auth-logo-icon">U</div>
          <h1>Unified UI</h1>
        </div>
        <p className="auth-subtitle">
          {mode === 'login' ? 'Log in to continue' : 'Create an account to get started'}
        </p>

        {error && <div className="error-banner">⚠️ {error}</div>}

        <label className="auth-field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>

        <label className="auth-field">
          <span>Password</span>
          <input
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </label>

        <button type="submit" className="auth-submit-btn" disabled={loading}>
          {loading ? '...' : mode === 'login' ? 'Log in' : 'Sign up'}
        </button>

        <button
          type="button"
          className="auth-toggle-btn"
          onClick={() => {
            setMode((m) => (m === 'login' ? 'signup' : 'login'));
            setError('');
          }}
        >
          {mode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Log in'}
        </button>
      </form>
    </div>
  );
}
