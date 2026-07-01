# ============================================================
# FastAPI Backend — Detailed Forecast
# Outputs: Branch / Cust.Code / CustomerName /
#          Sales Employee Name / Item Description /
#          ForecastedDate / ForecastedRevenue / LastDateOfPurchase
# Run: uvicorn main:app --reload
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import pickle, json
import numpy as np
import pandas as pd
from datetime import date, timedelta
import os
try:
    import anthropic
except ImportError:
    anthropic = None

app = FastAPI(title="Sales Forecast API")

# ── CORS — allow React dev server + Vercel deployment ────────
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")
ALLOWED_ORIGINS += [
    "http://localhost:5173",
    "http://localhost:3000",
]
# Allow all origins if ALLOWED_ORIGINS env var is set to "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Public API — open to all
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load everything at startup ────────────────────────────────
with open("model_metadata.json", "r") as f:
    metadata = json.load(f)

winner_name     = metadata["winner_model_name"]
winner_mape     = metadata["winner_mape"]
feature_columns = metadata["feature_columns"]

with open("winner_model.pkl", "rb") as f:
    model = pickle.load(f)

with open("scaler.pkl", "rb") as f:
    scaler = pickle.load(f)

with open("historical_weights.pkl", "rb") as f:
    historical_weights = pickle.load(f)

print(f"Loaded winner: {winner_name}  (MAPE: {winner_mape}%)")
print(f"Loaded historical_weights: {len(historical_weights):,} rows")


# ── Request schema ────────────────────────────────────────────
class ForecastRequest(BaseModel):
    start_date: str   = "2026-04-01"
    days:       int   = 30
    lag_1:      float = 0.0
    lag_2:      float = 0.0
    lag_3:      float = 0.0
    lag_6:      float = 0.0
    lag_7:      float = 0.0
    lag_14:     float = 0.0
    lag_21:     float = 0.0
    lag_28:     float = 0.0
    roll7_mean:  float = 0.0
    roll7_std:   float = 0.0
    roll28_mean: float = 0.0
    branch:      Optional[str] = None
    customer:    Optional[str] = None
    product:     Optional[str] = None

class ExplainRequest(BaseModel):
    date: str
    sales: float
    avg: float
    type: str


# ── Helper: build one feature row ────────────────────────────
def build_row(dt: date, lag_values: dict) -> dict:
    row = {}
    for col in feature_columns:
        if col in lag_values:
            row[col] = lag_values[col]
        elif col == "day_of_week":    row[col] = dt.weekday()
        elif col == "is_weekend":     row[col] = int(dt.weekday() >= 5)
        elif col == "month":          row[col] = dt.month
        elif col == "day_of_month":   row[col] = dt.day
        elif col == "is_month_end":   row[col] = int(dt.day >= 28)
        elif col == "quarter":        row[col] = (dt.month - 1) // 3 + 1
        else:                         row[col] = 0.0
    return row


