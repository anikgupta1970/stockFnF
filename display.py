from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from collections import Counter

console = Console(width=180)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_color(score: float) -> str:
    if score >= 70:   return "bold green"
    elif score >= 55: return "yellow"
    else:             return "red"


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _score_bar(score: float) -> str:
    filled = int(score / 10)
    return "█" * filled + "░" * (10 - filled)


def _fmt_price(v) -> str:
    if v != v or v is None:   # nan check
        return "—"
    return f"₹{v:,.1f}"


def _fmt_pct(v) -> str:
    if v != v or v is None:
        return "—"
    return f"{v:.1f}%"


def _rsi_cell(rsi_val: float) -> str:
    if rsi_val < 30:  return f"[bold green]{rsi_val:.0f}[/bold green]"
    if rsi_val > 70:  return f"[bold red]{rsi_val:.0f}[/bold red]"
    return f"{rsi_val:.0f}"


# ── General (positional) table ─────────────────────────────────────────────────

def render_table(results: list, top_n: int, sector_map: dict,
                 show_regime: bool = False) -> None:
    shown = results[:top_n]

    table = Table(
        title=f"[bold cyan]NSE Stock Analysis — {top_n} Stocks by Buy Probability[/bold cyan]",
        box=box.SIMPLE_HEAVY, show_lines=False,
        header_style="bold white on dark_blue", expand=False,
    )

    table.add_column("#",        justify="center", style="dim", width=3)
    table.add_column("Ticker",   style="bold",     width=12, no_wrap=True)
    table.add_column("Sector",                     width=14, no_wrap=True)
    table.add_column("Score",                      width=14, no_wrap=True)
    table.add_column("Entry ₹",  justify="right",  width=9,  no_wrap=True)
    table.add_column("Stop ₹",   justify="right",  width=9,  no_wrap=True)
    table.add_column("Target ₹", justify="right",  width=10, no_wrap=True)
    table.add_column("Risk %",   justify="center", width=7,  no_wrap=True)
    table.add_column("R:R",      justify="center", width=5,  no_wrap=True)
    if show_regime:
        table.add_column("Regime", justify="center", width=10, no_wrap=True)
    table.add_column("RSI",      justify="center", width=5,  no_wrap=True)
    table.add_column("MACD",     justify="center", width=7,  no_wrap=True)
    table.add_column("MA",       justify="center", width=7,  no_wrap=True)
    table.add_column("Vol×",     justify="center", width=5,  no_wrap=True)
    table.add_column("Key Signals")

    for i, row in enumerate(shown, 1):
        ticker = row["ticker"]
        score  = row["score"]
        color  = _score_color(score)

        score_text = Text()
        score_text.append(_score_bar(score), style=color)
        score_text.append(f" {score:.0f}", style=f"bold {color}")

        rr  = row.get("rr_ratio", float("nan"))
        rr_str = f"{rr:.1f}" if rr == rr else "—"

        extra = []
        if show_regime:
            from regime import regime_label
            extra.append(regime_label(row.get("regime", "neutral")))

        vol = row.get("vol_ratio", float("nan"))

        table.add_row(
            str(i),
            ticker.replace(".NS", ""),
            sector_map.get(ticker, "—"),
            score_text,
            _fmt_price(row.get("entry")),
            f"[red]{_fmt_price(row.get('stop'))}[/red]",
            f"[green]{_fmt_price(row.get('target'))}[/green]",
            _fmt_pct(row.get("risk_pct")),
            rr_str,
            *extra,
            _rsi_cell(row["rsi"]),
            "[green]Bull ▲[/green]" if row["macd_bullish"] else "[red]Bear ▼[/red]",
            "[green]Gold[/green]" if row["ma_cross"] == "Golden" else "[red]Death[/red]",
            f"{vol:.1f}" if vol == vol else "—",
            " | ".join(row.get("reasoning", [])),
        )

    console.print()
    console.print(table)


