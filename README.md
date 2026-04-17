# NSE Stock Analyser

A fully algorithmic, terminal-based tool for analysing NSE-listed Indian stocks. It scores every stock across multiple technical and fundamental dimensions, ranks them by buy probability, generates ATR-scaled entry/stop/target levels, backtests the strategy on historical data, and lets you record and evaluate forward predictions.

---

## Features

| Feature | Detail |
|---|---|
| **General mode** | Daily candles · scores every stock · regime-aware weights · fundamentals blend |
| **Intraday/Swing mode** | 1-hour candles · VWAP · Stochastic · optimised for 1-5 day trades |
| **ATR-based trade levels** | Entry, stop-loss, and target calculated from Average True Range — target multiplier varies by regime |
| **Market regime detection** | ADX classifies each stock as Trending / Ranging / Neutral and adjusts signal weights and R:R |
| **Market uptrend filter** | Checks NIFTY 50 vs 50-day MA before analysis — warns when market is in downtrend |
| **Signal confluence filter** | `--strict` flag: only shows stocks where MACD bullish + Golden cross + RSI<65 + Score≥70 all agree |
| **Fundamental scoring** | P/E, P/B, Revenue Growth, Debt/Equity, Profit Margin blended at 20% |
| **Built-in backtester** | Walk-forward, no lookahead bias; exits at ATR stop/target or max 10 days — Sharpe + drawdown |
| **Prediction tracker** | Record today's picks, evaluate later whether stop or target was hit |
| **Smart caching** | OHLCV cached for 4h, fundamentals for 24h — fast repeated runs |
| **Commodity ETFs** | Gold & Silver ETFs traded on NSE — same scoring and trade levels as stocks |
| **Full NSE universe** | Analyses ~2,100 NSE equities, NIFTY 50, or commodity ETFs (your choice) |
| **Rich terminal UI** | Colour-coded tables, score bars, sector summaries |

---

## Requirements

- Python 3.9 or higher
- Internet connection (NSE / Yahoo Finance APIs, no API key needed)

---

## Installation

```bash
# 1. Clone or unzip the project folder
cd stocks

# 2. Create a virtual environment
python3 -m venv venv

# 3. Activate it
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

# 4. Install dependencies
pip install -r requirements.txt
```

---

## Quick Start

```bash
# Always activate the virtual environment first
source venv/bin/activate

# Analyse NIFTY 50 — fastest way to get started
python3 main.py general --index nifty50 --top 20

# Swing / intraday picks from NIFTY 50
python3 main.py intraday --index nifty50 --top 10
```

---

## All Commands

### Setup (run once)

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### `main.py` commands

```bash
# NIFTY 50, general analysis, top 20 results
python3 main.py general --index nifty50 --top 20

# All NIFTY 50, no limit on results
python3 main.py general --index nifty50

# Full NSE universe (~2,100 stocks) — slow on first run, cached after
python3 main.py general --index all --top 50

# Filter to a specific sector
python3 main.py general --index nifty50 --sector Banking
python3 main.py general --index nifty50 --sector IT
python3 main.py general --index nifty50 --sector Pharma
python3 main.py general --index nifty50 --sector Auto
python3 main.py general --index nifty50 --sector FMCG

# Intraday / swing mode — 1h candles, signals for 1-5 day trades
python3 main.py intraday --index nifty50 --top 10
python3 main.py intraday --index all --top 20

# Fresher intraday signals — 15m candles (recommended for same-day trading)
python3 main.py intraday --index nifty50 --top 10 --interval 15m

# Very short-term — 5m candles (act within minutes)
python3 main.py intraday --index nifty50 --top 10 --interval 5m

# Commodity ETFs — Gold & Silver analysis
python3 main.py general --index commodities --no-market-filter
python3 main.py intraday --index commodities
python3 main.py general --index commodities --sector Gold --no-market-filter
python3 main.py general --index commodities --sector Silver --no-market-filter

# Force fresh data download (bypass 4h cache)
python3 main.py general --index nifty50 --no-cache

# Skip NIFTY market direction check (useful in sideways markets)
python3 main.py general --index nifty50 --no-market-filter

# Only show stocks where all 4 conditions align (strongest signals)
python3 main.py general --index nifty50 --strict
```

**Valid sector names (stocks):** `Banking`, `IT`, `Pharma`, `Auto`, `FMCG`, `Energy`, `Metals`, `Infrastructure`, `Consumer`, `Financial Services`, `Insurance`, `Telecom`, `Cement`, `Chemicals`, `Diversified`

**Valid sector names (commodities):** `Gold`, `Silver`

### `predict.py` commands

