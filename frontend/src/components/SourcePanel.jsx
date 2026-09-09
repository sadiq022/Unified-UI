import React, { useEffect, useRef } from 'react';

// One shared right-side drawer for the whole conversation — not per panel,
// not per model. Whichever citation was last clicked (in any panel, from any
// model's MoM output) is what it shows; it doesn't spawn a copy per model.
export default function SourcePanel({ panel, onClose }) {
  const highlightRef = useRef(null);

  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [panel]);

  if (!panel) return null;

  const highlightSet = new Set(panel.highlightIds || []);
  let firstHighlightAssigned = false;

  return (
    <div className="source-panel">
      <div className="source-panel-header">
        <div className="source-panel-title">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          Source
        </div>
        <button type="button" className="source-panel-close" onClick={onClose}>✕</button>
      </div>

      {panel.label && <div className="source-panel-label">{panel.label}</div>}

      <div className="source-panel-body">
        {(panel.sentences || []).map((s) => {
          const isHighlighted = highlightSet.has(s.id);
          const ref = isHighlighted && !firstHighlightAssigned ? highlightRef : null;
          if (isHighlighted) firstHighlightAssigned = true;
          return (
            <span
              key={s.id}
              ref={ref}
              className={`source-sentence${isHighlighted ? ' highlighted' : ''}`}
            >
              {s.text}{' '}
            </span>
          );
        })}
      </div>
    </div>
  );
}
