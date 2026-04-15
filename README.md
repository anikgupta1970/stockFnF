# NSE Stock Analyser

A fully algorithmic, terminal-based tool for analysing NSE-listed Indian stocks. It scores every stock across multiple technical and fundamental dimensions, ranks them by buy probability, generates ATR-scaled entry/stop/target levels, backtests the strategy on historical data, and lets you record and evaluate forward predictions.

---

## Features

| Feature | Detail |
|---|---|
| **General mode** | Daily candles · scores every stock · regime-aware weights · fundamentals blend |
| **Intraday/Swing mode** | 1-hour candles · VWAP · Stochastic · optimised for 1-5 day trades |
| **ATR-based trade levels** | Entry, stop-loss, and target calculated from Average True Range |
| **Market regime detection** | ADX classifies each stock as Trending / Ranging / Neutral and adjusts signal weights |
| **Fundamental scoring** | P/E, P/B, Revenue Growth, Debt/Equity, Profit Margin blended at 20% |
| **Built-in backtester** | Walk-forward, no lookahead bias, Sharpe ratio + drawdown metrics |
| **Prediction tracker** | Record today's picks, evaluate later whether stop or target was hit |
| **Smart caching** | OHLCV cached for 4h, fundamentals for 24h — fast repeated runs |
| **Full NSE universe** | Analyses ~2,100 NSE equities or NIFTY 50 only (your choice) |
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

# Force fresh data download (bypass 4h cache)
python3 main.py general --index nifty50 --no-cache
```

**Valid sector names:** `Banking`, `IT`, `Pharma`, `Auto`, `FMCG`, `Energy`, `Metals`, `Infrastructure`, `Consumer`, `Financial Services`, `Insurance`, `Telecom`, `Cement`, `Chemicals`, `Diversified`

### `predict.py` commands

```bash
# Record today's top picks (score ≥ 65) from NIFTY 50
python3 predict.py record

# Record only top 10 picks
python3 predict.py record --top 10

# Stricter — only high-conviction picks (score ≥ 70)
python3 predict.py record --threshold 70 --top 10

# Record from full NSE universe
python3 predict.py record --index all --top 20

# Check all open predictions — did they hit target or stop?
python3 predict.py evaluate

# View current state without fetching new prices
python3 predict.py list

# Use a separate file (e.g. for swing picks)
python3 predict.py record --file swing_predictions.json
python3 predict.py evaluate --file swing_predictions.json
```

### Typical daily workflow

```bash
source venv/bin/activate

# Morning — see today's top picks
python3 main.py general --index nifty50 --top 20

# Record the picks you want to track
python3 predict.py record --top 10 --threshold 68

# A few days later — check how they did
python3 predict.py evaluate
```

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
| `--index` | `nifty50` / `all` | NIFTY 50 only (~50 stocks, fast) or full NSE (~2,100 stocks, slow first run) |
| `--no-cache` | flag | Force fresh data download, ignore disk cache |

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
```

**Output columns — General mode**

| Column | Meaning |
|---|---|
| Score | 0-100 composite buy probability (≥70 strong, 55-69 watch, <55 avoid) |
| Entry ₹ | Current close price — suggested entry |
| Stop ₹ | Stop-loss level (entry − 1.5 × ATR) |
| Target ₹ | Take-profit level (entry + 2.5 × ATR) |
| Risk % | % distance from entry to stop |
| R:R | Reward-to-risk ratio (prefer ≥ 1.5) |
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

Records today's top picks with their trade levels and later evaluates whether the price hit the target or stop-loss.

```
python3 predict.py <command> [options]
```

| Command | What it does |
|---|---|
| `record` | Run analysis and save qualifying picks to `predictions.json` |
| `evaluate` | Fetch price history for all open picks and determine outcomes |
| `list` | Print current state of all predictions without fetching new data |

**Options**

| Option | Default | Description |
|---|---|---|
| `--top N` | all | Record only the top N picks |
| `--threshold SCORE` | 65 | Minimum score to record a pick |
| `--index` | `nifty50` | Stock universe (`nifty50` or `all`) |
| `--file PATH` | `predictions.json` | Custom file path for storing predictions |

**Workflow**

```bash
# Day 1 — record today's high-conviction picks (score ≥ 70, top 10)
python3 predict.py record --top 10 --threshold 70

# Any day after — evaluate all open predictions
python3 predict.py evaluate

# Just view the current state without fetching prices
python3 predict.py list
```

**Outcome logic**

For each open prediction the script walks forward through daily OHLC data:
- If the day's **low** touches or crosses the **stop** → `STOP HIT` (loss)
- If the day's **high** touches or crosses the **target** → `TARGET HIT` (win)
- If both happen on the same day → `STOP HIT` (conservative)
- If neither has happened yet → `OPEN` (shows current price and unrealised P&L)

Results include a win-rate summary and a sector breakdown of closed trades.

**Predictions are stored in `predictions.json`** — a plain JSON file you can open in any editor or import into Excel/Sheets.

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
| `ATR_MULTIPLIER_STOP` | `1.5` | Stop = entry − (1.5 × ATR) |
| `ATR_MULTIPLIER_TARGET` | `2.5` | Target = entry + (2.5 × ATR) |
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
