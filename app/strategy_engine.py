from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from typing import Any

from .indicators import annualized_volatility, atr, ema_series, macd, max_drawdown, pct_change, rsi, sma


MIN_HISTORY_BARS = 220
LEVERAGED_SYMBOLS = {"TQQQ", "SQQQ", "SOXL", "SOXS", "UPRO", "SPXU", "SPXL", "SPXS"}


@dataclass(frozen=True)
class TradePlan:
    instrument: str
    setup: str
    score: int
    lane: str
    close: float
    ema20: float
    sma50: float
    sma200: float
    rsi14: float
    macd_line: float
    macd_signal: float
    atr_pct: float
    volume_ratio: float
    relative_strength_20d: float
    momentum_20d: float
    stop: float
    target1: float
    target2: float
    reward_to_risk: float
    suggested_cash_position: float
    max_trade_risk: float
    options_candidate: str
    exit_rule: str
    notes: str
    date: str
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _option_candidate(
    symbol: str,
    score: int,
    setup: str,
    atr_pct: float,
    rsi14: float,
    close: float,
    target1: float,
    stop: float,
    kind: str,
) -> str:
    if symbol in LEVERAGED_SYMBOLS:
        return "Avoid options on leveraged ETF until risk model is stricter."
    if setup in {"Avoid", "Defensive"}:
        return "No bullish option. If already holding shares, evaluate protective put or collar."
    if score >= 80 and atr_pct <= 8 and rsi14 < 72:
        width = max(1, round((target1 - close) / 5) * 5)
        return (
            "Call debit spread candidate: 30-60 DTE, buy 0.55-0.65 delta call, "
            f"sell near target zone around {close + width:.2f}. Needs live chain validation."
        )
    if score >= 70 and atr_pct <= 6:
        return "Shares/ETF preferred first. Options only after bid-ask spread and IV are acceptable."
    if kind == "stock" and score >= 65:
        return "Long call candidate only with small size and 45+ DTE; spread preferred over naked call."
    return "No option edge yet. Wait for cleaner timing."


def _setup_from_score(score: int, latest_close: float, ema20: float, sma50_value: float, sma200_value: float) -> str:
    if latest_close < sma200_value:
        return "Defensive"
    if latest_close < sma50_value:
        return "Avoid"
    if score >= 80 and latest_close > ema20:
        return "Entry Confirmed"
    if score >= 65:
        return "Entry Watch"
    if score >= 50:
        return "Hold / Manage"
    return "Avoid"


