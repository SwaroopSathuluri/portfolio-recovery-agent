from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .alerts import record_alert_once
from .config import CONFIG_DIR, DATA_DIR, get_massive_api_key, get_pushover_credentials, read_json
from .indicators import atr, ema_series, macd, pct_change, rsi, sma
from .market_data import fetch_daily_history, fetch_intraday_history
from .notifiers.pushover import send_pushover_message


EASTERN = ZoneInfo("America/New_York")
MONITOR_STATUS_PATH = DATA_DIR / "notification_status.json"
MONITOR_ALERT_LOG_PATH = DATA_DIR / "monitor_alerts.jsonl"


@dataclass(frozen=True)
class IntradaySnapshot:
    symbol: str
    market_date: str
    last_time_et: str
    close: float
    previous_close: float
    vwap: float
    opening_range_high: float
    opening_range_low: float
    session_high: float
    session_low: float
    bars: int
    above_vwap: bool
    broke_opening_high: bool
    lost_opening_low: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_notification_rules() -> dict[str, Any]:
    return read_json(CONFIG_DIR / "notification_rules.json", {})


def pushover_ready() -> bool:
    token, user_key = get_pushover_credentials()
    return bool(token and user_key)


def _today_market_date() -> str:
    return datetime.now(EASTERN).date().isoformat()


def _bar_datetime_et(bar: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(bar["time_utc"])).astimezone(EASTERN)


def _regular_session_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = time(9, 30)
    end = time(16, 0)
    return [bar for bar in bars if start <= _bar_datetime_et(bar).time() < end]


def _vwap(bars: list[dict[str, Any]]) -> float:
    dollar_volume = sum(float(bar["close"]) * float(bar["volume"]) for bar in bars)
    volume = sum(float(bar["volume"]) for bar in bars)
    return dollar_volume / volume if volume else 0.0


def _daily_levels(history: list[dict[str, Any]]) -> dict[str, float]:
    closes = [float(row["close"]) for row in history]
    highs = [float(row["high"]) for row in history]
    lows = [float(row["low"]) for row in history]
    macd_line, macd_signal, _hist = macd(closes)
    atr14 = atr(highs, lows, closes, 14)
    return {
        "close": closes[-1],
        "prev_close": closes[-2],
        "ema20": ema_series(closes, 20)[-1],
        "sma50": sma(closes, 50),
        "sma200": sma(closes, 200),
        "atr14": atr14,
        "atr_pct": (atr14 / closes[-1]) * 100 if closes[-1] else 0.0,
        "rsi14": rsi(closes, 14),
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "extension_from_ema20_pct": pct_change(closes[-1], ema_series(closes, 20)[-1]),
    }


def _intraday_snapshot(symbol: str, bars: list[dict[str, Any]], opening_range_minutes: int, bar_minutes: int) -> IntradaySnapshot | None:
    session_bars = _regular_session_bars(bars)
    opening_count = max(1, opening_range_minutes // bar_minutes)
    if len(session_bars) < opening_count:
        return None

    opening = session_bars[:opening_count]
    last = session_bars[-1]
    previous = session_bars[-2] if len(session_bars) >= 2 else session_bars[-1]
    opening_high = max(float(bar["high"]) for bar in opening)
    opening_low = min(float(bar["low"]) for bar in opening)
    session_high = max(float(bar["high"]) for bar in session_bars)
    session_low = min(float(bar["low"]) for bar in session_bars)
    close = float(last["close"])
    current_vwap = _vwap(session_bars)
    return IntradaySnapshot(
        symbol=symbol,
        market_date=str(last["date"]),
        last_time_et=_bar_datetime_et(last).strftime("%H:%M ET"),
        close=round(close, 2),
        previous_close=round(float(previous["close"]), 2),
        vwap=round(current_vwap, 2),
        opening_range_high=round(opening_high, 2),
        opening_range_low=round(opening_low, 2),
        session_high=round(session_high, 2),
        session_low=round(session_low, 2),
        bars=len(session_bars),
        above_vwap=close > current_vwap,
        broke_opening_high=close > opening_high,
        lost_opening_low=close < opening_low,
    )


def _monitor_alert(
    symbol: str,
    alert_type: str,
    priority: int,
    title: str,
    message: str,
    snapshot: IntradaySnapshot,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": alert_type,
        "priority": priority,
        "instrument": symbol,
        "setup": alert_type.replace("_", " ").title(),
        "score": details.get("score", 0),
        "message": message,
        "title": title,
        "source": "market_monitor",
        "snapshot": snapshot.to_dict(),
        "details": details,
    }


def _append_monitor_alert(alert: dict[str, Any]) -> None:
    with MONITOR_ALERT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(alert) + "\n")


