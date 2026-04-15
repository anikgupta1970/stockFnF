import numpy as np
import pandas as pd
from config import SCORE_WEIGHTS, SWING_WEIGHTS, ATR_MULTIPLIER_STOP, ATR_MULTIPLIER_TARGET


# ── Shared sub-scorers ────────────────────────────────────────────────────────

def _rsi_score(rsi_val: float) -> tuple:
    if np.isnan(rsi_val):
        return 50.0, "RSI: N/A"
    score = float(np.interp(rsi_val,
                            [0,  30,  45,  55,  70,  100],
                            [95, 85,  60,  40,  15,   5]))
    if rsi_val < 30:
        label = f"RSI={rsi_val:.1f} (oversold — buy signal)"
    elif rsi_val < 45:
        label = f"RSI={rsi_val:.1f} (approaching oversold)"
    elif rsi_val < 55:
        label = f"RSI={rsi_val:.1f} (neutral)"
    elif rsi_val < 70:
        label = f"RSI={rsi_val:.1f} (approaching overbought)"
    else:
        label = f"RSI={rsi_val:.1f} (overbought — caution)"
    return score, label


def _macd_score(macd: float, macd_sig: float, hist_vals: pd.Series) -> tuple:
    if any(np.isnan(v) for v in [macd, macd_sig]):
        return 50.0, "MACD: N/A"
    score, parts = 0.0, []
    if macd > macd_sig:
        score += 40; parts.append("MACD above signal (bullish)")
    else:
        parts.append("MACD below signal (bearish)")
    recent = hist_vals.dropna().tail(3)
    if len(recent) >= 2:
        if recent.iloc[-1] > recent.iloc[-2]:
            score += 30; parts.append("histogram rising")
        else:
            parts.append("histogram falling")
    if macd > 0:
        score += 30
    return score, "MACD: " + ", ".join(parts[:2])


def _bb_score(close: float, bb_lower: float, bb_upper: float) -> tuple:
    if any(np.isnan(v) for v in [close, bb_lower, bb_upper]):
        return 50.0, "BB: N/A"
    width = bb_upper - bb_lower
    if width == 0:
        return 50.0, "BB: flat"
    pos   = (close - bb_lower) / width
    score = float(np.clip((1 - pos) * 100, 0, 100))
    if pos < 0.2:
        label = f"BB: near lower band ({pos:.0%}) — oversold zone"
    elif pos > 0.8:
        label = f"BB: near upper band ({pos:.0%}) — overbought zone"
    else:
        label = f"BB: mid-band ({pos:.0%})"
    return score, label


def _ma_score(df: pd.DataFrame) -> tuple:
    last = df.iloc[-1]
    ms, ml = last.get("ma_short", np.nan), last.get("ma_long", np.nan)
    if np.isnan(ms) or np.isnan(ml):
        return 50.0, "MA: N/A"
    tail5         = df.tail(5)
    recent_golden = tail5["golden_cross"].sum() > 0
    recent_death  = tail5["death_cross"].sum() > 0
    gap_pct       = abs(ms - ml) / max(ml, 1e-9) * 100
    if recent_golden:
        return 90.0, "Golden cross recently (bullish)"
    elif recent_death:
        return 10.0, "Death cross recently (bearish)"
    elif ms > ml:
        score = float(np.clip(60 + gap_pct * 2, 60, 80))
        return score, f"Fast MA above slow MA by {gap_pct:.1f}% (uptrend)"
    else:
        score = float(np.clip(40 - gap_pct * 2, 20, 40))
        return score, f"Fast MA below slow MA by {gap_pct:.1f}% (downtrend)"


def _volume_score(vol_ratio: float, price_change: float) -> tuple:
    if np.isnan(vol_ratio) or np.isnan(price_change):
        return 50.0, "Volume: N/A"
    if price_change > 0 and vol_ratio > 1.5:
        return float(np.interp(vol_ratio, [1.5, 3.0], [80, 100])), \
               f"High-volume up-move (×{vol_ratio:.1f}) — conviction buying"
    elif price_change > 0 and vol_ratio > 1.0:
        return 65.0, f"Above-avg volume with gain (×{vol_ratio:.1f})"
    elif vol_ratio < 0.8:
        return 50.0, f"Low volume (×{vol_ratio:.1f}) — weak signal"
    elif price_change < 0 and vol_ratio > 1.5:
        return float(np.interp(vol_ratio, [1.5, 3.0], [20, 0])), \
               f"High-volume down-move (×{vol_ratio:.1f}) — selling pressure"
    else:
        return 35.0, f"Volume ×{vol_ratio:.1f} with loss"


def _volume_score_scalar(vol_ratio: float, price_change: float) -> float:
    """Pure scalar version for O(1) per-row backtest scoring."""
    score, _ = _volume_score(vol_ratio, price_change)
    return score


