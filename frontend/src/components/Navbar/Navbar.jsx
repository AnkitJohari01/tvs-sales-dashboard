/* ============================================================
   Navbar — sticky top navigation bar
   ============================================================ */

import { useState } from 'react';
import './Navbar.css';

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <nav className="navbar" id="main-navbar">
      <div className="navbar__inner container">
        {/* Logo / Brand */}
        <a href="/" className="navbar__brand" id="brand-link">
          <span className="navbar__logo-icon">📊</span>
          <span className="navbar__logo-text">
            TVS <span className="text-gradient">Forecast</span>
          </span>
        </a>

        {/* Desktop nav links */}
        <ul className={`navbar__links ${menuOpen ? 'navbar__links--open' : ''}`}>
          <li><a href="#dashboard" className="navbar__link navbar__link--active" id="nav-dashboard">Dashboard</a></li>
          <li><a href="#forecast" className="navbar__link" id="nav-forecast">Forecast</a></li>
          <li><a href="#eda" className="navbar__link" id="nav-eda">EDA Graphs</a></li>
        </ul>

        {/* Status pill */}
        <div className="navbar__status" id="api-status-pill">
          <span className="navbar__status-dot"></span>
          API Live
        </div>

        {/* Hamburger for mobile */}
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
