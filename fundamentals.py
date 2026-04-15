"""
Fundamental data fetching and scoring.
Uses yfinance Ticker.info (free). Cached as JSON for 24h.
"""

import os
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

FUND_CACHE_DIR = os.path.expanduser("~/.stocks_cache/fundamentals")
FUND_CACHE_TTL_HOURS = 24


def _cache_path(ticker: str) -> str:
    return os.path.join(FUND_CACHE_DIR,
                        ticker.replace(".", "_").replace("/", "_") + ".json")


def _cache_valid(path: str) -> bool:
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) / 3600 < FUND_CACHE_TTL_HOURS


def fetch_fundamentals(ticker: str, use_cache: bool = True) -> dict:
    path = _cache_path(ticker)
    if use_cache and _cache_valid(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass

    time.sleep(random.uniform(0.1, 0.4))
    try:
        info = yf.Ticker(ticker).info
        data = {
            "pe_ratio":       info.get("trailingPE"),
            "pb_ratio":       info.get("priceToBook"),
            "debt_equity":    info.get("debtToEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margin":  info.get("profitMargins"),
            "roe":            info.get("returnOnEquity"),
            "current_ratio":  info.get("currentRatio"),
            "market_cap":     info.get("marketCap"),
            "sector":         info.get("sector"),
            "industry":       info.get("industry"),
        }
        os.makedirs(FUND_CACHE_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        return data
    except Exception:
        return {}


def score_fundamentals(info: dict) -> tuple:
    """
    Score fundamentals 0-100 across 5 axes, 20 pts each:
      P/E   — lower is cheaper
      P/B   — below book value is attractive
      Revenue growth — positive and strong
      Debt/Equity   — lower is safer
      Profit margin  — higher is better
    Returns (score, label).
    """
    if not info:
        return 50.0, "Fundamentals: N/A"

    score = 0.0
    parts = []

    # P/E ratio
    pe = info.get("pe_ratio")
    if pe and pe > 0:
        if pe < 15:   score += 20; parts.append(f"P/E {pe:.1f} (cheap)")
        elif pe < 25: score += 15; parts.append(f"P/E {pe:.1f} (fair)")
        elif pe < 40: score += 8
        else:         score += 0;  parts.append(f"P/E {pe:.1f} (expensive)")
    else:
        score += 10  # neutral if missing

    # P/B ratio
    pb = info.get("pb_ratio")
    if pb and pb > 0:
        if pb < 1:    score += 20; parts.append(f"P/B {pb:.1f} (below book)")
        elif pb < 3:  score += 15
        elif pb < 6:  score += 8
        else:         score += 0;  parts.append(f"P/B {pb:.1f} (pricey)")
    else:
        score += 10

    # Revenue growth (YoY)
    rg = info.get("revenue_growth")
    if rg is not None:
        if rg > 0.20:   score += 20; parts.append(f"Revenue +{rg*100:.0f}% YoY")
        elif rg > 0.10: score += 15
        elif rg > 0:    score += 8
        else:           score += 0;  parts.append(f"Revenue {rg*100:.0f}% (declining)")
    else:
        score += 10

    # Debt/Equity (yfinance returns as %, e.g. 45.3 means 45.3%)
    de = info.get("debt_equity")
    if de is not None:
        if de < 30:    score += 20; parts.append(f"Low debt D/E {de:.0f}%")
        elif de < 80:  score += 15
        elif de < 150: score += 8
        else:          score += 0;  parts.append(f"High debt D/E {de:.0f}%")
    else:
        score += 10

    # Profit margin
    margin = info.get("profit_margin")
    if margin is not None:
        if margin > 0.20:   score += 20; parts.append(f"Margin {margin*100:.0f}%")
        elif margin > 0.10: score += 15
        elif margin > 0.05: score += 8
        elif margin > 0:    score += 3
        else:               score += 0;  parts.append("Loss-making")
    else:
        score += 10

    score = max(0.0, min(100.0, score))
    label = "Fundamentals: " + (", ".join(parts[:2]) if parts else "data OK")
    return round(score, 1), label


def fetch_all_fundamentals(tickers: list, max_workers: int = 4,
                           use_cache: bool = True) -> dict:
    results = {}

    def _fetch(ticker):
        return ticker, fetch_fundamentals(ticker, use_cache)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, data = future.result()
            results[ticker] = data
    return results
