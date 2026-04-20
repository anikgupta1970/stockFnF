"""
Data fetching with:
  1. nsepython (NSE direct API) as primary source for daily data — free, no scraping
  2. yfinance as fallback with exponential-backoff retry
  3. Disk cache (pickle) with configurable TTL
"""

import os
import time
import pickle
import random
import datetime
import requests
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import MIN_ROWS

_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}


def _nse_session() -> requests.Session:
    """Return a requests Session pre-seeded with NSE cookies."""
    s = requests.Session()
    s.get("https://www.nseindia.com", headers=_NSE_HEADERS, timeout=10)
    return s

CACHE_DIR                   = os.path.expanduser("~/.stocks_cache/data")
DAILY_CACHE_TTL_HOURS       = 24   # daily candles — refresh once per day
INTRADAY_CACHE_TTL_HOURS    = 4    # intraday candles — refresh every 4 hours
MAX_RETRIES                 = 3

# Period string → approximate calendar days
_PERIOD_DAYS = {
    "1mo": 35,  "3mo": 95,  "6mo": 185,
    "1y":  370, "2y":  740, "5y": 1830,
}


def _period_to_days(period: str) -> int:
    return _PERIOD_DAYS.get(period, 185)


def _cache_path(ticker: str, period: str, interval: str) -> str:
    safe = ticker.replace(".", "_").replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe}_{period}_{interval}.pkl")


