# ============================================================
# run_analysis.py — Produces model_report.json
# ============================================================
# Emits a single JSON consumed by BOTH the React "Model Report"
# page and the client PDF. Two clearly-separated sections:
#
#   1. REAL findings computed from delivered artifacts
#      (historical_weights.pkl) — data quality, concentration,
#      and the stale-allocation risk. These are ground truth.
#
#   2. METHODOLOGY demonstration of the honest backtest harness
#      (1-step CV vs multi-step, model vs seasonal-naive). Run
#      here on a reconstructed proxy because the real training
#      series (extended_3year_sales_dataset.csv) is NOT present
#      in the delivered artifacts. Clearly labelled as such.
# ============================================================

import json
import numpy as np
import pandas as pd
import evaluation as ev

REPORT = {"generated_for": "TVS sales forecasting — model audit", "sections": {}}


# ────────────────────────────────────────────────────────────
# Section 1 — REAL findings from historical_weights.pkl
# ────────────────────────────────────────────────────────────
def real_findings():
    import pickle
    hw = pickle.load(open("historical_weights.pkl", "rb"))
    hw["LastDateOfPurchase"] = pd.to_datetime(hw["LastDateOfPurchase"])
    asof = hw["LastDateOfPurchase"].max()
    days = (asof - hw["LastDateOfPurchase"]).dt.days
    pos = hw["weight"].clip(lower=0)
    total_pos = pos.sum()

    def bucket(d):
        if d <= 30: return "Active (0-30d)"
        if d <= 60: return "At Risk (31-60d)"
        if d <= 90: return "Lapsing (61-90d)"
        return "Churned (>90d)"

    hw["_bucket"] = days.apply(bucket)
    order = ["Active (0-30d)", "At Risk (31-60d)", "Lapsing (61-90d)", "Churned (>90d)"]
    rows = []
    for b in order:
        mask = hw["_bucket"] == b
        wm = hw.loc[mask, "weight"].clip(lower=0).sum()
        rows.append({
            "bucket": b,
            "combos": int(mask.sum()),
            "weight_pct": round(100 * wm / total_pos, 1),
        })
    stale = round(sum(r["weight_pct"] for r in rows if r["bucket"] in
                      ("Lapsing (61-90d)", "Churned (>90d)")), 1)

    w = pos.sort_values(ascending=False).values
    cum = np.cumsum(w) / w.sum()

    return {
        "as_of": str(asof.date()),
        "n_combos": int(len(hw)),
        "n_customers": int(hw["Cust.Code"].nunique()),
        "n_products": int(hw["Item Description"].nunique()),
        "recency_buckets": rows,
        "stale_allocation_pct": stale,
        "median_days_since_purchase": int(days.median()),
        "mean_days_since_purchase": int(days.mean()),
        "data_quality": {
            "negative_revenue_rows": int((hw["HistRevenue"] < 0).sum()),
            "negative_revenue_sum": round(float(hw.loc[hw["HistRevenue"] < 0, "HistRevenue"].sum()), 0),
            "zero_revenue_rows": int((hw["HistRevenue"] == 0).sum()),
            "negative_weight_mass": round(float(hw.loc[hw["weight"] < 0, "weight"].sum()), 5),
        },
        "concentration": {
            "top_100_pct": round(100 * cum[99], 1),
            "top_500_pct": round(100 * cum[499], 1),
            "top_2000_pct": round(100 * cum[1999], 1),
        },
    }


