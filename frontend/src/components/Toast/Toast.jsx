/* ============================================================
   Toast — notification banner that auto-dismisses
   ============================================================ */

import { useEffect } from 'react';
import './Toast.css';

export default function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(onClose, 4000);
    return () => clearTimeout(timer);
  }, [toast, onClose]);

  if (!toast) return null;

  const icon = toast.type === 'success' ? '✅' : toast.type === 'error' ? '❌' : 'ℹ️';

  return (
    <div className={`toast toast--${toast.type}`} id="toast-notification">
      <span className="toast__icon">{icon}</span>
      <span className="toast__message">{toast.message}</span>
      <button className="toast__close" onClick={onClose} aria-label="Close notification">✕</button>
    </div>
  );
}