```bash
# ── General (multi-day) picks ──────────────────────────────────────────────

# Record NIFTY 50 general picks (score ≥ 65)
python3 predict.py record --mode general

# Top 10 only, stricter threshold
python3 predict.py record --mode general --top 10 --threshold 68

# Full NSE universe
python3 predict.py record --mode general --index all --top 20

# ── Intraday / swing picks (1-5 day trades) ───────────────────────────────

# Record NIFTY 50 intraday picks (1h candles)
python3 predict.py record --mode intraday

# Top 10, stricter threshold
python3 predict.py record --mode intraday --top 10 --threshold 68

# ── Force fresh data (bypass 4h cache) ───────────────────────────────────

python3 predict.py record --mode general  --no-cache --top 10
python3 predict.py record --mode intraday --no-cache --top 10

# ── Evaluate ──────────────────────────────────────────────────────────────

# Evaluate all open predictions (auto-uses daily or 1h candles per pick)
python3 predict.py evaluate

# View current state without fetching new prices
python3 predict.py list

# ── Separate files per mode (recommended) ────────────────────────────────

python3 predict.py record --mode general  --file general_preds.json
python3 predict.py record --mode intraday --file intraday_preds.json
python3 predict.py evaluate --file general_preds.json
python3 predict.py evaluate --file intraday_preds.json
```

> **Important for intraday:** Yahoo Finance only keeps ~60 days of 1-hour candle history.
> Run `evaluate` within 60 days of recording intraday picks or they will show as `OPEN` permanently.

### Choosing the Right Interval for Intraday

| Interval | Best for | Signal freshness | History used |
|---|---|---|---|
| `5m` | Scalping — act within minutes | Highest | Last 5 days |
| `15m` | Same-day trades — act within 30 min | High | Last 10 days |
| `30m` | Half-day trades | Medium | Last 20 days |
| `1h` | 1-5 day swing trades (default) | Lower | Last 1 month |

**Recommended:** Use `--interval 15m` for intraday trading. Signals update every 15 minutes instead of every hour — by the time you act, the signal is still valid.

### Typical daily workflow

```bash
source venv/bin/activate

# Morning — check market direction first, then see top picks
python3 main.py general  --index nifty50 --top 20          # includes automatic market uptrend check
python3 main.py intraday --index nifty50 --top 10 --interval 15m   # fresher intraday signals

# High-conviction picks only (all signals must agree)
python3 main.py general  --index nifty50 --strict

# If market is in downtrend but you still want to analyse
python3 main.py general  --index nifty50 --no-market-filter --top 20

# Record picks you want to track (add --no-cache to force fresh data)
python3 predict.py record --mode general  --top 10 --threshold 68 --file general_preds.json
python3 predict.py record --mode intraday --top 10 --threshold 65 --file intraday_preds.json

# Same day or next day — check intraday results
python3 predict.py evaluate --file intraday_preds.json

# After 5+ days — check general results
python3 predict.py evaluate --file general_preds.json
```

### When to use `--strict`

The `--strict` flag requires **all four conditions** to hold simultaneously:
- Score ≥ 70
- MACD bullish (MACD above signal line)
- Golden cross (20-day MA above 50-day MA)
- RSI < 65 (not overbought)

Use `--strict` when you want only the highest-conviction setups, e.g. before deploying larger capital or when the market itself is in a confirmed uptrend. On most days, fewer than 5 NIFTY 50 stocks will pass all four conditions.

### Key output to watch

| Score | Meaning |
|---|---|
| ≥ 70 | Strong buy signal |
| 55–69 | Watch — potential setup |
| < 55 | Avoid |

| R:R | Meaning |
|---|---|
| ≥ 2.0 | Excellent risk/reward |
| 1.5–2.0 | Acceptable |
| < 1.5 | Skip the trade |

---

## Usage

### `main.py` — Core Analyser

```
python3 main.py <mode> [options]
```

| Argument | Values | Description |
|---|---|---|
| `mode` | `general` / `intraday` | Daily multi-day view or 1h swing view |
| `--top N` | integer | Show only the top N stocks |
| `--sector NAME` | Banking, IT, Pharma, Auto, FMCG … | Filter results to one sector |
| `--index` | `nifty50` / `all` / `commodities` | NIFTY 50, full NSE (~2,100 stocks), or Gold & Silver ETFs |
| `--no-cache` | flag | Force fresh data download, ignore disk cache |
| `--no-market-filter` | flag | Skip the NIFTY 50 uptrend check — useful in sideways or recovering markets |
| `--strict` | flag | Only show stocks meeting ALL 4 confluence conditions (strongest signals) |
| `--interval` | `5m` / `15m` / `30m` / `1h` | Candle size for intraday mode (default: `1h`). Smaller = fresher signals, tighter stops |

**Examples**

