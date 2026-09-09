import React from 'react';

// The "Account" tab content inside the unified Settings modal.
export default function AccountTab({ userEmail, onLogout }) {
  return (
    <div className="settings-pane-body">
      <div className="account-row">
        <div className="account-row-label">Signed in as</div>
        <div className="account-email">{userEmail}</div>
      </div>

      <button type="button" className="account-logout-btn" onClick={onLogout}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <polyline points="16 17 21 12 16 7" />
          <line x1="21" y1="12" x2="9" y2="12" />
        </svg>
        Log out
      </button>
    </div>
  );
}
