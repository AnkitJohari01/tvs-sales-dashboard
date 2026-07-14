/* ============================================================
   Footer — minimal branded footer
   ============================================================ */

import './Footer.css';

export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="footer" id="main-footer">
      <div className="container footer__inner">
        <p className="footer__text">
          © {year} <span className="text-gradient">Forecast</span> — Sales Intelligence Platform
        </p>
        <p className="footer__tech">
          Built with React + FastAPI
        </p>
      </div>
    </footer>
  );
}