def render_summary(results: list, sector_map: dict, errors: list) -> None:
    top10 = results[:10]
    sector_counts = Counter(sector_map.get(r["ticker"], "Other") for r in top10)
    avg_score  = sum(r["score"] for r in results) / max(len(results), 1)
    top        = results[0] if results else {}

    lines = [
        f"[bold]Stocks analysed:[/bold]  {len(results)}",
        f"[bold]Average score:[/bold]    {avg_score:.1f} / 100",
        f"[bold]Top pick:[/bold]         "
        f"{top.get('ticker','—').replace('.NS','')} (score {top.get('score',0):.1f})",
        "",
        "[bold]Sector distribution in top 10:[/bold]",
    ]
    for sector, count in sector_counts.most_common():
        lines.append(f"  {'█' * count}  {sector} ({count})")

    if errors:
        lines += ["", f"[yellow]Skipped:[/yellow] {', '.join(e.replace('.NS','') for e in errors[:20])}"
                      + (f" (+{len(errors)-20} more)" if len(errors) > 20 else "")]

    lines += [
        "",
        "[dim]Entry/Stop/Target based on ATR (Average True Range).[/dim]",
        "[dim]Score guide: [bold green]≥70[/bold green] Strong · "
        "[yellow]55-69[/yellow] Watch · [red]<55[/red] Avoid[/dim]",
        "[dim italic]Disclaimer: Algorithmic analysis only — not financial advice.[/dim italic]",
    ]
    console.print(Panel("\n".join(lines), title="[bold cyan]Summary[/bold cyan]",
                        border_style="cyan", width=110))


# ── Swing (intraday) table ────────────────────────────────────────────────────

def render_swing_table(results: list, top_n: int, sector_map: dict) -> None:
    shown = results[:top_n]

    table = Table(
        title=f"[bold cyan]NSE Swing Analysis — Top {top_n} Picks (1h candles)[/bold cyan]",
        box=box.SIMPLE_HEAVY, show_lines=False,
        header_style="bold white on dark_blue", expand=False,
    )

    table.add_column("#",         justify="center", style="dim", width=3)
    table.add_column("Ticker",    style="bold",     width=12, no_wrap=True)
    table.add_column("Sector",                      width=14, no_wrap=True)
    table.add_column("Score",                       width=14, no_wrap=True)
    table.add_column("Entry ₹",   justify="right",  width=9,  no_wrap=True)
    table.add_column("Stop ₹",    justify="right",  width=9,  no_wrap=True)
    table.add_column("Target ₹",  justify="right",  width=10, no_wrap=True)
    table.add_column("Risk %",    justify="center", width=7,  no_wrap=True)
    table.add_column("R:R",       justify="center", width=5,  no_wrap=True)
    table.add_column("RSI",       justify="center", width=5,  no_wrap=True)
    table.add_column("Stoch",     justify="center", width=6,  no_wrap=True)
    table.add_column("VWAP",      justify="center", width=6,  no_wrap=True)
    table.add_column("Vol×",      justify="center", width=5,  no_wrap=True)
    table.add_column("Signals")

    for i, row in enumerate(shown, 1):
        score  = row["score"]
        color  = _score_color(score)

        score_text = Text()
        score_text.append(_score_bar(score), style=color)
        score_text.append(f" {score:.0f}", style=f"bold {color}")

        stoch = row.get("stoch_k", float("nan"))
        if stoch == stoch:
            stoch_cell = f"[bold green]{stoch:.0f}[/bold green]" if stoch < 20 \
                    else f"[bold red]{stoch:.0f}[/bold red]"   if stoch > 80 \
                    else f"{stoch:.0f}"
        else:
            stoch_cell = "—"

        above = row.get("above_vwap")
        vwap_cell = "[green]Above[/green]" if above else \
                    "[red]Below[/red]" if above is not None else "—"

        rr  = row.get("rr_ratio", float("nan"))
        vol = row.get("vol_ratio", float("nan"))

        table.add_row(
            str(i),
            row["ticker"].replace(".NS", ""),
            sector_map.get(row["ticker"], "—"),
            score_text,
            _fmt_price(row.get("entry")),
            f"[red]{_fmt_price(row.get('stop'))}[/red]",
            f"[green]{_fmt_price(row.get('target'))}[/green]",
            _fmt_pct(row.get("risk_pct")),
            f"{rr:.1f}" if rr == rr else "—",
            _rsi_cell(row["rsi"]),
            stoch_cell,
            vwap_cell,
            f"{vol:.1f}" if vol == vol else "—",
            " | ".join(row.get("reasoning", [])),
        )

    console.print()
    console.print(table)


