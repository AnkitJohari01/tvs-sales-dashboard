import { useEffect, useState, useMemo, useRef } from 'react';
import { useForecast } from '../../contexts/ForecastContext';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Area,
  AreaChart, ReferenceLine, ReferenceDot, LabelList
} from 'recharts';
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';
import './EDADashboard.css';

/* ── Color Palette — aligned to Editorial Monograph design system ──
   Ink & paper base + single risograph accent (coral red-orange),
   riso-blue as the secondary specimen accent. Mirrors index.css. */
const INK    = '#0A0A0A';
const PAPER  = '#F4F1EA';
const NAVY   = '#FF3B1E'; /* primary series (bars) → coral accent */
const TEAL   = '#FF5A3C'; /* trend line → coral light */
const GOLD   = '#2E5BFF'; /* forecast band → riso blue */
const CARD   = '#121212';
const AXIS   = '#7A756B'; /* muted paper */
const GRID   = 'rgba(244,241,234,0.08)';
const DONUT_COLORS = ['#FF3B1E', '#FF5A3C', '#2E5BFF', '#C9C3B4', '#8A857A', '#4A4A4A'];

/* ── Formatters ─────────────────────────────────────── */
const fmtINR = (v) => {
  if (v >= 10000000) return `₹${(v / 10000000).toFixed(2)}Cr`;
  if (v >= 100000)   return `₹${(v / 100000).toFixed(2)}L`;
  if (v >= 1000)     return `₹${(v / 1000).toFixed(1)}K`;
  return `₹${Math.round(v)}`;
};

const fmtDate = (d) => {
  if (!d) return '';
  const dt = new Date(d);
  return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
};

/* ── Custom Tooltip ─────────────────────────────────── */
const DarkTooltip = ({ active, payload, label, labelFormatter }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="eda-tooltip">
      <p className="eda-tooltip__label">{labelFormatter ? labelFormatter(label) : label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || p.fill }}>
          {p.name}: {typeof p.value === 'number' ? fmtINR(p.value) : p.value}
        </p>
      ))}
    </div>
  );
};

/* ── Insight generator ──────────────────────────────── */
function useInsights(d) {
  return useMemo(() => {
    if (!d) return {};
    const b = d.branch_sales?.[0];
    const p = d.product_share?.[0];
    const c = d.top_customers?.[0];
    const bestDay  = d.daily_trend?.find(r => r.is_best);
    const worstDay = d.daily_trend?.find(r => r.is_worst);
    return {
      branch:  b ? `"${b.Branch}" leads all branches with ${fmtINR(b.HistRevenue)} in total sales.` : '',
      product: p ? `"${p['Item Description']}" is the top product, contributing ${p.pct}% of revenue.` : '',
      customer: c ? `"${c.CustomerName}" is the most valuable customer at ${fmtINR(c.HistRevenue)}.` : '',
      trend: bestDay && worstDay
        ? `Best day: ${fmtDate(bestDay.date)} (${fmtINR(bestDay.sales)}). Weakest: ${fmtDate(worstDay.date)}.`
        : '',
      mom: d.mom_change > 0
        ? `Sales grew ${d.mom_change}% compared to the previous month.`
        : d.mom_change < 0
        ? `Sales declined ${Math.abs(d.mom_change)}% compared to the previous month.`
        : '',
    };
  }, [d]);
}

/* ──────────────────────────────────────────────────────
   MAIN COMPONENT
   ────────────────────────────────────────────────────── */
