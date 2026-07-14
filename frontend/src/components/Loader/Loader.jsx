/* ============================================================
   Loader — spinner + skeleton utilities
   ============================================================ */

import './Loader.css';

export function Spinner({ size = 32, className = '' }) {
  return (
    <div className={`spinner ${className}`} style={{ width: size, height: size }} id="spinner">
      <svg viewBox="0 0 50 50" className="spinner__svg">
        <circle className="spinner__track" cx="25" cy="25" r="20" fill="none" strokeWidth="4" />
        <circle className="spinner__fill" cx="25" cy="25" r="20" fill="none" strokeWidth="4" />
      </svg>
    </div>
  );
}

export function Skeleton({ width = '100%', height = 20, radius = 'var(--radius-sm)', className = '' }) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width, height, borderRadius: radius }}
    />
  );
}

export function FullPageLoader({ message = 'Loading...' }) {
  return (
    <div className="fullpage-loader" id="fullpage-loader">
      <Spinner size={48} />
      <p className="fullpage-loader__text">{message}</p>
    </div>
  );
}
