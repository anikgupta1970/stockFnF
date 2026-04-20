#!/usr/bin/env python3
"""
NSE Stock Analyser

  python3 main.py general    — daily candles, regime + fundamentals + backtest
  python3 main.py intraday   — hourly candles, entry/stop/target for 1-5 day trades

Optional filters:
  --top N          show only top N stocks
  --sector NAME    filter by sector (e.g. Banking, IT, Pharma)
  --index nifty50  analyse NIFTY 50 only instead of all NSE stocks
  --no-cache       force fresh data download
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.progress import (Progress, SpinnerColumn, TextColumn,
                           BarColumn, MofNCompleteColumn, TimeElapsedColumn)

from config import (NIFTY_50_TICKERS, COMMODITY_TICKERS, SECTOR_MAP,
                    DEFAULT_PERIOD, DEFAULT_INTERVAL, SCORE_WEIGHTS,
                    SWING_PERIOD, SWING_INTERVAL, SWING_MIN_ROWS)
from data_fetcher import fetch_ticker_data, fetch_live_ltps, fetch_todays_candles, append_todays_candle
from scorer import _trade_levels
from indicators import (add_all_indicators, add_all_indicators_swing,
                        add_regime_columns)
from scorer import score_stock, score_stock_swing, rank_stocks
from display import (render_table, render_summary,
                     render_swing_table, render_swing_summary,
                     render_backtest, console)


def parse_args():
    p = argparse.ArgumentParser(
        description="NSE Stock Analyser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py general               # All NSE stocks, full analysis
  python3 main.py intraday              # All NSE stocks, swing picks
  python3 main.py general --top 20      # Top 20 general picks
  python3 main.py intraday --top 10     # Top 10 intraday picks
  python3 main.py general --sector IT   # General, IT sector only
  python3 main.py general --index nifty50  # NIFTY 50 only (faster)
        """,
    )
    p.add_argument("mode", choices=["general", "intraday"],
                   help="general = multi-day view | intraday = 1-5 day swing trades")
    p.add_argument("--top",    type=int, default=None,
                   help="Show only top N stocks (default: all)")
    p.add_argument("--sector", type=str, default=None,
                   help="Filter by sector, e.g. Banking, IT, Pharma, FMCG, Auto")
    p.add_argument("--index",  choices=["all", "nifty50", "commodities"], default="all",
                   help="Stock universe: all ~2100 NSE equities, nifty50, or commodities (Gold/Silver ETFs)")
    p.add_argument("--no-cache", action="store_true",
                   help="Ignore cached data, re-download everything")
    p.add_argument("--no-market-filter", action="store_true",
                   help="Skip NIFTY 50 uptrend check and analyse regardless of market direction")
    p.add_argument("--strict", action="store_true",
                   help="Confluence filter: only show stocks where MACD bullish + Golden cross + RSI<65 + Score>=70")
    p.add_argument("--interval", choices=["5m", "15m", "30m", "1h"],
                   default=None,
                   help="Candle interval for intraday mode (default: 1h). 5m/15m = fresher signals, more noise")
    return p.parse_args()


def _get_nifty_live_price(fallback: float) -> float:
    """
    Fetch the most current NIFTY price:
      1. NSE direct API — real-time during market hours
      2. yfinance fast_info.last_price — fallback (last traded price)
      3. last daily close — final fallback
    """
    try:
        from data_fetcher import _nse_session, _NSE_HEADERS
        session = _nse_session()
        resp = session.get(
            "https://www.nseindia.com/api/allIndices",
            headers=_NSE_HEADERS, timeout=8,
        )
        for item in resp.json().get("data", []):
            if item.get("index") == "NIFTY 50":
                return float(item["last"])
    except Exception:
        pass
    try:
        import yfinance as yf
        price = yf.Ticker("^NSEI").fast_info.last_price
        if price and price > 0:
            return float(price)
    except Exception:
        pass
    return fallback


def check_market_regime(use_cache: bool = True) -> bool:
    """
    Returns True if NIFTY 50 (^NSEI) is above its 50-day MA (uptrend).
    Prints a warning and returns False if in downtrend.
    """
    df = fetch_ticker_data("^NSEI", "6mo", "1d", use_cache)
    if df.empty or len(df) < 50:
        console.print("[yellow]Could not fetch NIFTY index data — skipping market filter.[/yellow]")
        return True
    ma50       = df["Close"].rolling(50).mean().iloc[-1]
    last_close = _get_nifty_live_price(df["Close"].iloc[-1])
    if last_close < ma50:
        console.print(
            f"\n[bold red]⚠  Market in downtrend[/bold red] — "
            f"NIFTY ₹{last_close:,.1f} is below its 50-day MA ₹{ma50:,.1f}. "
            f"[dim]Signals are unreliable in a falling market.[/dim]"
        )
        return False
    console.print(
        f"[dim]Market uptrend confirmed — NIFTY ₹{last_close:,.1f} above 50-day MA ₹{ma50:,.1f}.[/dim]"
    )
    return True


