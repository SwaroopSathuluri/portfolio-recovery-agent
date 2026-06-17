# Portfolio Recovery Agent

Local research dashboard for recovery-focused trade planning across ETFs, stocks,
and defined-risk option ideas.

This project is intentionally separate from `swing_trading_project`.

## What it does first

- Tracks configurable recovery math from a local private portfolio file.
- Shows the monthly return required over the chosen recovery window.
- Scans a configurable ETF and stock watchlist when a market data key is present.
- Scores trend, momentum, volume, relative strength, volatility, and risk levels.
- Adds SPY/QQQ put-wall and call-wall context from option open interest to the market forecast.
- Suggests the best trade lane:
  - ETF/share purchase
  - call debit spread candidate
  - put debit spread or hedge candidate
  - wait / no trade
- Logs local alerts without sending phone notifications yet.

## What it does not do

- It does not auto-trade.
- It does not modify the existing swing bot.
- It does not send mobile alerts until the notification layer is enabled later.
- It does not guarantee that a recovery target can be reached.

## Setup

Create a `.env` file in this folder:

```text
MASSIVE_API_KEY=your_key_here
```

The app also checks the parent Trading folder for `.env` as a convenience, but
keeping a project-local `.env` is cleaner.

Install dependencies:

```bat
pip install -r requirements.txt
```

Run the local dashboard:

```bat
run_dashboard.cmd
```

Then open:

```text
http://127.0.0.1:8010
```

## Configuration

- `config/portfolio.json` stores account value, target, risk limits, and recovery window.
- `config/watchlist.json` stores ETF and stock tickers to scan.
- `data/alerts.jsonl` stores local alert events after scans.

## Later phases

1. Add full spread pricing, IV rank, and liquidity scoring on top of the option-chain data.
2. Add note ingestion from your investing PDFs and strategy document.
3. Add paper alert mode during market hours.
4. Add Pushover mobile notifications after local alerts are trustworthy.

## Intraday notifications

The project includes an intraday SPY/QQQ monitor:

```bat
run_monitor_once.cmd
```

This runs a dry check and logs monitor status without sending phone alerts.

To send phone alerts through Pushover, add these to `.env`:

```text
PUSHOVER_APP_TOKEN=your_pushover_app_token
PUSHOVER_USER_KEY=your_pushover_user_key
```

Then send one test:

```bat
python -B send_test_pushover.py
```

Start the monitor loop:

```bat
start_market_monitor.cmd
```

The monitor checks every 5 minutes and watches:

- Opening range confirmation
- VWAP / opening range failure
- Daily 20 EMA reclaim
- Daily 50 SMA failure
- Chase-risk warning

It suppresses duplicate alerts per symbol/rule/day.
