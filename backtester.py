"""
O(n) backtester — precomputes all indicator columns once, then does a single
forward pass to simulate trades. No lookahead bias on indicator values.
"""

import numpy as np
import pandas as pd
from indicators import add_all_indicators, add_backtest_columns
from scorer import score_row


def backtest(df: pd.DataFrame, weights: dict,
             buy_threshold: float = 65.0,
             hold_days: int = 5) -> dict:
    """
    Simulate buy-and-hold trades on historical daily data.

    Rules:
      - Buy at Close[i] when score[i] >= buy_threshold
      - Sell at Close[i + hold_days]
      - Skip hold_days forward after a trade (no overlapping positions)

    Returns metrics dict + list of individual trades.
    """
    df = add_all_indicators(df.copy())
    df = add_backtest_columns(df)
    df = df.dropna().reset_index(drop=True)

    empty = {"n_trades": 0, "sharpe": 0.0, "win_rate": 0.0,
             "avg_return_pct": 0.0, "max_drawdown_pct": 0.0,
             "total_return_pct": 0.0, "trades": []}

    if len(df) < hold_days + 20:
        return empty

    # Vectorised scoring — O(n), each row scored in O(1)
    scores = df.apply(lambda row: score_row(row, weights), axis=1).values
    closes = df["Close"].values
    dates  = df.index.tolist()

    trades = []
    i = 0
    while i < len(df) - hold_days:
        if scores[i] >= buy_threshold:
            entry      = closes[i]
            exit_price = closes[i + hold_days]
            ret        = (exit_price - entry) / max(entry, 1e-9)
            trades.append({
                "date":       dates[i],
                "entry":      round(float(entry), 2),
                "exit":       round(float(exit_price), 2),
                "return_pct": round(ret * 100, 2),
                "score":      round(float(scores[i]), 1),
                "won":        ret > 0,
            })
            i += hold_days          # skip forward — avoid overlapping trades
        else:
            i += 1

    if not trades:
        return empty

    returns = np.array([t["return_pct"] / 100 for t in trades])
    return {"trades": trades, **_compute_metrics(returns)}


def _compute_metrics(returns: np.ndarray) -> dict:
    if len(returns) == 0:
        return {"n_trades": 0, "sharpe": 0.0, "win_rate": 0.0,
                "avg_return_pct": 0.0, "max_drawdown_pct": 0.0,
                "total_return_pct": 0.0}

    mean_r = float(returns.mean())
    std_r  = float(returns.std())
    # Annualised Sharpe — needs ≥3 trades to be meaningful
    sharpe = (mean_r / std_r) * np.sqrt(252 / 5) if (len(returns) >= 3 and std_r > 1e-6) else float("nan")
    win_rate  = float((returns > 0).mean())
    equity    = np.cumprod(1 + returns)
    peak      = np.maximum.accumulate(equity)
    max_dd    = float(((equity - peak) / (peak + 1e-9)).min() * 100)
    total_ret = float((equity[-1] - 1) * 100)

    return {
        "n_trades":          len(returns),
        "sharpe":            round(sharpe, 2),
        "win_rate":          round(win_rate * 100, 1),
        "avg_return_pct":    round(mean_r * 100, 2),
        "max_drawdown_pct":  round(max_dd, 2),
        "total_return_pct":  round(total_ret, 2),
    }


def backtest_universe(data: dict, weights: dict,
                      buy_threshold: float = 65.0,
                      hold_days: int = 5) -> dict:
    """
    Run backtest across a dict of {ticker: df}.
    Returns per-ticker metrics + aggregate across all trades.
    """
    per_ticker   = {}
    all_returns  = []

    for ticker, df in data.items():
        result = backtest(df, weights,
                          buy_threshold=buy_threshold,
                          hold_days=hold_days)
        per_ticker[ticker] = result
        all_returns.extend(t["return_pct"] / 100 for t in result.get("trades", []))

    agg = _compute_metrics(np.array(all_returns)) if all_returns else \
          {"n_trades": 0, "sharpe": 0.0, "win_rate": 0.0,
           "avg_return_pct": 0.0, "max_drawdown_pct": 0.0,
           "total_return_pct": 0.0}

    return {
        "aggregate": {**agg, "n_stocks": len(per_ticker)},
        "by_ticker": per_ticker,
    }
