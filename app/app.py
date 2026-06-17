from __future__ import annotations

import urllib.error
import json
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .alerts import evaluate_local_alerts, read_recent_alerts
from .config import DATA_DIR, get_massive_api_key, get_private_dashboard_token, load_portfolio_config, load_watchlist_config
from .dashboard import public_alert, public_plan, render_dashboard
from .goal import compute_goal_snapshot
from .market_data import fetch_histories
from .market_forecast import CORE_SYMBOLS, build_market_forecast, market_session_state
from .market_monitor import read_notification_status
from .options_walls import fetch_live_option_walls_for_watchlist, fetch_options_walls
from .strategy_engine import build_ranked_plans


app = FastAPI(title="Portfolio Recovery Agent")


STATE: dict[str, Any] = {
    "goal": compute_goal_snapshot(load_portfolio_config()).to_dict(),
    "plans": [],
    "alerts": [],
    "forecast": None,
    "forecast_error": None,
    "notification_status": {},
    "live_options_walls": None,
    "last_scan": None,
    "error": None,
}


def load_latest_forecast() -> dict[str, Any] | None:
    forecast_path = DATA_DIR / "latest_premarket_forecast.json"
    if not forecast_path.exists():
        return None
    return json.loads(forecast_path.read_text(encoding="utf-8"))


def save_forecast_artifact(forecast: dict[str, Any]) -> None:
    rendered = json.dumps(forecast, indent=2)
    (DATA_DIR / "latest_premarket_forecast.json").write_text(rendered, encoding="utf-8")
    forecast_dir = DATA_DIR / "forecasts"
    forecast_dir.mkdir(exist_ok=True)
    target = forecast_dir / f"forecast_asof_{forecast.get('as_of')}_for_{forecast.get('next_session')}.json"
    target.write_text(rendered, encoding="utf-8")


def require_private_access(token: str | None) -> None:
    expected = get_private_dashboard_token()
    if not expected or token != expected:
        raise HTTPException(status_code=404, detail="Not Found")


def public_summary() -> dict[str, Any]:
    plans = [public_plan(plan) for plan in STATE.get("plans", [])]
    alerts = [public_alert(alert) for alert in STATE.get("alerts", [])]
    return {
        "project": "portfolio_recovery_agent",
        "last_scan": STATE.get("last_scan"),
        "error": STATE.get("error"),
        "candidate_count": len(plans),
        "entry_confirmed": sum(1 for plan in plans if plan.get("setup") == "Entry Confirmed"),
        "entry_watch": sum(1 for plan in plans if plan.get("setup") == "Entry Watch"),
        "forecast": STATE.get("forecast"),
        "forecast_error": STATE.get("forecast_error"),
        "notification_status": STATE.get("notification_status"),
        "live_options_walls": STATE.get("live_options_walls"),
        "plans": plans,
        "alerts": alerts,
    }


