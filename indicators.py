import pandas as pd
import numpy as np
import ta


# ── Standard daily indicators ─────────────────────────────────────────────────

def add_rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = ta.momentum.RSIIndicator(close=df["Close"], window=window).rsi()
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
             signal: int = 9) -> pd.DataFrame:
    df = df.copy()
    macd = ta.trend.MACD(close=df["Close"], window_fast=fast,
                         window_slow=slow, window_sign=signal)
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"]   = macd.macd_diff()
    return df


def add_bollinger_bands(df: pd.DataFrame, window: int = 20,
                        std: float = 2.0) -> pd.DataFrame:
    df = df.copy()
    bb = ta.volatility.BollingerBands(close=df["Close"], window=window,
                                      window_dev=std)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"]   = bb.bollinger_mavg()
    return df


def add_moving_averages(df: pd.DataFrame, short: int = 20,
                        long: int = 50) -> pd.DataFrame:
    df = df.copy()
    df["ma_short"]  = df["Close"].rolling(short).mean()
    df["ma_long"]   = df["Close"].rolling(long).mean()
    df["ma_cross"]  = (df["ma_short"] > df["ma_long"]).astype(int)
    prev            = df["ma_cross"].shift(1)
    df["golden_cross"] = ((df["ma_cross"] == 1) & (prev == 0)).astype(int)
    df["death_cross"]  = ((df["ma_cross"] == 0) & (prev == 1)).astype(int)
    return df


def add_volume_trend(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["vol_avg"]          = df["Volume"].rolling(window).mean()
    df["vol_ratio"]        = df["Volume"] / df["vol_avg"]
    df["price_change_pct"] = df["Close"].pct_change()
    return df


def add_atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    df = df.copy()
    atr = ta.volatility.AverageTrueRange(
        high=df["High"], low=df["Low"], close=df["Close"], window=window
    )
    df["atr"] = atr.average_true_range()
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Standard daily indicators for positional analysis."""
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger_bands(df)
    df = add_moving_averages(df)
    df = add_volume_trend(df)
    df = add_atr(df)          # needed for stop/target in general mode too
    return df


# ── Backtest helper columns (O(n) vectorised) ─────────────────────────────────

def add_backtest_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Precompute all derived boolean signals so each row can be scored in O(1)
    without looking at neighbouring rows. Called once before the backtest loop.
    """
    df = df.copy()
    df["hist_rising"]       = df["macd_hist"] > df["macd_hist"].shift(1)
    df["macd_positive"]     = df["macd"] > 0
    df["macd_above_signal"] = df["macd"] > df["macd_signal"]
    df["ma_above"]          = df["ma_short"] > df["ma_long"]
    df["ma_gap_pct"]        = (
        (df["ma_short"] - df["ma_long"]).abs()
        / df["ma_long"].replace(0, float("nan")) * 100
    )
    # Rolling look-back windows — still O(n) total, just vectorised pandas ops
    df["recent_golden"]  = df["golden_cross"].rolling(5, min_periods=1).max().astype(bool)
    df["recent_death"]   = df["death_cross"].rolling(5,  min_periods=1).max().astype(bool)
    df["bb_position"]    = (
        (df["Close"] - df["bb_lower"])
        / (df["bb_upper"] - df["bb_lower"]).replace(0, float("nan"))
    )
    return df


# ── Swing / intraday indicators ───────────────────────────────────────────────

def add_stochastic(df: pd.DataFrame, window: int = 14,
                   smooth: int = 3) -> pd.DataFrame:
    df = df.copy()
    stoch = ta.momentum.StochasticOscillator(
        high=df["High"], low=df["Low"], close=df["Close"],
        window=window, smooth_window=smooth
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    df["vwap"] = (typical * df["Volume"]).cumsum() / df["Volume"].cumsum()
    return df


def add_all_indicators_swing(df: pd.DataFrame) -> pd.DataFrame:
    """Faster parameters for 1h candles: RSI(9), MACD(5,13,4), BB(10), MA(9,21)."""
    df = add_rsi(df, window=9)
    df = add_macd(df, fast=5, slow=13, signal=4)
    df = add_bollinger_bands(df, window=10, std=2.0)
    df = add_moving_averages(df, short=9, long=21)
    df = add_volume_trend(df, window=20)
    df = add_atr(df, window=14)
    df = add_stochastic(df, window=14, smooth=3)
    df = add_vwap(df)
    return df


# ── Regime columns ────────────────────────────────────────────────────────────

def add_regime_columns(df: pd.DataFrame, adx_window: int = 14) -> pd.DataFrame:
    """Adds ADX, BB width %, and regime label column."""
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
    import numpy as np
    df["regime"] = np.where(
        df["adx"] > 25, "trending",
        np.where(df["adx"] < 20, "ranging", "neutral")
    )
    return df
