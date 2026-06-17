from __future__ import annotations

import argparse
import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.config import get_massive_api_key
from app.indicators import pct_change
from app.market_data import fetch_daily_history, fetch_intraday_history


EASTERN = ZoneInfo("America/New_York")


def bar_time_et(bar: dict) -> str:
    return datetime.fromisoformat(str(bar["time_utc"])).astimezone(EASTERN).strftime("%H:%M ET")


def session_bars(bars: list[dict]) -> list[dict]:
    return [
        bar
        for bar in bars
        if time(9, 30) <= datetime.fromisoformat(str(bar["time_utc"])).astimezone(EASTERN).time() < time(16, 0)
    ]


def rolling_vwap(bars: list[dict], idx: int) -> float:
    selected = bars[: idx + 1]
    volume = sum(float(bar["volume"]) for bar in selected)
    dollar_volume = sum(float(bar["close"]) * float(bar["volume"]) for bar in selected)
    return dollar_volume / volume if volume else 0.0


def audit_symbol(symbol: str, date: str, api_key: str) -> dict:
    daily = fetch_daily_history(symbol, api_key, lookback_days=10)
    row_map = {row["date"]: row for row in daily}
    current = row_map[date]
    prior_dates = [row["date"] for row in daily if row["date"] < date]
    previous = row_map[prior_dates[-1]]

    bars = session_bars(fetch_intraday_history(symbol, api_key, date, multiplier=5))
    opening = bars[:6]
    opening_high = max(float(bar["high"]) for bar in opening)
    opening_low = min(float(bar["low"]) for bar in opening)

    first_break_high = None
    first_break_low = None
    first_vwap_loss = None
    for idx, bar in enumerate(bars):
        close = float(bar["close"])
        vwap = rolling_vwap(bars, idx)
        if idx >= 6 and first_break_high is None and close > opening_high:
            first_break_high = {"time": bar_time_et(bar), "close": round(close, 2), "vwap": round(vwap, 2)}
        if idx >= 6 and first_break_low is None and close < opening_low:
            first_break_low = {"time": bar_time_et(bar), "close": round(close, 2), "vwap": round(vwap, 2)}
        if idx >= 1:
            prev_close = float(bars[idx - 1]["close"])
            prev_vwap = rolling_vwap(bars, idx - 1)
            if first_vwap_loss is None and prev_close >= prev_vwap and close < vwap:
                first_vwap_loss = {"time": bar_time_et(bar), "close": round(close, 2), "vwap": round(vwap, 2)}

    return {
        "symbol": symbol,
        "date": date,
        "previous_close": round(float(previous["close"]), 2),
        "open": round(float(current["open"]), 2),
        "high": round(float(current["high"]), 2),
        "low": round(float(current["low"]), 2),
        "close": round(float(current["close"]), 2),
        "daily_change_pct": round(pct_change(float(current["close"]), float(previous["close"])), 2),
        "open_to_close_pct": round(pct_change(float(current["close"]), float(current["open"])), 2),
        "opening_range_high": round(opening_high, 2),
        "opening_range_low": round(opening_low, 2),
        "first_break_opening_high": first_break_high,
        "first_break_opening_low": first_break_low,
        "first_vwap_loss": first_vwap_loss,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--symbols", nargs="+", default=["SPY", "QQQ"])
    args = parser.parse_args()
    api_key = get_massive_api_key()
    if not api_key:
        raise SystemExit("Missing MASSIVE_API_KEY")
    print(json.dumps([audit_symbol(symbol, args.date, api_key) for symbol in args.symbols], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
