from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import CONFIG_DIR, read_json
from .indicators import annualized_volatility, atr, ema_series, macd, max_drawdown, pct_change, rsi, sma


CORE_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "XLK", "SMH", "XLF", "XLI", "TLT", "GLD"]
RISK_ON_SYMBOLS = ["QQQ", "IWM", "XLK", "SMH", "XLF", "XLI"]
DEFENSIVE_SYMBOLS = ["TLT", "GLD"]
EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class IndexForecast:
    symbol: str
    date: str
    close: float
    daily_change_pct: float
    five_day_change_pct: float
    twenty_day_change_pct: float
    ema20: float
    sma50: float
    sma200: float
    rsi14: float
    macd_line: float
    macd_signal: float
    atr_pct: float
    trend_score: int
    bias: str
    upside_probability: int
    sideways_probability: int
    downside_probability: int
    expected_move_pct: float
    entry_zone: str
    exit_zone: str
    invalidation: str
    notes: list[str]
    options_context: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _history_values(history: list[dict[str, Any]]) -> tuple[list[float], list[float], list[float], list[float]]:
    closes = [float(row["close"]) for row in history]
    highs = [float(row["high"]) for row in history]
    lows = [float(row["low"]) for row in history]
    volumes = [float(row["volume"]) for row in history]
    return closes, highs, lows, volumes


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _next_trading_day(last_date: str) -> str:
    current = datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current.isoformat()


def market_session_state(now: datetime | None = None) -> str:
    current = now or datetime.now(EASTERN)
    current = current.astimezone(EASTERN)
    if current.weekday() >= 5:
        return "closed"
    if current.time() < time(9, 30):
        return "premarket"
    if current.time() < time(16, 15):
        return "regular_or_settlement"
    return "closed"


