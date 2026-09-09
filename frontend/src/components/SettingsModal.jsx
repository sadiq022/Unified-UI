import React, { useState, useEffect } from 'react';
import AccountTab from './AccountTab.jsx';
import ApiKeysTab from './ApiKeysTab.jsx';
import MemoriesTab from './MemoriesTab.jsx';

const TABS = [
  {
    id: 'account',
    label: 'Account',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    ),
  },
  {
    id: 'apikeys',
    label: 'API Keys',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="7.5" cy="15.5" r="5.5" />
        <path d="M21 2l-9.6 9.6" />
        <path d="M15.5 7.5l3 3L22 7l-3-3" />
      </svg>
    ),
  },
  {
    id: 'memories',
    label: 'Memories',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9.5 2A5.5 5.5 0 0 0 4 7.5v.5a3.5 3.5 0 0 0-1 6.7V17a5 5 0 0 0 5 5h.5" />
        <path d="M14.5 2A5.5 5.5 0 0 1 20 7.5v.5a3.5 3.5 0 0 1 1 6.7V17a5 5 0 0 1-5 5h-.5" />
        <path d="M9.5 2c1.5 0 2.5 1 2.5 2.5v15c0 1.1-.9 2.5-2.5 2.5" />
        <path d="M14.5 2c-1.5 0-2.5 1-2.5 2.5v15c0 1.1.9 2.5 2.5 2.5" />
      </svg>
    ),
  },
];

export default function SettingsModal({ isOpen, onClose, initialTab, userEmail, onLogout, onKeysChange }) {
  const [activeTab, setActiveTab] = useState(initialTab || 'account');

  // Jump to whichever tab was requested each time the modal opens (e.g.
  // opening it from a "Memories" shortcut should land there, not wherever
  // the tab was left last time).
  useEffect(() => {
    if (isOpen) setActiveTab(initialTab || 'account');
  }, [isOpen, initialTab]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>⚙️ Settings</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="settings-modal-body">
          <div className="settings-tabs">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`settings-tab${activeTab === tab.id ? ' active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          <div className="settings-tab-content">
            {activeTab === 'account' && <AccountTab userEmail={userEmail} onLogout={onLogout} />}
            {activeTab === 'apikeys' && <ApiKeysTab onKeysChange={onKeysChange} />}
            {activeTab === 'memories' && <MemoriesTab />}
          </div>
        </div>
      </div>
    </div>
  );
}
