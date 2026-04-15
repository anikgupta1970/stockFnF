NIFTY_50_TICKERS = [
    "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS",
    "AXISBANK.NS", "BAJAJ-AUTO.NS", "BAJAJFINSV.NS", "BAJFINANCE.NS",
    "BHARTIARTL.NS", "BPCL.NS", "BRITANNIA.NS", "CIPLA.NS",
    "COALINDIA.NS", "DIVISLAB.NS", "DRREDDY.NS", "EICHERMOT.NS",
    "GRASIM.NS", "HCLTECH.NS", "HDFCBANK.NS", "HDFCLIFE.NS",
    "HEROMOTOCO.NS", "HINDALCO.NS", "HINDUNILVR.NS", "ICICIBANK.NS",
    "INDUSINDBK.NS", "INFY.NS", "ITC.NS", "JSWSTEEL.NS",
    "KOTAKBANK.NS", "LT.NS", "M&M.NS", "MARUTI.NS",
    "NESTLEIND.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS",
    "RELIANCE.NS", "SBILIFE.NS", "SBIN.NS", "SHRIRAMFIN.NS",
    "SUNPHARMA.NS", "TATACONSUM.NS", "TATAMOTORS.NS", "TATASTEEL.NS",
    "TCS.NS", "TECHM.NS", "TITAN.NS", "ULTRACEMCO.NS",
    "UPL.NS", "WIPRO.NS",
]

SECTOR_MAP = {
    "ADANIENT.NS":   "Energy",
    "ADANIPORTS.NS": "Infrastructure",
    "APOLLOHOSP.NS": "Healthcare",
    "ASIANPAINT.NS": "Consumer",
    "AXISBANK.NS":   "Banking",
    "BAJAJ-AUTO.NS": "Auto",
    "BAJAJFINSV.NS": "Financial Services",
    "BAJFINANCE.NS": "Financial Services",
    "BHARTIARTL.NS": "Telecom",
    "BPCL.NS":       "Energy",
    "BRITANNIA.NS":  "FMCG",
    "CIPLA.NS":      "Pharma",
    "COALINDIA.NS":  "Energy",
    "DIVISLAB.NS":   "Pharma",
    "DRREDDY.NS":    "Pharma",
    "EICHERMOT.NS":  "Auto",
    "GRASIM.NS":     "Diversified",
    "HCLTECH.NS":    "IT",
    "HDFCBANK.NS":   "Banking",
    "HDFCLIFE.NS":   "Insurance",
    "HEROMOTOCO.NS": "Auto",
    "HINDALCO.NS":   "Metals",
    "HINDUNILVR.NS": "FMCG",
    "ICICIBANK.NS":  "Banking",
    "INDUSINDBK.NS": "Banking",
    "INFY.NS":       "IT",
    "ITC.NS":        "FMCG",
    "JSWSTEEL.NS":   "Metals",
    "KOTAKBANK.NS":  "Banking",
    "LT.NS":         "Infrastructure",
    "M&M.NS":        "Auto",
    "MARUTI.NS":     "Auto",
    "NESTLEIND.NS":  "FMCG",
    "NTPC.NS":       "Energy",
    "ONGC.NS":       "Energy",
    "POWERGRID.NS":  "Energy",
    "RELIANCE.NS":   "Diversified",
    "SBILIFE.NS":    "Insurance",
    "SBIN.NS":       "Banking",
    "SHRIRAMFIN.NS": "Financial Services",
    "SUNPHARMA.NS":  "Pharma",
    "TATACONSUM.NS": "FMCG",
    "TATAMOTORS.NS": "Auto",
    "TATASTEEL.NS":  "Metals",
    "TCS.NS":        "IT",
    "TECHM.NS":      "IT",
    "TITAN.NS":      "Consumer",
    "ULTRACEMCO.NS": "Cement",
    "UPL.NS":        "Chemicals",
    "WIPRO.NS":      "IT",
}

# ── Positional (multi-day) mode ──────────────────────────────────────────────
DEFAULT_PERIOD   = "6mo"
DEFAULT_INTERVAL = "1d"
MIN_ROWS = 60

SCORE_WEIGHTS = {
    "rsi":    0.25,
    "macd":   0.25,
    "bb":     0.20,
    "ma":     0.20,
    "volume": 0.10,
}

# ── Swing / short-term mode (buy & sell within 1-5 days) ─────────────────────
SWING_PERIOD   = "1mo"   # 1 month of hourly candles (~160 bars)
SWING_INTERVAL = "1h"
SWING_MIN_ROWS = 50

SWING_WEIGHTS = {
    "rsi":       0.20,
    "macd":      0.20,
    "bb":        0.15,
    "ma":        0.15,
    "volume":    0.25,   # volume is king for short-term
    "stoch":     0.05,
}

ATR_MULTIPLIER_STOP   = 1.5   # stop loss  = entry - 1.5 × ATR
ATR_MULTIPLIER_TARGET = 2.5   # target     = entry + 2.5 × ATR
