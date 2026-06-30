/* ============================================================
   ForecastContext — global state for forecast data,
   loading states, errors, and health info.
   ============================================================ */

import { createContext, useContext, useReducer, useCallback } from 'react';
import { getHealth, getFeatures, postForecast, getEDA } from '../services/api';

const ForecastContext = createContext(null);

const initialState = {
  /* health */
  health: null,
  healthLoading: false,
  healthError: null,

  /* features */
  features: [],
  featuresLoading: false,
  featuresError: null,

  /* forecast */
  forecast: null,
  forecastLoading: false,
  forecastError: null,

  /* eda */
  eda: null,
  edaLoading: false,
  edaError: null,

  /* toast notifications */
  toast: null,
};

function reducer(state, action) {
  switch (action.type) {
    /* ── health ─────────────────────── */
    case 'HEALTH_LOADING':
      return { ...state, healthLoading: true, healthError: null };
    case 'HEALTH_SUCCESS':
      return { ...state, healthLoading: false, health: action.payload };
    case 'HEALTH_ERROR':
      return { ...state, healthLoading: false, healthError: action.payload };

    /* ── features ───────────────────── */
    case 'FEATURES_LOADING':
      return { ...state, featuresLoading: true, featuresError: null };
    case 'FEATURES_SUCCESS':
      return { ...state, featuresLoading: false, features: action.payload };
    case 'FEATURES_ERROR':
      return { ...state, featuresLoading: false, featuresError: action.payload };

    /* ── forecast ───────────────────── */
    case 'FORECAST_LOADING':
      return { ...state, forecastLoading: true, forecastError: null };
    case 'FORECAST_SUCCESS':
      return { ...state, forecastLoading: false, forecast: action.payload };
    case 'FORECAST_ERROR':
      return { ...state, forecastLoading: false, forecastError: action.payload };

    /* ── eda ────────────────────────── */
    case 'EDA_LOADING':
      return { ...state, edaLoading: true, edaError: null };
    case 'EDA_SUCCESS':
      return { ...state, edaLoading: false, eda: action.payload };
    case 'EDA_ERROR':
      return { ...state, edaLoading: false, edaError: action.payload };

    /* ── toast ──────────────────────── */
    case 'SHOW_TOAST':
      return { ...state, toast: action.payload };
    case 'HIDE_TOAST':
      return { ...state, toast: null };

    default:
      return state;
  }
}

export function ForecastProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const fetchHealth = useCallback(async () => {
    dispatch({ type: 'HEALTH_LOADING' });
    try {
      const data = await getHealth();
      dispatch({ type: 'HEALTH_SUCCESS', payload: data });
    } catch (err) {
      dispatch({ type: 'HEALTH_ERROR', payload: err.message });
      dispatch({ type: 'SHOW_TOAST', payload: { type: 'error', message: err.message } });
    }
  }, []);

  const fetchFeatures = useCallback(async () => {
    dispatch({ type: 'FEATURES_LOADING' });
    try {
      const data = await getFeatures();
      dispatch({ type: 'FEATURES_SUCCESS', payload: data.features });
    } catch (err) {
      dispatch({ type: 'FEATURES_ERROR', payload: err.message });
    }
  }, []);

  const submitForecast = useCallback(async (payload) => {
    dispatch({ type: 'FORECAST_LOADING' });
    try {
      const data = await postForecast(payload);
      dispatch({ type: 'FORECAST_SUCCESS', payload: data });
      dispatch({ type: 'SHOW_TOAST', payload: { type: 'success', message: `Forecast generated: ${data.total_rows.toLocaleString()} rows` } });
    } catch (err) {
      dispatch({ type: 'FORECAST_ERROR', payload: err.message });
      dispatch({ type: 'SHOW_TOAST', payload: { type: 'error', message: err.message } });
    }
  }, []);

  const fetchEDA = useCallback(async () => {
    dispatch({ type: 'EDA_LOADING' });
    try {
      const data = await getEDA();
      dispatch({ type: 'EDA_SUCCESS', payload: data });
    } catch (err) {
      dispatch({ type: 'EDA_ERROR', payload: err.message });
      dispatch({ type: 'SHOW_TOAST', payload: { type: 'error', message: err.message } });
    }
  }, []);

  const hideToast = useCallback(() => {
    dispatch({ type: 'HIDE_TOAST' });
  }, []);

  return (
    <ForecastContext.Provider value={{ state, fetchHealth, fetchFeatures, submitForecast, fetchEDA, hideToast }}>
      {children}
    </ForecastContext.Provider>
  );
}

export function useForecast() {
  const context = useContext(ForecastContext);
  if (!context) throw new Error('useForecast must be used within ForecastProvider');
  return context;
}