def render_swing_summary(results: list, sector_map: dict, errors: list) -> None:
    top10    = results[:10]
    avg_score = sum(r["score"] for r in results) / max(len(results), 1)
    top      = results[0] if results else {}
    top10_rr = [r["rr_ratio"] for r in top10 if r.get("rr_ratio") == r.get("rr_ratio")]
    avg_rr   = sum(top10_rr) / len(top10_rr) if top10_rr else float("nan")
    above_vwap = sum(1 for r in top10 if r.get("above_vwap"))

    lines = [
        f"[bold]Stocks analysed:[/bold]  {len(results)}",
        f"[bold]Timeframe:[/bold]         1-hour candles (1-month lookback)",
        f"[bold]Avg score:[/bold]         {avg_score:.1f} / 100",
        f"[bold]Top pick:[/bold]          {top.get('ticker','—').replace('.NS','')} "
        f"(score {top.get('score',0):.1f})",
        f"[bold]Avg R:R (top 10):[/bold]  {avg_rr:.1f}" if avg_rr == avg_rr else "",
        f"[bold]Above VWAP (top 10):[/bold] {above_vwap}/10",
        "",
        "[bold]How to trade:[/bold]",
        "  [green]Entry[/green]  → buy near this price",
        "  [red]Stop[/red]   → exit immediately if price drops here",
        "  [green]Target[/green] → take profit here",
        "  R:R    → reward ÷ risk (prefer ≥ 1.5)",
        "",
        "[dim]Stop & Target use ATR (volatility-scaled). "
        "Score ≥70 Strong · 55-69 Watch · <55 Skip[/dim]",
        "[dim italic]Disclaimer: Algorithmic signals only — not financial advice.[/dim italic]",
    ]
    console.print(Panel("\n".join(l for l in lines if l is not None),
                        title="[bold cyan]Swing Trading Summary[/bold cyan]",
                        border_style="cyan", width=110))


# ── Backtest results ──────────────────────────────────────────────────────────

def render_backtest(results: dict, top_n: int = 20) -> None:
    agg = results.get("aggregate", {})
    by_ticker = results.get("by_ticker", {})

    # Aggregate panel
    lines = [
        f"[bold]Stocks backtested:[/bold]  {agg.get('n_stocks', 0)}",
        f"[bold]Total trades:[/bold]       {agg.get('n_trades', 0)}",
        f"[bold]Sharpe ratio:[/bold]       "
        + (f"{agg['sharpe']:.2f}  [dim](>1.0 good, >2.0 excellent)[/dim]"
           if agg.get('sharpe') == agg.get('sharpe') and agg.get('n_trades',0) >= 3
           else "[dim]N/A (need ≥3 trades — lower --bt-threshold)[/dim]"),
        f"[bold]Win rate:[/bold]           {agg.get('win_rate', 0):.1f}%",
        f"[bold]Avg return/trade:[/bold]   {agg.get('avg_return_pct', 0):.2f}%",
        f"[bold]Max drawdown:[/bold]       {agg.get('max_drawdown_pct', 0):.1f}%",
        f"[bold]Total return:[/bold]       {agg.get('total_return_pct', 0):.1f}%",
        "",
        "[dim]Backtest: buy when score ≥ threshold, sell after 5 days. "
        "No lookahead bias.[/dim]",
    ]
    console.print(Panel("\n".join(lines), title="[bold cyan]Backtest Results — Aggregate[/bold cyan]",
                        border_style="cyan", width=80))

    # Per-ticker table (top N by Sharpe)
    rows = sorted(
        [(t, m) for t, m in by_ticker.items() if m.get("n_trades", 0) > 0],
        key=lambda x: x[1].get("sharpe", 0),
        reverse=True,
    )[:top_n]

    if not rows:
        console.print("[yellow]No trades were generated. Try lowering --bt-threshold.[/yellow]")
        return

    table = Table(
        title=f"[bold cyan]Backtest — Top {len(rows)} Stocks by Sharpe[/bold cyan]",
        box=box.SIMPLE_HEAVY, header_style="bold white on dark_blue",
    )
    table.add_column("Ticker",       width=14, style="bold")
    table.add_column("Trades",       justify="center", width=7)
    table.add_column("Sharpe",       justify="center", width=8)
    table.add_column("Win %",        justify="center", width=7)
    table.add_column("Avg Ret %",    justify="center", width=10)
    table.add_column("Max DD %",     justify="center", width=10)
    table.add_column("Total Ret %",  justify="center", width=12)

    for ticker, m in rows:
        sharpe   = m.get("sharpe", float("nan"))
        sh_valid = sharpe == sharpe   # nan check
        sc       = "bold green" if sh_valid and sharpe > 1 else \
                   "yellow"    if sh_valid and sharpe > 0 else "red"
        sh_str   = f"[{sc}]{sharpe:.2f}[/{sc}]" if sh_valid else "[dim]N/A[/dim]"
        table.add_row(
            ticker.replace(".NS", ""),
            str(m.get("n_trades", 0)),
            sh_str,
            f"{m.get('win_rate', 0):.1f}%",
            f"{m.get('avg_return_pct', 0):.2f}%",
            f"[red]{m.get('max_drawdown_pct', 0):.1f}%[/red]",
            f"{m.get('total_return_pct', 0):.1f}%",
        )

    console.print()
    console.print(table)


