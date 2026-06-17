from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .market_data import fetch_option_chain_snapshot, fetch_option_contracts


EASTERN = ZoneInfo("America/New_York")
DEFAULT_RELEVANCE_PCT = 3.0
LIVE_WALL_SYMBOL_LIMIT = 60


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_pct(strike: float, spot: float) -> float:
    if spot <= 0:
        return 0.0
    return ((strike / spot) - 1) * 100


def _level(strike: float, open_interest: int, spot: float) -> dict[str, Any]:
    return {
        "strike": round(strike, 2),
        "open_interest": int(open_interest),
        "distance_pct": round(_distance_pct(strike, spot), 2),
    }


def _top_levels(levels: list[tuple[float, int]], spot: float, limit: int = 5) -> list[dict[str, Any]]:
    return [_level(strike, oi, spot) for strike, oi in sorted(levels, key=lambda item: item[1], reverse=True)[:limit]]


def _max_pain(call_oi: dict[float, int], put_oi: dict[float, int]) -> float | None:
    strikes = sorted(set(call_oi) | set(put_oi))
    if not strikes:
        return None

    best_strike = None
    best_payout = None
    for settlement in strikes:
        call_payout = sum(max(0.0, settlement - strike) * oi for strike, oi in call_oi.items())
        put_payout = sum(max(0.0, strike - settlement) * oi for strike, oi in put_oi.items())
        payout = call_payout + put_payout
        if best_payout is None or payout < best_payout:
            best_payout = payout
            best_strike = settlement
    return round(best_strike, 2) if best_strike is not None else None


def _wall_adjustment(
    spot: float,
    put_wall: dict[str, Any] | None,
    call_wall: dict[str, Any] | None,
    near_put_oi: int,
    near_call_oi: int,
) -> tuple[float, float, str]:
    edge = 0.0
    sideways_bonus = 0.0
    reads: list[str] = []

    if put_wall and call_wall:
        put_strike = float(put_wall["strike"])
        call_strike = float(call_wall["strike"])
        range_width_pct = ((call_strike - put_strike) / spot) * 100 if spot else 0.0
        put_distance = ((spot - put_strike) / spot) * 100 if spot else 0.0
        call_distance = ((call_strike - spot) / spot) * 100 if spot else 0.0

        if range_width_pct <= 1.2:
            sideways_bonus += 4.0
            reads.append("tight wall range favors pin/chop until one wall breaks")
        elif range_width_pct <= 2.0:
            sideways_bonus += 2.0
            reads.append("moderate wall range favors confirmation over chasing")

        if 0 <= put_distance <= 0.35:
            edge += 1.0
            sideways_bonus += 1.0
            reads.append("spot is sitting near put-wall support")
        if 0 <= call_distance <= 0.35:
            edge -= 1.0
            sideways_bonus += 1.0
            reads.append("spot is sitting near call-wall resistance")

        if call_distance > put_distance + 0.75:
            edge += 0.8
            reads.append("more upside room before the call wall")
        elif put_distance > call_distance + 0.75:
            edge -= 0.8
            reads.append("call wall is closer than put-wall support")

    elif put_wall:
        edge += 0.8
        reads.append("nearby put wall gives a defined downside level")
    elif call_wall:
        edge -= 0.8
        reads.append("nearby call wall gives a defined upside cap")

    if near_call_oi and near_put_oi:
        near_pcr = near_put_oi / near_call_oi
        if near_pcr >= 1.35:
            edge += 0.5
            reads.append("nearby put OI is heavier than call OI")
        elif near_pcr <= 0.75:
            edge -= 0.5
            reads.append("nearby call OI is heavier than put OI")

    if not reads:
        reads.append("options walls are neutral from current spot")

    return round(edge, 2), round(sideways_bonus, 2), "; ".join(reads)