def _write_status(status: dict[str, Any]) -> None:
    MONITOR_STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")


def read_notification_status() -> dict[str, Any]:
    if not MONITOR_STATUS_PATH.exists():
        return {
            "last_run": None,
            "pushover_ready": pushover_ready(),
            "message": "Monitor has not run yet.",
        }
    return json.loads(MONITOR_STATUS_PATH.read_text(encoding="utf-8"))


def _deliver_alert(alert: dict[str, Any], dry_run: bool, dashboard_url: str) -> dict[str, Any]:
    _append_monitor_alert(alert)
    if dry_run:
        return {"sent": False, "dry_run": True, "reason": "dry run"}
    if not pushover_ready():
        return {"sent": False, "dry_run": False, "reason": "missing Pushover credentials"}
    response = send_pushover_message(
        title=str(alert.get("title", "Market Alert")),
        message=str(alert.get("message", "")),
        priority=int(alert.get("priority", 0)),
        url=dashboard_url,
    )
    return {"sent": response.get("status") == 1, "dry_run": False, "response": response}


def evaluate_monitor_rules(
    snapshots: dict[str, IntradaySnapshot],
    daily_levels: dict[str, dict[str, float]],
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    enabled_rules = rules.get("rules", {})
    breadth_required = float(rules.get("breadth_above_vwap_required_pct", 60))
    pullback_tolerance_atr_pct = float(rules.get("pullback_tolerance_atr_pct", 0.25))
    breadth_symbols = [symbol for symbol in rules.get("breadth_symbols", []) if symbol in snapshots]
    breadth_count = len(breadth_symbols) or 1
    breadth_above_vwap = sum(1 for symbol in breadth_symbols if snapshots[symbol].above_vwap) / breadth_count * 100

    for symbol in rules.get("symbols", []):
        snapshot = snapshots.get(symbol)
        levels = daily_levels.get(symbol)
        if not snapshot or not levels:
            continue

        score = 0
        score += 25 if snapshot.close > snapshot.vwap else 0
        score += 25 if snapshot.broke_opening_high else 0
        score += 20 if breadth_above_vwap >= breadth_required else 0
        score += 15 if snapshot.close > levels["ema20"] else 0
        score += 15 if levels["ema20"] > levels["sma50"] > levels["sma200"] else 0

        if enabled_rules.get("opening_range_confirmation", True):
            if snapshot.broke_opening_high and snapshot.above_vwap and breadth_above_vwap >= breadth_required:
                alerts.append(
                    _monitor_alert(
                        symbol=symbol,
                        alert_type="OPENING_RANGE_LONG",
                        priority=1,
                        title=f"{symbol} Opening Range Long",
                        message=(
                            f"{symbol} broke opening range high {snapshot.opening_range_high:.2f} and holds above "
                            f"VWAP {snapshot.vwap:.2f}. Breadth above VWAP: {breadth_above_vwap:.0f}%. "
                            "Entry only after confirmation; do not chase if spread/price runs away."
                        ),
                        snapshot=snapshot,
                        details={"score": score, "breadth_above_vwap_pct": round(breadth_above_vwap, 1)},
                    )
                )

        if enabled_rules.get("vwap_loss_exit", True):
            crossed_below_vwap = snapshot.previous_close >= snapshot.vwap and snapshot.close < snapshot.vwap
            if crossed_below_vwap or snapshot.lost_opening_low:
                alerts.append(
                    _monitor_alert(
                        symbol=symbol,
                        alert_type="VWAP_OR_RANGE_EXIT",
                        priority=1,
                        title=f"{symbol} Exit/Risk Warning",
                        message=(
                            f"{symbol} lost VWAP/opening range structure. Close {snapshot.close:.2f}, "
                            f"VWAP {snapshot.vwap:.2f}, opening low {snapshot.opening_range_low:.2f}. "
                            "Avoid fresh longs; manage or reduce risk."
                        ),
                        snapshot=snapshot,
                        details={"score": 0, "breadth_above_vwap_pct": round(breadth_above_vwap, 1)},
                    )
                )

        if enabled_rules.get("daily_20ema_reclaim", True):
            tolerance = levels["atr14"] * pullback_tolerance_atr_pct
            touched_ema20_area = snapshot.session_low <= levels["ema20"] + tolerance
            reclaimed_ema20 = snapshot.previous_close <= levels["ema20"] < snapshot.close
            trend_ok = levels["ema20"] > levels["sma50"] > levels["sma200"]
            if trend_ok and touched_ema20_area and reclaimed_ema20:
                alerts.append(
                    _monitor_alert(
                        symbol=symbol,
                        alert_type="EMA20_RECLAIM",
                        priority=1,
                        title=f"{symbol} 20 EMA Reclaim",
                        message=(
                            f"{symbol} reclaimed daily 20 EMA {levels['ema20']:.2f} after a pullback. "
                            f"Close {snapshot.close:.2f}; VWAP {snapshot.vwap:.2f}. "
                            "This is the cleaner swing-entry pattern than chasing strength."
                        ),
                        snapshot=snapshot,
                        details={"score": score, "ema20": round(levels["ema20"], 2)},
                    )
                )

        if enabled_rules.get("daily_50sma_failure_exit", True):
            if snapshot.close < levels["sma50"]:
                alerts.append(
                    _monitor_alert(
                        symbol=symbol,
                        alert_type="SMA50_FAILURE_EXIT",
                        priority=2,
                        title=f"{symbol} 50 SMA Failure",
                        message=(
                            f"{symbol} is below 50 SMA {levels['sma50']:.2f}. Close {snapshot.close:.2f}. "
                            "This is a hard risk-management alert: close, hedge, or avoid new longs."
                        ),
                        snapshot=snapshot,
                        details={"score": 0, "sma50": round(levels["sma50"], 2)},
                    )
                )

        if enabled_rules.get("chase_risk_warning", True):
            extended = snapshot.close > levels["ema20"] * 1.035
            big_prior_move = levels["extension_from_ema20_pct"] > 3.0 or levels["rsi14"] > 68
            if extended and big_prior_move and not snapshot.broke_opening_high:
                alerts.append(
                    _monitor_alert(
                        symbol=symbol,
                        alert_type="CHASE_RISK_WARNING",
                        priority=0,
                        title=f"{symbol} Chase Risk",
                        message=(
                            f"{symbol} is extended above 20 EMA {levels['ema20']:.2f} without a clean opening-range break. "
                            "Wait for pullback/reclaim or confirmed breakout."
                        ),
                        snapshot=snapshot,
                        details={"score": 0, "extension_from_ema20_pct": round(levels["extension_from_ema20_pct"], 2)},
                    )
                )

    return alerts


def run_monitor_once(market_date: str | None = None, dry_run: bool = True) -> dict[str, Any]:
    rules = load_notification_rules()
    api_key = get_massive_api_key()
    if not api_key:
        status = {
            "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": "Missing MASSIVE_API_KEY",
            "pushover_ready": pushover_ready(),
            "dry_run": dry_run,
        }
        _write_status(status)
        return status

    market_date = market_date or _today_market_date()
    bar_minutes = int(rules.get("bar_minutes", 5))
    opening_range_minutes = int(rules.get("opening_range_minutes", 30))
    symbols = sorted(set([*rules.get("symbols", []), *rules.get("breadth_symbols", [])]))

    snapshots: dict[str, IntradaySnapshot] = {}
    daily_levels: dict[str, dict[str, float]] = {}
    errors: list[str] = []

    for symbol in symbols:
        try:
            daily_history = fetch_daily_history(symbol, api_key)
            daily_levels[symbol] = _daily_levels(daily_history)
            intraday = fetch_intraday_history(symbol, api_key, market_date, multiplier=bar_minutes)
            snapshot = _intraday_snapshot(symbol, intraday, opening_range_minutes, bar_minutes)
            if snapshot:
                snapshots[symbol] = snapshot
            else:
                errors.append(f"{symbol}: not enough regular-session intraday bars for {market_date}")
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")

    raw_alerts = evaluate_monitor_rules(snapshots, daily_levels, rules)
    created: list[dict[str, Any]] = []
    delivered: list[dict[str, Any]] = []
    dashboard_url = str(rules.get("dashboard_url", "http://127.0.0.1:8010/"))

    for alert in raw_alerts:
        snapshot = alert.get("snapshot", {})
        key = f"monitor:{snapshot.get('market_date')}:{alert.get('instrument')}:{alert.get('type')}"
        if not record_alert_once(alert, key):
            continue
        created.append(alert)
        delivered.append(_deliver_alert(alert, dry_run=dry_run or not bool(rules.get("send_pushover", True)), dashboard_url=dashboard_url))

    status = {
        "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_date": market_date,
        "dry_run": dry_run,
        "pushover_ready": pushover_ready(),
        "symbols_checked": symbols,
        "snapshots": {symbol: snapshot.to_dict() for symbol, snapshot in snapshots.items()},
        "alerts_evaluated": len(raw_alerts),
        "alerts_created": len(created),
        "alerts_sent": sum(1 for item in delivered if item.get("sent")),
        "delivery_results": delivered,
        "latest_alerts": created[-10:],
        "errors": errors,
    }
    _write_status(status)
    return status
