import React, { useState, useRef, useEffect } from 'react';

export default function PresetsMenu({ presets, onApply, onSave, onDelete }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [open]);

  const handleSave = () => {
    const name = window.prompt('Save current panel setup as:');
    if (name && name.trim()) {
      onSave(name.trim());
      setOpen(false);
    }
  };

  return (
    <div className="presets-menu" ref={menuRef}>
      <button
        type="button"
        className="add-panel-btn"
        onClick={() => setOpen((o) => !o)}
        id="presets-menu-btn"
      >
        Presets ▾
      </button>

      {open && (
        <div className="presets-dropdown">
          {presets.length === 0 ? (
            <div className="presets-empty">No saved presets yet</div>
          ) : (
            presets.map((p) => (
              <div key={p.id} className="presets-item">
                <button
                  type="button"
                  className="presets-item-apply"
                  onClick={() => {
                    onApply(p);
                    setOpen(false);
                  }}
                >
                  {p.name}
                </button>
                <button
                  type="button"
                  className="presets-item-delete"
                  onClick={() => onDelete(p.id)}
                  title="Delete preset"
                >
                  ✕
                </button>
              </div>
            ))
          )}
          <div className="presets-divider" />
          <button type="button" className="presets-save-btn" onClick={handleSave}>
            + Save current as preset
          </button>
        </div>
      )}
    </div>
  );
}
