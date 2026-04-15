#!/usr/bin/env python3
"""
Prediction Tracker — record today's top picks and later evaluate accuracy.

Usage:
  python3 predict.py record   [--top N] [--index nifty50] [--threshold 65]
  python3 predict.py evaluate [--file predictions.json]
  python3 predict.py list     [--file predictions.json]

  record   : Run analysis, save top picks with entry/stop/target to a JSON file.
  evaluate : Load saved predictions, fetch price history, determine outcome.
  list     : Show saved (unevaluated) predictions.
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import numpy as np
import yfinance as yf
from rich.console import Console
from rich.table import Table
from rich import box

from config import (
    NIFTY_50_TICKERS, SECTOR_MAP, SCORE_WEIGHTS,
    DEFAULT_PERIOD, DEFAULT_INTERVAL,
)
from data_fetcher import fetch_ticker_data
from indicators import add_all_indicators, add_regime_columns
from scorer import score_stock, rank_stocks

PREDICTIONS_FILE = Path("predictions.json")
console = Console()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path: Path) -> list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def _save(path: Path, records: list) -> None:
    with open(path, "w") as f:
        json.dump(records, f, indent=2, default=str)


def _today() -> str:
    return date.today().isoformat()


# ── Record ────────────────────────────────────────────────────────────────────

def cmd_record(args):
    tickers = NIFTY_50_TICKERS if args.index == "nifty50" else NIFTY_50_TICKERS
    if args.index != "nifty50":
        try:
            from universe import get_all_tickers
            tickers = get_all_tickers()
            console.print(f"[dim]NSE universe: {len(tickers):,} equities[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not fetch full NSE list ({e}). Using NIFTY 50.[/yellow]")

    console.print(f"\n[bold cyan]Recording predictions[/bold cyan] · {len(tickers):,} stocks · {_today()}\n")

    raw_data, errors = {}, []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_ticker_data, t, DEFAULT_PERIOD, DEFAULT_INTERVAL, True): t
                   for t in tickers}
        for fut in as_completed(futures):
            ticker, df = futures[fut], fut.result()
            if df.empty or len(df) < 60:
                errors.append(ticker)
            else:
                raw_data[ticker] = df

    console.print(f"[dim]Fetched {len(raw_data):,} · skipped {len(errors):,}[/dim]")

    enriched = {}
    for ticker, df in raw_data.items():
        try:
            df_ind = add_all_indicators(df)
            df_ind = add_regime_columns(df_ind)
            enriched[ticker] = df_ind
        except Exception:
            errors.append(ticker)

    scored = {}
    for ticker, df in enriched.items():
        try:
            scored[ticker] = score_stock(df, weights=SCORE_WEIGHTS, use_regime=True)
        except Exception:
            pass

    ranked = rank_stocks(scored)
    top_picks = [r for r in ranked if r["score"] >= args.threshold]
    if args.top:
        top_picks = top_picks[: args.top]

    if not top_picks:
        console.print(f"[yellow]No stocks scored >= {args.threshold}. Lowering threshold or try --threshold.[/yellow]")
        return

    today = _today()
    new_records = []
    for pick in top_picks:
        new_records.append({
            "id":        f"{pick['ticker']}_{today}",
            "ticker":    pick["ticker"],
            "sector":    SECTOR_MAP.get(pick["ticker"], "—"),
            "date":      today,
            "score":     pick["score"],
            "percentile": pick.get("percentile", None),
            "entry":     pick["entry"],
            "stop":      pick["stop"],
            "target":    pick["target"],
            "risk_pct":  pick["risk_pct"],
            "reward_pct": pick["reward_pct"],
            "rr_ratio":  pick["rr_ratio"],
            "regime":    pick.get("regime", "—"),
            "reasoning": pick.get("reasoning", []),
            "outcome":   "open",          # filled in by evaluate
            "outcome_date": None,
            "outcome_price": None,
            "actual_return_pct": None,
        })

    existing = _load(args.file)
    # Avoid duplicate predictions for same ticker on same day
    existing_ids = {r["id"] for r in existing}
    added = [r for r in new_records if r["id"] not in existing_ids]
    _save(args.file, existing + added)

    # Display
    tbl = Table(title=f"Predictions recorded ({today})", box=box.SIMPLE_HEAVY)
    tbl.add_column("Ticker",  style="bold cyan", no_wrap=True)
    tbl.add_column("Score",   justify="right")
    tbl.add_column("Entry",   justify="right")
    tbl.add_column("Stop",    justify="right")
    tbl.add_column("Target",  justify="right")
    tbl.add_column("R:R",     justify="right")
    tbl.add_column("Regime")
    tbl.add_column("Reason")

    for r in added:
        tbl.add_row(
            r["ticker"],
            str(r["score"]),
            f"₹{r['entry']:.2f}",
            f"₹{r['stop']:.2f}",
            f"₹{r['target']:.2f}",
            f"{r['rr_ratio']:.1f}" if r["rr_ratio"] else "—",
            r["regime"],
            "; ".join(r["reasoning"][:1]),
        )

    console.print(tbl)
    console.print(f"[green]Saved {len(added)} new prediction(s) to [bold]{args.file}[/bold][/green]")
    if len(new_records) - len(added):
        console.print(f"[dim]Skipped {len(new_records)-len(added)} duplicate(s) already recorded today.[/dim]")


# ── Evaluate ──────────────────────────────────────────────────────────────────

def _fetch_history_since(ticker: str, since: str) -> "pd.DataFrame":
    """Fetch daily OHLC from `since` date to today."""
    import pandas as pd
    try:
        df = yf.download(ticker, start=since, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        df = df.dropna(subset=["High", "Low", "Close"])
        return df
    except Exception:
        return __import__("pandas").DataFrame()


def _determine_outcome(entry: float, stop: float, target: float,
                       df) -> tuple:
    """
    Walk forward through price history day-by-day.
    Returns (outcome, date_str, price).
      outcome: 'target_hit' | 'stop_hit' | 'open'
    """
    if df is None or len(df) == 0:
        return "open", None, None

    for idx, row in df.iterrows():
        high = float(row["High"])
        low  = float(row["Low"])
        date_str = str(idx.date())

        # Check stop first (conservative — if both touched, stop wins on same day)
        if low <= stop:
            return "stop_hit", date_str, round(stop, 2)
        if high >= target:
            return "target_hit", date_str, round(target, 2)

    # Still open — use latest close
    last_close = float(df["Close"].iloc[-1])
    last_date  = str(df.index[-1].date())
    return "open", last_date, round(last_close, 2)


def cmd_evaluate(args):
    records = _load(args.file)
    if not records:
        console.print(f"[yellow]No predictions found in {args.file}[/yellow]")
        return

    open_records = [r for r in records if r["outcome"] == "open"]
    console.print(f"\n[bold cyan]Evaluating predictions[/bold cyan] · "
                  f"{len(open_records)} open / {len(records)} total\n")

    if not open_records:
        console.print("[green]All predictions already evaluated.[/green]")
        _show_summary(records)
        return

    # Fetch price history for each open prediction
    updated = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(_fetch_history_since, r["ticker"], r["date"]): r
            for r in open_records
        }
        for fut in as_completed(futures):
            rec = futures[fut]
            df  = fut.result()
            if df.empty or len(df) < 2:
                continue  # not enough data yet

            # Skip the entry day itself (first row = entry day)
            df_fwd = df.iloc[1:]
            if df_fwd.empty:
                continue

            outcome, out_date, out_price = _determine_outcome(
                rec["entry"], rec["stop"], rec["target"], df_fwd
            )
            rec["outcome"]       = outcome
            rec["outcome_date"]  = out_date
            rec["outcome_price"] = out_price
            if out_price and rec["entry"]:
                ret = (out_price - rec["entry"]) / rec["entry"] * 100
                rec["actual_return_pct"] = round(ret, 2)
            updated += 1

    _save(args.file, records)
    console.print(f"[dim]Updated {updated} record(s).[/dim]\n")
    _show_summary(records)


def _show_summary(records: list):
    # Split by outcome
    target_hit = [r for r in records if r["outcome"] == "target_hit"]
    stop_hit   = [r for r in records if r["outcome"] == "stop_hit"]
    open_recs  = [r for r in records if r["outcome"] == "open"]

    total_closed = len(target_hit) + len(stop_hit)
    win_rate = len(target_hit) / total_closed * 100 if total_closed else 0

    returns_closed = [r["actual_return_pct"] for r in records
                      if r["outcome"] != "open" and r["actual_return_pct"] is not None]
    avg_return = sum(returns_closed) / len(returns_closed) if returns_closed else 0

    # Summary panel
    console.print(
        f"[bold]Results:[/bold] "
        f"[green]{len(target_hit)} target hit[/green]  "
        f"[red]{len(stop_hit)} stop hit[/red]  "
        f"[yellow]{len(open_recs)} open[/yellow]  "
        f"| Win rate: [bold]{win_rate:.1f}%[/bold]"
        f"  Avg return (closed): [bold]{avg_return:+.2f}%[/bold]"
    )

    # Detailed table
    tbl = Table(title="Prediction Outcomes", box=box.SIMPLE_HEAVY)
    tbl.add_column("Ticker",    style="bold cyan", no_wrap=True)
    tbl.add_column("Date",      no_wrap=True)
    tbl.add_column("Score",     justify="right")
    tbl.add_column("Entry",     justify="right")
    tbl.add_column("Stop",      justify="right")
    tbl.add_column("Target",    justify="right")
    tbl.add_column("Outcome",   justify="center")
    tbl.add_column("Out date",  no_wrap=True)
    tbl.add_column("Return",    justify="right")

    STATUS_STYLE = {
        "target_hit": "[green]TARGET HIT[/green]",
        "stop_hit":   "[red]STOP HIT[/red]",
        "open":       "[yellow]OPEN[/yellow]",
    }

    sorted_records = sorted(records, key=lambda r: r["date"], reverse=True)
    for r in sorted_records:
        ret_str = ""
        if r["actual_return_pct"] is not None:
            v = r["actual_return_pct"]
            colour = "green" if v > 0 else "red"
            ret_str = f"[{colour}]{v:+.2f}%[/{colour}]"

        tbl.add_row(
            r["ticker"],
            r["date"],
            str(r["score"]),
            f"₹{r['entry']:.2f}" if r["entry"] else "—",
            f"₹{r['stop']:.2f}"  if r["stop"]  else "—",
            f"₹{r['target']:.2f}" if r["target"] else "—",
            STATUS_STYLE.get(r["outcome"], r["outcome"]),
            r["outcome_date"] or "—",
            ret_str or "—",
        )

    console.print(tbl)

    # Sector breakdown (closed trades only)
    closed = [r for r in records if r["outcome"] != "open"]
    if closed:
        from collections import defaultdict
        by_sector: dict = defaultdict(lambda: {"wins": 0, "total": 0})
        for r in closed:
            sec = r.get("sector", "—")
            by_sector[sec]["total"] += 1
            if r["outcome"] == "target_hit":
                by_sector[sec]["wins"] += 1

        stbl = Table(title="By Sector (closed trades)", box=box.SIMPLE)
        stbl.add_column("Sector")
        stbl.add_column("Wins",  justify="right")
        stbl.add_column("Total", justify="right")
        stbl.add_column("Win %", justify="right")
        for sec, v in sorted(by_sector.items(), key=lambda x: -x[1]["total"]):
            pct = v["wins"] / v["total"] * 100
            stbl.add_row(sec, str(v["wins"]), str(v["total"]), f"{pct:.0f}%")
        console.print(stbl)


# ── List ──────────────────────────────────────────────────────────────────────

def cmd_list(args):
    records = _load(args.file)
    if not records:
        console.print(f"[yellow]No predictions in {args.file}[/yellow]")
        return
    _show_summary(records)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Prediction Tracker for NSE Stock Analyser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 predict.py record                      # Record NIFTY 50 top picks today
  python3 predict.py record --top 10             # Record top 10 picks only
  python3 predict.py record --threshold 70       # Stricter threshold (default 65)
  python3 predict.py record --index all          # Full NSE universe (slower)
  python3 predict.py evaluate                    # Evaluate all open predictions
  python3 predict.py list                        # Show current state without fetching
  python3 predict.py record --file my_preds.json # Use a custom file
        """,
    )
    p.add_argument("command", choices=["record", "evaluate", "list"])
    p.add_argument("--top",       type=int,   default=None,
                   help="Record only top N picks (default: all above threshold)")
    p.add_argument("--threshold", type=float, default=65.0,
                   help="Min score to record as a prediction (default 65)")
    p.add_argument("--index",     choices=["all", "nifty50"], default="nifty50",
                   help="Stock universe for record command (default: nifty50)")
    p.add_argument("--file",      type=Path,  default=PREDICTIONS_FILE,
                   help=f"Predictions JSON file (default: {PREDICTIONS_FILE})")
    return p.parse_args()


def main():
    args = parse_args()
    dispatch = {"record": cmd_record, "evaluate": cmd_evaluate, "list": cmd_list}
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
