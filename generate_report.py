# ============================================================
# generate_report.py — builds client_report.html from model_report.json
# Numbers are injected from the computed JSON so they never drift.
# Open in a browser and Print -> Save as PDF for the client deliverable.
# ============================================================
import json, datetime

R = json.load(open("model_report.json"))
real = R["sections"]["real_findings"]
bt = R["sections"]["backtest_demo"]
today = datetime.date.today().isoformat()

rows = "".join(
    f"<tr class='{'stale' if ('Lapsing' in b['bucket'] or 'Churned' in b['bucket']) else ''}'>"
    f"<td>{b['bucket']}</td><td>{b['combos']:,}</td><td>{b['weight_pct']}%</td></tr>"
    for b in real["recency_buckets"]
)

dq = real["data_quality"]
conc = real["concentration"]

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>TVS Sales Forecasting — Model Audit</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    color: #1a2230; max-width: 860px; margin: 0 auto; padding: 48px 40px; line-height: 1.55; }}
  h1 {{ font-size: 26px; margin: 0 0 4px; }}
  h2 {{ font-size: 18px; margin: 32px 0 8px; border-bottom: 2px solid #E29578; padding-bottom: 4px; }}
  h3 {{ font-size: 14px; margin: 18px 0 6px; color: #33475b; }}
  .sub {{ color: #667085; margin: 0 0 24px; }}
  .kpi {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }}
  .kpi div {{ flex: 1; min-width: 150px; background: #f6f8fa; border: 1px solid #e4e9f0;
    border-radius: 8px; padding: 12px 14px; }}
  .kpi .n {{ font-size: 22px; font-weight: 700; }}
  .kpi .l {{ font-size: 11px; color: #667085; text-transform: uppercase; letter-spacing: .04em; }}
  .hot {{ color: #b4531f; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }}
  th, td {{ text-align: left; padding: 7px 10px; border-bottom: 1px solid #e4e9f0; }}
  th {{ background: #f6f8fa; }}
  tr.stale td {{ background: #fdf1ec; }}
  .callout {{ background: #fdf1ec; border-left: 4px solid #E29578; padding: 14px 16px;
    border-radius: 6px; margin: 14px 0; }}
  .note {{ background: #f0f5f1; border-left: 4px solid #84A98C; padding: 12px 16px;
    border-radius: 6px; font-size: 12.5px; color: #33475b; margin: 12px 0; }}
  ol li, ul li {{ margin: 6px 0; }}
  .foot {{ margin-top: 40px; color: #98a2b3; font-size: 11px; border-top: 1px solid #e4e9f0; padding-top: 12px; }}
  @media print {{ body {{ padding: 24px; }} h2 {{ page-break-after: avoid; }} table, .callout, .note {{ page-break-inside: avoid; }} }}
</style></head><body>

<h1>Sales Forecasting — Model Audit &amp; Accuracy Review</h1>
<p class="sub">Prepared {today} &middot; Data as-of {real['as_of']} &middot; Confidential</p>

<h2>Executive summary</h2>
<p>The forecasting system works and produces daily, customer, and product-level projections.
However, this review finds that <strong>the headline accuracy figure does not describe the numbers
the product actually shows</strong>, and that the customer-level allocation carries a material,
measurable risk. We recommend three fixes before this is positioned to the client as a reliability
guarantee. None of them require rebuilding the system.</p>

<div class="callout">
  <strong>Headline finding.</strong> {real['stale_allocation_pct']}% of all allocated future revenue
  is assigned to customers who have <strong>not purchased in over 60 days</strong>. Because the
  forecast divides each future day's total using a <em>fixed</em> historical share, revenue keeps
  being attributed to lapsing and churned accounts. Median time since last purchase across the base
  is {real['median_days_since_purchase']} days.
</div>

<h2>1. What the accuracy number really measures</h2>
<p>The reported accuracy applies to the <strong>total daily revenue</strong> only. The customer- and
product-level figures shown in the app are produced by multiplying that single total against static
historical weights. That allocation step is <strong>not measured by any accuracy metric today</strong>,
yet it drives every line item a user sees. In addition, the underlying sales history required to
independently reproduce the headline figure was not present in the delivered artifacts, so the number
could not be verified during this review.</p>

<h3>Why the metric matters</h3>
<p>The system optimised MAPE, which is undefined on near-zero days (e.g. Sundays) and is asymmetric —
it quietly rewards under-forecasting. We have moved the system to <strong>WMAPE</strong> (weighted
absolute error over total actual): scale-stable, always defined, and aligned with rupee impact. Every
model is now also scored against a <strong>seasonal-naive baseline</strong> so we can prove a model
adds value rather than just producing a plausible line.</p>

<h2>2. The allocation risk, quantified</h2>
<p>Every future rupee is split across {real['n_combos']:,} customer/product combinations
({real['n_customers']:,} customers, {real['n_products']:,} products) using shares that never update:</p>
<table>
  <thead><tr><th>Customer recency</th><th>Combos</th><th>Share of allocated revenue</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<p>Rows shaded above represent customers with no purchase in 60+ days still receiving
<strong>{real['stale_allocation_pct']}%</strong> of forecasted revenue. Allocation is also highly
concentrated: the top 2,000 combinations hold {conc['top_2000_pct']}% of all weight
(top 100 hold {conc['top_100_pct']}%).</p>

<h3>Data quality flags</h3>
<div class="kpi">
  <div><div class="n hot">{dq['negative_revenue_rows']}</div><div class="l">Negative-revenue rows</div></div>
  <div><div class="n">{dq['zero_revenue_rows']}</div><div class="l">Zero-revenue rows</div></div>
  <div><div class="n">{conc['top_500_pct']}%</div><div class="l">Weight in top 500 combos</div></div>
</div>

<h2>3. Honest accuracy: how we now measure it</h2>
<p>We rebuilt evaluation to mirror how the forecast is actually deployed — a 30-day recursive
projection — using <strong>rolling-origin backtesting</strong> instead of one-step cross-validation,
which flatters multi-step forecasts. The figures below are a <em>harness demonstration</em> (the real
sales history was unavailable); they illustrate the method and the gap it exposes.</p>
<div class="kpi">
  <div><div class="n">{bt['model_1step_wmape']}%</div><div class="l">1-step CV (optimistic)</div></div>
  <div><div class="n hot">{bt['model_multistep_wmape']}%</div><div class="l">30-day multi-step (honest)</div></div>
  <div><div class="n">{bt['naive_multistep_wmape']}%</div><div class="l">Seasonal-naive floor</div></div>
  <div><div class="n">{bt['model_mase']}</div><div class="l">MASE vs naive (&lt;1 = beats)</div></div>
</div>
<div class="note">{bt['note']}</div>

<h2>4. Recommendations</h2>
<ol>
  <li><strong>Report WMAPE against the seasonal-naive baseline</strong>, not raw MAPE, on every model card.</li>
  <li><strong>Validate multi-step, rolling-origin</strong> — measure the 30-day forecast you actually ship.</li>
  <li><strong>Refresh allocation weights on a rolling window and decay inactive customers</strong>, so churned
      accounts stop absorbing forecasted revenue.</li>
  <li><strong>Measure accuracy at the customer/product level shown in the UI</strong>, not only the daily total.</li>
  <li><strong>Supply the source sales history</strong> so the headline accuracy can be independently reproduced.</li>
</ol>

<h2>Appendix — engineering changes delivered</h2>
<ul>
  <li>New <code>evaluation.py</code>: WMAPE, MASE, bias, and a rolling-origin multi-step backtest (unit-tested, 7/7 passing).</li>
  <li>Tournament now selects on WMAPE and includes a seasonal-naive baseline; the winner card states whether it beats that floor.</li>
  <li>Log-transformed target and cyclical seasonality features for the learned models (better fit on skewed revenue).</li>
  <li>New <code>/model-report</code> API + in-app "Model Audit" page surfacing these findings live.</li>
  <li>Security &amp; deploy: API key moved out of committed config, <code>Dockerfile</code>, pinned <code>requirements.txt</code>, <code>.env.example</code>.</li>
</ul>

<p class="foot">Figures in Sections 2 are computed directly from the delivered <code>historical_weights.pkl</code>
via <code>run_analysis.py</code>. Section 3 figures are a labelled harness demonstration on a reconstructed
series, pending the source sales history. This document regenerates from <code>model_report.json</code>.</p>
</body></html>"""

open("client_report.html", "w", encoding="utf-8").write(html)
print("Wrote client_report.html")
