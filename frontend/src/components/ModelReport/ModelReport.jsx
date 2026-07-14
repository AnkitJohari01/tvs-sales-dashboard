/* ============================================================
   ModelReport — honest model-audit panel
   Surfaces the REAL allocation-risk findings computed from the
   delivered artifacts, plus a clearly-labelled demonstration of
   the rolling-origin backtest harness. Consumes GET /model-report.
   ============================================================ */

import React, { useEffect, useState } from 'react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts';
import { getModelReport } from '../../services/api';
import { formatNumberIN } from '../../utils/format';
import './ModelReport.css';

const fmtPct = (v) => (v == null ? '—' : `${v}%`);

export default function ModelReport() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getModelReport()
      .then((d) => { if (alive) { setData(d); setLoading(false); } })
      .catch((e) => { if (alive) { setError(e.message || 'Failed to load model report'); setLoading(false); } });
    return () => { alive = false; };
  }, []);

  if (loading) {
    return (
      <section className="section" id="model-report">
        <div className="container"><div className="mr-loading">Loading model audit…</div></div>
      </section>
    );
  }
  if (error) {
    return (
      <section className="section" id="model-report">
        <div className="container">
          <div className="mr-error">Model report unavailable: {error}
            <div className="mr-hint">Run <code>python run_analysis.py</code> on the backend to generate it.</div>
          </div>
        </div>
      </section>
    );
  }

  const real = data.sections.real_findings;
  const bt = data.sections.backtest_demo;

  const recencyData = real.recency_buckets.map((b) => ({
    name: b.bucket, pct: b.weight_pct,
    stale: b.bucket.includes('Lapsing') || b.bucket.includes('Churned'),
  }));

  const stepData = (bt.wmape_by_step || []).map((v, i) => ({
    step: i + 1, model: v, naive: bt.naive_wmape_by_step ? bt.naive_wmape_by_step[i] : null,
  }));

  return (
    <section className="section" id="model-report">
      <div className="container">
        <h2 className="mr-title">Model Audit — Honest Accuracy & Risk</h2>
        <p className="mr-sub">
          A senior-data-science review of what this forecaster actually measures.
          Findings in the first block are computed from the delivered data; the backtest
          block demonstrates the evaluation harness.
        </p>

        {/* ── REAL FINDINGS ─────────────────────────────── */}
        <div className="mr-banner mr-banner-real">
          <span className="mr-tag">MEASURED FROM YOUR DATA</span>
          <div className="mr-headline">
            <strong>{fmtPct(real.stale_allocation_pct)}</strong> of all allocated future revenue
            is assigned to customers who have <strong>not purchased in 60+ days</strong>.
          </div>
          <p className="mr-headline-note">
            The forecast splits every future rupee using a fixed historical share. Because that
            share never updates, revenue keeps flowing to lapsing and churned accounts. As-of
            {' '}{real.as_of}; median {real.median_days_since_purchase} days since last purchase.
          </p>
        </div>

        <div className="mr-grid">
          <div className="mr-card mr-chart-card">
            <h3>Where allocated revenue goes (by customer recency)</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={recencyData} margin={{ top: 8, right: 16, left: 0, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="name" stroke="#94A3B8" fontSize={11} angle={-12} textAnchor="end" height={50} />
                <YAxis stroke="#94A3B8" fontSize={11} unit="%" />
                <RTooltip contentStyle={{ background: '#1E293B', border: '1px solid #334155', borderRadius: 8, color: '#fff' }} />
                <Bar dataKey="pct" name="% of allocated revenue" radius={[4, 4, 0, 0]}>
                  {recencyData.map((d, i) => (
                    <Cell key={i} fill={d.stale ? '#E29578' : '#84A98C'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="mr-card mr-kpis">
            <h3>Data & structure</h3>
            <ul className="mr-kpi-list">
              <li><span>Customers</span><strong>{formatNumberIN(real.n_customers)}</strong></li>
              <li><span>Products</span><strong>{formatNumberIN(real.n_products)}</strong></li>
              <li><span>Customer/product combos</span><strong>{formatNumberIN(real.n_combos)}</strong></li>
              <li><span>Top 2000 combos hold</span><strong>{fmtPct(real.concentration.top_2000_pct)} of weight</strong></li>
              <li className="mr-warn"><span>Negative-revenue rows</span><strong>{real.data_quality.negative_revenue_rows}</strong></li>
              <li className="mr-warn"><span>Zero-revenue rows</span><strong>{real.data_quality.zero_revenue_rows}</strong></li>
            </ul>
          </div>
        </div>

        {/* ── BACKTEST HARNESS ──────────────────────────── */}
        <div className="mr-banner mr-banner-demo">
          <span className="mr-tag mr-tag-demo">HARNESS DEMONSTRATION</span>
          <div className="mr-demo-metrics">
            <div className="mr-metric">
              <span className="mr-metric-label">1-step CV (optimistic)</span>
              <span className="mr-metric-val">{fmtPct(bt.model_1step_wmape)}</span>
            </div>
            <div className="mr-metric-arrow">→</div>
            <div className="mr-metric">
              <span className="mr-metric-label">30-day multi-step (honest)</span>
              <span className="mr-metric-val mr-metric-hot">{fmtPct(bt.model_multistep_wmape)}</span>
            </div>
            <div className="mr-metric">
              <span className="mr-metric-label">Seasonal-naive floor</span>
              <span className="mr-metric-val">{fmtPct(bt.naive_multistep_wmape)}</span>
            </div>
            <div className="mr-metric">
              <span className="mr-metric-label">MASE vs naive</span>
              <span className="mr-metric-val">{bt.model_mase} {bt.model_mase < 1 ? '✓' : '✗'}</span>
            </div>
          </div>
          <p className="mr-demo-note">{bt.note}</p>
        </div>

        <div className="mr-card mr-chart-card">
          <h3>Error grows with the forecast horizon (WMAPE by day ahead)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={stepData} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.08)" />
              <XAxis dataKey="step" stroke="#94A3B8" fontSize={11} label={{ value: 'days ahead', position: 'insideBottom', offset: -2, fill: '#94A3B8', fontSize: 11 }} />
              <YAxis stroke="#94A3B8" fontSize={11} unit="%" />
              <RTooltip contentStyle={{ background: '#1E293B', border: '1px solid #334155', borderRadius: 8, color: '#fff' }} />
              <Legend />
              <Line type="monotone" dataKey="model" name="Model" stroke="#84A98C" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="naive" name="Seasonal-naive" stroke="#E29578" strokeWidth={2} strokeDasharray="5 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="mr-takeaways">
          <h3>What we recommend</h3>
          <ol>
            <li>Report <strong>WMAPE</strong> (scale-stable) and always against the <strong>seasonal-naive baseline</strong>, not raw MAPE.</li>
            <li>Validate the forecast the way it ships: <strong>rolling-origin, multi-step</strong> — not 1-step CV.</li>
            <li>Refresh allocation weights on a rolling window and <strong>decay churned customers</strong> instead of paying them forever.</li>
            <li>Measure accuracy at the <strong>customer/product level actually displayed</strong>, not just the daily total.</li>
            <li>Supply the source sales history so the headline accuracy can be <strong>independently reproduced</strong>.</li>
          </ol>
        </div>
      </div>
    </section>
  );
}
