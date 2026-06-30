/* ============================================================
   ForecastSummary — dynamic AI insights summary
   ============================================================ */

import { useMemo } from 'react';
import { useForecast } from '../../contexts/ForecastContext';
import './ForecastSummary.css';

export default function ForecastSummary() {
  const { state } = useForecast();
  
  const insights = useMemo(() => {
    if (!state.forecast || !state.forecast.forecast || state.forecast.forecast.length === 0) return null;
    
    const { start_date, days, total_rows, mape_pct, forecast } = state.forecast;
    
    // Revenue calculations
    const totalRev = forecast.reduce((sum, row) => sum + (row.ForecastedRevenue || 0), 0);
    const avgDailyRev = totalRev / days;
    
    // Aggregations
    const branchRev = {};
    const productRev = {};
    const customerRev = {};
    
    forecast.forEach(row => {
      const b = row['Branch'] || 'Unknown';
      const p = row['Item Description'] || 'Unknown';
      const c = row['CustomerName'] || row['Cust.Code'] || 'Unknown';
      const rev = row.ForecastedRevenue || 0;
      
      branchRev[b] = (branchRev[b] || 0) + rev;
      productRev[p] = (productRev[p] || 0) + rev;
      customerRev[c] = (customerRev[c] || 0) + rev;
    });
    
    // Top Performers
    const getTop = (dict) => Object.entries(dict).sort((a,b) => b[1] - a[1])[0] || ["None", 0];
    const topBranch = getTop(branchRev);
    const topProduct = getTop(productRev);
    const topCustomer = getTop(customerRev);
    
    // Additional metrics
    const branchConcentration = totalRev > 0 ? ((topBranch[1] / totalRev) * 100).toFixed(1) : 0;
    
    // Date calculation
    const startDateObj = new Date(start_date);
    const endDateObj = new Date(startDateObj);
    endDateObj.setDate(startDateObj.getDate() + days - 1);
    const endDateStr = endDateObj.toISOString().split('T')[0];

    return {
      totalRev, avgDailyRev,
      topBranch, topProduct, topCustomer,
      branchConcentration,
      start_date, endDateStr, days, total_rows, mape_pct
    };
  }, [state.forecast]);

  if (!insights) return null;

  const fmt = (val) => `₹${(val / 100000).toFixed(2)} Lakhs`;

  return (
    <div className="forecast-summary animate-fade-in-up">
      <h3 className="forecast-summary__title">
        <span className="forecast-summary__icon">✨</span> AI Forecast Summary
      </h3>
      <ul className="forecast-summary__list">
        <li>
          <strong>Total Revenue Outlook:</strong> We expect a total of {fmt(insights.totalRev)} in sales over the selected period.
        </li>
        <li>
          <strong>Daily Run Rate:</strong> On average, this translates to about {fmt(insights.avgDailyRev)} in sales each day.
        </li>
        <li>
          <strong>Timeline Horizon:</strong> This prediction covers a {insights.days}-day window, starting on {insights.start_date} and ending on {insights.endDateStr}.
        </li>
        <li>
          <strong>Data Coverage:</strong> The system analyzed {insights.total_rows.toLocaleString()} individual historical records to build this projection.
        </li>
        <li>
          <strong>Top Branch:</strong> The {insights.topBranch[0]} location is predicted to be the strongest performer, bringing in {fmt(insights.topBranch[1])}.
        </li>
        <li>
          <strong>Branch Concentration:</strong> Interestingly, our top branch alone accounts for {insights.branchConcentration}% of all expected sales.
        </li>
        <li>
          <strong>Top Product:</strong> The highest demand will be for {insights.topProduct[0]}, which is expected to generate {fmt(insights.topProduct[1])}.
        </li>
        <li>
          <strong>Top Customer:</strong> {insights.topCustomer[0]} is projected to be the most valuable buyer during this timeframe.
        </li>
        <li>
          <strong>Prediction Accuracy:</strong> Our underlying artificial intelligence model has a historical error margin of roughly {insights.mape_pct}%.
        </li>
      </ul>
    </div>
  );
}
