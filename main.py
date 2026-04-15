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

from config import (NIFTY_50_TICKERS, SECTOR_MAP,
                    DEFAULT_PERIOD, DEFAULT_INTERVAL, SCORE_WEIGHTS,
                    SWING_PERIOD, SWING_INTERVAL, SWING_MIN_ROWS)
from data_fetcher import fetch_ticker_data
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
    p.add_argument("--index",  choices=["all", "nifty50"], default="all",
                   help="Stock universe (default: all ~2100 NSE equities)")
    p.add_argument("--no-cache", action="store_true",
                   help="Ignore cached data, re-download everything")
    return p.parse_args()


def get_tickers(index: str) -> list:
    if index == "nifty50":
        return NIFTY_50_TICKERS.copy()
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

    period   = SWING_PERIOD   if is_swing else DEFAULT_PERIOD
    interval = SWING_INTERVAL if is_swing else DEFAULT_INTERVAL
    min_rows = SWING_MIN_ROWS if is_swing else 60

    tickers = get_tickers(args.index)

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

    # ── Backtest (general mode only) ──────────────────────────────────────────
    if not is_swing:
        console.print("\n[dim]Running backtest on fetched data...[/dim]")
        from backtester import backtest_universe
        bt_result = backtest_universe(raw_data, SCORE_WEIGHTS,
                                      buy_threshold=65.0, hold_days=5)
        render_backtest(bt_result)


if __name__ == "__main__":
    main()
