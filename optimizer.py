"""
Walk-forward weight optimisation using scipy SLSQP.

Window structure (default, 1 year of daily data ~252 bars):
  train = 84 bars (~4 months), test = 21 bars (~1 month)
  Advances by 21 bars each step → ~7 windows from 1 year of data.

For each window:
  1. Optimise weights on train data (maximise avg Sharpe across basket)
  2. Evaluate optimised weights on test data (OOS / out-of-sample)

Final recommended weights = average of all per-window optimised weights.
"""

import numpy as np
from scipy.optimize import minimize
from indicators import add_all_indicators, add_backtest_columns
from backtester import backtest_universe


def _prep(data: dict, min_rows: int = 50) -> dict:
    """Precompute indicators + backtest columns for all tickers once."""
    prepped = {}
    for ticker, df in data.items():
        try:
            df_ind = add_all_indicators(df.copy())
            df_ind = add_backtest_columns(df_ind)
            df_ind = df_ind.dropna().reset_index(drop=True)
            if len(df_ind) >= min_rows:
                prepped[ticker] = df_ind
        except Exception:
            pass
    return prepped


def optimize_weights(train_data: dict, base_weights: dict,
                     buy_threshold: float = 65.0,
                     hold_days: int = 5) -> dict:
    """
    SLSQP minimisation: find weights that maximise average Sharpe ratio
    across all stocks in train_data.

    Constraints:
      - weights sum to 1.0
      - each weight in [0.05, 0.60]
    """
    keys = list(base_weights.keys())
    x0   = np.array([base_weights[k] for k in keys], dtype=float)

    def neg_avg_sharpe(x):
        x = np.abs(x)
        x = x / x.sum()            # renormalise in case SLSQP drifts
        w = dict(zip(keys, x))
        result = backtest_universe(train_data, w,
                                   buy_threshold=buy_threshold,
                                   hold_days=hold_days)
        return -result["aggregate"]["sharpe"]

    constraints = [{"type": "eq", "fun": lambda x: x.sum() - 1.0}]
    bounds      = [(0.05, 0.60)] * len(keys)

    res = minimize(
        neg_avg_sharpe, x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 80, "ftol": 1e-4, "disp": False},
    )

    opt_x = np.abs(res.x)
    opt_x = opt_x / opt_x.sum()
    return {k: round(float(v), 4) for k, v in zip(keys, opt_x)}


def run_walk_forward(data: dict, base_weights: dict,
                     train_days: int = 84,
                     test_days:  int = 21,
                     buy_threshold: float = 65.0,
                     hold_days: int = 5) -> dict:
    """
    Full walk-forward pipeline:
      1. Precompute indicators once for all tickers
      2. Slide a train/test window across the data
      3. Optimise weights on each train window
      4. Evaluate OOS on each test window
      5. Return per-window results + recommended (averaged) weights

    Returns:
      {
        "windows": list of window result dicts,
        "recommended_weights": dict,
        "n_stocks_used": int,
        "base_weights_oos": dict,   # baseline performance with original weights
      }
    """
    prepped = _prep(data, min_rows=train_days + test_days)

    if not prepped:
        return {"windows": [], "recommended_weights": base_weights,
                "n_stocks_used": 0, "base_weights_oos": {}}

    min_length  = min(len(df) for df in prepped.values())
    n_windows   = max(0, (min_length - train_days) // test_days)

    if n_windows == 0:
        return {"windows": [], "recommended_weights": base_weights,
                "n_stocks_used": len(prepped), "base_weights_oos": {}}

    window_results  = []
    all_opt_weights = []
    base_oos_returns = []

    for i in range(n_windows):
        t_start = i * test_days
        t_end   = t_start + train_days
        v_end   = t_end   + test_days

        train_data = {t: df.iloc[t_start:t_end] for t, df in prepped.items()
                      if t_end <= len(df)}
        test_data  = {t: df.iloc[t_end:v_end]   for t, df in prepped.items()
                      if v_end <= len(df)}

        train_data = {t: df for t, df in train_data.items() if len(df) >= 20}
        test_data  = {t: df for t, df in test_data.items()  if len(df) >= 5}

        if not train_data or not test_data:
            continue

        # Optimised weights on this train window
        opt_w = optimize_weights(train_data, base_weights, buy_threshold, hold_days)

        # OOS evaluation
        oos_opt  = backtest_universe(test_data, opt_w,
                                     buy_threshold=buy_threshold, hold_days=hold_days)
        oos_base = backtest_universe(test_data, base_weights,
                                     buy_threshold=buy_threshold, hold_days=hold_days)

        window_results.append({
            "window":            i + 1,
            "opt_weights":       opt_w,
            "oos_sharpe":        oos_opt["aggregate"]["sharpe"],
            "oos_win_rate":      oos_opt["aggregate"]["win_rate"],
            "oos_avg_return":    oos_opt["aggregate"]["avg_return_pct"],
            "oos_n_trades":      oos_opt["aggregate"]["n_trades"],
            "base_oos_sharpe":   oos_base["aggregate"]["sharpe"],
        })
        all_opt_weights.append(opt_w)
        base_oos_returns.append(oos_base["aggregate"]["sharpe"])

    # Average optimised weights across all windows
    if all_opt_weights:
        keys  = list(base_weights.keys())
        avg_w = {k: float(np.mean([w.get(k, base_weights[k])
                                   for w in all_opt_weights])) for k in keys}
        total = sum(avg_w.values())
        recommended = {k: round(v / total, 4) for k, v in avg_w.items()}
    else:
        recommended = base_weights

    return {
        "windows":             window_results,
        "recommended_weights": recommended,
        "n_stocks_used":       len(prepped),
        "avg_oos_sharpe":      round(float(np.mean([w["oos_sharpe"] for w in window_results])), 2)
                               if window_results else 0.0,
        "avg_base_sharpe":     round(float(np.mean(base_oos_returns)), 2)
                               if base_oos_returns else 0.0,
    }
