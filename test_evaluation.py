"""Unit tests for evaluation.py — run with: python3 -m pytest test_evaluation.py
Also runnable directly: python3 test_evaluation.py"""
import numpy as np
import evaluation as ev


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


def test_wmape_perfect():
    y = [10, 20, 30]
    assert approx(ev.wmape(y, y), 0.0)


def test_wmape_known():
    # actual sum=100, abs error sum=10 -> 10%
    y_true = [40, 60]
    y_pred = [45, 55]  # errors 5,5 -> 10 / 100 = 10%
    assert approx(ev.wmape(y_true, y_pred), 10.0)


def test_wmape_ignores_near_zero_blowup():
    # A tiny actual should not explode WMAPE the way MAPE does
    y_true = [1e-6, 1000, 1000]
    y_pred = [50, 1000, 1000]
    assert ev.wmape(y_true, y_pred) < 5.0  # dominated by the big correct values


def test_bias_sign():
    y_true = [100, 100]
    over = ev.bias_pct(y_true, [120, 120])   # over-forecast -> positive
    under = ev.bias_pct(y_true, [80, 80])    # under-forecast -> negative
    assert over > 0 and under < 0
    assert approx(over, 20.0) and approx(under, -20.0)


def test_mase_beats_naive():
    # Perfect prediction -> MASE 0 (< 1 means beats naive)
    rng = np.arange(1, 31, dtype=float)
    assert ev.mase(rng, rng, rng, season=7) == 0.0


def test_seasonal_naive_repeats_week():
    hist = np.array([1, 2, 3, 4, 5, 6, 7], dtype=float)
    f = ev.seasonal_naive_forecast(hist, horizon=3, season=7)
    assert list(f) == [1.0, 2.0, 3.0]


def test_rolling_origin_runs_and_grows():
    # Build a noisy weekly-seasonal series; error should be finite
    rng = np.random.RandomState(0)
    weeks = np.tile([10, 40, 20, 15, 18, 25, 2], 26).astype(float)
    weeks += rng.normal(0, 1, size=len(weeks))
    res = ev.rolling_origin_backtest(
        weeks, horizon=7,
        forecast_fn=lambda h, hz: ev.seasonal_naive_forecast(h, hz, 7),
        n_folds=4, season=7,
    )
    assert res["n_folds"] >= 1
    assert np.isfinite(res["avg"]["wmape"])
    assert len(res["wmape_by_step"]) == 7


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
