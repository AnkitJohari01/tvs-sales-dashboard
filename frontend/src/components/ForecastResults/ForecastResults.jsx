/* ============================================================
   ForecastResults — data table + summary for forecast output
   ============================================================ */

import { useState, useMemo } from 'react';
import { useForecast } from '../../contexts/ForecastContext';
import StatCard from '../StatCard/StatCard';
import './ForecastResults.css';
import './ForecastResultsFilters.css';

const PAGE_SIZE = 25;

export default function ForecastResults() {
  const { state } = useForecast();
  const { forecast } = state;
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');

  /* Dropdown states — must be declared before any early return */
  const [selectedBranch, setSelectedBranch] = useState('');
  const [selectedCustomer, setSelectedCustomer] = useState('');
  const [selectedProduct, setSelectedProduct] = useState('');
  const [selectedDate, setSelectedDate] = useState('');

  const rows = forecast?.forecast || [];

  /* Extract unique values for dropdowns */
  const uniqueBranches = useMemo(() => [...new Set(rows.map(r => r['Branch']).filter(Boolean))].sort(), [rows]);
  const uniqueCustomers = useMemo(() => [...new Set(rows.map(r => r['CustomerName'] || r['Cust.Code']).filter(Boolean))].sort(), [rows]);
  const uniqueProducts = useMemo(() => [...new Set(rows.map(r => r['Item Description']).filter(Boolean))].sort(), [rows]);
  const uniqueDates = useMemo(() => [...new Set(rows.map(r => r['ForecastedDate']).filter(Boolean))].sort(), [rows]);

  /* Filter rows by dropdowns AND search term */
  const filtered = useMemo(() => {
    return rows.filter(row => {
      if (selectedBranch && row['Branch'] !== selectedBranch) return false;
      if (selectedCustomer && row['CustomerName'] !== selectedCustomer && row['Cust.Code'] !== selectedCustomer) return false;
      if (selectedProduct && row['Item Description'] !== selectedProduct) return false;
      if (selectedDate && row['ForecastedDate'] !== selectedDate) return false;

      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return Object.values(row).some(v => String(v).toLowerCase().includes(q));
    });
  }, [rows, search, selectedBranch, selectedCustomer, selectedProduct, selectedDate]);

  /* Total revenue */
  const totalRevenue = useMemo(() => {
    return rows.reduce((sum, r) => sum + (r.ForecastedRevenue || 0), 0);
  }, [rows]);

  /* Early return AFTER all hooks */
  if (!forecast) return null;

  const { model, mape_pct, start_date, days, total_rows } = forecast;

  /* Pagination */
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  return (
    <div className="forecast-results animate-fade-in-up" id="forecast-results">
      {/* Summary cards */}
      <div className="forecast-results__summary">
        <StatCard icon="🏆" label="Model" value={model} accent="teal" delay={0} />
        <StatCard icon="📉" label="MAPE" value={`${mape_pct}%`} accent="coral" delay={80} />
        <StatCard icon="📅" label="Period" value={`${start_date} → ${days}d`} accent="violet" delay={160} />
        <StatCard icon="💰" label="Total Rev." value={`₹${(totalRevenue / 1e5).toFixed(1)}L`} accent="teal" delay={240} />
      </div>

      {/* Table controls */}
      <div className="forecast-results__controls">
        {/* Dropdown Filters */}
        <div className="forecast-results__filters">
          {uniqueBranches.length > 0 && (
            <select className="forecast-results__select" value={selectedBranch} onChange={e => { setSelectedBranch(e.target.value); setPage(0); }}>
              <option value="">All Branches</option>
              {uniqueBranches.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          )}
          {uniqueCustomers.length > 0 && (
            <select className="forecast-results__select" value={selectedCustomer} onChange={e => { setSelectedCustomer(e.target.value); setPage(0); }}>
              <option value="">All Customers</option>
              {uniqueCustomers.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          )}
          {uniqueProducts.length > 0 && (
            <select className="forecast-results__select" value={selectedProduct} onChange={e => { setSelectedProduct(e.target.value); setPage(0); }}>
              <option value="">All Products</option>
              {uniqueProducts.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          )}
          {uniqueDates.length > 0 && (
            <select className="forecast-results__select" value={selectedDate} onChange={e => { setSelectedDate(e.target.value); setPage(0); }}>
              <option value="">All Dates</option>
              {uniqueDates.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          )}
        </div>

        <div className="forecast-results__search-row">
          <div className="forecast-results__info">
            <span className="forecast-results__badge">{total_rows.toLocaleString()} rows</span>
            {(search || selectedBranch || selectedCustomer || selectedProduct || selectedDate) && (
              <span className="forecast-results__badge forecast-results__badge--filtered">{filtered.length.toLocaleString()} matched</span>
            )}
          </div>
          <input
            type="text"
            className="forecast-results__search"
            placeholder="🔍 Search results..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            id="search-results"
          />
        </div>
      </div>

      {/* Data table */}
      <div className="forecast-results__table-wrap">
        <table className="forecast-results__table" id="results-table">
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginated.map((row, i) => (
              <tr key={i} style={{ animationDelay: `${i * 20}ms` }}>
                {columns.map(col => (
                  <td key={col}>
                    {col === 'ForecastedRevenue'
                      ? `₹${Number(row[col]).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                      : row[col]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="forecast-results__pagination" id="pagination">
          <button
            className="forecast-results__page-btn"
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
          >
            ← Prev
          </button>
          <span className="forecast-results__page-info">
            Page {page + 1} of {totalPages}
          </span>
          <button
            className="forecast-results__page-btn"
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
