/* ============================================================
   HeroSection — animated landing section with gradient text
   ============================================================ */

import { useEffect } from 'react';
import { useForecast } from '../../contexts/ForecastContext';
import StatCard from '../StatCard/StatCard';
import { Skeleton } from '../Loader/Loader';
import './HeroSection.css';

export default function HeroSection() {
  const { state, fetchHealth } = useForecast();
  const { health, healthLoading } = state;

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  return (
    <section className="hero" id="dashboard">
      {/* Background decorations */}
      <div className="hero__glow hero__glow--teal"></div>
      <div className="hero__glow hero__glow--coral"></div>

      <div className="hero__content container">
        <div className="hero__text">
          <span className="hero__eyebrow">TVS Sales Intelligence</span>
          <h1 className="hero__title">
            Predict Revenue with
            <br />
            <span className="text-gradient">Machine Learning</span>
          </h1>
          <p className="hero__description">
            Generate detailed, customer-level sales forecasts powered by our trained ML model.
            Explore predictions by branch, customer, product, and date.
          </p>
        </div>

        {/* Health stat cards */}
        <div className="hero__stats">
          {healthLoading ? (
            <>
              <Skeleton height={96} radius="var(--radius-lg)" />
              <Skeleton height={96} radius="var(--radius-lg)" />
            </>
          ) : health ? (
            <>
              <StatCard icon="🤖" label="Winner Model" value={health.winner_model} accent="teal" delay={100} />
            </>
          ) : (
            <div className="hero__error">
              <p>⚠️ Could not connect to API. Make sure the backend is running.</p>
              <code>uvicorn main:app --reload</code>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
