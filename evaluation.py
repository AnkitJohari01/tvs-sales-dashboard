# ============================================================
# evaluation.py — Honest forecast evaluation
# ============================================================
# Scale-stable metrics (WMAPE, MASE) plus a rolling-origin,
# multi-step backtest that mirrors the DEPLOYED recursive
# forecast protocol — not 1-step CV. Pure numpy/pandas so it
# runs anywhere (no xgboost/optuna required).
#
# Why this module exists:
#   * MAPE is undefined on near-zero actuals and asymmetric,
#     so it silently rewards under-forecasting.
#   * 1-step cross-validation flatters a model that is actually
#     deployed as a 30-day recursive forecast (errors compound).
#   * Without a seasonal-naive baseline you cannot tell whether
#     a model adds any value over "same weekday last week".
# ============================================================

import numpy as np
import pandas as pd
from typing import Callable, Optional


# ────────────────────────────────────────────────────────────
# 1. Metrics
# ────────────────────────────────────────────────────────────
def _clean(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    m = np.isfinite(y_true) & np.isfinite(y_pred)
    return y_true[m], y_pred[m]


def mae(y_true, y_pred) -> float:
    y_true, y_pred = _clean(y_true, y_pred)
    if len(y_true) == 0:
        return float("nan")
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred) -> float:
    y_true, y_pred = _clean(y_true, y_pred)
    if len(y_true) == 0:
        return float("nan")
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def wmape(y_true, y_pred) -> float:
    """Weighted MAPE = sum|error| / sum|actual|, as a percentage.

    Scale-stable, always defined when total actual != 0, and weights
    high-value periods appropriately. This is the primary metric.
    """
    y_true, y_pred = _clean(y_true, y_pred)
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return float("nan")
    return float(np.sum(np.abs(y_true - y_pred)) / denom * 100)


def bias_pct(y_true, y_pred) -> float:
    """Signed mean error as % of mean actual. Positive => over-forecast."""
    y_true, y_pred = _clean(y_true, y_pred)
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return float("nan")
    return float(np.sum(y_pred - y_true) / denom * 100)


def robust_mape(y_true, y_pred) -> float:
    """MAPE that masks out near-zero actuals (kept for continuity with the
    existing UI, which shows a MAPE column)."""
    y_true, y_pred = _clean(y_true, y_pred)
    if len(y_true) == 0:
        return float("nan")
    scale = np.mean(np.abs(y_true))
    floor = max(scale * 1e-3, 1e-8)
    mask = np.abs(y_true) >= floor
    if not np.any(mask):
        return mae(y_true, y_pred)
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def mase(y_true, y_pred, y_train, season: int = 7) -> float:
    """Mean Absolute Scaled Error.

    Scales error by the in-sample seasonal-naive MAE. MASE < 1 means the
    model beats seasonal-naive; MASE >= 1 means it does not.
    """
    y_true, y_pred = _clean(y_true, y_pred)
    y_train = np.asarray(y_train, dtype=float)
    y_train = y_train[np.isfinite(y_train)]
    if len(y_train) <= season:
        season = 1
    if len(y_train) <= season:
        return float("nan")
    naive_err = np.mean(np.abs(y_train[season:] - y_train[:-season]))
    if naive_err == 0:
        return float("nan")
    return float(np.mean(np.abs(y_true - y_pred)) / naive_err)


def all_metrics(y_true, y_pred, y_train=None, season: int = 7) -> dict:
    out = {
        "wmape": round(wmape(y_true, y_pred), 2),
        "mape": round(robust_mape(y_true, y_pred), 2),
        "mae": round(mae(y_true, y_pred), 2),
        "rmse": round(rmse(y_true, y_pred), 2),
        "bias_pct": round(bias_pct(y_true, y_pred), 2),
    }
    if y_train is not None:
        out["mase"] = round(mase(y_true, y_pred, y_train, season), 3)
    return out


# ────────────────────────────────────────────────────────────
# 2. Seasonal-naive baseline — the floor every model must beat
# ────────────────────────────────────────────────────────────
def seasonal_naive_forecast(history: np.ndarray, horizon: int, season: int = 7) -> np.ndarray:
    """Forecast = value from `season` steps ago, repeated across the horizon."""
    history = np.asarray(history, dtype=float)
    if len(history) == 0:
        return np.zeros(horizon)
    if len(history) < season:
        season = 1
    preds = []
    ext = list(history)
    for h in range(horizon):
        preds.append(ext[-season])
        ext.append(ext[-season])  # roll forward using its own seasonal value
    return np.clip(np.array(preds), 0, None)


# ────────────────────────────────────────────────────────────
# 3. Rolling-origin, multi-step backtest (the honest one)
# ────────────────────────────────────────────────────────────
def rolling_origin_backtest(
    y: np.ndarray,
    horizon: int,
    forecast_fn: Callable[[np.ndarray, int], np.ndarray],
    n_folds: int = 4,
    min_train: Optional[int] = None,
    season: int = 7,
) -> dict:
    """Evaluate a forecaster the way it is actually deployed.

    For each fold we train on data up to an origin, forecast `horizon`
    steps ahead, and score against the held-out actuals. Origins step
    forward by `horizon`. This exposes error growth over the horizon and
    prevents 1-step CV from flattering a recursive multi-step forecast.

    forecast_fn(history, horizon) -> np.ndarray of length `horizon`.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    if min_train is None:
        min_train = max(2 * season, n - n_folds * horizon)
    min_train = max(min_train, season + 1)

    fold_metrics = []
    per_step_abs = [[] for _ in range(horizon)]   # abs error by horizon step
    per_step_act = [[] for _ in range(horizon)]   # |actual| by horizon step

    origins = list(range(min_train, n - 0, horizon))
    used = 0
    for origin in origins:
        if origin + 1 > n:
            break
        h = min(horizon, n - origin)
        if h <= 0:
            break
        history = y[:origin]
        actual = y[origin:origin + h]
        pred = np.asarray(forecast_fn(history, h), dtype=float)[:h]
        if len(pred) < h:
            pred = np.concatenate([pred, np.full(h - len(pred), pred[-1] if len(pred) else 0.0)])

        fold_metrics.append(all_metrics(actual, pred, y_train=history, season=season))
        for s in range(h):
            per_step_abs[s].append(abs(actual[s] - pred[s]))
            per_step_act[s].append(abs(actual[s]))
        used += 1

    if used == 0:
        return {"error": "not enough data for backtest", "n_folds": 0}

    def _avg(key):
        vals = [fm[key] for fm in fold_metrics if np.isfinite(fm.get(key, np.nan))]
        return round(float(np.mean(vals)), 3) if vals else float("nan")

    # WMAPE growth across the horizon (aggregated across folds)
    step_wmape = []
    for s in range(horizon):
        num = np.sum(per_step_abs[s]) if per_step_abs[s] else 0.0
        den = np.sum(per_step_act[s]) if per_step_act[s] else 0.0
        step_wmape.append(round(num / den * 100, 2) if den > 0 else None)

    return {
        "n_folds": used,
        "horizon": horizon,
        "avg": {k: _avg(k) for k in ["wmape", "mape", "mae", "rmse", "bias_pct", "mase"]},
        "wmape_by_step": step_wmape,
        "folds": fold_metrics,
    }
