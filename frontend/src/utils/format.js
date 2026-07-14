/* ============================================================
   Number & currency formatting — Indian conventions
   ============================================================
   Sales figures here are INR and often large, so we use lakh/
   crore abbreviation for compact display (KPIs, axes) and full
   en-IN grouping for tooltips/tables where precision matters.
   ============================================================ */

/** Full Indian-grouped integer, e.g. 4493313 -> "44,93,313". */
export function formatNumberIN(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

/** Compact lakh/crore, e.g. 4493313 -> "44.9L", 55209906 -> "5.5Cr". */
export function abbreviateIN(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e7) return `${sign}${(abs / 1e7).toFixed(abs >= 1e8 ? 0 : 1)}Cr`;
  if (abs >= 1e5) return `${sign}${(abs / 1e5).toFixed(1)}L`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

/** Rupee-prefixed compact value for KPIs/axes, e.g. "₹44.9L". */
export function formatINR(value, { compact = true } = {}) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `₹${compact ? abbreviateIN(value) : formatNumberIN(value)}`;
}