def _stoch_score(stoch_k: float, stoch_d: float) -> tuple:
    if np.isnan(stoch_k) or np.isnan(stoch_d):
        return 50.0, "Stoch: N/A"
    score = float(np.interp(stoch_k,
                            [0, 20, 40, 60, 80, 100],
                            [90, 80, 55, 45, 20, 10]))
    bull = stoch_k > stoch_d
    if stoch_k < 20:
        label = f"Stoch={stoch_k:.0f} (oversold{' + bullish cross' if bull else ''})"
    elif stoch_k > 80:
        label = f"Stoch={stoch_k:.0f} (overbought{' + bearish cross' if not bull else ''})"
    else:
        label = f"Stoch={stoch_k:.0f} ({'bullish' if bull else 'bearish'} cross)"
    return score, label


# ── O(1) row scorer for backtesting ──────────────────────────────────────────

def score_row(row: pd.Series, weights: dict) -> float:
    """
    Score a single precomputed row in O(1).
    Requires add_backtest_columns() to have been called on the DataFrame first.
    """
    rsi = float(row.get("rsi", 50))
    rsi_s = float(np.interp(rsi, [0, 30, 45, 55, 70, 100], [95, 85, 60, 40, 15, 5])) \
            if not np.isnan(rsi) else 50.0

    macd_s = (40 * bool(row.get("macd_above_signal", False)) +
              30 * bool(row.get("hist_rising",        False)) +
              30 * bool(row.get("macd_positive",      False)))

    bb_pos = float(row.get("bb_position", 0.5))
    bb_s   = float(np.clip((1 - bb_pos) * 100, 0, 100)) if not np.isnan(bb_pos) else 50.0

    if bool(row.get("recent_golden", False)):
        ma_s = 90.0
    elif bool(row.get("recent_death", False)):
        ma_s = 10.0
    elif bool(row.get("ma_above", False)):
        ma_s = float(np.clip(60 + float(row.get("ma_gap_pct", 0)) * 2, 60, 80))
    else:
        ma_s = float(np.clip(40 - float(row.get("ma_gap_pct", 0)) * 2, 20, 40))

    vol_s = _volume_score_scalar(
        float(row.get("vol_ratio",        float("nan"))),
        float(row.get("price_change_pct", float("nan"))),
    )

    sub = {"rsi": rsi_s, "macd": macd_s, "bb": bb_s, "ma": ma_s, "volume": vol_s}
    return sum(sub[k] * weights.get(k, 0) for k in sub if k in weights)


# ── ATR-based trade levels (shared by both modes) ─────────────────────────────

def _trade_levels(close: float, atr: float,
                  stop_mult: float = ATR_MULTIPLIER_STOP,
                  target_mult: float = ATR_MULTIPLIER_TARGET) -> dict:
    if np.isnan(atr) or atr <= 0:
        nan = float("nan")
        return {"entry": close, "stop": nan, "target": nan,
                "risk_pct": nan, "reward_pct": nan, "rr_ratio": nan}
    stop   = close - stop_mult   * atr
    target = close + target_mult * atr
    risk   = (close - stop)   / close * 100
    reward = (target - close) / close * 100
    rr     = reward / risk if risk > 0 else float("nan")
    return {
        "entry":      round(close,  2),
        "stop":       round(stop,   2),
        "target":     round(target, 2),
        "risk_pct":   round(risk,   2),
        "reward_pct": round(reward, 2),
        "rr_ratio":   round(rr,     2),
    }


# ── Positional scorer (daily candles) ─────────────────────────────────────────

