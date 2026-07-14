# ============================================================
# forecasting_engine.py — Dynamic Multi-Model Forecasting Pipeline
# ============================================================
# Accepts ANY CSV, auto-detects columns, engineers features,
# runs an Optuna-tuned model tournament, and returns forecasts
# with a natural-language AI summary.
#
# Uses model_metadata.json as schema REFERENCE ONLY (not for
# training or inference with the existing .pkl model).
# ============================================================

import json
import warnings
import logging
import numpy as np
import pandas as pd
from datetime import timedelta
from typing import Optional

from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error

import optuna

# Suppress noisy logs during optimization
optuna.logging.set_verbosity(optuna.logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)
logger = logging.getLogger("forecasting_engine")


# ────────────────────────────────────────────────────────────
# 1. DataPreprocessor — auto-detect, clean, encode, scale
# ────────────────────────────────────────────────────────────
class DataPreprocessor:
    """Automatically detects column types, handles missing data,
    encodes categoricals, and scales numerics."""

    # Only unambiguous date-related keywords — no 'invoice'
    DATE_PATTERNS = [
        "date", "datetime", "timestamp", "dt", "_date", "forecast_date",
        "forecasted_date", "forecasteddate", "month", "period", "time",
        "year", "day"
    ]

    def __init__(self):
        self.date_col = None
        self.numeric_cols = []
        self.categorical_cols = []
        self.label_encoders = {}

    @staticmethod
    def _is_valid_date_column(series: pd.Series) -> bool:
        """Validate that a parsed datetime series contains real dates (not epoch artefacts).
        Rejects columns where parsing integer IDs yields dates near 1970."""
        sample = series.dropna().head(50)
        if len(sample) == 0:
            return False
        try:
            # format='mixed' is recommended for Pandas 2.0+ when parsing varied date strings
            parsed = pd.to_datetime(sample, errors="coerce", format='mixed')
            valid = parsed.dropna()
            if len(valid) < len(sample) * 0.5:
                return False  # more than half failed to parse → not a date column
            # Check year range: real dates should be between 1990 and 2100
            years = valid.dt.year
            if years.min() < 1990 or years.max() > 2100:
                return False
            return True
        except Exception:
            return False

    def detect_date_column(self, df: pd.DataFrame) -> Optional[str]:
        """Find the most likely date column via name heuristics + strict parse validation.
        
        Strategy:
        1. Check columns whose names contain date-specific keywords.
        2. Fallback: check every string/object column.
        3. In both cases, validate that parsed values have realistic years (1990-2100).
        """
        # Priority pass: columns with date-like names
        for col in df.columns:
            col_lower = col.lower().strip().replace(" ", "").replace("_", "")
            if any(p.replace("_", "") in col_lower for p in self.DATE_PATTERNS):
                if self._is_valid_date_column(df[col]):
                    logger.info(f"Date column detected by name match: '{col}'")
                    return col

        # Fallback: try every string column
        for col in df.select_dtypes(include=["object", "string"]).columns:
            if self._is_valid_date_column(df[col]):
                logger.info(f"Date column detected by fallback parse: '{col}'")
                return col
        return None

    def detect_column_types(self, df: pd.DataFrame, date_col: str, target_col: str):
        """Classify remaining columns as numeric or categorical."""
        self.numeric_cols = []
        self.categorical_cols = []
        skip = {date_col, target_col}

        for col in df.columns:
            if col in skip:
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                self.numeric_cols.append(col)
            elif df[col].nunique() <= 50:  # cap cardinality
                self.categorical_cols.append(col)

    def clean(self, df: pd.DataFrame, date_col: str, target_col: str) -> pd.DataFrame:
        """Handle missing values and type conversions."""
        df = df.copy()

        # Parse dates
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])

        # Ensure target is numeric
        df[target_col] = pd.to_numeric(df[target_col], errors="coerce")
        med = df[target_col].median()
        if pd.isna(med):
            med = 0.0
        df[target_col] = df[target_col].fillna(med)

        # Fill numeric cols
        for c in self.numeric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            col_med = df[c].median()
            df[c] = df[c].fillna(col_med if not pd.isna(col_med) else 0.0)

        # Fill categorical cols
        for c in self.categorical_cols:
            df[c] = df[c].fillna(df[c].mode().iloc[0] if len(df[c].mode()) > 0 else "Unknown")

        # Sort by date
        df = df.sort_values(date_col).reset_index(drop=True)
        return df

    def encode_categoricals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Label-encode categorical columns (lightweight, no OHE explosion)."""
        df = df.copy()
        for c in self.categorical_cols:
            le = LabelEncoder()
            df[c] = le.fit_transform(df[c].astype(str))
            self.label_encoders[c] = le
        return df

    # Column-name hints. Names that strongly imply a forecast target (sales,
    # revenue, etc.) win over pure statistics; names that imply an identifier
    # are demoted even when they slip past the ID-pattern filter.
    TARGET_NAME_HINTS = [
        "sales", "revenue", "amount", "amt", "total", "turnover", "gmv",
        "qty", "quantity", "units", "volume", "demand", "value", "price",
        "cost", "profit", "count", "orders", "sold", "inr", "usd",
    ]
    ID_NAME_PATTERNS = ["id", "code", "key", "index", "num", "no.", "sr"]

    def _find_best_numeric_column(self, df: pd.DataFrame, date_col: str) -> Optional[str]:
        """Find the best numeric column for forecasting.

        Ranking priority:
          1. Column name looks like a target (sales/revenue/qty/…) — highest.
          2. Coefficient of variation (most 'interesting' to forecast).
        ID-like columns are skipped entirely; if all columns look like IDs we
        fall back to the first numeric column so we never return None silently.
        """
        candidates = []
        for col in df.columns:
            if col == date_col:
                continue
            if not pd.api.types.is_numeric_dtype(df[col]):
                continue
            col_lower = str(col).lower()
            # Skip columns that look like IDs
            if any(p in col_lower for p in self.ID_NAME_PATTERNS):
                continue
            # Prefer columns with meaningful variance
            std = df[col].std()
            mean = df[col].mean()
            if pd.notna(std) and std > 0:
                name_score = 1 if any(h in col_lower for h in self.TARGET_NAME_HINTS) else 0
                cov = std / max(abs(mean), 1e-6)
                candidates.append((col, name_score, cov))

        if not candidates:
            # Fallback: any numeric column
            numeric_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != date_col]
            return numeric_cols[0] if numeric_cols else None

        # Sort by (name looks like a target, then coefficient of variation), both descending.
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return candidates[0][0]

    def suggest_target_column(self, df: pd.DataFrame, date_col: Optional[str] = None) -> Optional[str]:
        """Public helper: best-guess forecast target for an arbitrary dataset.
        Used by /analyze-csv to pre-select the right column in the UI."""
        if date_col is None:
            date_col = self.detect_date_column(df)
        return self._find_best_numeric_column(df, date_col)

    def preprocess(self, df: pd.DataFrame, target_col: str, group_col: Optional[str] = None):
        """Full preprocessing pipeline. Returns cleaned DataFrame and metadata.
        
        Smart handling:
        - If target_col is categorical → treat it as group_col and auto-detect
          the best numeric column as the real forecast target.
        - If target_col is numeric → forecast it directly.
        """
        # Step 1: Detect date column
        self.date_col = self.detect_date_column(df)
        if not self.date_col:
            raise ValueError("No date column detected. Ensure your CSV has a column with dates.")

        # Step 2: Validate target column exists
        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found. Available: {list(df.columns)}")

        # Step 2b: Smart categorical handling
        # If the user selected a categorical column, use it as a group-by
        # and auto-pick the best numeric column as the actual forecast target
        self.original_target = target_col  # remember what the user selected
        self.resolved_group_col = group_col  # may be updated below
        
        is_target_numeric = pd.api.types.is_numeric_dtype(df[target_col])
        if not is_target_numeric:
            # Check: can it be parsed as numeric at all?
            test_numeric = pd.to_numeric(df[target_col], errors="coerce")
            pct_numeric = test_numeric.notna().mean()
            if pct_numeric < 0.5:
                # It's truly categorical — use it as a group dimension
                logger.info(
                    f"Target '{target_col}' is categorical ({df[target_col].nunique()} unique values). "
                    f"Using it as group_col and auto-detecting numeric target."
                )
                best_numeric = self._find_best_numeric_column(df, self.date_col)
                if best_numeric is None:
                    raise ValueError(
                        f"'{target_col}' is categorical and no suitable numeric column was found "
                        f"for forecasting. Available columns: {list(df.columns)}"
                    )
                logger.info(f"  → Auto-selected '{best_numeric}' as forecast target, grouped by '{target_col}'")
                group_col = target_col
                target_col = best_numeric
                self.resolved_group_col = group_col

        # Step 3: Collapse to a SINGLE daily time series.
        # Even when the user picked a categorical column (resolved as a group),
        # we forecast the daily TOTAL of the numeric target. Grouping is a display
        # dimension, not a training one: keeping one row per (date, group) would
        # interleave thousands of customers per date, making lag/rolling features
        # meaningless (the cause of all-zero forecasts) and exploding row count
        # (the cause of the tournament timing out so only baselines survived).
        other_cols = [c for c in df.columns if c != self.date_col and c != target_col
                      and pd.api.types.is_numeric_dtype(df[c])]
        agg_dict = {target_col: "sum"}
        for c in other_cols[:5]:  # keep first 5 numeric cols as mean
            agg_dict[c] = "mean"
        df = df.groupby(self.date_col).agg(agg_dict).reset_index()

        # Step 4: Detect types, clean, encode
        self.detect_column_types(df, self.date_col, target_col)
        df = self.clean(df, self.date_col, target_col)
        df = self.encode_categoricals(df)

        return df, target_col


# ────────────────────────────────────────────────────────────
# 2. FeatureEngineer — lags, rolling, calendar, seasonal
# ────────────────────────────────────────────────────────────
class FeatureEngineer:
    """Generates time-series features from any date + target column.
    References model_metadata.json for alignment when available."""

    # Default lag periods
    LAG_PERIODS = [1, 2, 3, 7, 14, 28]
    ROLLING_WINDOWS = [7, 28]

    def __init__(self, metadata_path: str = "model_metadata.json"):
        self.metadata_features = []
        try:
            with open(metadata_path, "r") as f:
                meta = json.load(f)
                self.metadata_features = meta.get("feature_columns", [])
        except FileNotFoundError:
            logger.info("No model_metadata.json found; using default feature set.")

    def add_lag_features(self, df: pd.DataFrame, target_col: str) -> pd.DataFrame:
        """Create lagged versions of the target variable."""
        for lag in self.LAG_PERIODS:
            col_name = f"lag_{lag}"
            df[col_name] = df[target_col].shift(lag)
        return df

    def add_rolling_features(self, df: pd.DataFrame, target_col: str) -> pd.DataFrame:
        """Create rolling mean and std features."""
        for w in self.ROLLING_WINDOWS:
            df[f"roll{w}_mean"] = df[target_col].shift(1).rolling(window=w, min_periods=1).mean()
            df[f"roll{w}_std"] = df[target_col].shift(1).rolling(window=w, min_periods=1).std().fillna(0)
        return df

    def add_calendar_features(self, df: pd.DataFrame, date_col: str) -> pd.DataFrame:
        """Extract calendar features from the date column."""
        dt = df[date_col]
        df["day_of_week"] = dt.dt.dayofweek
        df["is_weekend"] = (dt.dt.dayofweek >= 5).astype(int)
        df["month"] = dt.dt.month
        df["day_of_month"] = dt.dt.day
        df["is_month_end"] = (dt.dt.day >= 28).astype(int)
        df["quarter"] = dt.dt.quarter
        df["week_of_year"] = dt.dt.isocalendar().week.astype(int)
        # Cyclical encodings - let the model see that day 6->0 and month 12->1
        # are adjacent. Strongly improves fit on data with weekly/annual cycles.
        df["dow_sin"] = np.sin(2 * np.pi * dt.dt.dayofweek / 7)
        df["dow_cos"] = np.cos(2 * np.pi * dt.dt.dayofweek / 7)
        df["month_sin"] = np.sin(2 * np.pi * dt.dt.month / 12)
        df["month_cos"] = np.cos(2 * np.pi * dt.dt.month / 12)
        return df

    def engineer(self, df: pd.DataFrame, date_col: str, target_col: str) -> pd.DataFrame:
        """Full feature engineering pipeline."""
        df = df.copy()
        
        # Dynamically adjust lags based on dataset length
        max_allowed = max(1, len(df) // 3)
        self.LAG_PERIODS = [L for L in [1, 2, 3, 7, 14, 28] if L <= max_allowed]
        self.ROLLING_WINDOWS = [W for W in [7, 28] if W <= max_allowed]
        
        if not self.LAG_PERIODS:
            self.LAG_PERIODS = [1]
        if not self.ROLLING_WINDOWS:
            self.ROLLING_WINDOWS = [2]
            
        df = self.add_lag_features(df, target_col)
        df = self.add_rolling_features(df, target_col)
        df = self.add_calendar_features(df, date_col)

        # Drop rows where lag features create NaN, unless it destroys the dataset
        df_clean = df.dropna()
        if len(df_clean) >= 10:
            df = df_clean.reset_index(drop=True)
        else:
            df = df.bfill().fillna(0).reset_index(drop=True)
            
        return df

    def get_feature_columns(self, df: pd.DataFrame, date_col: str, target_col: str) -> list:
        """Return list of feature column names (everything except date & target)."""
        exclude = {date_col, target_col}
        return [c for c in df.columns if c not in exclude]


# ────────────────────────────────────────────────────────────
# 3. ModelTournament — Optuna-powered multi-model competition
# ────────────────────────────────────────────────────────────
class ModelTournament:
    """Runs an Optuna-tuned tournament across multiple ML models.
    Selects the winner based on lowest MAPE via TimeSeriesSplit CV."""

    MAX_TRIALS = 20       # Cap for Render RAM safety
    N_SPLITS = 3          # TimeSeriesSplit folds
    TIMEOUT_SECS = 25     # Max seconds for Optuna per model (tightened for speed)
    # Default to the two strong gradient-boosting learners + instant baselines.
    # ARIMA/SARIMA/Prophet are slow (each up to TIMEOUT_SECS x trials) and lose
    # on this data; enable them explicitly with include_slow_models=True.
    INCLUDE_SLOW_MODELS = False

    def __init__(self):
        self.results = {}
        self.best_model = None
        self.best_model_name = None

    @staticmethod
    def _mape(y_true, y_pred):
        """Robust Mean Absolute Percentage Error.

        Only averages over points whose actual value is meaningfully non-zero.
        The old `y_true + epsilon` denominator turned tiny actuals (e.g. a low
        Sunday) into thousands-of-percent errors that dominated the mean and
        corrupted model selection. We instead mask out points below a small
        fraction of the mean magnitude, which is the standard robust MAPE.
        """
        y_true = np.asarray(y_true, dtype=float)
        y_pred = np.asarray(y_pred, dtype=float)
        scale = np.mean(np.abs(y_true))
        floor = max(scale * 1e-3, 1e-8)
        mask = np.abs(y_true) >= floor
        if not np.any(mask):
            return float(np.mean(np.abs(y_true - y_pred)))
        return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)

    @staticmethod
    def _check_stationarity(y: pd.Series) -> bool:
        """Run Augmented Dickey-Fuller test. Returns True if stationary."""
        try:
            from statsmodels.tsa.stattools import adfuller
            if len(y) < 20:
                return True
            result = adfuller(y.dropna())
            return result[1] < 0.05
        except Exception:
            return True

    @staticmethod
    def _wmape(y_true, y_pred) -> float:
        """Weighted MAPE = sum|error| / sum|actual|. Scale-stable, always
        defined, and the PRIMARY selection metric (unlike raw MAPE it is not
        undefined on near-zero days nor dominated by them)."""
        y_true = np.asarray(y_true, dtype=float)
        y_pred = np.asarray(y_pred, dtype=float)
        denom = np.sum(np.abs(y_true))
        if denom == 0:
            return float("nan")
        return float(np.sum(np.abs(y_true - y_pred)) / denom * 100)

    @staticmethod
    def _bias_pct(y_true, y_pred) -> float:
        """Signed error as % of total actual. Positive => over-forecast."""
        y_true = np.asarray(y_true, dtype=float)
        y_pred = np.asarray(y_pred, dtype=float)
        denom = np.sum(np.abs(y_true))
        if denom == 0:
            return float("nan")
        return float(np.sum(y_pred - y_true) / denom * 100)

    def _evaluate_cv(self, model, X, y, dates=None, is_prophet=False) -> dict:
        """Run TimeSeriesSplit cross-validation and return averaged metrics.

        Reports WMAPE (primary), MAPE (legacy/UI), MAE, RMSE and bias so model
        selection is driven by a scale-stable, well-defined metric.
        """
        tscv = TimeSeriesSplit(n_splits=self.N_SPLITS)
        maes, rmses, mapes, wmapes, biases = [], [], [], [], []

        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            model.fit(X_train, y_train)

            # For prophet we don't use predict(X_val) in the same way, but Prophet wrapper handles it
            preds = model.predict(X_val)

            maes.append(mean_absolute_error(y_val, preds))
            rmses.append(np.sqrt(mean_squared_error(y_val, preds)))
            mapes.append(self._mape(y_val.values, preds))
            wmapes.append(self._wmape(y_val.values, preds))
            biases.append(self._bias_pct(y_val.values, preds))

        return {
            "wmape": round(float(np.nanmean(wmapes)), 2),
            "mae": round(float(np.mean(maes)), 2),
            "rmse": round(float(np.mean(rmses)), 2),
            "mape": round(float(np.mean(mapes)), 2),
            "bias_pct": round(float(np.nanmean(biases)), 2),
        }

    class _LogTargetModel:
        """Wraps any sklearn-style regressor to train on log1p(target) and
        predict back in the original scale. Multiplicative errors (which MAPE
        measures) become additive in log space, so the fit stops being
        dominated by a handful of very large days."""

        def __init__(self, base):
            self.base = base

        def fit(self, X, y):
            self.base.fit(X, np.log1p(np.clip(np.asarray(y, dtype=float), 0, None)))
            return self

        def predict(self, X):
            return np.clip(np.expm1(self.base.predict(X)), 0, None)

    @staticmethod
    def _use_log_target(y) -> bool:
        """Log-transform pays off only for non-negative, right-skewed targets."""
        y = np.asarray(y, dtype=float)
        if np.nanmin(y) < 0:
            return False
        mean = np.nanmean(y)
        std = np.nanstd(y)
        # High coefficient of variation => heavy tail => log helps.
        return mean > 0 and (std / mean) > 0.5

    def _wrap(self, model, y):
        """Conditionally wrap a regressor in the log-target transform."""
        if self._use_log_target(y):
            return self._LogTargetModel(model)
        return model

    def _run_xgboost(self, X, y):
        """Optuna-tuned XGBoost."""
        try:
            import xgboost as xgb
        except ImportError:
            logger.warning("XGBoost not installed, skipping.")
            return None, None

        def objective(trial):
            params = {
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "random_state": 42,
            }
            model = self._wrap(xgb.XGBRegressor(**params), y)
            metrics = self._evaluate_cv(model, X, y)
            return metrics["mape"]

        study = optuna.create_study(
            direction="minimize",
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
        )
        study.optimize(objective, n_trials=self.MAX_TRIALS, timeout=self.TIMEOUT_SECS, show_progress_bar=False)

        best_params = study.best_params
        best_params["random_state"] = 42
        best_model = self._wrap(xgb.XGBRegressor(**best_params), y)
        best_model.fit(X, y)
        metrics = self._evaluate_cv(self._wrap(xgb.XGBRegressor(**best_params), y), X, y)
        metrics["optuna_history"] = [t.value for t in study.trials if t.state.name == "COMPLETE"]
        return best_model, metrics

    def _run_lightgbm(self, X, y):
        """Optuna-tuned LightGBM."""
        try:
            import lightgbm as lgb
        except ImportError:
            logger.warning("LightGBM not installed, skipping.")
            return None, None

        def objective(trial):
            params = {
                "num_leaves": trial.suggest_int("num_leaves", 20, 150),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "random_state": 42,
                "verbosity": -1,
            }
            model = self._wrap(lgb.LGBMRegressor(**params), y)
            metrics = self._evaluate_cv(model, X, y)
            return metrics["mape"]

        study = optuna.create_study(
            direction="minimize",
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
        )
        study.optimize(objective, n_trials=self.MAX_TRIALS, timeout=self.TIMEOUT_SECS, show_progress_bar=False)

        best_params = study.best_params
        best_params["random_state"] = 42
        best_params["verbosity"] = -1
        best_model = self._wrap(lgb.LGBMRegressor(**best_params), y)
        best_model.fit(X, y)
        metrics = self._evaluate_cv(self._wrap(lgb.LGBMRegressor(**best_params), y), X, y)
        metrics["optuna_history"] = [t.value for t in study.trials if t.state.name == "COMPLETE"]
        return best_model, metrics

    def _run_ridge(self, X, y):
        """Optuna-tuned Ridge Regression (baseline)."""
        def objective(trial):
            alpha = trial.suggest_float("alpha", 0.01, 100.0, log=True)
            model = self._wrap(Ridge(alpha=alpha), y)
            metrics = self._evaluate_cv(model, X, y)
            return metrics["mape"]

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=10, timeout=30, show_progress_bar=False)

        best_model = self._wrap(Ridge(alpha=study.best_params["alpha"]), y)
        best_model.fit(X, y)
        metrics = self._evaluate_cv(self._wrap(Ridge(alpha=study.best_params["alpha"]), y), X, y)
        
        # Extract optimization history
        history = [t.value for t in study.trials if t.state.name == "COMPLETE"]
        metrics["optuna_history"] = history
        return best_model, metrics

    def _run_moving_average(self, X, y):
        """Simple moving average baseline (no Optuna needed)."""
        window = min(7, len(y))
        preds = y.rolling(window=window, min_periods=1).mean().values
        yv = y.values
        return None, {
            "wmape": round(self._wmape(yv, preds), 2),
            "mae": round(mean_absolute_error(yv, preds), 2),
            "rmse": round(np.sqrt(mean_squared_error(yv, preds)), 2),
            "mape": round(self._mape(yv, preds), 2),
            "bias_pct": round(self._bias_pct(yv, preds), 2),
        }


    def _run_arima(self, X, y, dates):
        """Optuna-tuned ARIMA using exogenous variables (ARIMAX)."""
        try:
            import statsmodels.api as sm
            import warnings
            warnings.filterwarnings("ignore")
        except ImportError:
            return None, None

        is_stationary = self._check_stationarity(y)
        
        def objective(trial):
            p = trial.suggest_int("p", 0, 3)
            d = trial.suggest_int("d", 1 if not is_stationary else 0, 2)
            q = trial.suggest_int("q", 0, 3)
            
            try:
                # Use a small validation split for Optuna to save time
                train_size = int(len(y) * 0.8)
                y_tr, y_val = y.iloc[:train_size], y.iloc[train_size:]
                X_tr, X_val = X.iloc[:train_size], X.iloc[train_size:]
                
                model = sm.tsa.ARIMA(y_tr, exog=X_tr, order=(p, d, q))
                fitted = model.fit()
                
                # We can use AIC for fast tuning instead of CV
                return fitted.aic
            except Exception:
                return float("inf")

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=15, timeout=self.TIMEOUT_SECS)
        
        try:
            best_p = study.best_params["p"]
            best_d = study.best_params["d"]
            best_q = study.best_params["q"]
            
            # For ARIMA in evaluate_cv, we need a wrapper
            class ARIMAWrap:
                def __init__(self, p, d, q):
                    self.order = (p, d, q)
                def fit(self, X_train, y_train):
                    self.model = sm.tsa.ARIMA(y_train, exog=X_train, order=self.order).fit()
                def predict(self, X_test):
                    return self.model.forecast(steps=len(X_test), exog=X_test)
            
            best_model = ARIMAWrap(best_p, best_d, best_q)
            best_model.fit(X, y) # Fit on all data
            metrics = self._evaluate_cv(ARIMAWrap(best_p, best_d, best_q), X, y)
            metrics["optuna_history"] = [t.value for t in study.trials if t.state.name == "COMPLETE"]
            return best_model, metrics
        except Exception:
            return None, None

    def _run_sarima(self, X, y, dates):
        """Optuna-tuned SARIMA."""
        try:
            import statsmodels.api as sm
            import warnings
            warnings.filterwarnings("ignore")
        except ImportError:
            return None, None

        is_stationary = self._check_stationarity(y)
        
        def objective(trial):
            p = trial.suggest_int("p", 0, 2)
            d = trial.suggest_int("d", 1 if not is_stationary else 0, 1)
            q = trial.suggest_int("q", 0, 2)
            P = trial.suggest_int("P", 0, 1)
            D = trial.suggest_int("D", 0, 1)
            Q = trial.suggest_int("Q", 0, 1)
            s = 7 # Weekly seasonality assumption for daily data
            
            try:
                train_size = int(len(y) * 0.8)
                y_tr, y_val = y.iloc[:train_size], y.iloc[train_size:]
                X_tr, X_val = X.iloc[:train_size], X.iloc[train_size:]
                
                model = sm.tsa.statespace.SARIMAX(y_tr, exog=X_tr, order=(p, d, q), seasonal_order=(P, D, Q, s))
                fitted = model.fit(disp=False)
                return fitted.aic
            except Exception:
                return float("inf")

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=15, timeout=self.TIMEOUT_SECS)
        
        try:
            p, d, q = study.best_params["p"], study.best_params["d"], study.best_params["q"]
            P, D, Q = study.best_params["P"], study.best_params["D"], study.best_params["Q"]
            s = 7
            
            class SARIMAWrap:
                def __init__(self, order, seasonal_order):
                    self.order = order
                    self.seasonal_order = seasonal_order
                def fit(self, X_train, y_train):
                    self.model = sm.tsa.statespace.SARIMAX(y_train, exog=X_train, order=self.order, seasonal_order=self.seasonal_order).fit(disp=False)
                def predict(self, X_test):
                    return self.model.forecast(steps=len(X_test), exog=X_test)
            
            best_model = SARIMAWrap((p,d,q), (P,D,Q,s))
            best_model.fit(X, y)
            metrics = self._evaluate_cv(SARIMAWrap((p,d,q), (P,D,Q,s)), X, y)
            metrics["optuna_history"] = [t.value for t in study.trials if t.state.name == "COMPLETE"]
            return best_model, metrics
        except Exception:
            return None, None

    def _run_prophet(self, X, y, dates):
        """Optuna-tuned Facebook Prophet."""
        try:
            from prophet import Prophet
            import logging
            logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
        except ImportError:
            return None, None

        # Prepare prophet data
        df_prophet = pd.DataFrame({"ds": dates, "y": y.values})
        # Merge exogenous features
        df_prophet = pd.concat([df_prophet.reset_index(drop=True), X.reset_index(drop=True)], axis=1)

        def objective(trial):
            cps = trial.suggest_float("changepoint_prior_scale", 0.001, 0.5, log=True)
            sps = trial.suggest_float("seasonality_prior_scale", 0.01, 10, log=True)
            
            try:
                train_size = int(len(df_prophet) * 0.8)
                train = df_prophet.iloc[:train_size]
                val = df_prophet.iloc[train_size:]
                
                m = Prophet(changepoint_prior_scale=cps, seasonality_prior_scale=sps)
                for col in X.columns:
                    m.add_regressor(col)
                m.fit(train)
                
                forecast = m.predict(val.drop(columns=["y"]))
                mape = self._mape(val["y"].values, forecast["yhat"].values)
                return mape
            except Exception:
                return float("inf")

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=15, timeout=self.TIMEOUT_SECS)
        
        try:
            cps = study.best_params["changepoint_prior_scale"]
            sps = study.best_params["seasonality_prior_scale"]
            
            class ProphetWrap:
                def __init__(self, cps, sps, feature_cols, all_dates):
                    self.cps = cps
                    self.sps = sps
                    self.feature_cols = feature_cols
                    self.all_dates = all_dates.reset_index(drop=True)
                    self.current_idx = 0
                    
                def fit(self, X_train, y_train):
                    self.m = Prophet(changepoint_prior_scale=self.cps, seasonality_prior_scale=self.sps)
                    for col in self.feature_cols:
                        self.m.add_regressor(col)
                    train_df = pd.DataFrame({"y": y_train.values})
                    train_df["ds"] = self.all_dates.iloc[self.current_idx : self.current_idx + len(y_train)].values
                    train_df = pd.concat([train_df, X_train.reset_index(drop=True)], axis=1)
                    self.m.fit(train_df)
                    self.current_idx += len(y_train)
                    
                def predict(self, X_test):
                    test_df = pd.DataFrame()
                    test_df["ds"] = self.all_dates.iloc[self.current_idx : self.current_idx + len(X_test)].values
                    test_df = pd.concat([test_df, X_test.reset_index(drop=True)], axis=1)
                    forecast = self.m.predict(test_df)
                    self.current_idx += len(X_test)
                    return forecast["yhat"].values
            
            # Custom CV for Prophet because of date handling
            tscv = TimeSeriesSplit(n_splits=self.N_SPLITS)
            maes, rmses, mapes = [], [], []
            for train_idx, val_idx in tscv.split(X):
                X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
                
                model = ProphetWrap(cps, sps, X.columns, dates)
                model.fit(X_train, y_train)
                preds = model.predict(X_val)
                maes.append(mean_absolute_error(y_val, preds))
                rmses.append(np.sqrt(mean_squared_error(y_val, preds)))
                mapes.append(self._mape(y_val.values, preds))
                
            metrics = {
                "mae": round(float(np.mean(maes)), 2),
                "rmse": round(float(np.mean(rmses)), 2),
                "mape": round(float(np.mean(mapes)), 2),
                "optuna_history": [t.value for t in study.trials if t.state.name == "COMPLETE"]
            }
            
            best_model = ProphetWrap(cps, sps, X.columns, dates)
            best_model.fit(X, y) # Fit on all data for future forecasting
            return best_model, metrics
        except Exception:
            return None, None

    def _run_seasonal_naive(self, X, y):
        """Seasonal-naive baseline (same value one season ago).

        This is the floor every learned model MUST beat. On short, noisy
        series a fancy model that cannot beat this is selecting on noise.
        Season is inferred: 7 if we appear to have >= 2 weeks of daily data.
        """
        yv = np.asarray(y, dtype=float)
        season = 7 if len(yv) >= 14 else 1
        tscv = TimeSeriesSplit(n_splits=self.N_SPLITS)
        maes, rmses, mapes, wmapes, biases = [], [], [], [], []
        for train_idx, val_idx in tscv.split(yv):
            hist = list(yv[train_idx])
            preds = []
            ext = list(hist)
            for _ in range(len(val_idx)):
                preds.append(ext[-season] if len(ext) >= season else ext[-1])
                ext.append(preds[-1])
            preds = np.clip(np.array(preds), 0, None)
            yt = yv[val_idx]
            maes.append(mean_absolute_error(yt, preds))
            rmses.append(np.sqrt(mean_squared_error(yt, preds)))
            mapes.append(self._mape(yt, preds))
            wmapes.append(self._wmape(yt, preds))
            biases.append(self._bias_pct(yt, preds))
        metrics = {
            "wmape": round(float(np.nanmean(wmapes)), 2),
            "mae": round(float(np.mean(maes)), 2),
            "rmse": round(float(np.mean(rmses)), 2),
            "mape": round(float(np.mean(mapes)), 2),
            "bias_pct": round(float(np.nanmean(biases)), 2),
        }
        return None, metrics

    def run_tournament(self, X: pd.DataFrame, y: pd.Series, dates: pd.Series = None) -> dict:
        """Execute all models sequentially and pick the winner."""
        logger.info("Starting model tournament...")

        runners = [
            ("XGBoost (Optuna)", self._run_xgboost),
            ("LightGBM (Optuna)", self._run_lightgbm),
            ("Ridge Regression", self._run_ridge),
            ("Moving Average", self._run_moving_average),
            ("Seasonal-Naive (baseline)", self._run_seasonal_naive),
        ]
        if getattr(self, "INCLUDE_SLOW_MODELS", False):
            runners[2:2] = [
                ("ARIMA (Optuna)", self._run_arima),
                ("SARIMA (Optuna)", self._run_sarima),
                ("Prophet (Optuna)", self._run_prophet),
            ]

        for name, runner_fn in runners:
            try:
                logger.info(f"  Training: {name}")
                if dates is not None and "Prophet" in name:
                    model, metrics = runner_fn(X, y, dates)
                elif dates is not None and ("ARIMA" in name or "SARIMA" in name):
                    model, metrics = runner_fn(X, y, dates)
                else:
                    model, metrics = runner_fn(X, y)
                if metrics:
                    self.results[name] = {"model": model, "metrics": metrics}
                    logger.info(f"    {name}: MAPE={metrics['mape']}%")
            except Exception as e:
                logger.warning(f"  {name} failed: {e}")

        if not self.results:
            raise RuntimeError("All models failed. Check your data.")

        # Pick winner on WMAPE (scale-stable, well-defined). Fall back to MAPE
        # only if WMAPE is missing/NaN for a model.
        def _score(k):
            m = self.results[k]["metrics"]
            w = m.get("wmape")
            return w if (w is not None and np.isfinite(w)) else m.get("mape", float("inf"))

        winner_name = min(self.results, key=_score)
        self.best_model_name = winner_name
        self.best_model = self.results[winner_name]["model"]

        # Report how the winner compares to the seasonal-naive floor.
        baseline_wmape = None
        for k, info in self.results.items():
            if "Seasonal-Naive" in k:
                baseline_wmape = info["metrics"].get("wmape")
        winner_wmape = self.results[winner_name]["metrics"].get("wmape")
        beats_baseline = (
            baseline_wmape is not None and winner_wmape is not None
            and np.isfinite(baseline_wmape) and np.isfinite(winner_wmape)
            and winner_wmape < baseline_wmape
        )

        leaderboard = []
        for name, info in sorted(self.results.items(), key=lambda x: _score(x[0])):
            leaderboard.append({"name": name, **info["metrics"]})

        return {
            "winner": winner_name,
            "winner_metrics": self.results[winner_name]["metrics"],
            "leaderboard": leaderboard,
            "baseline_wmape": baseline_wmape,
            "winner_beats_baseline": bool(beats_baseline),
        }


# ────────────────────────────────────────────────────────────
# 4. SummaryGenerator — rule-based natural language summary
# ────────────────────────────────────────────────────────────
class SummaryGenerator:
    """Produces a human-readable AI summary of the forecast results."""

    def generate(self, forecast_df: pd.DataFrame, date_col: str,
                 target_col: str, winner_name: str, winner_mape: float,
                 historical_df: pd.DataFrame = None) -> str:
        """Analyze forecast and produce a 2-3 sentence summary."""
        parts = []

        # 1. Trend direction
        if len(forecast_df) >= 2:
            first_val = forecast_df["Forecast"].iloc[0]
            last_val = forecast_df["Forecast"].iloc[-1]
            if first_val > 0:
                pct_change = round((last_val - first_val) / first_val * 100, 1)
                if pct_change > 2:
                    parts.append(
                        f"{target_col} is projected to increase by {abs(pct_change)}% "
                        f"over the next {len(forecast_df)} days, driven by a consistent upward trend."
                    )
                elif pct_change < -2:
                    parts.append(
                        f"{target_col} is expected to decrease by {abs(pct_change)}% "
                        f"over the next {len(forecast_df)} days. Consider investigating potential causes."
                    )
                else:
                    parts.append(
                        f"{target_col} is projected to remain relatively stable "
                        f"over the next {len(forecast_df)} days."
                    )

        # 2. Best and worst predicted periods
        if len(forecast_df) >= 7:
            best_day = forecast_df.loc[forecast_df["Forecast"].idxmax()]
            worst_day = forecast_df.loc[forecast_df["Forecast"].idxmin()]
            parts.append(
                f"The highest predicted {target_col} is on {best_day[date_col]} "
                f"({round(best_day['Forecast']):,}), while the lowest is on "
                f"{worst_day[date_col]} ({round(worst_day['Forecast']):,})."
            )

        # 3. Weekday vs weekend pattern
        if "day_of_week" in forecast_df.columns or len(forecast_df) >= 7:
            forecast_df["_dow"] = pd.to_datetime(forecast_df[date_col]).dt.dayofweek
            weekday_avg = forecast_df[forecast_df["_dow"] < 5]["Forecast"].mean()
            weekend_avg = forecast_df[forecast_df["_dow"] >= 5]["Forecast"].mean()
            if weekday_avg > 0 and weekend_avg > 0:
                ratio = round((weekday_avg - weekend_avg) / weekend_avg * 100, 1)
                if abs(ratio) > 5:
                    higher = "Weekdays" if ratio > 0 else "Weekends"
                    parts.append(f"{higher} show {abs(ratio)}% higher predicted {target_col} than {'weekends' if ratio > 0 else 'weekdays'}.")
            forecast_df = forecast_df.drop(columns=["_dow"], errors="ignore")

        # 4. Confidence
        if "UpperBound" in forecast_df.columns and "LowerBound" in forecast_df.columns:
            avg_width = (forecast_df["UpperBound"] - forecast_df["LowerBound"]).mean()
            avg_forecast = forecast_df["Forecast"].mean()
            if avg_forecast > 0:
                pct_width = round(avg_width / avg_forecast * 100, 1)
                conf_label = "high" if pct_width < 20 else ("moderate" if pct_width < 40 else "low")
                parts.append(f"The model has {conf_label} confidence (±{pct_width}% average bound width).")

        # 5. Model info
        parts.append(
            f"The winning model is {winner_name} with a MAPE of {winner_mape}%."
        )

        return " ".join(parts)


# ────────────────────────────────────────────────────────────
# 5. ForecastPipeline — full orchestrator
# ────────────────────────────────────────────────────────────
class ForecastPipeline:
    """Orchestrates: preprocess → engineer → tournament → forecast → summary."""

    MAX_ROWS = 50_000  # Cap for Render RAM safety

    def __init__(self):
        self.preprocessor = DataPreprocessor()
        self.engineer = FeatureEngineer()
        self.tournament = ModelTournament()
        self.summarizer = SummaryGenerator()

    def run(self, df: pd.DataFrame, target_col: str,
            group_col: Optional[str] = None, forecast_days: int = 30) -> dict:
        """
        Full pipeline execution.

        Args:
            df: Raw uploaded DataFrame
            target_col: Column to forecast (numeric) or group by (categorical)
            group_col: Optional categorical column for grouped forecasting
            forecast_days: Number of future periods to predict

        Returns:
            dict with forecast, leaderboard, winner, ai_summary, metadata
        """
        # We no longer cap the raw dataset here. We let the preprocessor aggregate it first,
        # otherwise taking the tail of an unsorted dataset corrupts the date ranges.

        # ── Step 1: Preprocess ───────────────────────────────
        logger.info("Step 1/5: Preprocessing...")
        original_target = target_col  # what the user selected in the UI
        df, target_col = self.preprocessor.preprocess(df, target_col, group_col)
        date_col = self.preprocessor.date_col
        resolved_group = getattr(self.preprocessor, 'resolved_group_col', None)
        
        logger.info(f"  Resolved target: {target_col}, date: {date_col}, group: {resolved_group}")
        logger.info(f"  Preprocessed shape: {df.shape}")
        logger.info(f"  Target sample: {df[target_col].head(5).tolist()}")

        # ── Detect Date Frequency ────────────────────────────
        dates = pd.to_datetime(df[date_col]).sort_values()
        diffs = dates.diff().dt.days.dropna()
        if len(diffs) > 0:
            median_diff = diffs.median()
            if median_diff >= 28:
                self.freq = 'M'
            elif median_diff >= 7:
                self.freq = 'W'
            else:
                self.freq = 'D'
        else:
            self.freq = 'D'
        logger.info(f"  Detected Frequency: {self.freq}")

        # ── Step 2: Feature Engineering ──────────────────────
        logger.info("Step 2/5: Feature engineering...")
        df_feat = self.engineer.engineer(df, date_col, target_col)
        feature_cols = self.engineer.get_feature_columns(df_feat, date_col, target_col)

        if len(df_feat) < 10:
            raise ValueError(
                f"Not enough data after feature engineering ({len(df_feat)} rows). "
                "Need at least 10 rows with sufficient history for lag features."
            )

        X = df_feat[feature_cols]
        y = df_feat[target_col]

        # ── Step 3: Model Tournament ─────────────────────────
        logger.info("Step 3/5: Running model tournament...")
        dates = df_feat[date_col] if date_col in df_feat.columns else df[date_col]
        tournament_results = self.tournament.run_tournament(X, y, dates)

        # ── Step 4: Generate Forecast ────────────────────────
        logger.info("Step 4/5: Generating forecast...")
        forecast_rows = self._generate_forecast(
            df_feat, date_col, target_col, feature_cols, forecast_days
        )

        # ── Step 5: AI Summary ───────────────────────────────
        logger.info("Step 5/5: Generating AI summary...")
        forecast_df = pd.DataFrame(forecast_rows)
        
        # Use a display label that reflects what the user chose
        display_target = target_col
        if resolved_group and original_target != target_col:
            display_target = f"{target_col} (by {original_target})"
        
        summary = self.summarizer.generate(
            forecast_df, date_col, display_target,
            tournament_results["winner"],
            tournament_results["winner_metrics"]["mape"],
            historical_df=df_feat,
        )

        # ── Plain-English verdict + honest accuracy label ────
        wm = tournament_results["winner_metrics"].get("wmape")
        vals = [r["Forecast"] for r in forecast_rows if isinstance(r.get("Forecast"), (int, float))]
        avg_val = float(np.mean(vals)) if vals else 0.0
        trend = "flat"
        if len(vals) >= 2 and avg_val > 0:
            chg = (vals[-1] - vals[0]) / (abs(vals[0]) + 1e-9) * 100
            trend = "rising" if chg > 5 else ("falling" if chg < -5 else "flat")
        beats = tournament_results.get("winner_beats_baseline")
        if wm is None or not np.isfinite(wm):
            conf = "unvalidated"
        elif wm <= 15:
            conf = "high confidence"
        elif wm <= 30:
            conf = "moderate confidence"
        else:
            conf = "low confidence — treat as directional only"
        err_txt = f"typically within ±{round(wm)}%" if (wm is not None and np.isfinite(wm)) else "error not measurable"
        base_txt = "" if beats else " It does not beat a simple same-weekday-last-week baseline, so use with caution."
        verdict = (
            f"Over the next {len(forecast_rows)} periods, {display_target} is projected to stay {trend}, "
            f"averaging about {avg_val:,.0f} per period ({err_txt}, {conf}).{base_txt}"
        )
        accuracy_label = err_txt

        # Build response
        # Clean forecast for JSON serialization — ensure dates are proper strings
        for row in forecast_rows:
            val = row[date_col]
            if hasattr(val, 'strftime'):
                row[date_col] = val.strftime('%Y-%m-%d')
            elif hasattr(val, 'date'):
                row[date_col] = str(val.date())
            else:
                row[date_col] = str(val)[:10]

        return {
            "forecast": forecast_rows,
            "models_leaderboard": tournament_results["leaderboard"],
            "winner": {
                "name": tournament_results["winner"],
                "metrics": tournament_results["winner_metrics"],
                "reason": self._build_reason(
                    tournament_results["winner"],
                    tournament_results["winner_metrics"],
                    display_target,
                    tournament_results["leaderboard"],
                ),
            },
            "baseline_wmape": tournament_results.get("baseline_wmape"),
            "winner_beats_baseline": tournament_results.get("winner_beats_baseline"),
            "verdict": verdict,
            "accuracy_label": accuracy_label,
            "ai_summary": summary,
            "metadata": {
                "date_column": date_col,
                "target_column": target_col,
                "original_selection": original_target,
                "grouped_by": resolved_group,
                "total_training_rows": len(df_feat),
                "total_raw_rows": len(df),
                "forecast_days": forecast_days,
                "features_used": len(feature_cols),
            },
        }

    def _generate_forecast(self, df_feat, date_col, target_col, feature_cols, forecast_days):
        """Generate future predictions using the winning model."""
        model = self.tournament.best_model
        model_name = self.tournament.best_model_name

        # For Moving Average (no model object), use simple projection
        if model is None:
            return self._moving_average_forecast(df_feat, date_col, target_col, forecast_days)

        forecast_rows = []
        last_row = df_feat.iloc[-1].copy()
        last_date = last_row[date_col]
        recent_values = df_feat[target_col].tail(28).tolist()

        for i in range(1, forecast_days + 1):
            if getattr(self, 'freq', 'D') == 'M':
                next_date = last_date + pd.DateOffset(months=i)
            elif getattr(self, 'freq', 'D') == 'W':
                next_date = last_date + pd.Timedelta(weeks=i)
            else:
                next_date = last_date + pd.Timedelta(days=i)

            # Build feature row
            row = {}
            row[date_col] = next_date

            # Calendar features
            row["day_of_week"] = next_date.weekday()
            row["is_weekend"] = int(next_date.weekday() >= 5)
            row["month"] = next_date.month
            row["day_of_month"] = next_date.day
            row["is_month_end"] = int(next_date.day >= 28)
            row["quarter"] = (next_date.month - 1) // 3 + 1
            row["week_of_year"] = next_date.isocalendar()[1]
            # Cyclical calendar features (must mirror FeatureEngineer.add_calendar_features)
            row["dow_sin"] = float(np.sin(2 * np.pi * next_date.weekday() / 7))
            row["dow_cos"] = float(np.cos(2 * np.pi * next_date.weekday() / 7))
            row["month_sin"] = float(np.sin(2 * np.pi * next_date.month / 12))
            row["month_cos"] = float(np.cos(2 * np.pi * next_date.month / 12))

            # Lag features from recent_values
            n = len(recent_values)
            for lag in FeatureEngineer.LAG_PERIODS:
                idx = n - lag
                row[f"lag_{lag}"] = recent_values[idx] if idx >= 0 else recent_values[0]

            # Rolling features
            for w in FeatureEngineer.ROLLING_WINDOWS:
                window_vals = recent_values[-w:] if len(recent_values) >= w else recent_values
                row[f"roll{w}_mean"] = float(np.mean(window_vals))
                row[f"roll{w}_std"] = float(np.std(window_vals))

            # Add any other features that exist (encoded categoricals, etc.)
            for col in feature_cols:
                if col not in row:
                    row[col] = float(last_row.get(col, 0))

            # Predict
            X_pred = pd.DataFrame([{c: row.get(c, 0) for c in feature_cols}])
            pred = float(model.predict(X_pred)[0])
            pred = max(0.0, pred)

            # Confidence bounds (±15% variance)
            variance = pred * 0.15
            forecast_rows.append({
                date_col: str(next_date.date()) if hasattr(next_date, 'date') else str(next_date)[:10],
                "Forecast": round(pred, 2),
                "LowerBound": round(max(0, pred - variance), 2),
                "UpperBound": round(pred + variance, 2),
            })

            # Update recent_values for next iteration
            recent_values.append(pred)

        return forecast_rows

    def _moving_average_forecast(self, df_feat, date_col, target_col, forecast_days):
        """Fallback forecast using simple moving average."""
        recent = df_feat[target_col].tail(7).tolist()
        last_date = df_feat[date_col].iloc[-1]
        forecast_rows = []

        for i in range(1, forecast_days + 1):
            if getattr(self, 'freq', 'D') == 'M':
                next_date = last_date + pd.DateOffset(months=i)
            elif getattr(self, 'freq', 'D') == 'W':
                next_date = last_date + pd.Timedelta(weeks=i)
            else:
                next_date = last_date + pd.Timedelta(days=i)
            pred = float(np.mean(recent[-7:]))
            variance = pred * 0.15
            forecast_rows.append({
                date_col: str(next_date.date()) if hasattr(next_date, 'date') else str(next_date)[:10],
                "Forecast": round(pred, 2),
                "LowerBound": round(max(0, pred - variance), 2),
                "UpperBound": round(pred + variance, 2),
            })
            recent.append(pred)

        return forecast_rows

    @staticmethod
    def _build_reason(winner_name, winner_metrics, target_col, leaderboard):
        """Build human-readable reason for why this model won."""
        runner_up = None
        for m in leaderboard:
            if m["name"] != winner_name:
                runner_up = m
                break

        wm = winner_metrics.get("wmape")
        metric_str = f"WMAPE: {wm}%" if wm is not None else f"MAPE: {winner_metrics['mape']}%"
        reason = (
            f"{winner_name} was selected because it achieved the lowest error rate "
            f"for {target_col} ({metric_str})"
        )
        if runner_up:
            r_wm = runner_up.get("wmape")
            r_str = f"WMAPE: {r_wm}%" if r_wm is not None else f"MAPE: {runner_up['mape']}%"
            reason += f", outperforming {runner_up['name']} ({r_str})"
            if len(leaderboard) > 2:
                reason += f" and {len(leaderboard) - 2} other model(s)"
        reason += "."
        # Contextualise against the seasonal-naive floor when present.
        base = next((m for m in leaderboard if "Seasonal-Naive" in m["name"]), None)
        if base is not None and wm is not None and base.get("wmape") is not None:
            if wm < base["wmape"]:
                reason += (f" It also beats the seasonal-naive baseline "
                           f"({base['wmape']}% WMAPE), so it adds genuine value.")
            else:
                reason += (f" NOTE: it does NOT beat the seasonal-naive baseline "
                           f"({base['wmape']}% WMAPE) — on a short/noisy series the "
                           f"simple baseline is the safer choice.")
        return reason
