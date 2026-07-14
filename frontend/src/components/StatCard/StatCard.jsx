/* ============================================================
   StatCard — metric display card with gradient border glow
   ============================================================ */

import './StatCard.css';

export default function StatCard({ icon, label, value, accent = 'teal', delay = 0 }) {
  return (
    <div
      className={`stat-card stat-card--${accent}`}
      style={{ animationDelay: `${delay}ms` }}
      id={`stat-${label.replace(/\s+/g, '-').toLowerCase()}`}
    >
      <div className="stat-card__icon">{icon}</div>
      <div className="stat-card__body">
        <span className="stat-card__label">{label}</span>
        <span className="stat-card__value">{value ?? '—'}</span>
      </div>
      <div className="stat-card__glow"></div>
    </div>
  );
}
