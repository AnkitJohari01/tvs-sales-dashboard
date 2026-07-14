/* ============================================================
   ForecastForm — interactive form for submitting forecast request
   ============================================================ */

import { useState, useEffect } from 'react';
import { useForecast } from '../../contexts/ForecastContext';
import { Spinner } from '../Loader/Loader';
import { api } from '../../services/api';
import './ForecastForm.css';

const DEFAULT_VALUES = {
  start_date: '2026-04-01',
  days: 30,
  branch: '',
  customer: '',
  product: '',
};

const FIELD_META = [
  { name: 'start_date', label: 'Start Date', type: 'date', group: 'general' },
  { name: 'days',       label: 'Forecast Days', type: 'number', group: 'general', min: 1, max: 365 },
];

export default function ForecastForm() {
  const [form, setForm] = useState(DEFAULT_VALUES);
  const [filters, setFilters] = useState({ branches: [], customers: [], products: [] });
  const [loadingFilters, setLoadingFilters] = useState(true);
  
  const { state, submitForecast } = useForecast();

  useEffect(() => {
    async function fetchFilters() {
      try {
        const data = await api.getFilters();
        setFilters(data);
      } catch (err) {
        console.error("Failed to fetch filters", err);
      } finally {
        setLoadingFilters(false);
      }
    }
    fetchFilters();
  }, []);

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    setForm(prev => ({
      ...prev,
      [name]: type === 'number' ? parseFloat(value) || 0 : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    submitForecast(form);
  };

  const generalFields = FIELD_META.filter(f => f.group === 'general');

  return (
    <form className="forecast-form" onSubmit={handleSubmit} id="forecast-form">
      <div className="forecast-form__header">
        <h2 className="forecast-form__title">
          <span className="forecast-form__title-icon">🔮</span>
          Generate Forecast
        </h2>
        <p className="forecast-form__subtitle">
          Configure timeline and target scope to generate precise sales predictions.
        </p>
      </div>

      {/* General settings */}
      <fieldset className="forecast-form__group">
        <legend className="forecast-form__legend">
          <span className="forecast-form__legend-dot forecast-form__legend-dot--teal"></span>
          General Settings
        </legend>
        <div className="forecast-form__row">
          {generalFields.map(field => (
            <div className="forecast-form__field" key={field.name}>
              <label htmlFor={field.name} className="forecast-form__label">{field.label}</label>
              <input
                id={field.name}
                name={field.name}
                type={field.type}
                value={form[field.name]}
                onChange={handleChange}
                min={field.min}
                max={field.max}
                className="forecast-form__input"
              />
            </div>
          ))}
        </div>
      </fieldset>

      {/* Target Scope (Dropdowns) */}
      <fieldset className="forecast-form__group">
        <legend className="forecast-form__legend">
          <span className="forecast-form__legend-dot forecast-form__legend-dot--coral"></span>
          Target Scope (Optional Filters)
        </legend>
        {loadingFilters ? (
          <div className="forecast-form__loader"><Spinner size={16}/> Loading filters...</div>
        ) : (
          <div className="forecast-form__row forecast-form__row--3">
            <div className="forecast-form__field">
              <label htmlFor="branch" className="forecast-form__label">Branch</label>
              <select name="branch" id="branch" className="forecast-form__input" value={form.branch} onChange={handleChange}>
                <option value="">All Branches</option>
                {filters.branches.map(b => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>
            
            <div className="forecast-form__field">
              <label htmlFor="customer" className="forecast-form__label">Customer</label>
              <select name="customer" id="customer" className="forecast-form__input" value={form.customer} onChange={handleChange}>
                <option value="">All Customers</option>
                {filters.customers.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            <div className="forecast-form__field">
              <label htmlFor="product" className="forecast-form__label">Product</label>
              <select name="product" id="product" className="forecast-form__input" value={form.product} onChange={handleChange}>
                <option value="">All Products</option>
                {filters.products.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>
        )}
      </fieldset>

      {/* Submit */}
      <button
        type="submit"
        className="forecast-form__submit"
        disabled={state.forecastLoading}
        id="submit-forecast-btn"
      >
        {state.forecastLoading ? (
          <>
            <Spinner size={18} />
            Generating…
          </>
        ) : (
          <>
            <span>🚀</span>
            Run Forecast
          </>
        )}
      </button>

      {state.forecastError && (
        <div className="forecast-form__error" id="forecast-error">
          ❌ {state.forecastError}
        </div>
      )}
    </form>
  );
}