def analyze_option_walls(
    symbol: str,
    chain: list[dict[str, Any]],
    expiration_date: str,
    reference_price: float | None = None,
    relevance_pct: float = DEFAULT_RELEVANCE_PCT,
) -> dict[str, Any]:
    call_oi: dict[float, int] = defaultdict(int)
    put_oi: dict[float, int] = defaultdict(int)
    underlying_price = reference_price
    latest_update: int | None = None

    for row in chain:
        details = row.get("details") or {}
        contract_type = details.get("contract_type")
        strike = _float_or_none(details.get("strike_price"))
        if contract_type not in {"call", "put"} or strike is None:
            continue

        open_interest = int(row.get("open_interest") or 0)
        if open_interest <= 0:
            continue

        if contract_type == "call":
            call_oi[strike] += open_interest
        else:
            put_oi[strike] += open_interest

        asset = row.get("underlying_asset") or {}
        asset_price = _float_or_none(asset.get("price"))
        if asset_price:
            underlying_price = asset_price
        updated = asset.get("last_updated")
        if isinstance(updated, int):
            latest_update = updated if latest_update is None else max(latest_update, updated)

    if not underlying_price or underlying_price <= 0:
        return {
            "symbol": symbol,
            "expiration_date": expiration_date,
            "available": False,
            "error": "Missing underlying price in option snapshot.",
        }

    spot = float(underlying_price)
    calls_above = [
        (strike, oi)
        for strike, oi in call_oi.items()
        if strike >= spot and abs(_distance_pct(strike, spot)) <= relevance_pct
    ]
    puts_below = [
        (strike, oi)
        for strike, oi in put_oi.items()
        if strike <= spot and abs(_distance_pct(strike, spot)) <= relevance_pct
    ]
    near_calls = [
        (strike, oi)
        for strike, oi in call_oi.items()
        if abs(_distance_pct(strike, spot)) <= relevance_pct
    ]
    near_puts = [
        (strike, oi)
        for strike, oi in put_oi.items()
        if abs(_distance_pct(strike, spot)) <= relevance_pct
    ]

    call_wall_tuple = max(calls_above, key=lambda item: item[1]) if calls_above else None
    put_wall_tuple = max(puts_below, key=lambda item: item[1]) if puts_below else None
    call_wall = _level(*call_wall_tuple, spot) if call_wall_tuple else None
    put_wall = _level(*put_wall_tuple, spot) if put_wall_tuple else None
    near_call_oi = sum(oi for _strike, oi in near_calls)
    near_put_oi = sum(oi for _strike, oi in near_puts)
    total_call_oi = sum(call_oi.values())
    total_put_oi = sum(put_oi.values())
    edge, sideways_bonus, interpretation = _wall_adjustment(spot, put_wall, call_wall, near_put_oi, near_call_oi)

    updated_at = None
    if latest_update:
        updated_at = datetime.fromtimestamp(latest_update / 1_000_000_000, tz=EASTERN).isoformat()

    return {
        "symbol": symbol,
        "expiration_date": expiration_date,
        "available": bool(call_oi or put_oi),
        "underlying_price": round(spot, 2),
        "relevance_pct": relevance_pct,
        "put_wall": put_wall,
        "call_wall": call_wall,
        "max_pain": _max_pain(call_oi, put_oi),
        "total_put_oi": int(total_put_oi),
        "total_call_oi": int(total_call_oi),
        "put_call_oi_ratio": round(total_put_oi / total_call_oi, 2) if total_call_oi else None,
        "near_put_oi": int(near_put_oi),
        "near_call_oi": int(near_call_oi),
        "near_put_call_oi_ratio": round(near_put_oi / near_call_oi, 2) if near_call_oi else None,
        "top_put_walls": _top_levels(puts_below, spot),
        "top_call_walls": _top_levels(calls_above, spot),
        "forecast_adjustment": {
            "edge": edge,
            "sideways_bonus": sideways_bonus,
        },
        "interpretation": interpretation,
        "updated_at": updated_at,
    }


def nearest_option_expiration(symbol: str, api_key: str, from_date: str | None = None) -> str | None:
    start = from_date or datetime.now(EASTERN).date().isoformat()
    contracts = fetch_option_contracts(symbol, api_key, expiration_date_gte=start, limit=1000, max_pages=2)
    expirations = sorted({str(row.get("expiration_date")) for row in contracts if row.get("expiration_date")})
    return expirations[0] if expirations else None


