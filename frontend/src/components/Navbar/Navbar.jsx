/* ============================================================
   Navbar — sticky top navigation with scroll-spy
   ============================================================
   The active link now tracks the section currently in view via
   IntersectionObserver, so users always know where they are on
   the long single-page layout. Anchor links are unchanged.
   ============================================================ */

import { useState, useEffect } from 'react';
import './Navbar.css';

const LINKS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'forecast', label: 'Forecast' },
  { id: 'eda', label: 'EDA Graphs' },
  { id: 'model-report', label: 'Model Audit' },
  { id: 'data-studio', label: 'Data Studio' },
];

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeId, setActiveId] = useState('dashboard');

  useEffect(() => {
    const sections = LINKS
      .map((l) => document.getElementById(l.id))
      .filter(Boolean);
    if (!sections.length || !('IntersectionObserver' in window)) return;

    // Track which section occupies the most viewport space near the top.
    const visibility = new Map();
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => visibility.set(e.target.id, e.intersectionRatio));
        let best = activeId;
        let bestRatio = -1;
        visibility.forEach((ratio, id) => {
          if (ratio > bestRatio) { bestRatio = ratio; best = id; }
        });
        if (bestRatio > 0) setActiveId(best);
      },
      { rootMargin: '-45% 0px -45% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] }
    );
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <nav className="navbar" id="main-navbar">
      <div className="navbar__inner container">
        <a href="/" className="navbar__brand" id="brand-link">
          <span className="navbar__logo-icon">📊</span>
          <span className="navbar__logo-text">
            TVS <span className="text-gradient">Forecast</span>
          </span>
        </a>

        <ul className={`navbar__links ${menuOpen ? 'navbar__links--open' : ''}`}>
          {LINKS.map((l) => (
            <li key={l.id}>
              <a
                href={`#${l.id}`}
                className={`navbar__link ${activeId === l.id ? 'navbar__link--active' : ''}`}
                id={`nav-${l.id}`}
                aria-current={activeId === l.id ? 'true' : undefined}
                onClick={() => setMenuOpen(false)}
              >
                {l.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="navbar__status" id="api-status-pill">
          <span className="navbar__status-dot"></span>
          API Live
        </div>

        <button
          className={`navbar__hamburger ${menuOpen ? 'navbar__hamburger--active' : ''}`}
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="Toggle navigation menu"
          id="hamburger-btn"
        >
          <span></span><span></span><span></span>
        </button>
      </div>
    </nav>
  );
}
