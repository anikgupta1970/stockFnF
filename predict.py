#!/usr/bin/env python3
"""
Prediction Tracker — record top picks and later evaluate accuracy.

Usage:
  python3 predict.py record   --mode general   [--top N] [--threshold 65]
  python3 predict.py record   --mode intraday  [--top N] [--threshold 65]
  python3 predict.py evaluate [--file predictions.json]
  python3 predict.py list     [--file predictions.json]

  record   : Run analysis, save top picks with entry/stop/target to a JSON file.
  evaluate : Load saved predictions, fetch price history, determine outcome.
             General picks are evaluated on daily candles.
             Intraday picks are evaluated on 1h candles (Yahoo Finance keeps
             60 days of 1h history — evaluate within that window).
  list     : Show current state without fetching new data.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.table import Table
from rich import box

from config import (
    NIFTY_50_TICKERS, SECTOR_MAP,
    SCORE_WEIGHTS, SWING_WEIGHTS,
    DEFAULT_PERIOD, DEFAULT_INTERVAL,
    SWING_PERIOD, SWING_INTERVAL, SWING_MIN_ROWS,
)
from data_fetcher import fetch_ticker_data
from indicators import add_all_indicators, add_all_indicators_swing, add_regime_columns
from scorer import score_stock, score_stock_swing, rank_stocks

PREDICTIONS_FILE = Path("predictions.json")
console = Console(width=180)


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


def _get_tickers(index: str) -> list:
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


# ── Record ────────────────────────────────────────────────────────────────────

def cmd_record(args):
    is_intraday = args.mode == "intraday"
    mode_label  = "[yellow]INTRADAY[/yellow]" if is_intraday else "[blue]GENERAL[/blue]"
    tickers     = _get_tickers(args.index)

    period   = SWING_PERIOD   if is_intraday else DEFAULT_PERIOD
    interval = SWING_INTERVAL if is_intraday else DEFAULT_INTERVAL
    min_rows = SWING_MIN_ROWS if is_intraday else 60

    console.print(
        f"\n[bold cyan]Recording predictions[/bold cyan] · {mode_label}"
        f" · {len(tickers):,} stocks · {_today()}\n"
    )

    raw_data, errors = {}, []
    with ThreadPoolExecutor(max_workers=10) as ex:
        use_cache = not args.no_cache
        futures = {ex.submit(fetch_ticker_data, t, period, interval, use_cache): t
                   for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            df     = fut.result()
            if df.empty or len(df) < min_rows:
                errors.append(ticker)
            else:
                raw_data[ticker] = df

    console.print(f"[dim]Fetched {len(raw_data):,} · skipped {len(errors):,}[/dim]")

    enriched = {}
    for ticker, df in raw_data.items():
        try:
            if is_intraday:
                df_ind = add_all_indicators_swing(df)
            else:
                df_ind = add_all_indicators(df)
                df_ind = add_regime_columns(df_ind)
            enriched[ticker] = df_ind
        except Exception:
            errors.append(ticker)

    scored = {}
    for ticker, df in enriched.items():
        try:
            if is_intraday:
                scored[ticker] = score_stock_swing(df)
            else:
                scored[ticker] = score_stock(df, weights=SCORE_WEIGHTS, use_regime=True)
        except Exception:
            pass

    ranked    = rank_stocks(scored)
    top_picks = [r for r in ranked if r["score"] >= args.threshold]
    if args.top:
        top_picks = top_picks[: args.top]

    if not top_picks:
        console.print(
            f"[yellow]No stocks scored >= {args.threshold}. Try --threshold with a lower value.[/yellow]"
        )
        return

    today       = _today()
    new_records = []
    for pick in top_picks:
        rec_id = f"{pick['ticker']}_{today}_{args.mode}"
        new_records.append({
            "id":           rec_id,
            "ticker":       pick["ticker"],
            "sector":       SECTOR_MAP.get(pick["ticker"], "—"),
            "mode":         args.mode,          # "general" or "intraday"
            "date":         today,
            "score":        pick["score"],
            "percentile":   pick.get("percentile"),
            "entry":        pick["entry"],
            "stop":         pick["stop"],
            "target":       pick["target"],
            "risk_pct":     pick["risk_pct"],
            "reward_pct":   pick["reward_pct"],
            "rr_ratio":     pick["rr_ratio"],
            "regime":       pick.get("regime", "—"),
            "above_vwap":   pick.get("above_vwap"),   # intraday only
            "stoch_k":      pick.get("stoch_k"),       # intraday only
            "reasoning":    pick.get("reasoning", []),
            "outcome":      "open",
            "outcome_date": None,
            "outcome_price": None,
            "actual_return_pct": None,
        })

    existing     = _load(args.file)
    existing_ids = {r["id"] for r in existing}
    added        = [r for r in new_records if r["id"] not in existing_ids]
    _save(args.file, existing + added)

    # Display table
    tbl = Table(title=f"Predictions recorded · {args.mode} · {today}", box=box.SIMPLE_HEAVY)
    tbl.add_column("Ticker",  style="bold cyan", no_wrap=True)
    tbl.add_column("Score",   justify="right")
    tbl.add_column("Entry",   justify="right")
    tbl.add_column("Stop",    justify="right")
    tbl.add_column("Target",  justify="right")
    tbl.add_column("R:R",     justify="right")
    if is_intraday:
        tbl.add_column("VWAP",  justify="center")
        tbl.add_column("Stoch", justify="center")
    else:
        tbl.add_column("Regime")
    tbl.add_column("Reason")

    for r in added:
        extra = []
        if is_intraday:
            vwap_str  = ("Above" if r["above_vwap"] else "Below") if r["above_vwap"] is not None else "—"
            stoch_str = f"{r['stoch_k']:.0f}" if r["stoch_k"] is not None else "—"
            extra = [vwap_str, stoch_str]
        else:
            extra = [r["regime"]]

        tbl.add_row(
            r["ticker"],
            str(r["score"]),
            f"₹{r['entry']:.2f}",
            f"₹{r['stop']:.2f}",
            f"₹{r['target']:.2f}",
            f"{r['rr_ratio']:.1f}" if r["rr_ratio"] else "—",
            *extra,
            "; ".join(r["reasoning"][:1]),
        )

    console.print(tbl)
    console.print(f"[green]Saved {len(added)} new prediction(s) to [bold]{args.file}[/bold][/green]")
    if len(new_records) - len(added):
        console.print(f"[dim]Skipped {len(new_records)-len(added)} duplicate(s) already recorded today.[/dim]")
    if is_intraday:
        console.print(
            "[dim]Note: Yahoo Finance keeps ~60 days of 1h data. "
            "Run evaluate within that window for intraday picks.[/dim]"
        )


# ── Evaluate ──────────────────────────────────────────────────────────────────

def _fetch_ohlcv(ticker: str, period: str = None, interval: str = "1d",
                 start: str = None) -> pd.DataFrame:
    """
    Fetch OHLCV using yf.Ticker.history() — thread-safe, no MultiIndex issues.
    `period` OR `start` must be supplied.
    """
    try:
        t  = yf.Ticker(ticker)
        if start:
            df = t.history(start=start, interval=interval, auto_adjust=True)
        else:
            df = t.history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()
        df.columns = [c.strip().title() for c in df.columns]
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        return df[keep].dropna(subset=["High", "Low", "Close"])
    except Exception:
        return pd.DataFrame()


def _fetch_daily_since(ticker: str, since: str) -> pd.DataFrame:
    """Daily OHLCV from `since` to today — for general predictions."""
    return _fetch_ohlcv(ticker, interval="1d", start=since)


def _fetch_hourly_since(ticker: str, since: str) -> pd.DataFrame:
    """
    1h OHLCV — Yahoo Finance caps this at ~60 days of history.
    We fetch from `since` date or 59 days ago, whichever is more recent.
    """
    since_dt  = datetime.strptime(since, "%Y-%m-%d").date()
    cutoff_dt = date.today() - timedelta(days=59)
    start_dt  = max(since_dt, cutoff_dt)
    return _fetch_ohlcv(ticker, interval="1h", start=start_dt.isoformat())


def _determine_outcome(entry: float, stop: float, target: float,
                       df: pd.DataFrame) -> tuple:
    """
    Walk forward bar-by-bar. Returns (outcome, timestamp_str, price).
    Stop takes priority if both are touched in the same bar (conservative).
    """
    if df is None or df.empty:
        return "open", None, None

    for idx, row in df.iterrows():
        high  = float(row["High"])
        low   = float(row["Low"])
        close = float(row["Close"])
        ts    = str(idx)

        if low <= stop:
            return "stop_hit", ts, round(close, 2)
        if high >= target:
            return "target_hit", ts, round(close, 2)

    last_close = float(df["Close"].iloc[-1])
    last_ts    = str(df.index[-1])
    return "open", last_ts, round(last_close, 2)


def cmd_evaluate(args):
    records = _load(args.file)
    if not records:
        console.print(f"[yellow]No predictions found in {args.file}[/yellow]")
        return

    open_records = [r for r in records if r["outcome"] == "open"]
    console.print(
        f"\n[bold cyan]Evaluating predictions[/bold cyan] · "
        f"{len(open_records)} open / {len(records)} total\n"
    )

    if not open_records:
        console.print("[green]All predictions already evaluated.[/green]")
        _show_summary(records)
        return

    # Separate by mode so we can fetch the right candle size
    general_open  = [r for r in open_records if r.get("mode", "general") == "general"]
    intraday_open = [r for r in open_records if r.get("mode") == "intraday"]

    if intraday_open:
        console.print(
            f"[dim]{len(intraday_open)} intraday pick(s) — fetching 1h candles "
            f"(Yahoo keeps ~60 days)[/dim]"
        )
    if general_open:
        console.print(
            f"[dim]{len(general_open)} general pick(s) — fetching daily candles[/dim]"
        )

    updated = 0

    def _eval_record(rec):
        mode = rec.get("mode", "general")
        if mode == "intraday":
            df = _fetch_hourly_since(rec["ticker"], rec["date"])
        else:
            df = _fetch_daily_since(rec["ticker"], rec["date"])

        if df.empty:
            return  # no data yet

        outcome, out_ts, out_price = _determine_outcome(
            rec["entry"], rec["stop"], rec["target"], df
        )
        rec["outcome"]       = outcome
        rec["outcome_date"]  = out_ts
        rec["outcome_price"] = out_price
        if out_price and rec["entry"]:
            rec["actual_return_pct"] = round(
                (out_price - rec["entry"]) / rec["entry"] * 100, 2
            )

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_eval_record, r): r for r in open_records}
        for fut in as_completed(futures):
            fut.result()   # surface exceptions if any
            updated += 1

    _save(args.file, records)
    console.print(f"[dim]Processed {updated} record(s).[/dim]\n")
    _show_summary(records)


# ── Summary display ───────────────────────────────────────────────────────────

def _show_summary(records: list):
    # ── Overall stats ─────────────────────────────────────────────────────────
    target_hit = [r for r in records if r["outcome"] == "target_hit"]
    stop_hit   = [r for r in records if r["outcome"] == "stop_hit"]
    open_recs  = [r for r in records if r["outcome"] == "open"]

    total_closed = len(target_hit) + len(stop_hit)
    win_rate     = len(target_hit) / total_closed * 100 if total_closed else 0
    returns_closed = [r["actual_return_pct"] for r in records
                      if r["outcome"] != "open" and r["actual_return_pct"] is not None]
    avg_return = sum(returns_closed) / len(returns_closed) if returns_closed else 0

    console.print(
        f"[bold]Overall:[/bold]  "
        f"[green]{len(target_hit)} target hit[/green]  "
        f"[red]{len(stop_hit)} stop hit[/red]  "
        f"[yellow]{len(open_recs)} open[/yellow]  "
        f"| Win rate: [bold]{win_rate:.1f}%[/bold]"
        f"  Avg return (closed): [bold]{avg_return:+.2f}%[/bold]"
    )

    # Per-mode win rate
    for mode_name in ("general", "intraday"):
        mode_recs   = [r for r in records if r.get("mode", "general") == mode_name]
        mode_closed = [r for r in mode_recs if r["outcome"] != "open"]
        mode_wins   = [r for r in mode_closed if r["outcome"] == "target_hit"]
        if mode_closed:
            wr = len(mode_wins) / len(mode_closed) * 100
            console.print(
                f"  [dim]{mode_name.capitalize():9s}:[/dim] "
                f"[green]{len(mode_wins)} wins[/green] / {len(mode_closed)} closed · "
                f"win rate [bold]{wr:.1f}%[/bold]"
            )

    console.print()

    # ── Detailed table ────────────────────────────────────────────────────────
    STATUS_STYLE = {
        "target_hit": "[green]TARGET HIT[/green]",
        "stop_hit":   "[red]STOP HIT[/red]",
        "open":       "[yellow]OPEN[/yellow]",
    }

    tbl = Table(title="Prediction Outcomes", box=box.SIMPLE_HEAVY)
    tbl.add_column("Ticker",              style="bold cyan", no_wrap=True)
    tbl.add_column("Mode",               justify="center",  no_wrap=True)
    tbl.add_column("Date",               no_wrap=True)
    tbl.add_column("Score",              justify="right")
    tbl.add_column("Entry ₹",            justify="right")
    tbl.add_column("Stop ₹",             justify="right")
    tbl.add_column("Target ₹",           justify="right")
    tbl.add_column("Outcome",            justify="center")
    tbl.add_column("Ref Price ₹",        justify="right")
    tbl.add_column("Ref Timestamp",      no_wrap=True)
    tbl.add_column("Return",             justify="right")

    sorted_records = sorted(records, key=lambda r: r["date"], reverse=True)
    for r in sorted_records:
        ret_str   = ""
        ref_str   = "—"
        ref_ts    = "—"
        out_price = r.get("outcome_price")
        out_date  = r.get("outcome_date")

        if out_price is not None:
            ref_str = f"₹{out_price:.2f}"
        if out_date is not None:
            ref_ts = str(out_date)[:16]   # trim to minute precision

        if r["actual_return_pct"] is not None:
            v = r["actual_return_pct"]
            ret_str = f"[{'green' if v > 0 else 'red'}]{v:+.2f}%[/{'green' if v > 0 else 'red'}]"

        mode = r.get("mode", "general")
        mode_str = "[yellow]intraday[/yellow]" if mode == "intraday" else "[blue]general[/blue]"

        tbl.add_row(
            r["ticker"].replace(".NS", ""),
            mode_str,
            r["date"],
            str(r["score"]),
            f"₹{r['entry']:.2f}" if r.get("entry") else "—",
            f"₹{r['stop']:.2f}"  if r.get("stop")  else "—",
            f"₹{r['target']:.2f}" if r.get("target") else "—",
            STATUS_STYLE.get(r["outcome"], r["outcome"]),
            ref_str,
            ref_ts,
            ret_str or "—",
        )

    console.print(tbl)

    # ── Sector breakdown (closed trades) ─────────────────────────────────────
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
        description="Prediction Tracker — general and intraday modes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # General (multi-day) picks
  python3 predict.py record --mode general --top 10 --threshold 68
  python3 predict.py record --mode general --index all --top 20

  # Intraday / swing picks (1-5 day trades)
  python3 predict.py record --mode intraday --top 10 --threshold 65
  python3 predict.py record --mode intraday --index nifty50 --top 5

  # Evaluate all open predictions (uses correct candle size per pick)
  python3 predict.py evaluate

  # View without fetching
  python3 predict.py list

  # Separate files for general and intraday
  python3 predict.py record --mode general  --file general_preds.json
  python3 predict.py record --mode intraday --file intraday_preds.json
  python3 predict.py evaluate --file intraday_preds.json
        """,
    )
    p.add_argument("command", choices=["record", "evaluate", "list"])
    p.add_argument("--mode",      choices=["general", "intraday"], default="general",
                   help="Analysis mode for record command (default: general)")
    p.add_argument("--top",       type=int,   default=None,
                   help="Record only top N picks (default: all above threshold)")
    p.add_argument("--threshold", type=float, default=65.0,
                   help="Min score to record as a prediction (default: 65)")
    p.add_argument("--index",     choices=["all", "nifty50"], default="nifty50",
                   help="Stock universe for record command (default: nifty50)")
    p.add_argument("--no-cache",  action="store_true",
                   help="Force fresh data download, ignore disk cache")
    p.add_argument("--file",      type=Path,  default=PREDICTIONS_FILE,
                   help=f"Predictions JSON file (default: {PREDICTIONS_FILE})")
    return p.parse_args()


def main():
    args = parse_args()
    dispatch = {"record": cmd_record, "evaluate": cmd_evaluate, "list": cmd_list}
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