def _load_cache(ticker: str, period: str, interval: str):
    path = _cache_path(ticker, period, interval)
    if not os.path.exists(path):
        return None
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    ttl = DAILY_CACHE_TTL_HOURS if interval == "1d" else INTRADAY_CACHE_TTL_HOURS
    if age_hours > ttl:
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _save_cache(ticker: str, period: str, interval: str, df: pd.DataFrame):
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(_cache_path(ticker, period, interval), "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise column names and drop non-OHLCV columns."""
    df = df.copy()
    df.columns = [c.title() for c in df.columns]
    keep = [c for c in df.columns if c in {"Open", "High", "Low", "Close", "Volume"}]
    df = df[keep]
    df = df.dropna(subset=["Close", "Volume"])
    return df.ffill()


def _fetch_nsepython(ticker: str, period_days: int) -> pd.DataFrame:
    """
    Fetch daily OHLCV from NSE directly via nsepython (free, no API key).
    Only works for daily intervals — falls back to yfinance for hourly.
    """
    try:
        import nsepython  # optional dependency
        symbol   = ticker.replace(".NS", "").replace(".BO", "")
        end_dt   = datetime.date.today()
        start_dt = end_dt - datetime.timedelta(days=period_days)
        df = nsepython.equity_history(
            symbol, "EQ",
            start_dt.strftime("%d-%m-%Y"),
            end_dt.strftime("%d-%m-%Y"),
        )
        if df is None or df.empty:
            return pd.DataFrame()
        rename = {
            "CH_OPENING_PRICE":  "Open",
            "CH_TRADE_HIGH_PRICE": "High",
            "CH_TRADE_LOW_PRICE":  "Low",
            "CH_CLOSING_PRICE":  "Close",
            "CH_TOT_TRADED_QTY": "Volume",
        }
        df = df.rename(columns=rename)
        available = [c for c in rename.values() if c in df.columns]
        if len(available) < 4:
            return pd.DataFrame()
        df = df[available].copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        return df.sort_index().ffill()
    except Exception:
        return pd.DataFrame()


def _fetch_yfinance(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """yfinance with exponential-backoff retry."""
    for attempt in range(MAX_RETRIES):
        delay = random.uniform(0.1, 0.4) * (2 ** attempt)
        time.sleep(delay)
        try:
            t  = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval, auto_adjust=True)
            if df is not None and not df.empty:
                return _normalise(df)
        except Exception:
            if attempt == MAX_RETRIES - 1:
                return pd.DataFrame()
    return pd.DataFrame()


def fetch_ticker_data(ticker: str, period: str, interval: str,
                      use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch OHLCV for one ticker.
    Priority: cache → nsepython (daily only) → yfinance (retry).
    """
    if use_cache:
        cached = _load_cache(ticker, period, interval)
        if cached is not None:
            return cached

    df = pd.DataFrame()

    # nsepython for daily data only
    if interval == "1d":
        df = _fetch_nsepython(ticker, _period_to_days(period))

    # Fallback to yfinance
    if df.empty:
        df = _fetch_yfinance(ticker, period, interval)

    if df.empty or len(df) < MIN_ROWS:
        return pd.DataFrame()

    if use_cache:
        _save_cache(ticker, period, interval, df)
    return df


def fetch_all(tickers: list, period: str, interval: str,
              max_workers: int = 10, use_cache: bool = True,
              progress_callback=None) -> tuple:
    """
    Fetch all tickers in parallel.
    Returns (results_dict, error_list).
    """
    results, errors = {}, []

    def _fetch(ticker):
        return ticker, fetch_ticker_data(ticker, period, interval, use_cache)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, df = future.result()
            if df.empty:
                errors.append(ticker)
            else:
                results[ticker] = df
            if progress_callback:
                progress_callback(ticker, not df.empty)

    return results, errors


def fetch_live_ltps(tickers: list, max_workers: int = 10) -> dict:
    """
    Fetch live LTP for each ticker from NSE equity quote API.
    Returns {ticker: ltp_float} for tickers where fetch succeeded.
    Tickers should be in .NS format (e.g. 'RELIANCE.NS'); .NS/.BO suffix is stripped.
    """
    session = _nse_session()

    def _ltp(ticker):
        symbol = ticker.replace(".NS", "").replace(".BO", "")
        try:
            resp = session.get(
                f"https://www.nseindia.com/api/quote-equity?symbol={symbol}",
                headers=_NSE_HEADERS, timeout=8,
            )
            price = resp.json()["priceInfo"]["lastPrice"]
            return ticker, float(price)
        except Exception:
            return ticker, None

    ltps = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for ticker, price in executor.map(_ltp, tickers):
            if price is not None:
                ltps[ticker] = price
    return ltps


def fetch_todays_candles(tickers: list, max_workers: int = 10) -> dict:
    """
    Fetch today's live OHLCV candle for each ticker from NSE.
    Returns {ticker: {"Open": x, "High": x, "Low": x, "Close": x, "Volume": x}}.
    Used to append a live candle to historical daily data so indicators reflect
    today's intraday price action, not just yesterday's close.
    """
    session = _nse_session()

    def _candle(ticker):
        symbol = ticker.replace(".NS", "").replace(".BO", "")
        try:
            # First call: OHLC + last price
            r1 = session.get(
                f"https://www.nseindia.com/api/quote-equity?symbol={symbol}",
                headers=_NSE_HEADERS, timeout=8,
            ).json()
            pi = r1["priceInfo"]
            ild = pi["intraDayHighLow"]
            open_  = float(pi["open"])
            high   = float(ild["max"])
            low    = float(ild["min"])
            close  = float(pi["lastPrice"])

            # Second call: volume
            r2 = session.get(
                f"https://www.nseindia.com/api/quote-equity?symbol={symbol}&section=trade_info",
                headers=_NSE_HEADERS, timeout=8,
            ).json()
            volume = int(r2["securityWiseDP"]["quantityTraded"])

            return ticker, {"Open": open_, "High": high, "Low": low,
                            "Close": close, "Volume": volume}
        except Exception:
            return ticker, None

    candles = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for ticker, candle in executor.map(_candle, tickers):
            if candle is not None:
                candles[ticker] = candle
    return candles


def append_todays_candle(df: pd.DataFrame, candle: dict) -> pd.DataFrame:
    """
    Append (or replace) today's live candle in a daily OHLCV DataFrame.
    Ensures indicators computed on this df reflect today's intraday move.
    """
    today = pd.Timestamp(datetime.date.today()).tz_localize(df.index.tz)
    row   = pd.DataFrame([candle], index=[today])
    # Drop any existing row for today (partial candle from yfinance) then append
    df = df[df.index.normalize() != today.normalize()]
    return pd.concat([df, row]).sort_index()