def analyze_symbol(
    symbol: str,
    kind: str,
    history: list[dict[str, Any]],
    benchmark_history: list[dict[str, Any]],
    portfolio: dict[str, Any],
) -> TradePlan | None:
    if len(history) < MIN_HISTORY_BARS or len(benchmark_history) < MIN_HISTORY_BARS:
        return None

    closes = [float(row["close"]) for row in history]
    highs = [float(row["high"]) for row in history]
    lows = [float(row["low"]) for row in history]
    volumes = [float(row["volume"]) for row in history]
    benchmark_closes = [float(row["close"]) for row in benchmark_history]

    latest_close = closes[-1]
    ema20 = ema_series(closes, 20)[-1]
    sma50_value = sma(closes, 50)
    sma200_value = sma(closes, 200)
    rsi14 = rsi(closes, 14)
    macd_line, macd_signal, _hist = macd(closes)
    atr14 = atr(highs, lows, closes, 14)
    atr_pct = (atr14 / latest_close) * 100 if latest_close else 0.0
    avg_volume20 = statistics.mean(volumes[-20:])
    volume_ratio = volumes[-1] / avg_volume20 if avg_volume20 else 0.0
    momentum_20d = pct_change(closes[-1], closes[-21])
    benchmark_momentum = pct_change(benchmark_closes[-1], benchmark_closes[-21])
    relative_strength_20d = momentum_20d - benchmark_momentum
    drawdown_6m = max_drawdown(closes[-126:])
    volatility = annualized_volatility(closes[-126:])

    above20 = latest_close > ema20
    above50 = latest_close > sma50_value
    above200 = latest_close > sma200_value
    trend_aligned = ema20 > sma50_value > sma200_value
    bullish_rsi = 45 <= rsi14 <= 68
    extended_rsi = rsi14 > 74
    bullish_macd = macd_line > macd_signal
    strong_rs = relative_strength_20d > 0
    stable_vol = atr_pct <= 6

    score = 0
    score += 12 if above20 else 0
    score += 15 if above50 else 0
    score += 10 if above200 else 0
    score += 18 if trend_aligned else 0
    score += 12 if bullish_rsi else 0
    score += 10 if bullish_macd else 0
    score += 8 if volume_ratio >= 1 else 0
    score += 10 if strong_rs else 0
    score += 5 if stable_vol else 0
    score -= 10 if extended_rsi else 0
    score -= 8 if drawdown_6m < -25 else 0
    score -= 5 if volatility > 55 else 0
    score -= 8 if symbol in LEVERAGED_SYMBOLS else 0
    score = max(0, min(100, score))

    setup = _setup_from_score(score, latest_close, ema20, sma50_value, sma200_value)
    stop = latest_close - (1.5 * atr14)
    if above50:
        stop = max(stop, sma50_value)
    if stop >= latest_close:
        stop = latest_close - (1.25 * atr14)
    target1 = latest_close + (1.5 * atr14)
    target2 = latest_close + (3.0 * atr14)
    risk_per_share = max(0.01, latest_close - stop)
    reward_to_risk = (target1 - latest_close) / risk_per_share

    account_value = float(portfolio.get("current_value", 0))
    risk_pct = float(portfolio.get("max_risk_per_trade_pct", 1))
    max_position_pct = float(portfolio.get("max_single_position_pct", 20))
    risk_budget = account_value * (risk_pct / 100)
    size_by_risk = (risk_budget / risk_per_share) * latest_close
    size_by_cap = account_value * (max_position_pct / 100)
    suggested_cash_position = min(size_by_risk, size_by_cap)

    if setup in {"Entry Confirmed", "Entry Watch"} and score >= 75:
        lane = "ETF/share buy + option spread candidate"
    elif setup in {"Entry Confirmed", "Entry Watch"}:
        lane = "ETF/share buy candidate"
    elif setup == "Hold / Manage":
        lane = "Manage existing only"
    else:
        lane = "Wait / protect capital"

    if kind == "stock" and score >= 75 and atr_pct <= 8:
        lane = "Share buy + defined-risk option candidate"

    options_candidate = _option_candidate(symbol, score, setup, atr_pct, rsi14, latest_close, target1, stop, kind)
    exit_rule = (
        f"Exit or reassess on close below {stop:.2f}, failed 50-day reclaim, "
        "MACD bear cross, or portfolio risk breach."
    )

    notes: list[str] = []
    if trend_aligned:
        notes.append("20 EMA > 50 SMA > 200 SMA")
    if above50:
        notes.append("above 50-day")
    if bullish_macd:
        notes.append("MACD bullish")
    if bullish_rsi:
        notes.append("RSI constructive")
    if strong_rs:
        notes.append("beating SPY over 20 days")
    if extended_rsi:
        notes.append("RSI extended")
    if symbol in LEVERAGED_SYMBOLS:
        notes.append("leveraged ETF, smaller size")

    return TradePlan(
        instrument=symbol,
        setup=setup,
        score=score,
        lane=lane,
        close=round(latest_close, 2),
        ema20=round(ema20, 2),
        sma50=round(sma50_value, 2),
        sma200=round(sma200_value, 2),
        rsi14=round(rsi14, 1),
        macd_line=round(macd_line, 2),
        macd_signal=round(macd_signal, 2),
        atr_pct=round(atr_pct, 2),
        volume_ratio=round(volume_ratio, 2),
        relative_strength_20d=round(relative_strength_20d, 2),
        momentum_20d=round(momentum_20d, 2),
        stop=round(stop, 2),
        target1=round(target1, 2),
        target2=round(target2, 2),
        reward_to_risk=round(reward_to_risk, 2),
        suggested_cash_position=round(max(0, suggested_cash_position), 2),
        max_trade_risk=round(risk_budget, 2),
        options_candidate=options_candidate,
        exit_rule=exit_rule,
        notes="; ".join(notes),
        date=str(history[-1]["date"]),
        kind=kind,
    )


def build_ranked_plans(
    histories: dict[str, list[dict[str, Any]]],
    watchlist: dict[str, list[str]],
    portfolio: dict[str, Any],
) -> list[dict[str, Any]]:
    benchmark = histories.get("SPY", [])
    plans: list[TradePlan] = []
    for symbol in watchlist.get("etfs", []):
        plan = analyze_symbol(symbol, "etf", histories.get(symbol, []), benchmark, portfolio)
        if plan:
            plans.append(plan)
    for symbol in watchlist.get("stocks", []):
        plan = analyze_symbol(symbol, "stock", histories.get(symbol, []), benchmark, portfolio)
        if plan:
            plans.append(plan)
    plans.sort(key=lambda item: (item.score, item.relative_strength_20d, item.reward_to_risk), reverse=True)
    return [plan.to_dict() for plan in plans]