def score_stock(df: pd.DataFrame, weights: dict = None,
                use_regime: bool = False,
                fund_info: dict = None) -> dict:
    """
    Score for general/positional mode.
    Optional: regime-aware weight adjustment, fundamental blend.
    Now includes entry/stop/target based on ATR.
    """
    if weights is None:
        weights = SCORE_WEIGHTS

    # Regime-aware weight adjustment
    if use_regime and "regime" in df.columns:
        from regime import get_regime_weights, get_current_regime
        current_regime = get_current_regime(df)
        weights = get_regime_weights(weights, current_regime)
    else:
        current_regime = "neutral"

    last = df.iloc[-1]

    rsi_s,  rsi_lbl  = _rsi_score(last.get("rsi", np.nan))
    macd_s, macd_lbl = _macd_score(last.get("macd", np.nan),
                                    last.get("macd_signal", np.nan),
                                    df["macd_hist"])
    bb_s,   bb_lbl   = _bb_score(last.get("Close", np.nan),
                                  last.get("bb_lower", np.nan),
                                  last.get("bb_upper", np.nan))
    ma_s,   ma_lbl   = _ma_score(df)
    vol_s,  vol_lbl  = _volume_score(last.get("vol_ratio", np.nan),
                                     last.get("price_change_pct", np.nan))

    sub_scores = {"rsi": rsi_s, "macd": macd_s, "bb": bb_s,
                  "ma": ma_s, "volume": vol_s}
    labels     = {"rsi": rsi_lbl, "macd": macd_lbl, "bb": bb_lbl,
                  "ma": ma_lbl, "volume": vol_lbl}

    # Optional fundamental blend (20% weight, technical scaled to 80%)
    fund_score, fund_lbl = None, None
    if fund_info:
        from fundamentals import score_fundamentals
        fund_score, fund_lbl = score_fundamentals(fund_info)
        weights = {k: v * 0.80 for k, v in weights.items()}

    composite = sum(sub_scores[k] * weights.get(k, 0) for k in sub_scores)
    if fund_score is not None:
        composite += fund_score * 0.20

    ranked    = sorted(sub_scores.items(), key=lambda x: abs(x[1] - 50), reverse=True)
    reasoning = [labels[k] for k, _ in ranked[:2]]
    if fund_lbl and fund_score is not None and abs(fund_score - 50) > 10:
        reasoning = [reasoning[0], fund_lbl] if reasoning else [fund_lbl]

    close = last.get("Close", float("nan"))
    atr   = last.get("atr",   float("nan"))
    levels = _trade_levels(float(close), float(atr))

    return {
        "score":       round(composite, 1),
        "rsi":         round(last.get("rsi", float("nan")), 1),
        "macd_bullish": sub_scores["macd"] >= 50,
        "bb_position": round(
            (last.get("Close", 0) - last.get("bb_lower", 0)) /
            max(last.get("bb_upper", 1) - last.get("bb_lower", 0), 1e-9), 2),
        "ma_cross":    "Golden" if last.get("ma_short", 0) > last.get("ma_long", 0) else "Death",
        "vol_ratio":   round(last.get("vol_ratio", float("nan")), 2),
        "regime":      current_regime,
        "fund_score":  fund_score,
        "sub_scores":  sub_scores,
        "reasoning":   reasoning,
        "close":       round(float(close), 2),
        **levels,
    }


# ── Swing scorer (hourly candles) ─────────────────────────────────────────────

def score_stock_swing(df: pd.DataFrame) -> dict:
    """Score for intraday/swing mode. Includes entry/stop/target."""
    last    = df.iloc[-1]
    weights = SWING_WEIGHTS

    rsi_s,   rsi_lbl   = _rsi_score(last.get("rsi", np.nan))
    macd_s,  macd_lbl  = _macd_score(last.get("macd", np.nan),
                                      last.get("macd_signal", np.nan),
                                      df["macd_hist"])
    bb_s,    bb_lbl    = _bb_score(last.get("Close", np.nan),
                                   last.get("bb_lower", np.nan),
                                   last.get("bb_upper", np.nan))
    ma_s,    ma_lbl    = _ma_score(df)
    vol_s,   vol_lbl   = _volume_score(last.get("vol_ratio", np.nan),
                                       last.get("price_change_pct", np.nan))
    stoch_s, stoch_lbl = _stoch_score(last.get("stoch_k", np.nan),
                                      last.get("stoch_d", np.nan))

    sub_scores = {"rsi": rsi_s, "macd": macd_s, "bb": bb_s,
                  "ma": ma_s, "volume": vol_s, "stoch": stoch_s}
    labels     = {"rsi": rsi_lbl, "macd": macd_lbl, "bb": bb_lbl,
                  "ma": ma_lbl, "volume": vol_lbl, "stoch": stoch_lbl}

    composite = sum(sub_scores[k] * weights.get(k, 0) for k in sub_scores)
    ranked    = sorted(sub_scores.items(), key=lambda x: abs(x[1] - 50), reverse=True)
    reasoning = [labels[k] for k, _ in ranked[:2]]

    close = float(last.get("Close", float("nan")))
    atr   = float(last.get("atr",   float("nan")))
    levels = _trade_levels(close, atr)

    vwap       = last.get("vwap", float("nan"))
    above_vwap = (close > vwap) if not np.isnan(vwap) else None

    return {
        "score":        round(composite, 1),
        "rsi":          round(last.get("rsi",     float("nan")), 1),
        "stoch_k":      round(last.get("stoch_k", float("nan")), 1),
        "macd_bullish": sub_scores["macd"] >= 50,
        "ma_cross":     "Golden" if last.get("ma_short", 0) > last.get("ma_long", 0) else "Death",
        "vol_ratio":    round(last.get("vol_ratio", float("nan")), 2),
        "above_vwap":   above_vwap,
        "sub_scores":   sub_scores,
        "reasoning":    reasoning,
        **levels,
    }


# ── Ranking ───────────────────────────────────────────────────────────────────

def rank_stocks(scored: dict) -> list:
    from scipy.stats import percentileofscore
    rows = [{"ticker": t, **v} for t, v in scored.items()]
    all_scores = [r["score"] for r in rows]
    for r in rows:
        r["percentile"] = round(percentileofscore(all_scores, r["score"]), 0)
    return sorted(rows, key=lambda x: x["score"], reverse=True)