def refresh_state(run_scan: bool = False) -> dict[str, Any]:
    portfolio = load_portfolio_config()
    watchlist = load_watchlist_config()
    STATE["goal"] = compute_goal_snapshot(portfolio).to_dict()
    STATE["alerts"] = read_recent_alerts()
    STATE["notification_status"] = read_notification_status()
    try:
        latest_forecast = load_latest_forecast()
        if latest_forecast:
            STATE["forecast"] = latest_forecast
            STATE["forecast_error"] = None
    except Exception as exc:
        STATE["forecast_error"] = f"Forecast load failed: {exc}"

    if not run_scan:
        return STATE

    STATE["error"] = None
    STATE["forecast_error"] = None
    api_key = get_massive_api_key()
    if not api_key:
        STATE["error"] = "Missing MASSIVE_API_KEY. Add it to this project's .env file."
        return STATE

    symbols = sorted(set(["SPY", *CORE_SYMBOLS, *watchlist.get("etfs", []), *watchlist.get("stocks", [])]))
    try:
        histories = fetch_histories(symbols, api_key)
        plans = build_ranked_plans(histories, watchlist, portfolio)
        new_alerts = evaluate_local_alerts(plans)
        if market_session_state() != "regular_or_settlement":
            try:
                forecast = build_market_forecast(histories)
                reference_prices = {
                    symbol: forecast["indexes"][symbol]["close"]
                    for symbol in ("SPY", "QQQ")
                    if symbol in forecast.get("indexes", {})
                }
                options_walls = fetch_options_walls(
                    ["SPY", "QQQ"],
                    api_key,
                    expiration_date=forecast["next_session"],
                    reference_prices=reference_prices,
                )
                forecast = build_market_forecast(histories, options_walls=options_walls)
                save_forecast_artifact(forecast)
                STATE["forecast"] = forecast
            except Exception as exc:
                STATE["forecast_error"] = f"Forecast failed: {exc}"
        STATE["plans"] = plans
        STATE["alerts"] = [*new_alerts, *read_recent_alerts()]
        STATE["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except urllib.error.HTTPError as exc:
        STATE["error"] = f"Market data HTTP error: {exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        STATE["error"] = f"Market data network error: {exc.reason}"
    except Exception as exc:
        STATE["error"] = f"Scan failed: {exc}"
    return STATE


@app.on_event("startup")
def startup_event() -> None:
    refresh_state(run_scan=False)


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    refresh_state(run_scan=False)
    return HTMLResponse(render_dashboard(STATE, include_private=False))


@app.get("/private", response_class=HTMLResponse)
def private_home(token: str | None = None) -> HTMLResponse:
    require_private_access(token)
    refresh_state(run_scan=False)
    return HTMLResponse(render_dashboard(STATE, include_private=True))


@app.get("/refresh")
def refresh() -> RedirectResponse:
    refresh_state(run_scan=True)
    return RedirectResponse(url="/", status_code=303)


@app.get("/private/refresh")
def private_refresh(token: str | None = None) -> RedirectResponse:
    require_private_access(token)
    refresh_state(run_scan=True)
    return RedirectResponse(url=f"/private?token={token}", status_code=303)


@app.get("/api/refresh")
def api_refresh() -> JSONResponse:
    refresh_state(run_scan=True)
    return JSONResponse(public_summary())


@app.get("/api/summary")
def api_summary() -> JSONResponse:
    refresh_state(run_scan=False)
    return JSONResponse(public_summary())


@app.get("/api/alerts")
def api_alerts() -> JSONResponse:
    return JSONResponse({"alerts": [public_alert(alert) for alert in read_recent_alerts()]})


@app.get("/api/notification-status")
def api_notification_status() -> JSONResponse:
    return JSONResponse(read_notification_status())


@app.get("/api/market-forecast")
def api_market_forecast() -> JSONResponse:
    forecast = STATE.get("forecast") or load_latest_forecast()
    if not forecast:
        return JSONResponse({"error": "No forecast has been generated yet."})
    return JSONResponse(forecast)


@app.get("/api/live-options-walls")
def api_live_options_walls() -> JSONResponse:
    api_key = get_massive_api_key()
    if not api_key:
        return JSONResponse({"error": "Missing MASSIVE_API_KEY. Add it to this project's .env file."}, status_code=400)
    try:
        payload = fetch_live_option_walls_for_watchlist(load_watchlist_config(), api_key)
        STATE["live_options_walls"] = payload
        return JSONResponse(payload)
    except urllib.error.HTTPError as exc:
        return JSONResponse({"error": f"Options wall HTTP error: {exc.code} {exc.reason}"}, status_code=502)
    except urllib.error.URLError as exc:
        return JSONResponse({"error": f"Options wall network error: {exc.reason}"}, status_code=502)
    except Exception as exc:
        return JSONResponse({"error": f"Options wall refresh failed: {exc}"}, status_code=500)


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "project": "portfolio_recovery_agent",
            "last_scan": STATE.get("last_scan"),
            "plans": len(STATE.get("plans", [])),
            "error": STATE.get("error"),
        }
    )