# ── POST /forecast ────────────────────────────────────────────
@app.post("/forecast")
def forecast(req: ForecastRequest):
    try:
        start = date.fromisoformat(req.start_date)

        lag_values = {
            "lag_1":       scaler.transform([[req.lag_1]])[0][0],
            "lag_2":       scaler.transform([[req.lag_2]])[0][0],
            "lag_3":       scaler.transform([[req.lag_3]])[0][0],
            "lag_6":       scaler.transform([[req.lag_6]])[0][0],
            "lag_7":       scaler.transform([[req.lag_7]])[0][0],
            "lag_14":      scaler.transform([[req.lag_14]])[0][0],
            "lag_21":      scaler.transform([[req.lag_21]])[0][0],
            "lag_28":      scaler.transform([[req.lag_28]])[0][0],
            "roll7_mean":  req.roll7_mean,
            "roll7_std":   req.roll7_std,
            "roll28_mean": req.roll28_mean,
        }

        # ── Step 1: Get daily total forecast ─────────────────
        daily_forecasts = []
        for i in range(req.days):
            current_date = start + timedelta(days=i)
            row = build_row(current_date, lag_values)
            X   = pd.DataFrame([row])[feature_columns]

            pred_scaled = model.predict(X)[0]
            pred_inr    = float(scaler.inverse_transform([[pred_scaled]])[0][0])
            pred_inr    = max(0.0, pred_inr)
            daily_forecasts.append({"date": current_date, "total_inr": pred_inr})

            # Roll lags
            lag_values["lag_2"]  = lag_values["lag_1"]
            lag_values["lag_3"]  = lag_values["lag_2"]
            lag_values["lag_6"]  = lag_values.get("lag_5", lag_values["lag_6"])
            lag_values["lag_7"]  = lag_values["lag_6"]
            lag_values["lag_1"]  = pred_scaled

        daily_df = pd.DataFrame(daily_forecasts)

        # ── Step 2: Allocate & Filter ─────────────────────────
        hw = historical_weights.copy()
        if req.branch:
            hw = hw[hw["Branch"] == req.branch]
        if req.customer:
            hw = hw[(hw["CustomerName"] == req.customer) | (hw["Cust.Code"] == req.customer)]
        if req.product:
            hw = hw[hw["Item Description"] == req.product]

        # Optimization to prevent OOM crash on Render (512MB RAM):
        # If no specific customer/product is selected, the cross-join with 30 days generates 1.7M rows.
        # Instead, we aggregate to the Branch level to save massive amounts of memory.
        if not req.customer and not req.product and len(hw) > 500:
            hw = hw.groupby("Branch")["weight"].sum().reset_index()
            hw["CustomerName"] = "All Customers (Aggregated)"
            hw["Cust.Code"] = "ALL"
            hw["Item Description"] = "All Products"
            hw["Sales Employee Name"] = "Multiple"
            hw["LastDateOfPurchase"] = "N/A"

        daily_df["_key"] = 1
        hw["_key"] = 1
        detailed = pd.merge(daily_df, hw, on="_key").drop(columns="_key")

        detailed["ForecastedRevenue"] = (detailed["total_inr"] * detailed["weight"]).round(2)

        # ── Step 3: Rename & select final columns ─────────────
        DETAIL_COLS_FALLBACK = ["Branch", "Cust.Code", "CustomerName", "Sales Employee Name", "Item Description"]
        detail_columns = metadata.get("detail_columns", DETAIL_COLS_FALLBACK)
        if not detail_columns:
            detail_columns = DETAIL_COLS_FALLBACK
        detailed = detailed.rename(columns={"date": "ForecastedDate"})

        final_cols = ["ForecastedDate"] + detail_columns + ["ForecastedRevenue", "LastDateOfPurchase"]
        detailed = detailed[[c for c in final_cols if c in detailed.columns]]
        detailed["ForecastedDate"] = detailed["ForecastedDate"].astype(str)

        return {
            "model":      winner_name,
            "mape_pct":   winner_mape,
            "start_date": req.start_date,
            "days":       req.days,
            "total_rows": len(detailed),
            "forecast":   detailed.to_dict(orient="records")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.responses import StreamingResponse
import io

# ── GET /download-data-csv ────────────────────────────────────
@app.get("/download-data-csv")
def download_data_csv():
    import os
    if not os.path.exists("april_2026_detailed_forecast.csv"):
        raise HTTPException(
            status_code=503,
            detail="Detailed forecast CSV is not available on this deployment. Please run locally to access this file."
        )
    try:
        # We generate the requested 1.7M rows on the fly quickly
        fc = pd.read_csv("april_2026_detailed_forecast.csv")
        fc["ForecastedDate"] = pd.to_datetime(fc["ForecastedDate"])
        daily_df = fc.groupby("ForecastedDate")["ForecastedRevenue"].sum().reset_index()
        daily_df.rename(columns={"ForecastedRevenue": "total_inr"}, inplace=True)
        
        daily_df["_key"] = 1
        hw = historical_weights.copy()
        hw["_key"] = 1
        
        detailed = pd.merge(daily_df, hw, on="_key").drop(columns="_key")
        detailed["Forecasted_Revenue_Detailed"] = (detailed["total_inr"] * detailed["weight"]).round(2)
        detailed["ForecastedDate"] = detailed["ForecastedDate"].dt.date
        
        cols = ["ForecastedDate", "Branch", "Cust.Code", "CustomerName", "Sales Employee Name", "Item Description", "Forecasted_Revenue_Detailed"]
        detailed = detailed[cols]
        
        stream = io.StringIO()
        detailed.to_csv(stream, index=False)
        response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=Detailed_Forecast_Report.csv"
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── GET /health ───────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":          "ok",
        "winner_model":    winner_name,
        "winner_mape_pct": winner_mape,
        "features_loaded": len(feature_columns),
        "weight_rows":     len(historical_weights)
    }