```bash
# All NIFTY 50 stocks, general analysis, top 20
python3 main.py general --index nifty50 --top 20

# All NSE stocks, filter to IT sector
python3 main.py general --index all --sector IT

# NIFTY 50 intraday picks, top 10
python3 main.py intraday --index nifty50 --top 10

# Force fresh data (ignore cache)
python3 main.py general --index nifty50 --no-cache

# Only show highest-conviction picks (all 4 conditions must agree)
python3 main.py general --index nifty50 --strict

# Run even when market is in downtrend
python3 main.py general --index nifty50 --no-market-filter --top 20

# Gold & Silver ETF analysis
python3 main.py general --index commodities --no-market-filter
python3 main.py general --index commodities --sector Gold --no-market-filter
```

**Output columns — General mode**

| Column | Meaning |
|---|---|
| Score | 0-100 composite buy probability (≥70 strong, 55-69 watch, <55 avoid) |
| Entry ₹ | Current close price — suggested entry |
| Stop ₹ | Stop-loss level (entry − 1.5 × ATR) |
| Target ₹ | Take-profit level — multiplier varies by regime: Trending 3.5×ATR, Neutral 2.5×ATR, Ranging 2.0×ATR |
| Risk % | % distance from entry to stop (varies per stock's ATR) |
| R:R | Reward-to-risk ratio — Trending 2.3, Neutral 1.7, Ranging 1.3 |
| Regime | Trending / Ranging / Neutral (affects signal weights) |
| RSI | 14-day RSI — green if oversold (<30), red if overbought (>70) |
| MACD | Bull ▲ if MACD is above its signal line |
| MA | Golden if 20-day MA is above 50-day MA; Death otherwise |
| Vol× | Today's volume as a multiple of 20-day average |
| Key Signals | Top 2 reasons driving the score |

**Output columns — Intraday mode** adds:

| Column | Meaning |
|---|---|
| Stoch | Stochastic %K — oversold <20 (green), overbought >80 (red) |
| VWAP | Whether price is above or below the session VWAP |

---

### `predict.py` — Prediction Tracker

Records top picks (general or intraday) with their trade levels and later evaluates whether the price hit the target or stop-loss. Both modes are supported in the same file or separate files.

```
python3 predict.py <command> [options]
```

| Command | What it does |
|---|---|
| `record` | Run analysis and save qualifying picks to a JSON file |
| `evaluate` | Fetch price history for all open picks and determine outcomes |
| `list` | Print current state of all predictions without fetching new data |

**Options**

| Option | Default | Description |
|---|---|---|
| `--mode` | `general` | `general` (daily candles) or `intraday` (1h candles) |
| `--top N` | all | Record only the top N picks |
| `--threshold SCORE` | 65 | Minimum score to record a pick |
| `--index` | `nifty50` | Stock universe (`nifty50` or `all`) |
| `--no-cache` | off | Force fresh data download, ignore the 4h disk cache |
| `--file PATH` | `predictions.json` | Custom file path for storing predictions |

**Outcome logic**

For each open prediction the script walks forward bar-by-bar through price history:
- If the bar's **low** touches or crosses the **stop** → `STOP HIT` (loss)
- If the bar's **high** touches or crosses the **target** → `TARGET HIT` (win)
- If both happen in the same bar → `STOP HIT` (conservative)
- If neither has happened yet → `OPEN` (shows current price and unrealised P&L)

General picks use **daily** candles. Intraday picks use **1h** candles for finer-grained evaluation.

> **Intraday limit:** Yahoo Finance only retains ~60 days of 1h history. Evaluate intraday picks within that window.

Results include overall win rate, per-mode win rate, and a sector breakdown of closed trades.

**Predictions are stored as JSON** — open in any editor or import into Excel/Sheets.

---

## Commodity ETFs

The tool supports Gold and Silver ETFs traded on NSE via `--index commodities`. These are analysed identically to stocks — same scoring, same ATR-based trade levels, same backtest.

### Covered ETFs

| ETF | Type | Ticker |
|---|---|---|
| Nippon India ETF Gold BeES | Gold | `GOLDBEES.NS` |
| HDFC Gold ETF | Gold | `GOLDIETF.NS` |
| Axis Gold ETF | Gold | `AXISGOLD.NS` |
| Nippon India ETF Silver BeES | Silver | `SILVERBEES.NS` |
| HDFC Silver ETF | Silver | `HDFCSILVER.NS` |
| ICICI Prudential Silver ETF | Silver | `SILVERIETF.NS` |

### Commands

```bash
# All Gold & Silver ETFs
python3 main.py general --index commodities --no-market-filter

# Gold only
python3 main.py general --index commodities --sector Gold --no-market-filter

# Silver only
python3 main.py general --index commodities --sector Silver --no-market-filter

# Intraday swing picks on commodities
python3 main.py intraday --index commodities
```

### Notes on Commodity ETFs vs Stocks

| Aspect | Stocks | Commodity ETFs |
|---|---|---|
| Volume | Higher, more liquid | Lower — expect Vol× of 0.1-0.5 |
| Volatility | Higher | Lower — Gold/Silver trend slowly |
| Stop hits | More frequent | Less frequent — wider ATR |
| Signals | Frequent | Rare — score rarely crosses 65 |
| Market filter | Apply | Use `--no-market-filter` (gold is counter-cyclical) |

> Gold often moves **opposite** to equities — it rises when stock markets fall. The market uptrend filter (NIFTY check) is designed for stocks, so always use `--no-market-filter` when analysing commodities.

---

## How the Score Works

Each stock is scored 0-100. The composite score is a weighted sum of five sub-signals:

| Signal | Default Weight | What it measures |
|---|---|---|
| RSI (14) | 25% | Momentum — oversold zones score higher |
| MACD (12/26/9) | 25% | Trend direction and histogram momentum |
| Bollinger Bands (20) | 20% | Price position within the band — near lower band scores higher |
| Moving Averages (20/50) | 20% | Golden/Death cross and MA gap direction |
| Volume ratio | 10% | High-volume up-moves score higher; high-volume down-moves score lower |

**Regime adjustment** — ADX is used to classify each stock:
- **Trending** (ADX > 25): MACD and MA weights are boosted; RSI and BB are reduced
- **Ranging** (ADX < 20): RSI and BB weights are boosted; MACD and MA are reduced
- **Neutral**: base weights are used unchanged

**Fundamentals blend (general mode)** — when fundamental data is available, the technical score is scaled to 80% and fundamental score (P/E, P/B, revenue growth, debt/equity, profit margin) contributes the remaining 20%.

---

## Project Structure

```
stocks/
├── main.py           # Entry point — argument parsing, orchestration
├── predict.py        # Prediction recorder and evaluator
├── config.py         # Tickers, weights, periods, ATR multipliers
├── data_fetcher.py   # OHLCV fetch (NSEPython → yfinance fallback) + disk cache
├── universe.py       # Downloads full NSE equity list (~2,100 tickers)
├── indicators.py     # RSI, MACD, BB, MA, ATR, Stochastic, VWAP, ADX
├── regime.py         # Market regime detection and weight adjustment
├── scorer.py         # Per-stock scoring and ranking logic
├── fundamentals.py   # P/E, P/B, growth, debt fetching and scoring
├── backtester.py     # Walk-forward backtest engine (no lookahead bias)
├── display.py        # Rich terminal tables and summary panels
├── requirements.txt  # Python dependencies
└── predictions.json  # Created automatically when you run predict.py record
```

---

## Configuration

All tunable parameters are in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `SCORE_WEIGHTS` | `rsi:0.25, macd:0.25, bb:0.20, ma:0.20, volume:0.10` | Weights for the composite score |
| `SWING_WEIGHTS` | `volume:0.25` (higher) | Weights used in intraday mode |
| `ATR_MULTIPLIER_STOP` | `1.5` | Stop = entry − (1.5 × ATR) — fixed for all regimes |
| `ATR_MULTIPLIER_TARGET` | `2.5` | Default target multiplier (overridden by regime: Trending=3.5, Neutral=2.5, Ranging=2.0) |
| `DEFAULT_PERIOD` | `6mo` | Lookback for general mode |
| `SWING_PERIOD` | `1mo` | Lookback for intraday mode (hourly candles) |

---

## Caching

On first run data is downloaded from NSE / Yahoo Finance and saved to `~/.stocks_cache/`. Subsequent runs within the TTL window skip the download.

| Cache type | TTL | Location |
|---|---|---|
| OHLCV price data | 4 hours | `~/.stocks_cache/data/` |
| Fundamental data | 24 hours | `~/.stocks_cache/fundamentals/` |
| NSE ticker list | 24 hours | `~/.stocks_cache/nse_equity_list.csv` |

To bypass the cache entirely: `--no-cache`

---

## Dependencies

| Package | Purpose |
|---|---|
| `yfinance` | OHLCV price data (fallback) and fundamental info |
| `nsepython` | NSE direct API for daily OHLCV (primary source) |
| `pandas` | Data manipulation |
| `numpy` | Numerical operations |
| `ta` | Technical indicators (RSI, MACD, BB, ATR, ADX, Stochastic) |
| `scipy` | Percentile ranking |
| `rich` | Terminal colour output and tables |
| `requests` | HTTP for NSE universe download |

---

## Disclaimer

This tool is for **educational and research purposes only**. Scores and signals are purely algorithmic and do not constitute financial advice. Always do your own research before making any investment decisions.
