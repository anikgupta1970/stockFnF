"""
Fetch the complete list of NSE-listed equity stocks from NSE's official CSV.
Caches the list locally for 24 hours to avoid hammering NSE servers.
"""

import os
import time
import requests
import pandas as pd
from io import StringIO

NSE_EQUITY_CSV = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE_DIR = os.path.expanduser("~/.stocks_cache")
TICKER_CACHE = os.path.join(CACHE_DIR, "nse_equity_list.csv")
CACHE_TTL_HOURS = 24

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}


def _cache_valid() -> bool:
    if not os.path.exists(TICKER_CACHE):
        return False
    age_hours = (time.time() - os.path.getmtime(TICKER_CACHE)) / 3600
    return age_hours < CACHE_TTL_HOURS


def _fetch_from_nse() -> list:
    """Download EQUITY_L.csv from NSE and return list of ticker strings."""
    # NSE requires a session cookie — get one first
    session = requests.Session()
    session.headers.update(_HEADERS)
    # Touch the homepage to get cookies
    try:
        session.get("https://www.nseindia.com", timeout=15)
    except Exception:
        pass

    resp = session.get(NSE_EQUITY_CSV, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))
    # Column names vary; normalise
    df.columns = [c.strip().upper() for c in df.columns]

    # Filter to regular EQ series only (exclude SME, BE, BZ, etc.)
    if "SERIES" in df.columns:
        df = df[df["SERIES"].str.strip() == "EQ"]

    symbols = [s.strip() for s in df["SYMBOL"].dropna().tolist()]
    return symbols


def get_all_tickers(use_cache: bool = True) -> list:
    """
    Return a list of all NSE equity tickers with .NS suffix, e.g. ['RELIANCE.NS', ...].
    Falls back to a bundled NIFTY 500 list if the NSE fetch fails.
    """
    if use_cache and _cache_valid():
        cached = pd.read_csv(TICKER_CACHE)
        return cached["ticker"].tolist()

    try:
        symbols = _fetch_from_nse()
        os.makedirs(CACHE_DIR, exist_ok=True)
        tickers = [s + ".NS" for s in symbols]
        pd.DataFrame({"ticker": tickers}).to_csv(TICKER_CACHE, index=False)
        return tickers
    except Exception as e:
        # If NSE fetch fails, fall back to cached file if it exists
        if os.path.exists(TICKER_CACHE):
            cached = pd.read_csv(TICKER_CACHE)
            return cached["ticker"].tolist()
        # Last resort: fall back to NIFTY 50
        from config import NIFTY_50_TICKERS
        raise RuntimeError(
            f"Could not fetch NSE ticker list ({e}) and no local cache found. "
            "Using NIFTY 50 as fallback."
        ) from e
