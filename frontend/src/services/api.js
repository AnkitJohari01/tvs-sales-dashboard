/* ============================================================
   API Service — centralized FastAPI communication
   ============================================================ */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Generic fetch wrapper with error handling
 */
async function request(endpoint, options = {}) {
  // Remove trailing slash from API_BASE if present to prevent //endpoint and CORS 307 redirect issues
  const cleanBase = API_BASE.replace(/\/$/, '');
  const url = `${cleanBase}${endpoint}`;

  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const message = errorData?.detail || `API Error: ${response.status} ${response.statusText}`;
    throw new Error(message);
  }

  return response.json();
}

/** GET /health */
export function getHealth() {
  return request('/health');
}

/** GET /features */
export function getFeatures() {
  return request('/features');
}

/** GET /filters */
export function getFilters() {
  return request('/filters');
}

/** POST /forecast */
export function postForecast(payload) {
  return request('/forecast', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
/** GET /eda */
export function getEDA() {
  return request('/eda');
}

/** GET /model-report — honest model audit (allocation risk + backtest demo) */
export function getModelReport() {
  return request('/model-report');
}

export const api = { getHealth, getFeatures, getFilters, postForecast, getEDA, getModelReport };
export default api;
