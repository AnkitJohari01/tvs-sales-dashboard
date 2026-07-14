import { useEffect, useState } from 'react';
import './CursorTrail.css';

export default function CursorTrail() {
  const [dots, setDots] = useState([]);

  useEffect(() => {
    let frameId = 0;

    const clearTrail = () => setDots([]);

    const handleMove = (event) => {
      if (frameId) window.cancelAnimationFrame(frameId);

      frameId = window.requestAnimationFrame(() => {
        const id = `${event.clientX}-${event.clientY}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        setDots((prev) => [...prev.slice(-10), { id, x: event.clientX, y: event.clientY }]);

        window.setTimeout(() => {
          setDots((prev) => prev.filter((dot) => dot.id !== id));
        }, 650);
      });
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseleave', clearTrail);

    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseleave', clearTrail);
      if (frameId) window.cancelAnimationFrame(frameId);
    };
  }, []);

  return (
    <div className="cursor-trail" aria-hidden="true">
      {dots.map((dot) => (
        <span
          key={dot.id}
          className="cursor-trail__dot"
          style={{ left: dot.x, top: dot.y }}
        />
      ))}
    </div>
  );
}
