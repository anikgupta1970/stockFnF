"""
Market regime detection using ADX and Bollinger Band width.
Trending markets favour MACD/MA signals.
Ranging markets favour RSI/BB mean-reversion signals.
"""

import numpy as np
import pandas as pd
import ta


def add_regime_columns(df: pd.DataFrame, adx_window: int = 14) -> pd.DataFrame:
    """
    Adds: adx, bb_width_pct, regime ('trending' | 'ranging' | 'neutral')
    Requires bb_upper, bb_lower, bb_mid already computed.
    """
    df = df.copy()
    adx_ind = ta.trend.ADXIndicator(
        high=df["High"], low=df["Low"], close=df["Close"], window=adx_window
    )
    df["adx"] = adx_ind.adx()

    bb_mid = df.get("bb_mid", df["Close"])
    df["bb_width_pct"] = (
        (df.get("bb_upper", df["Close"]) - df.get("bb_lower", df["Close"]))
        / bb_mid.replace(0, float("nan")) * 100
    )

    df["regime"] = np.where(
        df["adx"] > 25, "trending",
        np.where(df["adx"] < 20, "ranging", "neutral")
    )
    return df


def get_current_regime(df: pd.DataFrame) -> str:
    """Return the regime of the most recent row."""
    if "regime" not in df.columns:
        return "neutral"
    return str(df["regime"].iloc[-1])


# Weight multipliers per regime — applied then renormalised to sum=1
_MULTIPLIERS = {
    "trending": {
        # Trend-following signals get boosted
        "macd": 1.40, "ma": 1.30,
        "rsi":  0.70, "bb": 0.70,
        "volume": 1.0, "stoch": 0.80,
    },
    "ranging": {
        # Mean-reversion signals get boosted
        "rsi":  1.40, "bb": 1.30,
        "macd": 0.70, "ma": 0.70,
        "volume": 1.0, "stoch": 1.20,
    },
    "neutral": {},  # no adjustment
}


def get_regime_weights(base_weights: dict, regime: str) -> dict:
    """
    Adjust base_weights according to the detected regime.
    Result is renormalised so weights still sum to 1.0.
    """
    multipliers = _MULTIPLIERS.get(regime, {})
    if not multipliers:
        return base_weights.copy()

    raw = {k: base_weights[k] * multipliers.get(k, 1.0) for k in base_weights}
    total = sum(raw.values())
    return {k: round(v / total, 4) for k, v in raw.items()}


def regime_label(regime: str) -> str:
    return {
        "trending": "[green]Trending[/green]",
        "ranging":  "[yellow]Ranging[/yellow]",
        "neutral":  "[dim]Neutral[/dim]",
    }.get(regime, "[dim]Unknown[/dim]")
