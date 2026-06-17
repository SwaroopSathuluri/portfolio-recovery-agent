from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DATA_DIR


ALERT_LOG_PATH = DATA_DIR / "alerts.jsonl"
ALERT_STATE_PATH = DATA_DIR / "alert_state.json"


def _load_state() -> dict[str, Any]:
    if not ALERT_STATE_PATH.exists():
        return {}
    return json.loads(ALERT_STATE_PATH.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    ALERT_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _append_alert(alert: dict[str, Any]) -> None:
    with ALERT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(alert) + "\n")


def record_alert_once(alert: dict[str, Any], key: str) -> bool:
    state = _load_state()
    if state.get(key):
        return False
    state[key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _append_alert(alert)
    _save_state(state)
    return True


def evaluate_local_alerts(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create local alerts only. Phone delivery comes in a later phase."""
    state = _load_state()
    created: list[dict[str, Any]] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for plan in plans:
        alert_type = ""
        priority = 0
        if plan["setup"] == "Entry Confirmed" and plan["score"] >= 80:
            alert_type = "ENTRY_CONFIRMED"
            priority = 1
        elif plan["setup"] == "Entry Watch" and plan["score"] >= 70:
            alert_type = "ENTRY_WATCH"
            priority = 0
        elif plan["setup"] in {"Avoid", "Defensive"}:
            alert_type = "RISK_AVOID"
            priority = -1

        if not alert_type:
            continue

        key = f"{plan['instrument']}:{alert_type}:{plan['date']}"
        if state.get(key):
            continue

        alert = {
            "created_at": now,
            "type": alert_type,
            "priority": priority,
            "instrument": plan["instrument"],
            "setup": plan["setup"],
            "score": plan["score"],
            "message": (
                f"{plan['instrument']} {alert_type.replace('_', ' ')} | "
                f"score {plan['score']} | close {plan['close']} | stop {plan['stop']}"
            ),
            "plan": plan,
        }
        _append_alert(alert)
        state[key] = now
        created.append(alert)

    _save_state(state)
    return created


def read_recent_alerts(limit: int = 50) -> list[dict[str, Any]]:
    if not ALERT_LOG_PATH.exists():
        return []
    lines = ALERT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    alerts = [json.loads(line) for line in lines[-limit:] if line.strip()]
    alerts.reverse()
    return alerts