def apply_confluence_filter(ranked: list) -> tuple:
    """
    Split ranked list into (strong, weak).
    Strong requires ALL four conditions:
      1. MACD bullish
      2. Golden cross on MA
      3. RSI < 65  (not overbought)
      4. Score >= 70
    """
    strong, weak = [], []
    for r in ranked:
        passes = (
            r.get("macd_bullish", False) and
            r.get("ma_cross") == "Golden" and
            r.get("rsi", 100) < 65 and
            r.get("score", 0) >= 70
        )
        (strong if passes else weak).append(r)
    return strong, weak


def get_tickers(index: str) -> list:
    if index == "nifty50":
        return NIFTY_50_TICKERS.copy()
    if index == "commodities":
        console.print(f"[dim]Commodity ETFs: {len(COMMODITY_TICKERS)} Gold & Silver ETFs[/dim]")
        return COMMODITY_TICKERS.copy()
    try:
        from universe import get_all_tickers
        tickers = get_all_tickers()
        console.print(f"[dim]NSE universe: {len(tickers):,} equities[/dim]")
        return tickers
    except Exception as e:
        console.print(f"[yellow]Could not fetch full NSE list ({e}). Using NIFTY 50.[/yellow]")
        return NIFTY_50_TICKERS.copy()


def main():
    args      = parse_args()
    is_swing  = args.mode == "intraday"
    use_cache = not args.no_cache

    # ── Interval / period selection ───────────────────────────────────────────
    if is_swing and args.interval:
        interval = args.interval
        # Smaller intervals need shorter periods (Yahoo Finance limit: 60 days for <1h)
        period_map  = {"5m": "5d", "15m": "10d", "30m": "20d", "1h": "1mo"}
        min_row_map = {"5m": 50,   "15m": 40,    "30m": 30,    "1h": 50}
        period   = period_map[interval]
        min_rows = min_row_map[interval]
    else:
        period   = SWING_PERIOD   if is_swing else DEFAULT_PERIOD
        interval = SWING_INTERVAL if is_swing else DEFAULT_INTERVAL
        min_rows = SWING_MIN_ROWS if is_swing else 60

    tickers = get_tickers(args.index)

    # ── Market regime filter ──────────────────────────────────────────────────
    if not args.no_market_filter:
        in_uptrend = check_market_regime(use_cache)
        if not in_uptrend:
            ans = input("\nMarket is in downtrend. Continue anyway? [y/N] ").strip().lower()
            if ans != "y":
                console.print("[dim]Exiting. Use --no-market-filter to skip this check.[/dim]")
                sys.exit(0)
            console.print()

    mode_label = "[yellow]INTRADAY[/yellow]" if is_swing else "[blue]GENERAL[/blue]"
    console.print(
        f"\n[bold cyan]NSE Stock Analyser[/bold cyan] · {mode_label}"
        f" · {len(tickers):,} stocks · {period} · {interval}\n"
    )
    if len(tickers) > 200:
        console.print("[dim]Large universe — first run caches data, subsequent runs are fast.[/dim]\n")

    # ── Fetch ─────────────────────────────────────────────────────────────────
    raw_data, errors = {}, []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=console) as prog:
        tid = prog.add_task("Fetching market data...", total=len(tickers))

        def _fetch(t):
            return t, fetch_ticker_data(t, period, interval, use_cache)

        with ThreadPoolExecutor(max_workers=10) as ex:
            for fut in as_completed({ex.submit(_fetch, t): t for t in tickers}):
                ticker, df = fut.result()
                if df.empty or len(df) < min_rows:
                    errors.append(ticker)
                else:
                    raw_data[ticker] = df
                prog.advance(tid)

    if not raw_data:
        console.print("[red]No data fetched. Check internet connection.[/red]")
        sys.exit(1)

    console.print(f"[dim]Fetched {len(raw_data):,} · skipped {len(errors):,}[/dim]")

    # ── Today's live candles (general mode, market hours only) ───────────────
    console.print("[dim]Fetching today's live candles...[/dim]")
    todays_candles = fetch_todays_candles(list(raw_data.keys()))
    if not is_swing:
        for ticker, candle in todays_candles.items():
            if ticker in raw_data:
                raw_data[ticker] = append_todays_candle(raw_data[ticker], candle)

    # ── Indicators ────────────────────────────────────────────────────────────
    console.print("[dim]Computing indicators...[/dim]")
    enriched = {}
    for ticker, df in raw_data.items():
        try:
            df_ind = add_all_indicators_swing(df) if is_swing else add_all_indicators(df)
            if not is_swing:
                df_ind = add_regime_columns(df_ind)   # always on in general mode
            enriched[ticker] = df_ind
        except Exception:
            errors.append(ticker)

    # ── Fundamentals (general mode only) ─────────────────────────────────────
    fund_data = {}
    if not is_swing:
        console.print(f"[dim]Fetching fundamentals (P/E, debt, growth) for {len(enriched):,} stocks...[/dim]")
        from fundamentals import fetch_all_fundamentals
        fund_data = fetch_all_fundamentals(list(enriched.keys()), use_cache=use_cache)

    # ── Score ─────────────────────────────────────────────────────────────────
    scored = {}
    for ticker, df in enriched.items():
        try:
            if is_swing:
                scored[ticker] = score_stock_swing(df)
            else:
                scored[ticker] = score_stock(
                    df,
                    weights=SCORE_WEIGHTS,
                    use_regime=True,          # always on
                    fund_info=fund_data.get(ticker),
                )
        except Exception:
            errors.append(ticker)

    if not scored:
        console.print("[red]Scoring failed for all stocks.[/red]")
        sys.exit(1)

    ranked = rank_stocks(scored)

    # ── Today's open from actual analysis data ────────────────────────────────
    # Use first candle of today from enriched df — this matches what indicators
    # were computed on, so it's consistent with the rest of the analysis.
    import datetime
    today = datetime.date.today()
    today_lows = {}
    for ticker, df in enriched.items():
        try:
            mask = df.index.normalize().date == today
            today_rows = df[mask]
            if not today_rows.empty:
                today_lows[ticker] = float(today_rows["Low"].min())
        except Exception:
            pass

    # ── Live LTP update ───────────────────────────────────────────────────────
    # Replace entry/close with real-time NSE price so users see current values.
    top_tickers = [r["ticker"] for r in ranked]
    live_ltps   = fetch_live_ltps(top_tickers)
    for r in ranked:
        r["day_low"] = today_lows.get(r["ticker"],
                       todays_candles.get(r["ticker"], {}).get("Low"))
        ltp = live_ltps.get(r["ticker"])
        if ltp:
            # Recalculate stop/target from live price so target is never below entry
            atr = r.get("atr") or (r["entry"] - r["stop"]) / 1.5
            levels = _trade_levels(ltp, atr, regime=r.get("regime", "neutral"),
                                   resistance=r.get("resistance"))
            r.update(levels)

    # Drop any remaining invalid setups (target <= entry)
    ranked = [r for r in ranked if r.get("target", 0) > r.get("entry", 0)]

    # ── Confluence filter (--strict) ──────────────────────────────────────────
    weak = []
    if args.strict:
        ranked, weak = apply_confluence_filter(ranked)
        console.print(f"[dim]Confluence filter: {len(ranked)} strong signal(s), {len(weak)} excluded[/dim]")
        if not ranked:
            console.print(
                "\n[yellow]No stocks passed all 4 confluence conditions today.[/yellow]\n"
                "[dim]Conditions: Score ≥ 70 · MACD bullish · Golden cross · RSI < 65[/dim]\n"
                "[dim]Re-run without --strict to see all results.[/dim]"
            )
            if weak:
                closest = ", ".join(
                    f"{r['ticker'].replace('.NS','')} ({r['score']:.0f})"
                    for r in weak[:5]
                )
                console.print(f"[dim]Closest misses: {closest}[/dim]")
            sys.exit(0)

    # Optional sector filter
    if args.sector:
        sl     = args.sector.strip().lower()
        ranked = [r for r in ranked if SECTOR_MAP.get(r["ticker"], "").lower() == sl]
        if not ranked:
            valid = sorted(set(SECTOR_MAP.values()))
            console.print(f"[red]No results for sector '{args.sector}'.[/red]\n"
                          f"Valid: {', '.join(valid)}")
            sys.exit(1)

    top_n = min(args.top, len(ranked)) if args.top else len(ranked)

    # ── Display scores ────────────────────────────────────────────────────────
    if is_swing:
        render_swing_table(ranked, top_n, SECTOR_MAP)
        render_swing_summary(ranked, SECTOR_MAP, errors)
    else:
        render_table(ranked, top_n, SECTOR_MAP, show_regime=True)
        render_summary(ranked, SECTOR_MAP, errors)

    if weak and args.strict:
        excluded = ", ".join(
            f"{r['ticker'].replace('.NS','')} ({r['score']:.0f})"
            for r in weak[:15]
        )
        console.print(
            f"\n[dim]── {len(weak)} stocks excluded by --strict filter: "
            f"{excluded}{'…' if len(weak) > 15 else ''}[/dim]"
        )

    # ── Backtest (general mode only) ──────────────────────────────────────────
    if not is_swing:
        console.print("\n[dim]Running backtest on fetched data...[/dim]")
        from backtester import backtest_universe
        bt_result = backtest_universe(raw_data, SCORE_WEIGHTS,
                                      buy_threshold=65.0, hold_days=5)
        render_backtest(bt_result)


if __name__ == "__main__":
    main()