def remove_unfinished_current_day(history: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    if not history:
        return history
    current = now or datetime.now(EASTERN)
    current = current.astimezone(EASTERN)
    last_date = str(history[-1].get("date"))
    if last_date == current.date().isoformat() and market_session_state(current) == "regular_or_settlement":
        return history[:-1]
    return history


def sanitize_histories_for_forecast(histories: dict[str, list[dict[str, Any]]], now: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    return {symbol: remove_unfinished_current_day(history, now=now) for symbol, history in histories.items()}


def _market_events(as_of: str) -> list[dict[str, Any]]:
    payload = read_json(CONFIG_DIR / "market_events.json", {"events": []})
    as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
    window_end = as_of_date + timedelta(days=3)
    events = []
    for event in payload.get("events", []):
        event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        if as_of_date <= event_date <= window_end:
            events.append(event)
    return events


def _technical_score(
    close: float,
    ema20: float,
    sma50_value: float,
    sma200_value: float,
    rsi14: float,
    macd_line: float,
    macd_signal: float,
    change_5d: float,
    change_20d: float,
    atr_pct: float,
) -> int:
    score = 50
    score += 9 if close > ema20 else -7
    score += 10 if close > sma50_value else -10
    score += 8 if close > sma200_value else -12
    score += 8 if ema20 > sma50_value > sma200_value else 0
    score += 6 if 45 <= rsi14 <= 68 else 0
    score -= 8 if rsi14 > 74 else 0
    score -= 7 if rsi14 < 38 else 0
    score += 6 if macd_line > macd_signal else -5
    score += 4 if change_5d > 0 else -3
    score += 5 if change_20d > 0 else -4
    score -= 4 if atr_pct > 4.5 else 0
    return round(_clamp(score, 0, 100))


def _probabilities(
    edge: float,
    event_penalty: float,
    atr_pct: float,
    chase_risk: float,
    sell_pressure: float,
    sideways_bonus: float = 0.0,
) -> tuple[int, int, int]:
    adjusted = edge - event_penalty
    sideways = (
        27
        + min(18, event_penalty * 2.6)
        + max(0, min(8, atr_pct * 1.2))
        + min(8, chase_risk * 1.8)
        + min(6, sell_pressure * 0.8)
        + min(8, max(0.0, sideways_bonus))
    )
    up = 37 + adjusted * 0.34 - min(5, chase_risk * 0.8) - min(7, sell_pressure * 0.9)
    down = 100 - up - sideways
    down += min(10, sell_pressure * 1.4)
    total_after_pressure = up + sideways + down
    up = up / total_after_pressure * 100
    sideways = sideways / total_after_pressure * 100
    down = down / total_after_pressure * 100
    if down < 12:
        down = 12
        up = 100 - sideways - down
    if up < 12:
        up = 12
        down = 100 - sideways - up
    total = up + sideways + down
    return round(up / total * 100), round(sideways / total * 100), round(down / total * 100)


def _bias(up: int, sideways: int, down: int) -> str:
    if up >= down + 12 and up >= sideways:
        return "Bullish"
    if down >= up + 12 and down >= sideways:
        return "Bearish"
    if up > down:
        return "Bullish-neutral"
    if down > up:
        return "Bearish-neutral"
    return "Neutral"


def _index_forecast(
    symbol: str,
    history: list[dict[str, Any]],
    breadth_edge: float,
    risk_edge: float,
    event_penalty: float,
    options_wall: dict[str, Any] | None = None,
) -> IndexForecast:
    closes, highs, lows, _volumes = _history_values(history)
    close = closes[-1]
    ema20 = ema_series(closes, 20)[-1]
    sma50_value = sma(closes, 50)
    sma200_value = sma(closes, 200)
    rsi14 = rsi(closes, 14)
    macd_line, macd_signal, _histogram = macd(closes)
    atr14 = atr(highs, lows, closes, 14)
    atr_pct = (atr14 / close) * 100 if close else 0.0
    day_range = max(0.01, highs[-1] - lows[-1])
    close_location = (close - lows[-1]) / day_range
    extension_pct = pct_change(close, ema20)
    daily_change = pct_change(closes[-1], closes[-2])
    change_5d = pct_change(closes[-1], closes[-6])
    change_20d = pct_change(closes[-1], closes[-21])
    score = _technical_score(
        close,
        ema20,
        sma50_value,
        sma200_value,
        rsi14,
        macd_line,
        macd_signal,
        change_5d,
        change_20d,
        atr_pct,
    )

    chase_risk = 0.0
    chase_risk += max(0.0, daily_change - 1.5) * 1.25
    chase_risk += max(0.0, extension_pct - 3.0) * 1.15
    chase_risk += max(0.0, rsi14 - 68) * 0.35
    if macd_line < macd_signal:
        chase_risk += min(2.0, abs(macd_line - macd_signal) / max(close, 1) * 200)

    sell_pressure = 0.0
    sell_pressure += max(0.0, 0.35 - close_location) * 14
    sell_pressure += max(0.0, -daily_change) * 1.5
    if close < ema20:
        sell_pressure += 3
    if macd_line < macd_signal:
        sell_pressure += 1.5

    momentum_edge = _clamp((change_20d - 2.0) * 0.75, -5.0, 5.0)
    five_day_edge = _clamp(change_5d * 0.35, -3.0, 3.0)
    extension_edge = -min(5.0, max(0.0, extension_pct - 2.5) * 0.8)
    options_adjustment = (options_wall or {}).get("forecast_adjustment", {}) if options_wall else {}
    options_edge = float(options_adjustment.get("edge", 0.0) or 0.0)
    options_sideways_bonus = float(options_adjustment.get("sideways_bonus", 0.0) or 0.0)
    edge = (score - 50) + breadth_edge + risk_edge + momentum_edge + five_day_edge + extension_edge + options_edge
    if daily_change > 2.2 and rsi14 > 66:
        edge -= 4
    if daily_change < -2.2 and rsi14 < 40:
        edge += 3
    edge -= chase_risk
    edge -= sell_pressure * 1.25
    up, sideways, down = _probabilities(
        edge,
        event_penalty,
        atr_pct,
        chase_risk,
        sell_pressure,
        sideways_bonus=options_sideways_bonus,
    )
    expected_move_pct = round(max(0.35, min(3.5, atr_pct * 0.75)), 2)
    entry_zone = (
        f"Prefer pullback/reclaim above {ema20:.2f}; breakout entry only if price holds above prior close {close:.2f}."
        if close > ema20
        else f"Wait for reclaim of 20 EMA {ema20:.2f}; no fresh long while below it."
    )
    exit_zone = f"Reduce risk below 20 EMA {ema20:.2f}; hard invalidation below 50 SMA {sma50_value:.2f}."
    invalidation = f"Daily close below {sma50_value:.2f}, MACD bear cross, or breadth below 45% above 50-day."
    if options_wall and options_wall.get("available"):
        put_wall = options_wall.get("put_wall") or {}
        call_wall = options_wall.get("call_wall") or {}
        put_strike = put_wall.get("strike")
        call_strike = call_wall.get("strike")
        if call_strike:
            entry_zone += f" Options confirmation improves on a hold above call wall {float(call_strike):.2f}."
        if put_strike:
            exit_zone += f" Watch put-wall support near {float(put_strike):.2f}."
            invalidation += f" Loss of put wall {float(put_strike):.2f} raises downside risk."
    notes: list[str] = []
    if close > ema20:
        notes.append("above 20 EMA")
    if close > sma50_value:
        notes.append("above 50 SMA")
    if close > sma200_value:
        notes.append("above 200 SMA")
    if ema20 > sma50_value > sma200_value:
        notes.append("trend stack aligned")
    if macd_line > macd_signal:
        notes.append("MACD bullish")
    if rsi14 > 70:
        notes.append("RSI extended")
    if daily_change > 2:
        notes.append("large one-day rally increases chase risk")
    if close_location < 0.25:
        notes.append("closed near session low, next-day follow-through risk")
    if extension_pct > 3:
        notes.append("extended above 20 EMA")
    if macd_line < macd_signal:
        notes.append("MACD below signal, wait for confirmation")
    if options_wall and options_wall.get("available"):
        if options_wall.get("interpretation"):
            notes.append(f"options walls: {options_wall['interpretation']}")
        if options_wall.get("max_pain") is not None:
            notes.append(f"max pain {float(options_wall['max_pain']):.2f}")

    return IndexForecast(
        symbol=symbol,
        date=str(history[-1]["date"]),
        close=round(close, 2),
        daily_change_pct=round(daily_change, 2),
        five_day_change_pct=round(change_5d, 2),
        twenty_day_change_pct=round(change_20d, 2),
        ema20=round(ema20, 2),
        sma50=round(sma50_value, 2),
        sma200=round(sma200_value, 2),
        rsi14=round(rsi14, 1),
        macd_line=round(macd_line, 2),
        macd_signal=round(macd_signal, 2),
        atr_pct=round(atr_pct, 2),
        trend_score=score,
        bias=_bias(up, sideways, down),
        upside_probability=up,
        sideways_probability=sideways,
        downside_probability=down,
        expected_move_pct=expected_move_pct,
        entry_zone=entry_zone,
        exit_zone=exit_zone,
        invalidation=invalidation,
        notes=notes,
        options_context=options_wall if options_wall and options_wall.get("available") else None,
    )


def _breadth(histories: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    eligible = []
    for symbol, history in histories.items():
        if len(history) < 220:
            continue
        closes, _highs, _lows, _volumes = _history_values(history)
        close = closes[-1]
        eligible.append(
            {
                "symbol": symbol,
                "above20": close > ema_series(closes, 20)[-1],
                "above50": close > sma(closes, 50),
                "above200": close > sma(closes, 200),
                "momentum20": pct_change(closes[-1], closes[-21]),
            }
        )
    count = len(eligible) or 1
    above20 = sum(1 for row in eligible if row["above20"]) / count * 100
    above50 = sum(1 for row in eligible if row["above50"]) / count * 100
    above200 = sum(1 for row in eligible if row["above200"]) / count * 100
    positive20 = sum(1 for row in eligible if row["momentum20"] > 0) / count * 100
    avg_momentum20 = sum(row["momentum20"] for row in eligible) / count
    edge = ((above50 - 50) * 0.16) + ((positive20 - 50) * 0.11) + avg_momentum20
    return {
        "symbols": len(eligible),
        "above20_pct": round(above20, 1),
        "above50_pct": round(above50, 1),
        "above200_pct": round(above200, 1),
        "positive20d_pct": round(positive20, 1),
        "avg_momentum20d_pct": round(avg_momentum20, 2),
        "edge": round(edge, 2),
    }


def _risk_appetite(histories: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    spy = histories.get("SPY", [])
    if len(spy) < 30:
        return {"edge": 0, "notes": ["SPY history missing"]}
    spy_closes = _history_values(spy)[0]
    spy_momentum = pct_change(spy_closes[-1], spy_closes[-21])
    spy_one_day = pct_change(spy_closes[-1], spy_closes[-2])
    notes: list[str] = []
    edge = 0.0
    comparisons: dict[str, float] = {}

    for symbol in RISK_ON_SYMBOLS:
        history = histories.get(symbol, [])
        if len(history) < 30:
            continue
        closes = _history_values(history)[0]
        rel = pct_change(closes[-1], closes[-21]) - spy_momentum
        one_day_rel = pct_change(closes[-1], closes[-2]) - spy_one_day
        comparisons[f"{symbol}_vs_SPY_20d"] = round(rel, 2)
        comparisons[f"{symbol}_vs_SPY_1d"] = round(one_day_rel, 2)
        if rel > 0:
            edge += 1.6
            notes.append(f"{symbol} outperforming SPY")
        else:
            edge -= 0.8
        if symbol in {"QQQ", "XLK", "SMH"} and one_day_rel < -0.7:
            edge -= 2.5
            notes.append(f"{symbol} one-day tech weakness")

    for symbol in DEFENSIVE_SYMBOLS:
        history = histories.get(symbol, [])
        if len(history) < 30:
            continue
        closes = _history_values(history)[0]
        rel = pct_change(closes[-1], closes[-21]) - spy_momentum
        one_day_rel = pct_change(closes[-1], closes[-2]) - spy_one_day
        comparisons[f"{symbol}_vs_SPY_20d"] = round(rel, 2)
        comparisons[f"{symbol}_vs_SPY_1d"] = round(one_day_rel, 2)
        if rel > 0:
            edge -= 1.5
            notes.append(f"{symbol} outperforming SPY, defensive bid")

    return {"edge": round(edge, 2), "comparisons": comparisons, "notes": notes[:8]}


def _event_penalty(events: list[dict[str, Any]]) -> float:
    penalty = 0.0
    for event in events:
        if event.get("risk") == "high":
            penalty += 3.5
        elif event.get("risk") == "medium":
            penalty += 1.5
    return min(8.0, penalty)


def strategy_playbook() -> list[dict[str, str]]:
    return [
        {
            "name": "Opening range confirmation",
            "entry": "After the first 15-30 minutes, go long only if SPY/QQQ hold above VWAP and break the opening range high with breadth positive.",
            "exit": "Exit on loss of VWAP, failed breakout back inside the range, or first target at 0.75-1.0x ATR.",
            "best_for": "High-probability intraday direction after the market shows its hand."
        },
        {
            "name": "20 EMA pullback continuation",
            "entry": "In an uptrend, buy a pullback that tags or slightly undercuts the 20 EMA, then reclaims it with RSI above 45.",
            "exit": "Stop below the pullback low or 1.5 ATR; take partials near prior high and trail the rest below rising 20 EMA.",
            "best_for": "Swing entries with better risk/reward than chasing green candles."
        },
        {
            "name": "50 SMA failure exit",
            "entry": "No fresh long if price is below the 50 SMA unless it reclaims and holds that level.",
            "exit": "Close or hedge if SPY/QQQ close below 50 SMA with MACD crossing bearish.",
            "best_for": "Avoiding portfolio damage during trend regime breaks."
        },
        {
            "name": "Defined-risk call spread",
            "entry": "Use only when trend score is 75+, RSI is not extremely extended, and expected target is at least 1.8x risk.",
            "exit": "Take profit at 50-70% of max gain; cut if underlying loses 20 EMA or option loses 40-50%.",
            "best_for": "Participating in upside without oversizing long calls."
        },
        {
            "name": "Event-risk cash filter",
            "entry": "Before FOMC/CPI/PPI, reduce new entries unless the setup is already confirmed and position size is smaller.",
            "exit": "Do not hold large short-dated options through binary macro events without a spread or hedge.",
            "best_for": "Preventing one headline from wrecking a good plan."
        }
    ]


def build_market_forecast(
    histories: dict[str, list[dict[str, Any]]],
    options_walls: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    histories = sanitize_histories_for_forecast(histories)
    spy = histories.get("SPY", [])
    qqq = histories.get("QQQ", [])
    if len(spy) < 220 or len(qqq) < 220:
        raise ValueError("Need at least 220 daily bars for SPY and QQQ")

    as_of = str(spy[-1]["date"])
    next_session = _next_trading_day(as_of)
    events = _market_events(next_session)
    breadth = _breadth(histories)
    risk = _risk_appetite(histories)
    penalty = _event_penalty(events)
    options_walls = options_walls or {}
    spy_forecast = _index_forecast("SPY", spy, breadth["edge"], risk["edge"], penalty, options_walls.get("SPY"))
    qqq_forecast = _index_forecast("QQQ", qqq, breadth["edge"], risk["edge"], penalty, options_walls.get("QQQ"))
    combined_up = round((spy_forecast.upside_probability + qqq_forecast.upside_probability) / 2)
    combined_sideways = round((spy_forecast.sideways_probability + qqq_forecast.sideways_probability) / 2)
    combined_down = 100 - combined_up - combined_sideways
    if combined_sideways >= max(combined_up, combined_down):
        if combined_up > combined_down:
            primary_direction = "Range / chop with bullish upside bias"
        elif combined_down > combined_up:
            primary_direction = "Range / chop with bearish downside bias"
        else:
            primary_direction = "Mixed / range likely"
    elif combined_up >= combined_down + 10:
        primary_direction = "Up / bullish continuation"
    elif combined_down >= combined_up + 10:
        primary_direction = "Down / bearish pressure"
    else:
        primary_direction = "Mixed / range likely"

    risk_note = "Normal sizing is acceptable only after confirmation."
    if events:
        risk_note = "Event risk is elevated. Favor smaller entries, defined risk, and confirmation after the open."
    if max(spy_forecast.daily_change_pct, qqq_forecast.daily_change_pct) > 2:
        risk_note += " Do not chase the opening print after a large prior-day rally."

    return {
        "as_of": as_of,
        "next_session": next_session,
        "primary_direction": primary_direction,
        "combined_probabilities": {
            "upside": combined_up,
            "sideways": combined_sideways,
            "downside": combined_down,
        },
        "risk_note": risk_note,
        "events": events,
        "breadth": breadth,
        "risk_appetite": risk,
        "options_walls": options_walls,
        "indexes": {
            "SPY": spy_forecast.to_dict(),
            "QQQ": qqq_forecast.to_dict(),
        },
        "strategy_playbook": strategy_playbook(),
        "model_note": (
            "Probabilities are a disciplined directional read from trend, momentum, breadth, risk appetite, "
            "volatility, and scheduled event risk. They are not guarantees."
        ),
    }