# ── Walk-forward optimiser results ────────────────────────────────────────────

def render_optimizer(opt_result: dict, base_weights: dict) -> None:
    windows     = opt_result.get("windows", [])
    rec_weights = opt_result.get("recommended_weights", base_weights)
    n_stocks    = opt_result.get("n_stocks_used", 0)
    avg_oos     = opt_result.get("avg_oos_sharpe", 0)
    avg_base    = opt_result.get("avg_base_sharpe", 0)

    # Summary panel
    improvement = avg_oos - avg_base
    imp_color   = "green" if improvement > 0 else "red"
    lines = [
        f"[bold]Stocks used:[/bold]          {n_stocks}",
        f"[bold]Walk-forward windows:[/bold] {len(windows)}",
        f"[bold]Avg OOS Sharpe (opt):[/bold] {avg_oos:.2f}",
        f"[bold]Avg OOS Sharpe (base):[/bold]{avg_base:.2f}",
        f"[bold]Improvement:[/bold]          "
        f"[{imp_color}]{improvement:+.2f}[/{imp_color}]",
        "",
        "[bold]Recommended weights (avg across all windows):[/bold]",
    ]
    keys = ["rsi", "macd", "bb", "ma", "volume"]
    for k in keys:
        base_v = base_weights.get(k, 0)
        rec_v  = rec_weights.get(k, 0)
        diff   = rec_v - base_v
        bar    = "█" * int(rec_v * 20)
        dc     = "green" if diff > 0.01 else "red" if diff < -0.01 else "dim"
        lines.append(f"  {k:<8} {bar:<10} {rec_v:.3f}  "
                     f"[{dc}]({diff:+.3f} vs base {base_v:.3f})[/{dc}]")

    lines += [
        "",
        "[dim]To use recommended weights, update SCORE_WEIGHTS in config.py.[/dim]",
    ]
    console.print(Panel("\n".join(lines),
                        title="[bold cyan]Walk-Forward Optimisation Results[/bold cyan]",
                        border_style="cyan", width=90))

    # Per-window table
    if not windows:
        return

    table = Table(title="[bold cyan]Per-Window Results[/bold cyan]",
                  box=box.SIMPLE_HEAVY, header_style="bold white on dark_blue")
    table.add_column("Window",   justify="center", width=7)
    table.add_column("OOS Sharpe", justify="center", width=12)
    table.add_column("Base Sharpe", justify="center", width=12)
    table.add_column("Win %",    justify="center", width=8)
    table.add_column("Avg Ret %", justify="center", width=10)
    table.add_column("Trades",   justify="center", width=7)
    table.add_column("Opt Weights (rsi/macd/bb/ma/vol)", width=40)

    for w in windows:
        oos_sh   = w.get("oos_sharpe", 0)
        base_sh  = w.get("base_oos_sharpe", 0)
        sc       = "green" if oos_sh > 1 else "yellow" if oos_sh > 0 else "red"
        opt_w    = w.get("opt_weights", {})
        w_str    = " / ".join(f"{opt_w.get(k,0):.3f}" for k in keys)
        table.add_row(
            str(w["window"]),
            f"[{sc}]{oos_sh:.2f}[/{sc}]",
            f"{base_sh:.2f}",
            f"{w.get('oos_win_rate', 0):.1f}%",
            f"{w.get('oos_avg_return', 0):.2f}%",
            str(w.get("oos_n_trades", 0)),
            w_str,
        )

    console.print()
    console.print(table)