# ────────────────────────────────────────────────────────────
# Section 2 — METHODOLOGY demo of the honest backtest
# ────────────────────────────────────────────────────────────
def backtest_demo():
    """Runs the harness on a reconstructed weekly-seasonal proxy so the
    client can see the tooling and the 1-step-vs-multi-step gap. Uses a
    fixed seed for reproducibility (no real actuals are available)."""
    rng = np.random.RandomState(42)
    n_days = 179  # same length as the delivered snapshot window
    t = np.arange(n_days)
    weekday_shape = np.array([1.0, 1.4, 1.0, 0.95, 1.05, 1.15, 0.15])  # strong weekly cycle
    level = 4_000_000 * (1 + 0.15 * np.sin(2 * np.pi * t / 90))         # slow drift
    series = level * weekday_shape[t % 7]
    series *= (1 + rng.normal(0, 0.18, n_days))                         # multiplicative noise
    series = np.clip(series, 0, None)

    horizon = 30

    # Model proxy: log-space weekly-seasonal regression, forecast recursively.
    def model_fn(history, hz):
        h = np.asarray(history, dtype=float)
        ly = np.log1p(h)
        idx = np.arange(len(h))
        # features: intercept, trend, weekly sin/cos
        X = np.column_stack([
            np.ones(len(h)), idx / len(h),
            np.sin(2 * np.pi * idx / 7), np.cos(2 * np.pi * idx / 7),
        ])
        beta, *_ = np.linalg.lstsq(X, ly, rcond=None)
        fidx = np.arange(len(h), len(h) + hz)
        Xf = np.column_stack([
            np.ones(hz), fidx / len(h),
            np.sin(2 * np.pi * fidx / 7), np.cos(2 * np.pi * fidx / 7),
        ])
        return np.clip(np.expm1(Xf @ beta), 0, None)

    def naive_fn(history, hz):
        return ev.seasonal_naive_forecast(history, hz, season=7)

    bt_model = ev.rolling_origin_backtest(series, horizon, model_fn, n_folds=4, season=7)
    bt_naive = ev.rolling_origin_backtest(series, horizon, naive_fn, n_folds=4, season=7)

    # Contrast: naive 1-step-ahead WMAPE (what optimistic CV would report)
    one_step = ev.rolling_origin_backtest(series, 1, model_fn, n_folds=20, season=7)

    return {
        "note": ("Illustrative run on a reconstructed weekly-seasonal proxy. The real "
                 "training series (extended_3year_sales_dataset.csv) is not in the "
                 "delivered artifacts, so the headline 22.65% MAPE could not be "
                 "reproduced. These numbers demonstrate the harness; rerun on the real "
                 "series to obtain production figures."),
        "horizon": horizon,
        "model_1step_wmape": one_step["avg"]["wmape"],
        "model_multistep_wmape": bt_model["avg"]["wmape"],
        "naive_multistep_wmape": bt_naive["avg"]["wmape"],
        "model_mase": bt_model["avg"]["mase"],
        "model_bias_pct": bt_model["avg"]["bias_pct"],
        "wmape_by_step": bt_model["wmape_by_step"],
        "naive_wmape_by_step": bt_naive["wmape_by_step"],
    }


if __name__ == "__main__":
    REPORT["sections"]["real_findings"] = real_findings()
    REPORT["sections"]["backtest_demo"] = backtest_demo()
    with open("model_report.json", "w") as f:
        json.dump(REPORT, f, indent=2)
    r = REPORT["sections"]["real_findings"]
    b = REPORT["sections"]["backtest_demo"]
    print("=== REAL FINDINGS (from historical_weights.pkl) ===")
    print(f"  Stale allocation (60+ days, no purchase): {r['stale_allocation_pct']}% of future revenue")
    print(f"  Median days since last purchase: {r['median_days_since_purchase']}")
    print(f"  Data quality: {r['data_quality']['negative_revenue_rows']} negative-rev rows, "
          f"{r['data_quality']['zero_revenue_rows']} zeros")
    print(f"  Concentration: top 2000 combos = {r['concentration']['top_2000_pct']}% of weight")
    print("\n=== BACKTEST HARNESS DEMO (reconstructed proxy) ===")
    print(f"  Model 1-step WMAPE (optimistic CV): {b['model_1step_wmape']}%")
    print(f"  Model 30-day multi-step WMAPE (honest): {b['model_multistep_wmape']}%")
    print(f"  Seasonal-naive 30-day WMAPE (floor): {b['naive_multistep_wmape']}%")
    print(f"  Model MASE vs naive: {b['model_mase']}  (<1 beats naive)")
    print("\nWrote model_report.json")
