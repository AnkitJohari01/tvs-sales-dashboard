import re

with open(r"d:\GetOnData\TVS\forecasting_engine.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add _check_stationarity
stationarity_code = """    @staticmethod
    def _check_stationarity(y: pd.Series) -> bool:
        \"\"\"Run Augmented Dickey-Fuller test. Returns True if stationary.\"\"\"
        try:
            from statsmodels.tsa.stattools import adfuller
            if len(y) < 20:
                return True
            result = adfuller(y.dropna())
            return result[1] < 0.05
        except Exception:
            return True

"""

# Insert _check_stationarity before _evaluate_cv
content = content.replace("    def _evaluate_cv", stationarity_code + "    def _evaluate_cv")

# 2. Add _run_arima, _run_sarima, _run_prophet
new_models_code = """
    def _run_arima(self, X, y, dates):
        \"\"\"Optuna-tuned ARIMA using exogenous variables (ARIMAX).\"\"\"
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
        \"\"\"Optuna-tuned SARIMA.\"\"\"
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
        \"\"\"Optuna-tuned Facebook Prophet.\"\"\"
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
"""

content = content.replace("    def run_tournament", new_models_code + "\n    def run_tournament")

# 3. Add them to runners list
runners_list = """        runners = [
            ("XGBoost (Optuna)", self._run_xgboost),
            ("LightGBM (Optuna)", self._run_lightgbm),
            ("ARIMA (Optuna)", self._run_arima),
            ("SARIMA (Optuna)", self._run_sarima),
            ("Prophet (Optuna)", self._run_prophet),
            ("Ridge Regression", self._run_ridge),
            ("Moving Average", self._run_moving_average),
        ]"""
content = re.sub(r'        runners = \[.*?# New models will be added here\n        \]', runners_list, content, flags=re.DOTALL)

with open(r"d:\GetOnData\TVS\forecasting_engine.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done updating forecasting_engine.py")