# ── GET /features ─────────────────────────────────────────────
@app.get("/features")
def features():
    return {"features": feature_columns}

# ── GET /filters ──────────────────────────────────────────────
@app.get("/filters")
def get_filters():
    return {
        "branches": sorted(historical_weights["Branch"].dropna().astype(str).unique().tolist()),
        "customers": sorted(historical_weights["CustomerName"].dropna().astype(str).unique().tolist()),
        "products": sorted(historical_weights["Item Description"].dropna().astype(str).unique().tolist())
    }

# ── GET /eda ──────────────────────────────────────────────────
@app.get("/eda")
def get_eda_full():
    """Comprehensive EDA data — all values computed dynamically."""
    hw = historical_weights.copy()
    hw["LastDateOfPurchase"] = pd.to_datetime(hw["LastDateOfPurchase"])

    # ── 1. Branch sales (sorted desc) ─────────────────────────
    branch_sales = (
        hw.groupby("Branch")["HistRevenue"]
        .sum()
        .nlargest(10)
        .sort_values(ascending=False)
        .reset_index()
    )

    # ── 2. Daily sales trend ──────────────────────────────────
    daily = hw.groupby("LastDateOfPurchase")["HistRevenue"].sum().reset_index()
    daily = daily.sort_values("LastDateOfPurchase")
    daily.columns = ["date", "sales"]
    best_idx = daily["sales"].idxmax()
    worst_idx = daily["sales"].idxmin()
    daily["is_best"] = False
    daily["is_worst"] = False
    daily.loc[best_idx, "is_best"] = True
    daily.loc[worst_idx, "is_worst"] = True
    daily["date"] = daily["date"].astype(str)

    # ── 3. Product share (top 5 + Others) ─────────────────────
    prod_all = hw.groupby("Item Description")["HistRevenue"].sum()
    total_rev = prod_all.sum()
    top5_prod = prod_all.nlargest(5).reset_index()
    top5_sum = top5_prod["HistRevenue"].sum()
    others_val = total_rev - top5_sum
    others_row = pd.DataFrame([{"Item Description": "Others", "HistRevenue": float(others_val)}])
    product_share = pd.concat([top5_prod, others_row], ignore_index=True)
    product_share["pct"] = (product_share["HistRevenue"] / total_rev * 100).round(1)

    # ── 4. Calendar heatmap (most recent full month) ──────────
    latest_month = hw["LastDateOfPurchase"].dt.to_period("M").max()
    cal_month = hw[hw["LastDateOfPurchase"].dt.to_period("M") == latest_month]
    cal_daily = cal_month.groupby("LastDateOfPurchase")["HistRevenue"].sum().reset_index()
    cal_daily.columns = ["date", "sales"]
    cal_daily["date"] = cal_daily["date"].astype(str)
    cal_daily["weekday"] = pd.to_datetime(cal_daily["date"]).dt.weekday  # 0=Mon
    cal_daily["week"] = (pd.to_datetime(cal_daily["date"]).dt.day - 1) // 7

    # ── 5. KPI cards ──────────────────────────────────────────
    total_sales = float(total_rev)
    daily_agg = hw.groupby("LastDateOfPurchase")["HistRevenue"].sum()
    best_day_date = daily_agg.idxmax()
    best_day_sales = float(daily_agg.max())
    avg_daily_sales = float(daily_agg.mean())
    forecast_accuracy = round(100 - winner_mape, 2)

    # ── 6. Top 5 customers ───────────────────────────────────
    top_cust = hw.groupby("CustomerName")["HistRevenue"].sum().nlargest(5).reset_index()
    cust_max = float(top_cust["HistRevenue"].max())

    # ── 7. Progress bar (target = avg monthly * growth) ───────
    monthly = hw.groupby(hw["LastDateOfPurchase"].dt.to_period("M"))["HistRevenue"].sum()
    monthly_sorted = monthly.sort_index()
    latest_month_sales = float(monthly_sorted.iloc[-1])
    prev_month_sales = float(monthly_sorted.iloc[-2]) if len(monthly_sorted) >= 2 else latest_month_sales
    # Target = previous month * 1.10 (10% growth target)
    target = prev_month_sales * 1.10
    achieved = latest_month_sales
    pct_complete = round(min(achieved / target * 100, 100), 1) if target > 0 else 0
    # Last year proxy: use 2 months ago
    ly_sales = float(monthly_sorted.iloc[-3]) if len(monthly_sorted) >= 3 else 0
    ly_pct = round(min(ly_sales / target * 100, 100), 1) if target > 0 else 0

    # ── 8. Table data (latest month, branch-level) ────────────
    table_month = hw[hw["LastDateOfPurchase"].dt.to_period("M") == latest_month].copy()
    table_agg = (
        table_month.groupby(["Branch", "CustomerName", "LastDateOfPurchase"])["HistRevenue"]
        .sum()
        .reset_index()
    )
    table_agg.columns = ["Branch", "Customer", "Date", "Sales"]
    avg_sale = float(table_agg["Sales"].mean())
    table_agg["vs_avg"] = ((table_agg["Sales"] - avg_sale) / avg_sale * 100).round(1)
    table_agg["status"] = table_agg["Sales"].apply(
        lambda x: "high" if x > avg_sale * 1.05 else ("low" if x < avg_sale * 0.95 else "avg")
    )
    table_agg = table_agg.sort_values("Sales", ascending=False).head(50)
    table_agg["Date"] = table_agg["Date"].astype(str)

    # ── 9. Monthly trend (MoM + sparkline) ────────────────────
    monthly_list = []
    for period, val in monthly_sorted.items():
        monthly_list.append({"month": str(period), "sales": float(val)})
    mom_change = 0
    if len(monthly_list) >= 2:
        cur = monthly_list[-1]["sales"]
        prev = monthly_list[-2]["sales"]
        mom_change = round((cur - prev) / prev * 100, 1) if prev != 0 else 0
    latest_period_label = monthly_list[-2]["month"] if len(monthly_list) >= 2 else ""

    # ── 10. Forecast vs Actual (daily, April 2026) ────────────
    try:
        fc = pd.read_csv("april_2026_detailed_forecast.csv")
        fc["ForecastedDate"] = pd.to_datetime(fc["ForecastedDate"])
        fc_daily = fc.groupby("ForecastedDate").agg(
            forecast=("ForecastedRevenue", "sum"),
            upper=("UpperBound", "sum"),
            lower=("LowerBound", "sum")
        ).reset_index()
        fc_daily = fc_daily.sort_values("ForecastedDate")
        fc_daily["ForecastedDate"] = fc_daily["ForecastedDate"].astype(str)
        forecast_vs = fc_daily.to_dict(orient="records")
    except Exception:
        forecast_vs = []

    # ── 11. 7-Day Rolling Average Alert ───────────────────────
    daily_sales_series = daily["sales"].values
    if len(daily_sales_series) >= 7:
        rolling_7 = float(np.mean(daily_sales_series[-8:-1])) if len(daily_sales_series) > 7 else float(np.mean(daily_sales_series[:-1]))
        latest_sales = float(daily_sales_series[-1])
        latest_date = str(daily["date"].values[-1])
        alert = None
        
        # Check if latest sales deviate > 2x or < 0.5x
        if latest_sales > 2 * rolling_7:
            alert = {"date": latest_date, "sales": latest_sales, "avg": rolling_7, "type": "high"}
        elif latest_sales < 0.5 * rolling_7:
            alert = {"date": latest_date, "sales": latest_sales, "avg": rolling_7, "type": "low"}
    else:
        alert = None

    # ── 12. Customer Health ───────────────────────────────────
    # Global max date is 2026-03-31
    global_max_date = pd.to_datetime("2026-03-31")
    cust_latest = hw.groupby(["CustomerName", "Branch"])["LastDateOfPurchase"].max().reset_index()
    cust_latest["DaysSince"] = (global_max_date - cust_latest["LastDateOfPurchase"]).dt.days
    
    def get_health_status(days):
        if days <= 30: return "Active"
        elif days <= 60: return "At Risk"
        else: return "Churned"
        
    cust_latest["Status"] = cust_latest["DaysSince"].apply(get_health_status)
    cust_latest["LastDateOfPurchase"] = cust_latest["LastDateOfPurchase"].astype(str)
    customer_health = cust_latest.to_dict(orient="records")

    return {
        "branch_sales": branch_sales.to_dict(orient="records"),
        "daily_trend": daily.to_dict(orient="records"),
        "product_share": product_share.to_dict(orient="records"),
        "calendar_data": cal_daily.to_dict(orient="records"),
        "calendar_month": str(latest_month),
        "kpis": {
            "total_sales": total_sales,
            "best_day": str(best_day_date.date()),
            "best_day_sales": best_day_sales,
            "avg_daily_sales": avg_daily_sales,
            "forecast_accuracy": forecast_accuracy,
        },
        "top_customers": top_cust.to_dict(orient="records"),
        "customer_max": cust_max,
        "target_progress": {
            "target": float(target),
            "achieved": float(achieved),
            "pct": pct_complete,
            "last_year_pct": ly_pct,
            "target_label": str(latest_month),
        },
        "table_data": table_agg.to_dict(orient="records"),
        "table_avg": avg_sale,
        "monthly_trend": monthly_list,
        "mom_change": mom_change,
        "mom_vs_label": latest_period_label,
        "forecast_vs_actual": forecast_vs,
        "alert": alert,
        "customer_health": customer_health
    }

# ── POST /explain-alert ───────────────────────────────────────
@app.post("/explain-alert")
def explain_alert(req: ExplainRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    diff_pct = round(abs(req.sales - req.avg) / req.avg * 100) if req.avg > 0 else 0
    direction = "higher" if req.type == "high" else "lower"
    
    fallback_text = f"Sales on {req.date} were {diff_pct}% {direction} than the 7-day average. This may be due to seasonal variations, a bulk order, or missing data."
    
    if not api_key or not anthropic:
        return {"explanation": fallback_text}
        
    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = f"We observed unusual sales activity on {req.date}. Sales were {req.sales}, which is {diff_pct}% {direction} than the 7-day average of {req.avg}. Provide a single, short plain English plausible reason for this. Be concise. Example format: 'Sales were {diff_pct}% {direction} than usual. Possible reason: ...'"
        
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}]
        )
        return {"explanation": message.content[0].text}
    except Exception as e:
        print(f"Claude API error: {e}")
        return {"explanation": fallback_text}