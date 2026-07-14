import React, { useState, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer, Area, AreaChart, ReferenceLine
} from 'recharts';
import { formatNumberIN, abbreviateIN } from '../../utils/format';
import './DynamicForecastUI.css';

/* Indeterminate multi-stage progress for the 30-60s tournament. Advances
   through named stages on a timeline and holds on the last until results
   arrive, so the wait reads as deliberate rather than a hung spinner. */
function ForecastProgress() {
  const steps = [
    { label: 'Preprocessing data', hint: 'Detecting dates & cleaning rows' },
    { label: 'Engineering features', hint: 'Lags, seasonality & calendar signals' },
    { label: 'Running model tournament', hint: 'XGBoost, LightGBM & baselines' },
    { label: 'Building forecast', hint: 'Projecting ahead & scoring accuracy' },
  ];
  const [active, setActive] = useState(0);
  useEffect(() => {
    const timers = [
      setTimeout(() => setActive(1), 1500),
      setTimeout(() => setActive(2), 4000),
      setTimeout(() => setActive(3), 12000),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);
  return (
    <div className="fc-progress">
      <ol className="fc-steps">
        {steps.map((s, i) => {
          const state = i < active ? 'done' : i === active ? 'active' : 'pending';
          return (
            <li key={s.label} className={`fc-step fc-step--${state}`}>
              <span className="fc-step-marker">
                {state === 'done' ? '✓' : state === 'active' ? <span className="fc-dot" /> : i + 1}
              </span>
              <span className="fc-step-text">
                <span className="fc-step-label">{s.label}</span>
                <span className="fc-step-hint">{s.hint}</span>
              </span>
            </li>
          );
        })}
      </ol>
      <p className="fc-progress-note">This usually takes 30-60 seconds.</p>
    </div>
  );
}

export default function DynamicForecastUI() {
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState("");
  const [targetColumn, setTargetColumn] = useState("");
  
  // Dataset stats from /analyze-csv
  const [datasetStats, setDatasetStats] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  
  const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

  // App state
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeFilters, setActiveFilters] = useState([]);
  
  // Backend Results
  const [forecastData, setForecastData] = useState(null);

  // ─── Step 1: Upload file → call /analyze-csv for instant stats ───
  const handleFileUpload = async (e) => {
    const uploadedFile = e.target.files[0];
    if (!uploadedFile) return;
    
    setFile(uploadedFile);
    setFileName(uploadedFile.name);
    setForecastData(null);
    setDatasetStats(null);
    setError("");
    setIsAnalyzing(true);

    try {
      const formData = new FormData();
      formData.append("file", uploadedFile);

      const response = await fetch(`${API_BASE_URL}/analyze-csv`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Failed to analyze CSV.");
      }

      const stats = await response.json();
      setDatasetStats(stats);

      // Prefer the backend's name-aware + variance suggestion so the correct
      // target is auto-selected for ANY dataset. Fall back to the first numeric
      // column only if the backend couldn't suggest one.
      if (stats.columns && stats.columns.length > 0) {
        const suggested = stats.suggested_target
          && stats.columns.find(c => c.name === stats.suggested_target);
        const numericCol = stats.columns.find(c => c.is_numeric);
        const defaultTarget = suggested
          ? stats.suggested_target
          : (numericCol ? numericCol.name : stats.columns[1]?.name || stats.columns[0].name);
        setTargetColumn(defaultTarget);
      }
    } catch (err) {
      console.error("Analyze error:", err);
      setError(err.message || "Failed to analyze the uploaded file.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  // ─── Step 2: Generate Forecast ───
  const generateForecast = async () => {
    if (!file || !targetColumn) {
        setError("Please select a file and a target column.");
        return;
    }

    setIsLoading(true);
    setError("");
    
    try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("target_col", targetColumn);

        const activeFiltersDict = {};
        activeFilters.forEach(f => {
            if (f.column && f.value) activeFiltersDict[f.column] = f.value;
        });
        if (Object.keys(activeFiltersDict).length > 0) {
            formData.append("filters", JSON.stringify(activeFiltersDict));
        }

        const response = await fetch(`${API_BASE_URL}/dynamic-forecast`, {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Failed to generate forecast.");
        }

        const data = await response.json();
        setForecastData(data);
    } catch (err) {
        console.error("Forecast error:", err);
        setError(err.message || "An unexpected error occurred.");
    } finally {
        setIsLoading(false);
    }
  };

  // ─── Reset everything ───
  const handleReset = () => {
    setFile(null);
    setFileName("");
    setTargetColumn("");
    setDatasetStats(null);
    setForecastData(null);
    setActiveFilters([]);
    setError("");
  };

  const handleDownloadCSV = () => {
    if (!forecastData || !forecastData.forecast) return;
    
    // Build CSV Headers
    const dateCol = forecastData.metadata.date_column;
    const header = [dateCol, "Forecast", "LowerBound", "UpperBound"];
    
    // Build Rows
    const rows = forecastData.forecast.map(row => 
      [row[dateCol], row.Forecast, row.LowerBound, row.UpperBound].join(",")
    );
    
    const csvContent = [header.join(","), ...rows].join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `forecast_${forecastData.metadata.target_column}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="dynamic-forecast-wrapper">
      
      {/* 1. DATA INGESTION ZONE */}
      <div className="upload-section">
        <h3 className="section-title">Data Studio (Dynamic AI Forecaster)</h3>
        <p className="section-subtitle">Upload any CSV file. The backend will auto-detect columns, engineer features, run an Optuna model tournament, and generate forecasts.</p>
        
        <div className="file-upload-box">
            <input 
              type="file" 
              accept=".csv" 
              onChange={handleFileUpload} 
              id="csvUpload" 
              className="hidden-input"
            />
            <label htmlFor="csvUpload" className="btn-upload">
                Choose CSV File
            </label>
            <span className="file-name">{fileName || "No file chosen"}</span>
        </div>
      </div>

      {error && (
          <div className="alert-error" role="alert">
              <span className="alert-error-icon" aria-hidden="true">⚠</span>
              <span className="alert-error-msg">{error}</span>
              <button
                  type="button"
                  className="alert-error-close"
                  aria-label="Dismiss error"
                  onClick={() => setError("")}
              >×</button>
          </div>
      )}

      {/* Skeleton placeholders while the CSV is analysed */}
      {isAnalyzing && (
          <div className="dataset-stats-card" aria-busy="true" aria-label="Analyzing dataset">
              <div className="stats-header">
                  <div className="skeleton skeleton-line" style={{ width: '220px', height: '1.1rem' }} />
              </div>
              <div className="stats-grid">
                  {Array.from({ length: 6 }).map((_, i) => (
                      <div className="stat-item" key={i}>
                          <div className="skeleton skeleton-line" style={{ width: '55%', height: '.7rem' }} />
                          <div className="skeleton skeleton-line" style={{ width: '80%', height: '1.3rem' }} />
                      </div>
                  ))}
              </div>
              <p className="skeleton-caption">Analyzing dataset structure — detecting columns, dates, and row counts…</p>
          </div>
      )}

      {/* 2. DATASET STATS PANEL — shows immediately after file analysis */}
      {datasetStats && !forecastData && !isLoading && (
          <div className="dataset-stats-card">
              <div className="stats-header">
                  <h3>📊 Dataset Overview</h3>
                  <button className="btn-secondary btn-small" onClick={handleReset}>
                      Upload Different File
                  </button>
              </div>
              <div className="stats-grid">
                  <div className="stat-item">
                      <span className="stat-label">File Name</span>
                      <span className="stat-value">{datasetStats.file_name}</span>
                  </div>
                  <div className="stat-item">
                      <span className="stat-label">Total Records</span>
                      <span className="stat-value stat-highlight">{formatNumberIN(datasetStats.total_rows)}</span>
                  </div>
                  <div className="stat-item">
                      <span className="stat-label">Total Columns</span>
                      <span className="stat-value">{datasetStats.total_columns}</span>
                  </div>
                  <div className="stat-item">
                      <span className="stat-label">Detected Date Column</span>
                      <span className="stat-value">{datasetStats.detected_date_column || "None found"}</span>
                  </div>
                  {datasetStats.date_range && (
                      <>
                          <div className="stat-item">
                              <span className="stat-label">Start Date</span>
                              <span className="stat-value stat-date">{datasetStats.date_range.start}</span>
                          </div>
                          <div className="stat-item">
                              <span className="stat-label">End Date</span>
                              <span className="stat-value stat-date">{datasetStats.date_range.end}</span>
                          </div>
                      </>
                  )}
              </div>

              {/* Column dropdown + Generate button */}
              <div className="config-card" style={{ marginTop: '1rem', flexDirection: 'column', alignItems: 'center' }}>
                  <div className="target-select-group">
                    <label htmlFor="target-col">Forecast Target:</label>
                    <select 
                      id="target-col"
                      value={targetColumn}
                      onChange={(e) => setTargetColumn(e.target.value)}
                    >
                      {datasetStats.columns.map(col => (
                        <option key={col.name} value={col.name}>
                            {col.name} ({col.is_numeric ? 'numeric' : 'categorical'} · {col.unique_count} unique)
                        </option>
                      ))}
                    </select>
                    <button className="btn-generate" onClick={generateForecast}>
                        Generate Forecast
                    </button>
                  </div>
                  
              </div>
          </div>
      )}

      {/* 3. LOADING STATE — full pipeline */}
      {isLoading && (
          <div className="loading-state">
              <ForecastProgress />
          </div>
      )}

      {/* 4. FORECAST RESULTS */}
      {forecastData && (
        <div className="dynamic-forecast-container">

          {/* Sticky context bar — keeps dataset, range & target visible while scrolling */}
          <div className="fc-context-bar">
            {datasetStats?.file_name && (
              <span className="fc-context-item" title="Dataset">
                <span className="fc-context-key">Dataset</span>
                <span className="fc-context-val">{datasetStats.file_name}</span>
              </span>
            )}
            {datasetStats?.date_range && (
              <span className="fc-context-item" title="Date range">
                <span className="fc-context-key">Range</span>
                <span className="fc-context-val">{datasetStats.date_range.start} → {datasetStats.date_range.end}</span>
              </span>
            )}
            <span className="fc-context-item" title="Forecast target">
              <span className="fc-context-key">Target</span>
              <span className="fc-context-val">{forecastData.metadata.target_column}</span>
            </span>
          </div>

          {/* Quick Filters Bar */}
          <div className="filters-section" style={{ marginTop: '1.5rem', width: '100%', background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: activeFilters.length ? '1rem' : '0' }}>
                  <div style={{display: 'flex', alignItems: 'center', gap: '1rem'}}>
                      <h4 style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Dynamically Slice Forecast</h4>
                      <button 
                          className="btn-secondary btn-small" 
                          onClick={() => setActiveFilters([...activeFilters, {column: '', value: ''}])}
                          style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
                      >
                          + Add Filter
                      </button>
                  </div>
                  {activeFilters.length > 0 && (
                      <button className="btn-generate btn-small" onClick={generateForecast}>
                          Apply & Re-Forecast
                      </button>
                  )}
              </div>
              
              {activeFilters.length === 0 && (
                  <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>No filters applied. Add a filter to drill down into a specific branch, product, or segment.</p>
              )}
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {activeFilters.map((f, i) => (
                      <div key={i} className="filter-row" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          <select 
                              value={f.column} 
                              onChange={e => {
                                  const newF = [...activeFilters];
                                  newF[i].column = e.target.value;
                                  newF[i].value = '';
                                  setActiveFilters(newF);
                              }}
                              style={{ flex: 1, maxWidth: '250px', background: 'var(--bg-dark)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', padding: '0.4rem', borderRadius: '4px' }}
                          >
                              <option value="">Select Column...</option>
                              {datasetStats.columns.filter(c => c.unique_values && c.unique_values.length > 0).map(c => (
                                  <option key={c.name} value={c.name}>{c.name}</option>
                              ))}
                          </select>
                          <span style={{color: 'var(--text-muted)'}}>equals</span>
                          <select 
                              value={f.value} 
                              onChange={e => {
                                  const newF = [...activeFilters];
                                  newF[i].value = e.target.value;
                                  setActiveFilters(newF);
                              }} 
                              disabled={!f.column}
                              style={{ flex: 1, maxWidth: '250px', background: 'var(--bg-dark)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', padding: '0.4rem', borderRadius: '4px' }}
                          >
                              <option value="">Select Value...</option>
                              {f.column && datasetStats.columns.find(c => c.name === f.column)?.unique_values.map(val => (
                                  <option key={val} value={val}>{val}</option>
                              ))}
                          </select>
                          <button 
                              className="btn-remove" 
                              onClick={() => {
                                  const newF = [...activeFilters];
                                  newF.splice(i, 1);
                                  setActiveFilters(newF);
                                  // Auto-trigger if removing the last active filter
                                  if (newF.length === 0) {
                                      setTimeout(generateForecast, 0);
                                  }
                              }}
                              title="Remove filter"
                              style={{ background: 'transparent', border: 'none', color: '#ef4444', fontSize: '1.5rem', cursor: 'pointer', padding: '0 0.5rem', lineHeight: '1' }}
                          >
                              ×
                          </button>
                      </div>
                  ))}
              </div>
          </div>

          <div className="controls-header">
            <div>
              <p className="detection-info">
                Auto-detected timeline: <span className="mono-badge">{forecastData.metadata.date_column}</span>
              </p>
              <p className="detection-info">
                Forecasting: <span className="mono-badge">{forecastData.metadata.target_column}</span>
              </p>
              <p className="detection-info">
                Features Engineered: <span className="mono-badge">{forecastData.metadata.features_used}</span>
              </p>
              <p className="detection-info">
                Training Rows Used: <span className="mono-badge">{formatNumberIN(forecastData.metadata.total_training_rows)}</span>
              </p>
              {forecastData.metadata.grouped_by && (
                <p className="detection-info">
                  Grouped By: <span className="mono-badge">{forecastData.metadata.grouped_by}</span>
                </p>
              )}
            </div>
            <button className="btn-secondary" onClick={handleReset}>
                Start New Forecast
            </button>
          </div>

          {/* PLAIN-ENGLISH VERDICT — the one line a manager reads first */}
          {forecastData.verdict && (
            <div className={`fc-verdict ${forecastData.winner_beats_baseline === false ? 'fc-verdict--warn' : ''}`}>
              <span className="fc-verdict-icon" aria-hidden="true">
                {forecastData.winner_beats_baseline === false ? '⚠' : '📌'}
              </span>
              <p className="fc-verdict-text">{forecastData.verdict}</p>
            </div>
          )}

          {/* FORECAST CHART */}
          <div className="chart-card">
            <h3 className="chart-title">
              Trend Analysis for {forecastData.metadata.target_column}
              {forecastData.metadata.grouped_by ? ` (by ${forecastData.metadata.grouped_by})` : ''}
            </h3>
            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height={350}>
                <AreaChart data={forecastData.forecast} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
<CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey={forecastData.metadata.date_column} stroke="#94A3B8" fontSize={12} tickMargin={10} />
                  <YAxis stroke="#94A3B8" fontSize={12} width={64} tickFormatter={abbreviateIN} />
                  <RechartsTooltip 
                    formatter={(value) => formatNumberIN(value)}
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#fff' }}
                  />
                  <Legend verticalAlign="top" height={36}/>
                  {(() => {
                    const vals = forecastData.forecast.map(r => r.Forecast).filter(v => typeof v === 'number');
                    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
                    return avg == null ? null : (
                      <ReferenceLine
                        y={avg}
                        stroke="#94A3B8"
                        strokeDasharray="4 4"
                        label={{ value: `avg ${abbreviateIN(avg)}`, position: 'right', fill: '#94A3B8', fontSize: 11 }}
                      />
                    );
                  })()}
                  
                  {/* Confidence range: shade only BETWEEN lower and upper bounds.
                      Upper draws the band; Lower re-fills with the card background
                      to mask everything beneath the lower bound. */}
                  <Area 
                    type="monotone" 
                    dataKey="UpperBound" 
                    stroke="none" 
                    fill="#64748B" 
                    fillOpacity={0.22} 
                    name="Confidence range"
                    isAnimationActive={false}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="LowerBound" 
                    stroke="none" 
                    fill="#1E293B" 
                    fillOpacity={1} 
                    legendType="none"
                    tooltipType="none"
                    isAnimationActive={false}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="Forecast" 
                    stroke="#84A98C" 
                    strokeWidth={3} 
                    dot={false} 
                    name={`Predicted ${forecastData.metadata.target_column}`} 
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* PROJECTED DATA TABLE */}
          <div className="table-card">
            <div className="table-header">
              <div style={{display: 'flex', alignItems: 'center', gap: '1rem'}}>
                <h3>Projected Data</h3>
                <span className="badge-warning">{forecastData.metadata.forecast_days} Future Periods</span>
              </div>
              <button className="btn-secondary btn-small" onClick={handleDownloadCSV}>
                Download CSV
              </button>
            </div>
            <div className="table-responsive">
              <table className="forecast-table">
                <thead>
                  <tr>
                    <th>Date (Future)</th>
                    <th>Predicted</th>
                    <th>Lower Bound</th>
                    <th>Upper Bound</th>
                  </tr>
                </thead>
                <tbody>
                  {forecastData.forecast.map((row, idx) => (
                    <tr key={idx}>
                      <td className="font-medium">{row[forecastData.metadata.date_column]}</td>
                      <td className="text-warning font-bold num">
                        {typeof row.Forecast === 'number' ? formatNumberIN(row.Forecast) : row.Forecast}
                      </td>
                      <td className="text-muted num">
                        {typeof row.LowerBound === 'number' ? formatNumberIN(row.LowerBound) : row.LowerBound}
                      </td>
                      <td className="text-muted num">
                        {typeof row.UpperBound === 'number' ? formatNumberIN(row.UpperBound) : row.UpperBound}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* MODEL INTELLIGENCE */}
          <div className="model-intelligence-card">
              <div className="mi-header">
                  <h3>🧠 Model Intelligence</h3>
              </div>
              <div className="mi-winner-banner">
                  <span className="mi-trophy">🏆</span>
                  <div className="mi-winner-text">
                      <strong>Winning Model: {forecastData.winner.name}</strong>
                      <p>{forecastData.winner.reason}</p>
                      <p className="mi-accuracy-line">
                          Typical error: <strong>{forecastData.accuracy_label || `±${forecastData.winner.metrics.wmape ?? forecastData.winner.metrics.mape}%`}</strong>
                          {forecastData.winner.metrics.wmape != null && (
                            <>{'  ·  '}WMAPE: <strong>{forecastData.winner.metrics.wmape}%</strong></>
                          )}
                      </p>
                  </div>
              </div>
              <div className="mi-metrics-table-wrapper">
                  <table className="mi-metrics-table">
                      <thead>
                          <tr>
                              <th>Tested Model</th>
                              <th>Optuna History</th>
                              <th>MAE</th>
                              <th>RMSE</th>
                              <th>MAPE</th>
                              <th>WMAPE</th>
                          </tr>
                      </thead>
                      <tbody>
                          {forecastData.models_leaderboard.map(m => (
                              <tr key={m.name} className={m.name === forecastData.winner.name ? 'mi-row-winner' : ''}>
                                  <td>{m.name} {m.name === forecastData.winner.name && '(Winner)'}</td>
                                  <td>
                                      {m.optuna_history && m.optuna_history.length > 1 ? (
                                        <div style={{ width: 80, height: 30 }}>
                                          <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={m.optuna_history.map((val, idx) => ({ idx, val }))}>
                                              <Line type="monotone" dataKey="val" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} />
                                            </LineChart>
                                          </ResponsiveContainer>
                                        </div>
                                      ) : (
                                        <span className="text-muted" style={{fontSize: '0.8rem'}}>No history</span>
                                      )}
                                  </td>
                                  <td>{m.mae}</td>
                                  <td>{m.rmse}</td>
                                  <td>{m.mape}%</td>
                                  <td className="mi-accuracy-cell">{m.wmape != null ? `${m.wmape}%` : '—'}</td>
                              </tr>
                          ))}
                      </tbody>
                  </table>
              </div>
          </div>

          {/* AI SUMMARY */}
          <div className="ai-summary-card">
              <div className="ai-header">
                  <h3>✨ AI Forecast Summary</h3>
              </div>
              <blockquote className="ai-quote">
                  {forecastData.ai_summary}
              </blockquote>
          </div>
          
        </div>
      )}
    </div>
  );
}
