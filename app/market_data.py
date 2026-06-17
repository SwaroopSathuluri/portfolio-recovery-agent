from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


def fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def daily_bar_date(timestamp_ms: int | float) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def utc_bar_time(timestamp_ms: int | float) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def fetch_daily_history(ticker: str, api_key: str, lookback_days: int = 420) -> list[dict[str, Any]]:
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    url = (
        "https://api.massive.com/v2/aggs/ticker/"
        f"{urllib.parse.quote(ticker)}/range/1/day/{start_date:%Y-%m-%d}/{end_date:%Y-%m-%d}"
        f"?adjusted=true&sort=asc&limit=5000&apiKey={urllib.parse.quote(api_key)}"
    )
    rows = fetch_json(url).get("results", [])
    return [
        {
            "date": daily_bar_date(row["t"]),
            "open": float(row["o"]),
            "high": float(row["h"]),
            "low": float(row["l"]),
            "close": float(row["c"]),
            "volume": float(row["v"]),
        }
        for row in rows
    ]


def fetch_histories(symbols: list[str], api_key: str, lookback_days: int = 420) -> dict[str, list[dict[str, Any]]]:
    histories: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        histories[symbol] = fetch_daily_history(symbol, api_key, lookback_days=lookback_days)
    return histories


def fetch_intraday_history(
    ticker: str,
    api_key: str,
    date_str: str,
    multiplier: int = 5,
    timespan: str = "minute",
) -> list[dict[str, Any]]:
    url = (
        "https://api.massive.com/v2/aggs/ticker/"
        f"{urllib.parse.quote(ticker)}/range/{multiplier}/{urllib.parse.quote(timespan)}/{date_str}/{date_str}"
        f"?adjusted=true&sort=asc&limit=5000&apiKey={urllib.parse.quote(api_key)}"
    )
    rows = fetch_json(url).get("results", [])
    return [
        {
            "date": daily_bar_date(row["t"]),
            "time_utc": utc_bar_time(row["t"]),
            "timestamp_ms": int(row["t"]),
            "open": float(row["o"]),
            "high": float(row["h"]),
            "low": float(row["l"]),
            "close": float(row["c"]),
            "volume": float(row["v"]),
        }
        for row in rows
    ]


def _url_with_api_key(url: str, api_key: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "apiKey" not in query:
        query["apiKey"] = [api_key]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))


def fetch_option_chain_snapshot(
    ticker: str,
    api_key: str,
    expiration_date: str | None = None,
    limit: int = 250,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "limit": str(limit),
        "apiKey": api_key,
    }
    if expiration_date:
        params["expiration_date"] = expiration_date

    url = (
        "https://api.massive.com/v3/snapshot/options/"
        f"{urllib.parse.quote(ticker)}?{urllib.parse.urlencode(params)}"
    )
    rows: list[dict[str, Any]] = []
    for _page in range(max_pages):
        payload = fetch_json(url)
        rows.extend(payload.get("results", []))
        next_url = payload.get("next_url")
        if not next_url:
            break
        url = _url_with_api_key(str(next_url), api_key)
    return rows


def fetch_option_contracts(
    ticker: str,
    api_key: str,
    expiration_date_gte: str | None = None,
    limit: int = 1000,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "underlying_ticker": ticker,
        "limit": str(limit),
        "apiKey": api_key,
    }
    if expiration_date_gte:
        params["expiration_date.gte"] = expiration_date_gte

    url = "https://api.massive.com/v3/reference/options/contracts?" + urllib.parse.urlencode(params)
    rows: list[dict[str, Any]] = []
    for _page in range(max_pages):
        payload = fetch_json(url)
        rows.extend(payload.get("results", []))
        next_url = payload.get("next_url")
        if not next_url:
            break
        url = _url_with_api_key(str(next_url), api_key)
    return rows
