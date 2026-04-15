"""
Backtester — buys when score >= threshold, exits when:
  1. Price hits stop loss  (entry - 1.5 × ATR)
  2. Price hits target     (entry + 2.5 × ATR)
  3. Max hold days reached (default 10)
No lookahead bias on indicator values.
"""

import numpy as np
import pandas as pd
from config import ATR_MULTIPLIER_STOP, ATR_MULTIPLIER_TARGET
from indicators import add_all_indicators, add_backtest_columns
from scorer import score_row


def backtest(df: pd.DataFrame, weights: dict,
             buy_threshold: float = 65.0,
             hold_days: int = 5,           # kept for API compatibility, unused
             max_hold_days: int = 10) -> dict:
    """
    Simulate trades on historical daily OHLCV.

    Entry  : Close[i] when score[i] >= buy_threshold
    Stop   : entry - ATR_MULTIPLIER_STOP   × ATR[i]
    Target : entry + ATR_MULTIPLIER_TARGET × ATR[i]
    Exit   : first of stop hit, target hit, or max_hold_days elapsed
    """
    df = add_all_indicators(df.copy())
    df = add_backtest_columns(df)
    df = df.dropna().reset_index(drop=True)

    empty = {"n_trades": 0, "sharpe": float("nan"), "win_rate": 0.0,
             "avg_return_pct": 0.0, "max_drawdown_pct": 0.0,
             "total_return_pct": 0.0, "avg_days_held": 0.0, "trades": []}

    if len(df) < max_hold_days + 20:
        return empty

    scores = df.apply(lambda row: score_row(row, weights), axis=1).values
    closes = df["Close"].values
    highs  = df["High"].values
    lows   = df["Low"].values
    atrs   = df["atr"].values
    dates  = df.index.tolist()

    trades = []
    i = 0
    while i < len(df) - 1:
        if scores[i] >= buy_threshold:
            entry_price = float(closes[i])
            entry_atr   = float(atrs[i])

            if np.isnan(entry_atr) or entry_atr <= 0:
                i += 1
                continue

            stop   = entry_price - ATR_MULTIPLIER_STOP   * entry_atr
            target = entry_price + ATR_MULTIPLIER_TARGET * entry_atr

            exit_price  = None
            exit_reason = "max_hold"
            days_held   = 0

            end = min(i + max_hold_days + 1, len(df))
            for j in range(i + 1, end):
                days_held = j - i
                # Stop checked first — pessimistic assumption
                if lows[j] <= stop:
                    exit_price  = stop
                    exit_reason = "stop"
                    break
                if highs[j] >= target:
                    exit_price  = target
                    exit_reason = "target"
                    break
            else:
                last_j      = min(i + max_hold_days, len(df) - 1)
                exit_price  = float(closes[last_j])
                days_held   = last_j - i

            ret = (exit_price - entry_price) / max(entry_price, 1e-9)
            trades.append({
                "date":        dates[i],
                "entry":       round(entry_price, 2),
                "exit":        round(exit_price, 2),
                "stop":        round(stop, 2),
                "target":      round(target, 2),
                "return_pct":  round(ret * 100, 2),
                "score":       round(float(scores[i]), 1),
                "won":         ret > 0,
                "exit_reason": exit_reason,
                "days_held":   days_held,
            })
            i += max(days_held, 1)
        else:
            i += 1

    if not trades:
        return empty

    returns    = np.array([t["return_pct"] / 100 for t in trades])
    avg_days   = sum(t["days_held"] for t in trades) / len(trades)
    exit_counts = {
        "stop":     sum(1 for t in trades if t["exit_reason"] == "stop"),
        "target":   sum(1 for t in trades if t["exit_reason"] == "target"),
        "max_hold": sum(1 for t in trades if t["exit_reason"] == "max_hold"),
    }
    return {"trades": trades, "exit_counts": exit_counts,
            **_compute_metrics(returns, avg_days)}


def _compute_metrics(returns: np.ndarray, avg_days_held: float = 5.0) -> dict:
    if len(returns) == 0:
        return {"n_trades": 0, "sharpe": float("nan"), "win_rate": 0.0,
                "avg_return_pct": 0.0, "max_drawdown_pct": 0.0,
                "total_return_pct": 0.0, "avg_days_held": 0.0}

    mean_r = float(returns.mean())
    std_r  = float(returns.std())
    sharpe = (mean_r / std_r) * np.sqrt(252 / max(avg_days_held, 1)) \
             if (len(returns) >= 3 and std_r > 1e-6) else float("nan")
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
        "avg_days_held":     round(avg_days_held, 1),
    }


def backtest_universe(data: dict, weights: dict,
                      buy_threshold: float = 65.0,
                      hold_days: int = 5,
                      max_hold_days: int = 10) -> dict:
    """
    Run backtest across a dict of {ticker: df}.
    Returns per-ticker metrics + aggregate across all trades.
    """
    per_ticker  = {}
    all_returns = []
    all_days    = []

    for ticker, df in data.items():
        result = backtest(df, weights,
                          buy_threshold=buy_threshold,
                          hold_days=hold_days,
                          max_hold_days=max_hold_days)
        per_ticker[ticker] = result
        for t in result.get("trades", []):
            all_returns.append(t["return_pct"] / 100)
            all_days.append(t["days_held"])

    avg_days = sum(all_days) / len(all_days) if all_days else 5.0
    agg      = _compute_metrics(np.array(all_returns), avg_days) \
               if all_returns else \
               {"n_trades": 0, "sharpe": float("nan"), "win_rate": 0.0,
                "avg_return_pct": 0.0, "max_drawdown_pct": 0.0,
                "total_return_pct": 0.0, "avg_days_held": 0.0}

    # Aggregate exit reason counts
    exit_counts = {"stop": 0, "target": 0, "max_hold": 0}
    for res in per_ticker.values():
        for k, v in res.get("exit_counts", {}).items():
            exit_counts[k] = exit_counts.get(k, 0) + v

    return {
        "aggregate": {**agg, "n_stocks": len(per_ticker),
                      "exit_counts": exit_counts},
        "by_ticker": per_ticker,
    }