export default function EDADashboard() {
  const { state, fetchEDA } = useForecast();
  const { eda: d, edaLoading, edaError } = state;
  const dashboardRef = useRef(null);
  const ins = useInsights(d);

  const [managerTarget, setManagerTarget] = useState(null);
  const [healthFilter, setHealthFilter] = useState('All');
  const [alertExplanation, setAlertExplanation] = useState(null);
  const [loadingExplanation, setLoadingExplanation] = useState(false);

  useEffect(() => { 
    if (!d && !edaLoading) fetchEDA(); 
    else if (managerTarget === null && d?.target_progress) {
      setManagerTarget(d.target_progress.target);
    }
  }, [d, edaLoading, fetchEDA, managerTarget]);

  const handleDownloadPDF = async () => {
    if (!dashboardRef.current) return;
    
    // Temporarily ensure the dashboard is fully expanded for capture
    const originalHeight = dashboardRef.current.style.height;
    dashboardRef.current.style.height = 'auto';

    const canvas = await html2canvas(dashboardRef.current, { 
      scale: 2,
      useCORS: true,
      windowHeight: dashboardRef.current.scrollHeight,
      scrollY: -window.scrollY
    });

    dashboardRef.current.style.height = originalHeight;

    const imgData = canvas.toDataURL('image/png');
    
    // Create a custom page size PDF to perfectly fit the entire long dashboard
    const pdf = new jsPDF('p', 'pt', [canvas.width, canvas.height]);
    
    // Fill the background just in case
    pdf.setFillColor('#121212');
    pdf.rect(0, 0, canvas.width, canvas.height, 'F');
    
    pdf.addImage(imgData, 'PNG', 0, 0, canvas.width, canvas.height);
    pdf.save('EDA_Report.pdf');
  };

  const handleExplainAlert = async () => {
    if (!d?.alert) return;
    setLoadingExplanation(true);
    try {
      const res = await fetch('http://localhost:8000/explain-alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(d.alert)
      });
      const data = await res.json();
      setAlertExplanation(data.explanation);
    } catch (err) {
      setAlertExplanation("Could not fetch explanation. Please check your connection.");
    } finally {
      setLoadingExplanation(false);
    }
  };

  if (edaLoading) return (
    <section id="eda" className="eda-dashboard"><div className="container">
      <div className="eda-loading"><div className="eda-spinner" /><p>Crunching the numbers...</p></div>
    </div></section>
  );
  if (edaError) return (
    <section id="eda" className="eda-dashboard"><div className="container">
      <div className="eda-error"><h3>Something went wrong</h3><p>{edaError}</p>
        <button className="eda-retry-btn" onClick={fetchEDA}>Try Again</button></div>
    </div></section>
  );
  if (!d) return null;

  const bestDay  = d.daily_trend?.find(r => r.is_best);
  const worstDay = d.daily_trend?.find(r => r.is_worst);

  return (
    <section id="eda" className="eda-dashboard" ref={dashboardRef}>
      <div className="container">

        {/* ═══ HEADER ═══ */}
        <div className="eda-header animate-fade-in-up">
          <div className="eda-header-left">
            <h2 className="eda-title">What does your data say?</h2>
            {/* <p className="eda-subtitle">A plain-language look at your sales — no jargon, just answers.</p> */}
          </div>
          <div style={{display: 'flex', gap: '12px'}}>
            <a className="btn-download" href={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/download-data-csv`} download style={{textDecoration:'none', color:'#0A0A0A', display:'flex', alignItems:'center'}}>
              <span style={{marginRight:'8px'}}>📊</span> Download CSV
            </a>
            <button className="btn-download" onClick={handleDownloadPDF} style={{display:'flex', alignItems:'center'}}>
              <span style={{marginRight:'8px'}}>⬇</span> Download PDF
            </button>
          </div>
        </div>

        {/* ═══ ALERT CARD ═══ */}
        {d.alert && (
          <div className="eda-alert-card animate-fade-in-up" style={{animationDelay:'40ms'}}>
            <div className="eda-alert-header">
              <span className="eda-alert-icon">⚠️</span>
              <h3>Unusual activity on {fmtDate(d.alert.date)}</h3>
            </div>
            <p className="eda-alert-text">
              Sales were {fmtINR(d.alert.sales)}, which is {Math.round(Math.abs(d.alert.sales - d.alert.avg) / d.alert.avg * 100)}% {d.alert.type === 'high' ? 'higher' : 'lower'} than the 7-day rolling average.
            </p>
            {alertExplanation ? (
              <p className="eda-alert-explanation"><strong>Possible reason:</strong> {alertExplanation}</p>
            ) : (
              <button className="btn-explain" onClick={handleExplainAlert} disabled={loadingExplanation}>
                {loadingExplanation ? 'Generating...' : 'Ask Claude for Explanation'}
              </button>
            )}
          </div>
        )}

        {/* ═══ 5. KPI CARDS ═══ */}
        <div className="kpi-row animate-fade-in-up" style={{animationDelay:'80ms'}}>
          <KPICard icon="💰" label="Total Sales"       value={fmtINR(d.kpis?.total_sales || 0)} />
          <KPICard icon="📅" label="Best Sales Day"    value={fmtDate(d.kpis?.best_day)} />
          <KPICard icon="📊" label="Avg Daily Sales"   value={fmtINR(d.kpis?.avg_daily_sales || 0)} />
          <KPICard icon="🎯" label="Forecast Accuracy" value={`${d.kpis?.forecast_accuracy || 0}%`} />
        </div>

        {/* ═══ 9. MoM METRIC TILE ═══ */}
        <div className="eda-two-col animate-fade-in-up" style={{animationDelay:'120ms'}}>
          <div className="metric-tile">
            <span className={`metric-tile__arrow ${d.mom_change >= 0 ? 'positive' : 'negative'}`}>
              {d.mom_change >= 0 ? '↑' : '↓'} {Math.abs(d.mom_change)}%
            </span>
            <span className="metric-tile__sub">vs {d.mom_vs_label}</span>
            <div className="metric-tile__spark">
              <ResponsiveContainer width="100%" height={50}>
                <LineChart data={d.monthly_trend}>
                  <Line type="monotone" dataKey="sales" stroke={TEAL} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="eda-insight">{ins.mom}</div>
          </div>

          {/* ═══ 7. PROGRESS BAR ═══ */}
          <div className="progress-card">
            <h3>Are we hitting the target?</h3>
            <p className="progress-card__label" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>{d.target_progress?.target_label} Target: ₹</span>
              <input 
                type="number" 
                className="target-input" 
                value={managerTarget !== null ? Math.round(managerTarget) : 0} 
                onChange={e => setManagerTarget(Number(e.target.value))}
              />
              <span>
                {' | '}Achieved: {fmtINR(d.target_progress?.achieved || 0)}
                {' | '}{managerTarget > 0 ? Math.round((d.target_progress?.achieved || 0) / managerTarget * 100) : 0}% Complete
              </span>
            </p>
            <div className="progress-bar">
              <div className="progress-bar__fill" style={{width: `${managerTarget > 0 ? Math.min(100, ((d.target_progress?.achieved || 0) / managerTarget * 100)) : 0}%`}} />
              <div className="progress-bar__marker" style={{left: `${d.target_progress?.last_year_pct || 0}%`}} title="Prior period benchmark" />
            </div>
            <div className="progress-bar__legend">
              <span><span className="dot dot--teal" /> Achieved</span>
              <span><span className="dot dot--grey" /> Remaining</span>
              <span><span className="dot dot--gold" /> Prior Period</span>
            </div>
          </div>
        </div>

        {/* ═══ CHART GRID ═══ */}
        <div className="eda-grid animate-fade-in-up" style={{animationDelay:'160ms'}}>

          {/* ═══ 1. VERTICAL BAR — Branch Sales ═══ */}
          <div className="eda-card">
            <h3>Which branch sold the most?</h3>
            <p>Total sales by branch, ranked highest to lowest.</p>
            <div className="eda-chart-wrapper">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.branch_sales} margin={{top:20,right:20,left:10,bottom:60}}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(244,241,234,0.08)" vertical={false} />
                  <XAxis dataKey="Branch" stroke="#7A756B" fontSize={10} angle={-35} textAnchor="end" interval={0} />
                  <YAxis tickFormatter={fmtINR} stroke="#7A756B" fontSize={11} />
                  <Tooltip content={<DarkTooltip />} />
                  <Bar dataKey="HistRevenue" fill={NAVY} radius={[4,4,0,0]} name="Sales">
                    <LabelList dataKey="HistRevenue" position="top" formatter={fmtINR} fill="#B9B4A9" fontSize={10} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="eda-insight">{ins.branch}</div>
          </div>

          {/* ═══ 2. LINE — Daily Trend ═══ */}
          <div className="eda-card">
            <h3>How did sales change over time?</h3>
            <p>Daily sales curve with highest and lowest days marked.</p>
            <div className="eda-chart-wrapper">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={d.daily_trend} margin={{top:10,right:20,left:10,bottom:5}}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(244,241,234,0.08)" />
                  <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#7A756B" fontSize={10} interval="preserveStartEnd" />
                  <YAxis tickFormatter={fmtINR} stroke="#7A756B" fontSize={11} />
                  <Tooltip content={<DarkTooltip labelFormatter={fmtDate} />} />
                  <Line type="monotone" dataKey="sales" stroke={TEAL} strokeWidth={2} dot={false} name="Sales" />
                  {bestDay && <ReferenceDot x={bestDay.date} y={bestDay.sales} r={6} fill={TEAL} stroke={PAPER} label={{value:`Best: ${fmtINR(bestDay.sales)}`, fill:'#FF5A3C', fontSize:10, position:'top'}} />}
                  {worstDay && <ReferenceDot x={worstDay.date} y={worstDay.sales} r={6} fill="#7A756B" stroke={PAPER} label={{value:`Low: ${fmtINR(worstDay.sales)}`, fill:'#7A756B', fontSize:10, position:'bottom'}} />}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="eda-insight">{ins.trend}</div>
          </div>

          {/* ═══ 3. DONUT — Product Share ═══ */}
          <div className="eda-card">
            <h3>What % does each product contribute?</h3>
            <p>Top 5 products plus everything else grouped as "Others".</p>
            <div className="eda-chart-wrapper eda-chart-wrapper--donut">
              <div className="donut-center">
                <span className="donut-center__value">{fmtINR(d.kpis?.total_sales || 0)}</span>
                <span className="donut-center__label">Total</span>
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Tooltip content={<DarkTooltip />} />
                  <Pie
                    data={d.product_share || []}
                    dataKey="HistRevenue"
                    nameKey="Item Description"
                    cx="50%" cy="50%"
                    innerRadius="55%" outerRadius="80%"
                    paddingAngle={2}
                    label={({pct}) => `${pct}%`}
                  >
                    {(d.product_share || []).map((_, i) => <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />)}
                  </Pie>
                  <Legend verticalAlign="bottom" wrapperStyle={{fontSize:'11px',color:'#B9B4A9'}} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="eda-insight">{ins.product}</div>
          </div>

          {/* ═══ 4. CALENDAR HEATMAP ═══ */}
          <div className="eda-card">
            <h3>Which days were hot vs cold?</h3>
            <p>Daily sales intensity for {d.calendar_month}. Darker = higher sales.</p>
            <CalendarHeatmap data={d.calendar_data} month={d.calendar_month} />
          </div>

          {/* ═══ 6. LEADERBOARD — Top Customers ═══ */}
          <div className="eda-card">
            <h3>Who are our best customers?</h3>
            <p>Top 5 customers ranked by total purchases.</p>
            <div className="leaderboard">
              {(d.top_customers || []).map((c, i) => {
                const pct = (c.HistRevenue / (d.customer_max || 1) * 100).toFixed(0);
                return (
                  <div key={i} className={`leaderboard__row ${i === 0 ? 'leaderboard__row--gold' : ''}`}>
                    <span className="leaderboard__rank">#{i+1}</span>
                    <div className="leaderboard__info">
                      <span className="leaderboard__name">{c.CustomerName}</span>
                      <div className="leaderboard__bar-bg">
                        <div className="leaderboard__bar-fill" style={{width:`${pct}%`}} />
                      </div>
                    </div>
                    <span className="leaderboard__value">{fmtINR(c.HistRevenue)}</span>
                  </div>
                );
              })}
            </div>
            <div className="eda-insight">{ins.customer}</div>
          </div>

          {/* ═══ 10. FORECAST vs ACTUAL ═══ */}
          <div className="eda-card">
            <h3>Forecast vs Actual — are we on track?</h3>
            <p>Comparing projected sales against the confidence band.</p>
            <div className="eda-chart-wrapper">
              {d.forecast_vs_actual?.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={d.forecast_vs_actual} margin={{top:10,right:20,left:10,bottom:5}}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(244,241,234,0.08)" />
                    <XAxis dataKey="ForecastedDate" tickFormatter={fmtDate} stroke="#7A756B" fontSize={10} interval="preserveStartEnd" />
                    <YAxis tickFormatter={fmtINR} stroke="#7A756B" fontSize={11} />
                    <Tooltip content={<DarkTooltip labelFormatter={fmtDate} />} />
                    <Area type="monotone" dataKey="upper" stroke="none" fill={GOLD} fillOpacity={0.15} name="Upper Bound" />
                    <Area type="monotone" dataKey="lower" stroke="none" fill={GOLD} fillOpacity={0.05} name="Lower Bound" />
                    <Line type="monotone" dataKey="forecast" stroke={GOLD} strokeWidth={2} strokeDasharray="6 3" dot={false} name="Forecasted" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : <p style={{color:'#7A756B',textAlign:'center',paddingTop:'4rem'}}>No forecast data available.</p>}
            </div>
          </div>

        </div>

        {/* ═══ 8. COLOR-CODED TABLE ═══ */}
        <div className="eda-table-section animate-fade-in-up" style={{animationDelay:'200ms'}}>
          <h3>Detailed breakdown — how did each branch perform?</h3>
          <p>Green rows beat the average, red rows fall below it.</p>
          <div className="eda-table-wrap">
            <table className="eda-table">
              <thead>
                <tr>
                  <th className="sticky-col">Branch</th>
                  <th>Customer</th>
                  <th>Date</th>
                  <th>Sales ₹</th>
                  <th>vs Avg %</th>
                </tr>
              </thead>
              <tbody>
                {(d.table_data || []).map((row, i) => (
                  <tr key={i} className={`eda-table__row--${row.status}`}>
                    <td className="sticky-col">{row.Branch}</td>
                    <td>{row.Customer}</td>
                    <td>{fmtDate(row.Date)}</td>
                    <td>{fmtINR(row.Sales)}</td>
                    <td>
                      <span className={row.vs_avg > 0 ? 'text-green' : row.vs_avg < 0 ? 'text-red' : ''}>
                        {row.vs_avg > 0 ? '↑' : row.vs_avg < 0 ? '↓' : '–'} {Math.abs(row.vs_avg)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* ═══ CUSTOMER HEALTH ═══ */}
        <div className="eda-health-section animate-fade-in-up" style={{animationDelay:'200ms', marginTop:'var(--sp-6)'}}>
          <div className="health-header">
            <h3>Customer Health</h3>
            <div className="health-filters">
              {['All', 'Active', 'At Risk', 'Churned'].map(f => (
                <button 
                  key={f} 
                  className={`health-filter-btn ${healthFilter === f ? 'active' : ''}`}
                  onClick={() => setHealthFilter(f)}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
          <div className="eda-table-container">
            <table className="eda-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Customer Name</th>
                  <th>Branch</th>
                  <th>Last Purchase Date</th>
                  <th>Days Since</th>
                </tr>
              </thead>
              <tbody>
                {(d.customer_health || [])
                  .filter(c => healthFilter === 'All' ? true : c.Status === healthFilter)
                  .sort((a,b) => b.DaysSince - a.DaysSince)
                  .map((row, i) => (
                  <tr key={i}>
                    <td>
                      <span className={`status-dot status-dot--${row.Status.replace(' ', '-').toLowerCase()}`} title={row.Status} />
                    </td>
                    <td>{row.CustomerName}</td>
                    <td>{row.Branch}</td>
                    <td>{fmtDate(row.LastDateOfPurchase)}</td>
                    <td>{row.DaysSince}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </section>
  );
}

/* ── Sub-Components ─────────────────────────────────── */

function KPICard({ icon, label, value }) {
  return (
    <div className="kpi-card">
      <span className="kpi-card__icon">{icon}</span>
      <div>
        <span className="kpi-card__value">{value}</span>
        <span className="kpi-card__label">{label}</span>
      </div>
    </div>
  );
}

function CalendarHeatmap({ data, month }) {
  if (!data?.length) return <p style={{color:'#7A756B'}}>No calendar data.</p>;
  const maxSales = Math.max(...data.map(d => d.sales));
  const minSales = Math.min(...data.map(d => d.sales));
  const dayLabels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

  const getColor = (sales) => {
    const ratio = maxSales === minSales ? 0.5 : (sales - minSales) / (maxSales - minSales);
    // Interpolate paper (#F4F1EA) → coral accent (#FF3B1E): darker/warmer = higher sales
    const r = Math.round(244 + ratio * (255 - 244));
    const g = Math.round(241 - ratio * (241 - 59));
    const b = Math.round(234 - ratio * (234 - 30));
    return `rgb(${r},${g},${b})`;
  };

  // Build grid: 5 weeks x 7 days
  const grid = Array.from({length: 5}, () => Array(7).fill(null));
  data.forEach(d => {
    if (d.week < 5 && d.weekday < 7) grid[d.week][d.weekday] = d;
  });

  return (
    <div className="cal-heatmap">
      <div className="cal-heatmap__header">
        {dayLabels.map(l => <span key={l}>{l}</span>)}
      </div>
      {grid.map((week, wi) => (
        <div key={wi} className="cal-heatmap__row">
          {week.map((cell, di) => (
            <div
              key={di}
              className={`cal-heatmap__cell ${cell ? '' : 'cal-heatmap__cell--empty'}`}
              style={cell ? {backgroundColor: getColor(cell.sales)} : {}}
              title={cell ? `${fmtDate(cell.date)}: ${fmtINR(cell.sales)}` : ''}
            >
              {cell && <span className="cal-heatmap__day">{new Date(cell.date).getDate()}</span>}
            </div>
          ))}
        </div>
      ))}
      <div className="cal-heatmap__scale">
        <span>Low</span>
        <div className="cal-heatmap__gradient" />
        <span>High</span>
      </div>
    </div>
  );
}
