from __future__ import annotations

import math


def sma(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"Need at least {period} values for SMA")
    return sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        raise ValueError(f"Need at least {period} values for EMA")
    seed = sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    result = [seed]
    for value in values[period:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError(f"Need more than {period} values for RSI")
    gains: list[float] = []
    losses: list[float] = []
    for idx in range(1, period + 1):
        change = values[idx] - values[idx - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for idx in range(period + 1, len(values)):
        change = values[idx] - values[idx - 1]
        gain = max(change, 0)
        loss = abs(min(change, 0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: list[float]) -> tuple[float, float, float]:
    if len(values) < 35:
        raise ValueError("Need at least 35 values for MACD")
    ema12 = ema_series(values, 12)
    ema26 = ema_series(values, 26)
    offset = len(ema12) - len(ema26)
    line = [ema12[idx + offset] - ema26[idx] for idx in range(len(ema26))]
    signal = ema_series(line, 9)
    histogram = line[-1] - signal[-1]
    return line[-1], signal[-1], histogram


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        raise ValueError(f"Need more than {period} bars for ATR")
    ranges: list[float] = []
    for idx, close in enumerate(closes):
        if idx == 0:
            ranges.append(highs[idx] - lows[idx])
            continue
        prev_close = closes[idx - 1]
        ranges.append(max(highs[idx] - lows[idx], abs(highs[idx] - prev_close), abs(lows[idx] - prev_close)))
    value = sum(ranges[:period]) / period
    for current in ranges[period:]:
        value = ((value * (period - 1)) + current) / period
    return value


def pct_change(new: float, old: float) -> float:
    return 0.0 if old == 0 else ((new - old) / old) * 100


def max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = min(worst, (value - peak) / peak)
    return worst * 100


def annualized_volatility(closes: list[float]) -> float:
    if len(closes) < 3:
        return 0.0
    returns = []
    for idx in range(1, len(closes)):
        if closes[idx - 1]:
            returns.append((closes[idx] / closes[idx - 1]) - 1)
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252) * 100