def _wall_summary(symbol: str, kind: str, wall: dict[str, Any], fallback_expiration: str | None = None) -> dict[str, Any]:
    if not wall.get("available"):
        return {
            "symbol": symbol,
            "kind": kind,
            "available": False,
            "expiration_date": wall.get("expiration_date") or fallback_expiration,
            "error": wall.get("error") or "Options wall data unavailable.",
        }

    put_wall = wall.get("put_wall") or {}
    call_wall = wall.get("call_wall") or {}
    return {
        "symbol": symbol,
        "kind": kind,
        "available": True,
        "expiration_date": wall.get("expiration_date"),
        "underlying_price": wall.get("underlying_price"),
        "put_wall_strike": put_wall.get("strike"),
        "put_wall_oi": put_wall.get("open_interest"),
        "put_wall_distance_pct": put_wall.get("distance_pct"),
        "call_wall_strike": call_wall.get("strike"),
        "call_wall_oi": call_wall.get("open_interest"),
        "call_wall_distance_pct": call_wall.get("distance_pct"),
        "max_pain": wall.get("max_pain"),
        "near_put_call_oi_ratio": wall.get("near_put_call_oi_ratio"),
        "total_put_call_oi_ratio": wall.get("put_call_oi_ratio"),
        "interpretation": wall.get("interpretation"),
        "updated_at": wall.get("updated_at"),
        "top_put_walls": wall.get("top_put_walls", []),
        "top_call_walls": wall.get("top_call_walls", []),
    }


def fetch_live_option_wall(symbol: str, kind: str, api_key: str, from_date: str | None = None) -> dict[str, Any]:
    try:
        expiration = nearest_option_expiration(symbol, api_key, from_date=from_date)
        if not expiration:
            return {
                "symbol": symbol,
                "kind": kind,
                "available": False,
                "error": "No listed option expiry found.",
            }
        chain = fetch_option_chain_snapshot(symbol, api_key, expiration_date=expiration, max_pages=20)
        wall = analyze_option_walls(symbol, chain, expiration_date=expiration, relevance_pct=DEFAULT_RELEVANCE_PCT)
        return _wall_summary(symbol, kind, wall, fallback_expiration=expiration)
    except Exception as exc:
        return {
            "symbol": symbol,
            "kind": kind,
            "available": False,
            "error": str(exc),
        }


def fetch_live_option_walls_for_watchlist(
    watchlist: dict[str, list[str]],
    api_key: str,
    from_date: str | None = None,
    max_workers: int = 6,
) -> dict[str, Any]:
    requested_at = datetime.now(EASTERN)
    from_date = from_date or requested_at.date().isoformat()
    symbols: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, items in (("etf", watchlist.get("etfs", [])), ("stock", watchlist.get("stocks", []))):
        for raw_symbol in items:
            symbol = str(raw_symbol).upper()
            if symbol and symbol not in seen:
                seen.add(symbol)
                symbols.append((symbol, kind))

    symbols = symbols[:LIVE_WALL_SYMBOL_LIMIT]
    rows: list[dict[str, Any]] = []
    if symbols:
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
            futures = {
                executor.submit(fetch_live_option_wall, symbol, kind, api_key, from_date): symbol
                for symbol, kind in symbols
            }
            for future in as_completed(futures):
                rows.append(future.result())

    order = {symbol: index for index, (symbol, _kind) in enumerate(symbols)}
    rows.sort(key=lambda row: (0 if row.get("available") else 1, order.get(str(row.get("symbol")), 999)))
    available = sum(1 for row in rows if row.get("available"))
    return {
        "requested_at": requested_at.isoformat(),
        "from_date": from_date,
        "next_refresh_hint": (requested_at + timedelta(minutes=5)).isoformat(),
        "symbol_count": len(rows),
        "available_count": available,
        "rows": rows,
    }


def fetch_options_walls(
    symbols: list[str],
    api_key: str,
    expiration_date: str,
    reference_prices: dict[str, float] | None = None,
    relevance_pct: float = DEFAULT_RELEVANCE_PCT,
) -> dict[str, dict[str, Any]]:
    reference_prices = reference_prices or {}
    walls: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        try:
            chain = fetch_option_chain_snapshot(symbol, api_key, expiration_date=expiration_date)
            walls[symbol] = analyze_option_walls(
                symbol,
                chain,
                expiration_date=expiration_date,
                reference_price=reference_prices.get(symbol),
                relevance_pct=relevance_pct,
            )
        except Exception as exc:
            walls[symbol] = {
                "symbol": symbol,
                "expiration_date": expiration_date,
                "available": False,
                "error": str(exc),
            }
    return walls
