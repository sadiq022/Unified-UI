import React from 'react';

const SECTIONS = [
  { key: 'action_items', label: 'Action Items' },
  { key: 'decisions', label: 'Decisions' },
  { key: 'discussion_points', label: 'Discussion Points' },
];

// Renders the shared {action_items, decisions, discussion_points} citation
// schema — the same component regardless of which model/provider produced
// the JSON, since the schema itself is provider-agnostic.
export default function MomView({ data, onCitationClick }) {
  const hasAnything = SECTIONS.some((s) => (data?.[s.key] || []).length > 0);

  if (!hasAnything) {
    return <p className="mom-empty">No clear action items, decisions, or discussion points were found.</p>;
  }

  return (
    <div className="mom-view">
      {data?.truncated && (
        <div className="mom-truncated-notice">
          ⚠️ This response was cut off before finishing — showing the items that completed.
        </div>
      )}
      {SECTIONS.map(({ key, label }) => {
        const items = data?.[key] || [];
        if (items.length === 0) return null;
        return (
          <div key={key} className="mom-section">
            <div className="mom-section-title">{label}</div>
            <ul className="mom-section-list">
              {items.map((item, i) => (
                <li key={i} className="mom-item">
                  <span>{item.text}</span>
                  {item.source_ids && item.source_ids.length > 0 ? (
                    <button
                      type="button"
                      className="mom-citation"
                      onClick={() => onCitationClick?.(item.source_ids, `${label}: ${item.text}`)}
                      title={`Show source (${item.source_ids.join(', ')})`}
                    >
                      {item.source_ids.length}
                    </button>
                  ) : (
                    <span className="mom-citation mom-citation-none" title="No source sentence found for this point">
                      ?
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
