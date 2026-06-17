from __future__ import annotations

import html
import json
from typing import Any


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _pct(value: float) -> str:
    return f"{value:.2f}%"


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in plan.items()
        if key not in {"max_trade_risk", "suggested_cash_position"}
    }


def public_alert(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": alert.get("created_at"),
        "type": alert.get("type"),
        "priority": alert.get("priority"),
        "instrument": alert.get("instrument"),
        "setup": alert.get("setup"),
        "score": alert.get("score"),
        "message": alert.get("message"),
    }


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def _intfmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _render_event_list(events: list[dict[str, Any]]) -> str:
    if not events:
        return "<div class='empty compact'>No high-impact event listed for the next few sessions.</div>"
    return "".join(
        f"""
        <article class="event-row">
          <strong>{html.escape(str(event.get("date", "-")))} · {html.escape(str(event.get("name", "-")))}</strong>
          <span>{html.escape(str(event.get("note", "")))}</span>
        </article>
        """
        for event in events
    )


def _render_wall_level(level: dict[str, Any] | None) -> str:
    if not level:
        return "-"
    return (
        f"{_fmt(level.get('strike'))} "
        f"({_intfmt(level.get('open_interest'))} OI, {_fmt(level.get('distance_pct'), '%')})"
    )


def _render_options_wall_list(walls: dict[str, Any]) -> str:
    if not walls:
        return "<div class='empty compact'>No options-wall snapshot has been generated yet.</div>"

    rendered_rows = []
    for symbol in ("SPY", "QQQ"):
        wall = walls.get(symbol) or {}
        if not wall:
            continue
        if not wall.get("available"):
            error = wall.get("error") or "Options wall data unavailable."
            rendered_rows.append(
                f"""
                <article class="strategy-row">
                  <strong>{html.escape(symbol)} Options Walls</strong>
                  <span>{html.escape(str(error))}</span>
                </article>
                """
            )
            continue
        rendered_rows.append(
            f"""
            <article class="strategy-row">
              <strong>{html.escape(symbol)} Options Walls</strong>
              <span><b>Spot / expiry:</b> {_fmt(wall.get("underlying_price"))} / {html.escape(str(wall.get("expiration_date", "-")))}</span>
              <span><b>Put wall:</b> {_render_wall_level(wall.get("put_wall"))}</span>
              <span><b>Call wall:</b> {_render_wall_level(wall.get("call_wall"))}</span>
              <span><b>Max pain / near PCR:</b> {_fmt(wall.get("max_pain"))} / {_fmt(wall.get("near_put_call_oi_ratio"))}</span>
              <span><b>Read:</b> {html.escape(str(wall.get("interpretation", "-")))}</span>
            </article>
            """
        )

    return "".join(rendered_rows) or "<div class='empty compact'>No SPY/QQQ options-wall data available.</div>"


def _render_index_forecast(symbol: str, forecast: dict[str, Any]) -> str:
    item = forecast.get("indexes", {}).get(symbol, {})
    if not item:
        return f"<article class='forecast-card'><h3>{symbol}</h3><p>No forecast data yet.</p></article>"
    notes = "; ".join(str(note) for note in item.get("notes", [])) or "No extra notes."
    options_context = item.get("options_context") or {}
    options_line = ""
    if options_context.get("available"):
        options_line = (
            f"<p><strong>Options walls:</strong> "
            f"Put {_render_wall_level(options_context.get('put_wall'))}; "
            f"Call {_render_wall_level(options_context.get('call_wall'))}; "
            f"Max pain {_fmt(options_context.get('max_pain'))}.</p>"
        )
    return f"""
    <article class="forecast-card">
      <div class="forecast-card-head">
        <h3>{html.escape(symbol)}</h3>
        <span class="tag manage">{html.escape(str(item.get("bias", "-")))}</span>
      </div>
      <div class="prob-grid">
        <div><label>Upside</label><strong>{_fmt(item.get("upside_probability"), "%")}</strong></div>
        <div><label>Sideways</label><strong>{_fmt(item.get("sideways_probability"), "%")}</strong></div>
        <div><label>Downside</label><strong>{_fmt(item.get("downside_probability"), "%")}</strong></div>
      </div>
      <div class="forecast-lines">
        <p><strong>Close:</strong> {_fmt(item.get("close"))} · <strong>Trend score:</strong> {_fmt(item.get("trend_score"))}/100 · <strong>Expected move:</strong> {_fmt(item.get("expected_move_pct"), "%")}</p>
        <p><strong>Entry:</strong> {html.escape(str(item.get("entry_zone", "-")))}</p>
        <p><strong>Exit:</strong> {html.escape(str(item.get("exit_zone", "-")))}</p>
        <p><strong>Invalidation:</strong> {html.escape(str(item.get("invalidation", "-")))}</p>
        {options_line}
        <p><strong>Notes:</strong> {html.escape(notes)}</p>
      </div>
    </article>
    """


def _render_strategy_playbook(playbook: list[dict[str, Any]]) -> str:
    if not playbook:
        return "<div class='empty compact'>No strategy playbook generated yet.</div>"
    return "".join(
        f"""
        <article class="strategy-row">
          <strong>{html.escape(str(item.get("name", "-")))}</strong>
          <span><b>Entry:</b> {html.escape(str(item.get("entry", "-")))}</span>
          <span><b>Exit:</b> {html.escape(str(item.get("exit", "-")))}</span>
        </article>
        """
        for item in playbook
    )


def _render_notification_status(status: dict[str, Any] | None) -> str:
    status = status or {}
    ready = "Ready" if status.get("pushover_ready") else "Missing Pushover credentials"
    dry_run = "Dry run" if status.get("dry_run", True) else "Phone send mode"
    errors = status.get("errors") or []
    latest_alerts = status.get("latest_alerts") or []
    error_text = "; ".join(str(item) for item in errors[:4]) if errors else "No monitor errors from the latest run."
    alerts_text = (
        "".join(
            f"<span>{html.escape(str(alert.get('instrument', '-')))} · {html.escape(str(alert.get('type', '-')))} · {html.escape(str(alert.get('message', '')))}</span>"
            for alert in latest_alerts[:4]
        )
        if latest_alerts
        else "<span>No monitor alerts created in the latest run.</span>"
    )
    return f"""
    <div class="panel forecast-panel">
      <div class="panel-head"><h2>Notification Monitor</h2><span>{html.escape(ready)}</span></div>
      <div class="list-body">
        <article class="strategy-row">
          <strong>{html.escape(dry_run)}</strong>
          <span><b>Last run:</b> {html.escape(str(status.get("last_run") or "Not run yet"))}</span>
          <span><b>Market date:</b> {html.escape(str(status.get("market_date") or "-"))}</span>
          <span><b>Alerts created/sent:</b> {html.escape(str(status.get("alerts_created", 0)))} / {html.escape(str(status.get("alerts_sent", 0)))}</span>
          <span><b>Status:</b> {html.escape(error_text)}</span>
        </article>
        <article class="strategy-row">
          <strong>Latest Rule Alerts</strong>
          {alerts_text}
        </article>
      </div>
    </div>
    """


def _render_forecast(forecast: dict[str, Any] | None, forecast_error: str | None) -> str:
    if forecast_error:
        return f"<div class='notice danger'>{html.escape(forecast_error)}</div>"
    if not forecast:
        return "<div class='empty'>No market forecast yet. Use Refresh Scan to generate SPY/QQQ forecast data.</div>"

    probabilities = forecast.get("combined_probabilities", {})
    breadth = forecast.get("breadth", {})
    events = forecast.get("events", [])
    risk_appetite = forecast.get("risk_appetite", {})
    options_walls = forecast.get("options_walls", {})
    risk_notes = "; ".join(str(note) for note in risk_appetite.get("notes", [])) or "No risk-appetite notes yet."
    return f"""
    <section class="forecast-hero">
      <div>
        <label>Expected Market Direction</label>
        <h2>{html.escape(str(forecast.get("primary_direction", "-")))}</h2>
        <p>{html.escape(str(forecast.get("risk_note", "")))}</p>
      </div>
      <div class="prob-grid hero-probs">
        <div><label>Upside</label><strong>{_fmt(probabilities.get("upside"), "%")}</strong></div>
        <div><label>Sideways</label><strong>{_fmt(probabilities.get("sideways"), "%")}</strong></div>
        <div><label>Downside</label><strong>{_fmt(probabilities.get("downside"), "%")}</strong></div>
      </div>
    </section>

    <section class="grid public-grid">
      <article class="metric"><label>As Of</label><strong>{html.escape(str(forecast.get("as_of", "-")))}</strong><p>Latest daily bar used.</p></article>
      <article class="metric"><label>Next Session</label><strong>{html.escape(str(forecast.get("next_session", "-")))}</strong><p>Forecast target session.</p></article>
      <article class="metric"><label>Above 50 SMA</label><strong>{_fmt(breadth.get("above50_pct"), "%")}</strong><p>Scanned breadth health.</p></article>
      <article class="metric"><label>Above 200 SMA</label><strong>{_fmt(breadth.get("above200_pct"), "%")}</strong><p>Longer-term trend breadth.</p></article>
      <article class="metric"><label>20D Positive</label><strong>{_fmt(breadth.get("positive20d_pct"), "%")}</strong><p>Names positive over 20 days.</p></article>
      <article class="metric"><label>Risk Edge</label><strong>{_fmt(risk_appetite.get("edge"))}</strong><p>{html.escape(risk_notes)}</p></article>
    </section>

    <section class="forecast-grid">
      {_render_index_forecast("SPY", forecast)}
      {_render_index_forecast("QQQ", forecast)}
    </section>

    <section class="forecast-grid narrow">
      <div class="panel forecast-panel">
        <div class="panel-head"><h2>Event Risk</h2><span>Next few sessions</span></div>
        <div class="list-body">{_render_event_list(events)}</div>
      </div>
      <div class="panel forecast-panel">
        <div class="panel-head"><h2>Options Walls</h2><span>Put / call OI</span></div>
        <div class="list-body">{_render_options_wall_list(options_walls)}</div>
      </div>
      <div class="panel forecast-panel">
        <div class="panel-head"><h2>Best Strategy Rules</h2><span>For this framework</span></div>
        <div class="list-body">{_render_strategy_playbook(forecast.get("strategy_playbook", []))}</div>
      </div>
    </section>

    <div class="notice">{html.escape(str(forecast.get("model_note", "")))}</div>
    """


def _checked(condition: bool) -> str:
    return " checked" if condition else ""


def _render_strategy_lab(goal: dict[str, Any], forecast: dict[str, Any] | None, include_private: bool) -> str:
    forecast = forecast or {}
    probabilities = forecast.get("combined_probabilities", {})
    breadth = forecast.get("breadth", {})
    risk_appetite = forecast.get("risk_appetite", {})
    events = forecast.get("events", [])
    indexes = forecast.get("indexes", {})
    spy = indexes.get("SPY", {})
    qqq = indexes.get("QQQ", {})
    options_walls = forecast.get("options_walls", {})

    avg_trend = 0.0
    trend_values = [float(item.get("trend_score", 0) or 0) for item in (spy, qqq) if item]
    if trend_values:
        avg_trend = sum(trend_values) / len(trend_values)

    account_value = str(goal.get("current_value", "")) if include_private else ""
    recovery_html = (
        f"""
        <div class="lab-mini">
          <span>Recovery Needed</span>
          <strong>{_money(goal.get("gain_needed", 0))}</strong>
          <small>{_pct(goal.get("required_monthly_return_pct", 0))} monthly for {html.escape(str(goal.get("recovery_months", "-")))} months.</small>
        </div>
        """
        if include_private
        else """
        <div class="lab-mini muted-box">
          <span>Recovery Math</span>
          <strong>Private</strong>
          <small>Open the private route to prefill account value and recovery targets.</small>
        </div>
        """
    )

    return f"""
    <section class="lab-hero">
      <div>
        <label>Professional Strategy Lab</label>
        <h2>Decision stack before money goes at risk</h2>
        <p>Use this tab like a trader's cockpit: regime first, setup second, risk third, options only after liquidity and defined loss are clear.</p>
      </div>
      <div class="lab-mini-grid">
        <div class="lab-mini">
          <span>Market Bias</span>
          <strong>{html.escape(str(forecast.get("primary_direction", "Not generated")))}</strong>
          <small>{_fmt(probabilities.get("upside"), "%")} up / {_fmt(probabilities.get("sideways"), "%")} sideways / {_fmt(probabilities.get("downside"), "%")} down</small>
        </div>
        {recovery_html}
      </div>
    </section>

    <section class="lab-grid lab-grid-3">
      <div class="panel lab-panel">
        <div class="panel-head"><h2>Regime Engine</h2><span id="regimeLabel">Scoring</span></div>
        <div class="lab-body">
          <div class="meter"><span id="regimeMeter"></span></div>
          <div class="lab-score-line"><strong id="regimeScore">0/100</strong><span id="regimeRead">Waiting for inputs.</span></div>
          <label class="check-row"><input class="lab-check" type="checkbox" data-weight="20"{_checked(avg_trend >= 75)}> SPY/QQQ trend score above 75</label>
          <label class="check-row"><input class="lab-check" type="checkbox" data-weight="16"{_checked(float(breadth.get("above50_pct", 0) or 0) >= 55)}> Breadth healthy: above 50 SMA greater than 55%</label>
          <label class="check-row"><input class="lab-check" type="checkbox" data-weight="14"{_checked(float(risk_appetite.get("edge", 0) or 0) >= 0)}> Risk appetite is neutral or positive</label>
          <label class="check-row"><input class="lab-check" type="checkbox" data-weight="14"{_checked(bool(options_walls))}> Options walls give clear support/resistance</label>
          <label class="check-row"><input class="lab-check" type="checkbox" data-weight="12"{_checked(not events)}> No high-impact event risk today</label>
          <label class="check-row"><input class="lab-check" type="checkbox" data-weight="12"> Opening range + VWAP confirm direction</label>
          <label class="check-row"><input class="lab-check" type="checkbox" data-weight="12"> Trade has at least 1.8R reward/risk</label>
        </div>
      </div>

      <div class="panel lab-panel">
        <div class="panel-head"><h2>Trade Ticket</h2><span id="tradeDecision">Not checked</span></div>
        <div class="lab-body">
          <div class="field-grid">
            <label class="field"><span>Candidate</span><select id="planSelect"></select></label>
            <label class="field"><span>Trade Type</span><select id="tradeType">
              <option>Shares / ETF</option>
              <option>Call debit spread</option>
              <option>Put debit spread</option>
              <option>Credit spread</option>
              <option>Cash / no trade</option>
            </select></label>
            <label class="field"><span>Account Value</span><input id="accountInput" type="number" min="0" step="100" value="{html.escape(account_value)}" placeholder="Manual"></label>
            <label class="field"><span>Risk %</span><input id="riskPctInput" type="number" min="0" max="5" step="0.1" value="1"></label>
            <label class="field"><span>Entry</span><input id="entryInput" type="number" min="0" step="0.01"></label>
            <label class="field"><span>Stop</span><input id="stopInput" type="number" min="0" step="0.01"></label>
            <label class="field"><span>Target</span><input id="targetInput" type="number" min="0" step="0.01"></label>
            <label class="field"><span>Win Probability %</span><input id="winProbInput" type="number" min="1" max="99" step="1" value="45"></label>
            <label class="field"><span>Option Debit</span><input id="optionDebitInput" type="number" min="0" step="0.01" value="0"></label>
            <label class="field"><span>Spread Width</span><input id="spreadWidthInput" type="number" min="0" step="0.5" value="0"></label>
          </div>
          <div class="output-grid">
            <div class="output"><span>Max Risk</span><strong id="maxRiskOut">-</strong></div>
            <div class="output"><span>Shares / Contracts</span><strong id="sizeOut">-</strong></div>
            <div class="output"><span>Reward / Risk</span><strong id="rrOut">-</strong></div>
            <div class="output"><span>Break-even Win Rate</span><strong id="breakevenOut">-</strong></div>
            <div class="output"><span>Expected Value</span><strong id="expectancyOut">-</strong></div>
            <div class="output"><span>Trade Grade</span><strong id="gradeOut">-</strong></div>
          </div>
        </div>
      </div>

      <div class="panel lab-panel">
        <div class="panel-head"><h2>Strategy Selector</h2><span>Playbook</span></div>
        <div class="lab-body">
          <label class="field"><span>Strategy</span><select id="strategySelect">
            <option value="trend">Trend following</option>
            <option value="rotation">ETF relative strength rotation</option>
            <option value="mean">Mean reversion pullback</option>
            <option value="walls">Put-wall / call-wall intraday</option>
            <option value="vol">Options volatility trade</option>
            <option value="event">Event-risk setup</option>
            <option value="fundamental">Long-term fundamental</option>
            <option value="factor">Factor basket</option>
          </select></label>
          <div id="strategyRead" class="strategy-read"></div>
        </div>
      </div>
    </section>

    <section class="lab-grid lab-grid-2">
      <div class="panel lab-panel">
        <div class="panel-head"><h2>Options Desk</h2><span>Defined-risk only</span></div>
        <div class="lab-body">
          <table class="lab-table">
            <thead><tr><th>Setup</th><th>Use When</th><th>Must Check</th><th>Avoid When</th></tr></thead>
            <tbody>
              <tr><td>Call debit spread</td><td>Trend up, pullback/reclaim, call wall above target</td><td>IV, spread width, open interest, bid/ask, 1.8R target</td><td>RSI stretched, event risk, weak VWAP</td></tr>
              <tr><td>Put debit spread</td><td>Trend breaks, VWAP loss, 50 SMA failure</td><td>Put wall distance, downside room, IV not inflated</td><td>Strong breadth, put wall holding, oversold washout</td></tr>
              <tr><td>Credit spread</td><td>Range day, strong wall rejection, IV rich</td><td>Max loss, assignment risk, liquidity, exit at 50-70% profit</td><td>Breakout day, FOMC/CPI, thin options</td></tr>
              <tr><td>0DTE directional</td><td>Only after opening range and VWAP confirmation</td><td>Small size, hard stop, no averaging down</td><td>Chop, meetings, unclear breadth</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel lab-panel">
        <div class="panel-head"><h2>Model Audit</h2><span id="auditStats">No journal yet</span></div>
        <div class="lab-body">
          <div class="field-grid compact">
            <label class="field"><span>Forecast Up %</span><input id="auditUp" type="number" min="0" max="100" value="{html.escape(str(probabilities.get("upside", 0) or 0))}"></label>
            <label class="field"><span>Forecast Sideways %</span><input id="auditSide" type="number" min="0" max="100" value="{html.escape(str(probabilities.get("sideways", 0) or 0))}"></label>
            <label class="field"><span>Forecast Down %</span><input id="auditDown" type="number" min="0" max="100" value="{html.escape(str(probabilities.get("downside", 0) or 0))}"></label>
            <label class="field"><span>Actual Move %</span><input id="actualMove" type="number" step="0.01" placeholder="After close"></label>
          </div>
          <button class="btn primary lab-action" type="button" id="recordAudit">Record Audit</button>
          <div id="auditLog" class="audit-log"></div>
        </div>
      </div>
    </section>

    <section class="panel lab-panel">
      <div class="panel-head"><h2>Professional Edge Map</h2><span>Legal public signals only</span></div>
      <div class="strategy-map">
        <article><strong>Trend</strong><span>20/50/200 MA alignment, breakouts, trailing stops, no prediction needed.</span></article>
        <article><strong>Rotation</strong><span>Rank ETFs by relative strength, volume, volatility, and breadth confirmation.</span></article>
        <article><strong>Mean Reversion</strong><span>Buy oversold pullbacks only inside confirmed uptrends; stop below structure.</span></article>
        <article><strong>Options Positioning</strong><span>Put walls, call walls, max pain, near put/call OI, and implied move.</span></article>
        <article><strong>Volatility</strong><span>Compare implied move to realized move; use spreads when IV is expensive.</span></article>
        <article><strong>Events</strong><span>FOMC, CPI, earnings, FDA, and major macro releases require smaller size or cash.</span></article>
        <article><strong>Fundamentals</strong><span>Revenue growth, margins, earnings revisions, debt, free cash flow, valuation.</span></article>
        <article><strong>Factors</strong><span>Momentum, value, quality, low volatility, and sector exposure.</span></article>
        <article><strong>Legal Public Signals</strong><span>SEC Form 4 buys, short interest, ETF flows, analyst revisions, Reg SHO lists.</span></article>
        <article><strong>Risk</strong><span>Daily loss limit, max risk per trade, no averaging down, no oversized options.</span></article>
      </div>
    </section>
    """


def _render_live_options_walls_view() -> str:
    return """
    <section class="lab-hero">
      <div>
        <label>Options Walls Live</label>
        <h2>Put-wall and call-wall open interest by ticker</h2>
        <p>This view refreshes from the options chain when the dashboard opens. Each symbol uses its nearest available option expiry.</p>
      </div>
      <div class="lab-mini-grid">
        <div class="lab-mini">
          <span>Refresh Status</span>
          <strong id="liveWallsStatus">Waiting</strong>
          <small id="liveWallsMeta">The table will load automatically.</small>
        </div>
        <div class="lab-mini">
          <span>Coverage</span>
          <strong id="liveWallsCoverage">-</strong>
          <small>ETF and stock watchlist symbols with listed option data.</small>
        </div>
      </div>
    </section>

    <section class="panel lab-panel options-wall-panel">
      <div class="panel-head">
        <h2>Live Options Walls</h2>
        <span id="liveWallsTimestamp">Not refreshed yet</span>
      </div>
      <div class="wall-toolbar">
        <label class="field wall-search"><span>Search</span><input id="wallSearch" type="search" placeholder="SPY, AAPL, XLK"></label>
        <label class="field"><span>Type</span><select id="wallKindFilter">
          <option value="all">All</option>
          <option value="etf">ETFs</option>
          <option value="stock">Stocks</option>
        </select></label>
        <label class="field"><span>Status</span><select id="wallAvailabilityFilter">
          <option value="all">All</option>
          <option value="available">Available</option>
          <option value="missing">Missing</option>
        </select></label>
        <button class="btn primary" type="button" id="refreshLiveWalls">Refresh Walls</button>
      </div>
      <div class="table-wrap wall-table-wrap">
        <table class="wall-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Type</th>
              <th>Expiry</th>
              <th>Spot</th>
              <th>Put Wall</th>
              <th>Put OI</th>
              <th>Put Dist.</th>
              <th>Call Wall</th>
              <th>Call OI</th>
              <th>Call Dist.</th>
              <th>Max Pain</th>
              <th>Near PCR</th>
              <th>Read</th>
            </tr>
          </thead>
          <tbody id="liveWallsBody">
            <tr><td colspan="13" class="empty">Loading fresh options-wall data...</td></tr>
          </tbody>
        </table>
      </div>
    </section>
    """


def render_dashboard(state: dict[str, Any], include_private: bool = False) -> str:
    goal = state["goal"]
    plans = state.get("plans", []) if include_private else [public_plan(plan) for plan in state.get("plans", [])]
    alerts = state.get("alerts", []) if include_private else [public_alert(alert) for alert in state.get("alerts", [])]
    error = state.get("error")
    forecast = state.get("forecast")
    forecast_error = state.get("forecast_error")
    notification_status = state.get("notification_status")
    last_scan = state.get("last_scan") or "Not scanned yet"
    top_json = json.dumps(plans)
    alerts_json = json.dumps(alerts)
    page_title = "Private Portfolio Recovery Agent" if include_private else "Market Setup Dashboard"
    subline = (
        f"Private recovery dashboard. Last scan: {html.escape(last_scan)}."
        if include_private
        else f"Share-safe market setup dashboard. Last scan: {html.escape(last_scan)}."
    )
    refresh_href = "/private/refresh" if include_private else "/refresh"
    actions_html = f"""
        <a class="btn primary" href="{refresh_href}">Refresh Scan</a>
        <a class="btn" href="/health">Health</a>
    """
    if not include_private:
        actions_html = f"""
        <a class="btn primary" href="{refresh_href}">Refresh Scan</a>
        <a class="btn" href="/api/summary">Public JSON</a>
    """

    error_html = ""
    if error:
        error_html = f"<div class='notice danger'>{html.escape(str(error))}</div>"

    if include_private:
        metrics_html = f"""
    <section class="grid private-grid">
      <article class="metric"><label>Account</label><strong>{html.escape(goal["account_name"])}</strong><p>Mode: local research.</p></article>
      <article class="metric"><label>Current Value</label><strong>{_money(goal["current_value"])}</strong><p>Initial capital {_money(goal["initial_capital"])}.</p></article>
      <article class="metric"><label>Current Loss</label><strong>{_money(goal["current_loss"])}</strong><p>{_pct(goal["current_loss_pct"])} versus starting capital.</p></article>
      <article class="metric"><label>Recovery Target</label><strong>{_money(goal["recovery_target"])}</strong><p>Need {_money(goal["gain_needed"])} total.</p></article>
      <article class="metric"><label>Required Monthly</label><strong>{_pct(goal["required_monthly_return_pct"])}</strong><p>{html.escape(goal["realism_label"])}.</p></article>
      <article class="metric"><label>Later Goal</label><strong>{_pct(goal["post_recovery_monthly_goal_pct"])}</strong><p>{_pct(goal["post_recovery_annualized_goal_pct"])} annualized.</p></article>
    </section>

    <div class="notice">{html.escape(goal["risk_note"])}</div>
"""
    else:
        confirmed = sum(1 for plan in plans if plan.get("setup") == "Entry Confirmed")
        watches = sum(1 for plan in plans if plan.get("setup") == "Entry Watch")
        stock_count = sum(1 for plan in plans if plan.get("kind") == "stock")
        etf_count = sum(1 for plan in plans if plan.get("kind") == "etf")
        metrics_html = f"""
    <section class="grid public-grid">
      <article class="metric"><label>Scanned</label><strong>{len(plans)}</strong><p>ETF and stock candidates in the current watchlist.</p></article>
      <article class="metric"><label>Entry Confirmed</label><strong>{confirmed}</strong><p>Highest-conviction technical setups.</p></article>
      <article class="metric"><label>Entry Watch</label><strong>{watches}</strong><p>Setups forming but not fully confirmed.</p></article>
      <article class="metric"><label>ETFs</label><strong>{etf_count}</strong><p>Funds included in this scan.</p></article>
      <article class="metric"><label>Stocks</label><strong>{stock_count}</strong><p>Shares included in this scan.</p></article>
      <article class="metric"><label>Alerts</label><strong>{len(alerts)}</strong><p>Recent local signal changes.</p></article>
    </section>

    <div class="notice">Share-safe view: account value, loss, recovery target, and position sizing are kept out of this page.</div>
"""

    risk_header = "<th>Risk</th>" if include_private else ""
    risk_note = (
        "Max risk per trade is read from config. Options are candidates only until live chain pricing, spread width, liquidity, and IV are validated."
        if include_private
        else "Options shown here are candidates only. They still need live option-chain pricing, bid-ask spread, open interest, IV, and defined-risk validation."
    )
    empty_colspan = "17" if include_private else "16"
    private_js = "true" if include_private else "false"
    forecast_html = _render_forecast(forecast, forecast_error)
    notification_html = _render_notification_status(notification_status)
    strategy_lab_html = _render_strategy_lab(goal, forecast, include_private)
    live_options_walls_html = _render_live_options_walls_view()
    forecast_json = json.dumps(forecast or {})

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{page_title}</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --panel: #ffffff;
      --ink: #18242f;
      --muted: #62707d;
      --line: #d8dee5;
      --green: #08785f;
      --blue: #2458b8;
      --amber: #a66a18;
      --red: #b13d3d;
      --soft: #eef2f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
    }}
    .shell {{ max-width: 1500px; margin: 0 auto; padding: 18px; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      padding: 16px 0 14px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 1.65rem; letter-spacing: 0; }}
    .subline {{ color: var(--muted); margin-top: 6px; font-size: .95rem; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 40px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      text-decoration: none;
      font-weight: 700;
      font-size: .92rem;
    }}
    .btn.primary {{ background: var(--blue); color: white; border-color: var(--blue); }}
    .grid {{
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }}
    .private-grid {{ grid-template-columns: repeat(6, minmax(0, 1fr)); }}
    .public-grid {{ grid-template-columns: repeat(6, minmax(0, 1fr)); }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 104px;
    }}
    .metric label {{
      display: block;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .06em;
      font-size: .72rem;
      margin-bottom: 10px;
    }}
    .metric strong {{ font-size: 1.45rem; letter-spacing: 0; }}
    .metric p {{ margin: 8px 0 0; color: var(--muted); line-height: 1.35; font-size: .86rem; }}
    .notice {{
      margin-top: 14px;
      background: #fff8e8;
      color: var(--amber);
      border: 1px solid #ecd7a7;
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .notice.danger {{ background: #fff0f0; color: var(--red); border-color: #efc0c0; }}
    .tab-bar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .tab-btn {{
      min-height: 40px;
      padding: 0 14px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      font-weight: 700;
      cursor: pointer;
    }}
    .tab-btn.active {{
      background: var(--blue);
      color: #ffffff;
      border-color: var(--blue);
    }}
    .tab-page {{ display: none; }}
    .tab-page.active {{ display: block; }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 14px;
      margin-top: 14px;
      align-items: start;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--soft);
    }}
    .panel-head h2 {{ margin: 0; font-size: 1rem; }}
    .panel-head span {{ color: var(--muted); font-size: .88rem; }}
    .table-wrap {{ overflow: auto; max-height: 70vh; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1320px; }}
    th, td {{
      padding: 10px 9px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: .88rem;
      line-height: 1.35;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #e9edf2;
      color: #253442;
      z-index: 1;
      font-size: .78rem;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 6px;
      font-size: .78rem;
      font-weight: 700;
      white-space: nowrap;
    }}
    .confirmed {{ color: var(--green); background: #e7f5f1; }}
    .watch {{ color: var(--amber); background: #fff2da; }}
    .avoid {{ color: var(--red); background: #ffe9e9; }}
    .manage {{ color: var(--blue); background: #e9effd; }}
    .side {{ display: grid; gap: 14px; }}
    .alert-list {{ display: grid; gap: 10px; padding: 12px; }}
    .alert {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfd;
    }}
    .alert strong {{ display: block; font-size: .92rem; }}
    .alert span {{ display: block; color: var(--muted); margin-top: 4px; font-size: .82rem; }}
    .empty {{ padding: 20px; color: var(--muted); line-height: 1.5; }}
    .empty.compact {{ padding: 12px; }}
    .forecast-hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 420px;
      gap: 14px;
      align-items: stretch;
      margin-top: 14px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .forecast-hero label,
    .prob-grid label {{
      display: block;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .06em;
      font-size: .72rem;
      margin-bottom: 8px;
    }}
    .forecast-hero h2 {{ margin: 0; font-size: 1.55rem; }}
    .forecast-hero p {{ margin: 10px 0 0; color: var(--muted); line-height: 1.45; }}
    .prob-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .prob-grid > div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .prob-grid strong {{ font-size: 1.35rem; }}
    .hero-probs {{ align-content: stretch; }}
    .forecast-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 14px;
    }}
    .forecast-grid.narrow {{ align-items: start; }}
    .forecast-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }}
    .forecast-card-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }}
    .forecast-card h3 {{ margin: 0; font-size: 1.15rem; }}
    .forecast-lines p {{ margin: 10px 0 0; color: var(--muted); line-height: 1.45; }}
    .forecast-lines strong {{ color: var(--ink); }}
    .forecast-panel {{ min-height: 240px; }}
    .list-body {{ display: grid; gap: 10px; padding: 12px; }}
    .event-row,
    .strategy-row {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfd;
    }}
    .event-row strong,
    .strategy-row strong {{ display: block; font-size: .92rem; }}
    .event-row span,
    .strategy-row span {{ display: block; color: var(--muted); margin-top: 5px; font-size: .84rem; line-height: 1.4; }}
    .lab-hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 520px;
      gap: 14px;
      align-items: stretch;
      margin-top: 14px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .lab-hero label {{
      display: block;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .06em;
      font-size: .72rem;
      margin-bottom: 8px;
    }}
    .lab-hero h2 {{ margin: 0; font-size: 1.45rem; }}
    .lab-hero p {{ margin: 10px 0 0; color: var(--muted); line-height: 1.45; }}
    .lab-mini-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .lab-mini {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      padding: 12px;
    }}
    .lab-mini span,
    .output span,
    .field span {{
      display: block;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .05em;
      font-size: .7rem;
      margin-bottom: 7px;
    }}
    .lab-mini strong {{ display: block; font-size: 1.05rem; line-height: 1.25; }}
    .lab-mini small {{ display: block; color: var(--muted); margin-top: 8px; line-height: 1.35; }}
    .muted-box {{ background: #f7f8fa; }}
    .lab-grid {{
      display: grid;
      gap: 14px;
      margin-top: 14px;
      align-items: start;
    }}
    .lab-grid-3 {{ grid-template-columns: 1fr 1.35fr 1fr; }}
    .lab-grid-2 {{ grid-template-columns: minmax(0, 1.15fr) minmax(360px, .85fr); }}
    .lab-panel {{ overflow: hidden; }}
    .lab-body {{ padding: 12px; display: grid; gap: 12px; }}
    .meter {{
      height: 12px;
      background: #e8edf2;
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid var(--line);
    }}
    .meter span {{
      display: block;
      height: 100%;
      width: 0%;
      background: var(--red);
      transition: width .2s ease, background .2s ease;
    }}
    .lab-score-line {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      color: var(--muted);
      font-size: .88rem;
    }}
    .lab-score-line strong {{ color: var(--ink); font-size: 1.05rem; }}
    .check-row {{
      display: flex;
      align-items: flex-start;
      gap: 9px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      padding: 10px;
      color: var(--ink);
      line-height: 1.35;
      font-size: .88rem;
    }}
    .check-row input {{ margin-top: 2px; width: 16px; height: 16px; }}
    .field-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .field-grid.compact {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .field input,
    .field select {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
      padding: 0 10px;
      font: inherit;
    }}
    .output-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .output {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      padding: 10px;
      min-height: 76px;
    }}
    .output strong {{ display: block; font-size: 1.05rem; }}
    .strategy-read {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      padding: 12px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .strategy-read strong {{ display: block; color: var(--ink); margin-bottom: 8px; }}
    .strategy-read span {{ display: block; margin-top: 7px; }}
    .lab-table {{
      min-width: 760px;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .lab-table th,
    .lab-table td {{ position: static; font-size: .84rem; }}
    .lab-action {{ width: fit-content; }}
    .audit-log {{
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: .86rem;
      line-height: 1.4;
    }}
    .audit-log article {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      padding: 9px;
    }}
    .strategy-map {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      padding: 12px;
    }}
    .strategy-map article {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      padding: 10px;
      min-height: 112px;
    }}
    .strategy-map strong {{ display: block; font-size: .92rem; }}
    .strategy-map span {{ display: block; color: var(--muted); margin-top: 6px; font-size: .82rem; line-height: 1.35; }}
    .options-wall-panel {{ margin-top: 14px; }}
    .wall-toolbar {{
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 150px 150px auto;
      gap: 10px;
      align-items: end;
      padding: 12px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }}
    .wall-search input {{ min-width: 0; }}
    .wall-table-wrap {{ max-height: 72vh; }}
    .wall-table {{ min-width: 1320px; }}
    .wall-table td:nth-child(13) {{ min-width: 260px; max-width: 360px; }}
    .wall-error {{ color: var(--red); font-weight: 700; }}
    .wall-good {{ color: var(--green); font-weight: 700; }}
    .wall-muted {{ color: var(--muted); }}
    @media (max-width: 1050px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .layout {{ grid-template-columns: 1fr; }}
      .forecast-hero,
      .forecast-grid,
      .lab-hero,
      .lab-grid-3,
      .lab-grid-2,
      .strategy-map {{ grid-template-columns: 1fr; }}
      .lab-mini-grid,
      .field-grid,
      .field-grid.compact,
      .output-grid,
      .wall-toolbar {{ grid-template-columns: 1fr; }}
      header {{ flex-direction: column; }}
      .actions {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1>{page_title}</h1>
        <div class="subline">{subline}</div>
      </div>
      <div class="actions">
{actions_html}
      </div>
    </header>

{metrics_html}
    {error_html}

    <nav class="tab-bar" aria-label="Dashboard views">
      <button class="tab-btn active" type="button" data-tab="candidatesTab">Trade Candidates</button>
      <button class="tab-btn" type="button" data-tab="forecastTab">SPY / QQQ Forecast</button>
      <button class="tab-btn" type="button" data-tab="strategyLabTab">Professional Strategy Lab</button>
      <button class="tab-btn" type="button" data-tab="optionsWallsTab">Options Walls Live</button>
    </nav>

    <section id="candidatesTab" class="tab-page active">
    <div class="layout">
      <main class="panel">
        <div class="panel-head">
          <h2>Trade Candidates</h2>
          <span id="candidateCount"></span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Kind</th>
                <th>Setup</th>
                <th>Score</th>
                <th>Lane</th>
                <th>Close</th>
                <th>20 EMA</th>
                <th>50 SMA</th>
                <th>200 SMA</th>
                <th>RSI</th>
                <th>ATR %</th>
                <th>RS vs SPY</th>
                <th>Stop</th>
                <th>Targets</th>
                {risk_header}
                <th>Options</th>
                <th>Exit Rule</th>
              </tr>
            </thead>
            <tbody id="planBody"></tbody>
          </table>
        </div>
      </main>
      <aside class="side">
        <section class="panel">
          <div class="panel-head"><h2>Local Alerts</h2><span id="alertCount"></span></div>
          <div class="alert-list" id="alertList"></div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Risk Guardrails</h2></div>
          <div class="empty">
            {risk_note}
          </div>
        </section>
      </aside>
    </div>
    </section>

    <section id="forecastTab" class="tab-page">
      {forecast_html}
      <section class="forecast-grid narrow">
        {notification_html}
      </section>
    </section>

    <section id="strategyLabTab" class="tab-page">
      {strategy_lab_html}
    </section>

    <section id="optionsWallsTab" class="tab-page">
      {live_options_walls_html}
    </section>
  </div>
  <script>
    const plans = {top_json};
    const alerts = {alerts_json};
    const includePrivate = {private_js};
    const forecast = {forecast_json};
    const body = document.getElementById("planBody");
    const alertList = document.getElementById("alertList");
    const candidateCount = document.getElementById("candidateCount");
    const alertCount = document.getElementById("alertCount");
    const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
    const tabPages = Array.from(document.querySelectorAll(".tab-page"));

    function setupClass(setup) {{
      if (setup === "Entry Confirmed") return "confirmed";
      if (setup === "Entry Watch") return "watch";
      if (setup === "Hold / Manage") return "manage";
      return "avoid";
    }}

    function money(value) {{
      return "$" + Number(value || 0).toLocaleString(undefined, {{ maximumFractionDigits: 0 }});
    }}

    function numberValue(id) {{
      const element = document.getElementById(id);
      return Number(element && element.value ? element.value : 0);
    }}

    function setText(id, value) {{
      const element = document.getElementById(id);
      if (element) element.textContent = value;
    }}

    function clamp(value, low, high) {{
      return Math.max(low, Math.min(high, value));
    }}

    let latestRegimeScore = 0;

    function updateRegimeScore() {{
      const checks = Array.from(document.querySelectorAll(".lab-check"));
      const score = checks.reduce((total, item) => total + (item.checked ? Number(item.dataset.weight || 0) : 0), 0);
      latestRegimeScore = score;
      const meter = document.getElementById("regimeMeter");
      if (meter) {{
        meter.style.width = score + "%";
        meter.style.background = score >= 75 ? "var(--green)" : score >= 55 ? "var(--amber)" : "var(--red)";
      }}
      const label = score >= 75 ? "Risk-on setup" : score >= 55 ? "Selective / wait for confirmation" : "Defensive / capital first";
      setText("regimeScore", score + "/100");
      setText("regimeRead", label);
      setText("regimeLabel", score >= 75 ? "Tradable" : score >= 55 ? "Selective" : "Defensive");
      updateTradeTicket();
    }}

    const strategyBook = {{
      trend: {{
        title: "Trend following",
        entry: "Buy strength or pullback reclaim only when 20/50/200 trend stack and breadth agree.",
        exit: "Trail below rising 20 EMA or structure low; cut on 50 SMA failure.",
        avoid: "Avoid in flat moving averages, low breadth, or event-driven chop."
      }},
      rotation: {{
        title: "ETF relative strength rotation",
        entry: "Rank ETFs by 20-day relative strength, trend score, volume, and volatility. Own the leaders only.",
        exit: "Rotate out when relative strength turns negative or price loses 50 SMA.",
        avoid: "Avoid buying the strongest ETF if it is extended and far above the 20 EMA."
      }},
      mean: {{
        title: "Mean reversion pullback",
        entry: "Buy oversold pullbacks only inside an uptrend after reclaim of VWAP or 20 EMA.",
        exit: "Stop below pullback low; take partials near prior high or 1R to 1.5R.",
        avoid: "Avoid if the 50 SMA is failing or the market is making lower lows."
      }},
      walls: {{
        title: "Put-wall / call-wall intraday",
        entry: "Use put wall as support and call wall as resistance context. Trade only after VWAP and opening range confirm.",
        exit: "Exit fast when the wall breaks and price accepts on the other side.",
        avoid: "Avoid treating walls as guarantees. They can break violently on event days."
      }},
      vol: {{
        title: "Options volatility trade",
        entry: "Compare implied move to likely realized move. Use defined-risk spreads when IV is rich or direction is uncertain.",
        exit: "Take profit at 50-70% of max gain or cut when underlying invalidates.",
        avoid: "Avoid naked short options and wide bid/ask spreads."
      }},
      event: {{
        title: "Event-risk setup",
        entry: "Before FOMC/CPI/earnings, reduce size or wait for the first confirmed move after the news.",
        exit: "Do not hold oversized short-dated options through binary events.",
        avoid: "Avoid forcing trades when the event can gap through your stop."
      }},
      fundamental: {{
        title: "Long-term fundamental",
        entry: "Prefer companies or ETFs with earnings growth, margin strength, cash flow, and reasonable valuation.",
        exit: "Exit when thesis breaks, earnings revisions roll over, or valuation becomes extreme.",
        avoid: "Avoid averaging down without a fresh thesis and risk limit."
      }},
      factor: {{
        title: "Factor basket",
        entry: "Blend momentum, quality, value, and low volatility rather than betting on one factor.",
        exit: "Rebalance on schedule; avoid emotional factor timing.",
        avoid: "Avoid crowded factors after huge inflows or parabolic runs."
      }}
    }};

    function updateStrategyRead() {{
      const select = document.getElementById("strategySelect");
      const target = document.getElementById("strategyRead");
      if (!select || !target) return;
      const strategy = strategyBook[select.value] || strategyBook.trend;
      target.innerHTML = `
        <strong>${{strategy.title}}</strong>
        <span><b>Entry:</b> ${{strategy.entry}}</span>
        <span><b>Exit:</b> ${{strategy.exit}}</span>
        <span><b>Avoid:</b> ${{strategy.avoid}}</span>
      `;
    }}

    function populatePlanSelect() {{
      const select = document.getElementById("planSelect");
      if (!select) return;
      const options = [`<option value="-1">Manual setup</option>`];
      plans.slice(0, 40).forEach((plan, index) => {{
        options.push(`<option value="${{index}}">${{plan.instrument}} - ${{plan.setup}} - score ${{plan.score}}</option>`);
      }});
      select.innerHTML = options.join("");
      if (plans.length) select.value = "0";
    }}

    function applySelectedPlan() {{
      const select = document.getElementById("planSelect");
      if (!select) return;
      const index = Number(select.value);
      if (index < 0 || !plans[index]) {{
        updateTradeTicket();
        return;
      }}
      const plan = plans[index];
      const entry = document.getElementById("entryInput");
      const stop = document.getElementById("stopInput");
      const target = document.getElementById("targetInput");
      const winProb = document.getElementById("winProbInput");
      if (entry) entry.value = Number(plan.close || 0).toFixed(2);
      if (stop) stop.value = Number(plan.stop || 0).toFixed(2);
      if (target) target.value = Number(plan.target1 || 0).toFixed(2);
      if (winProb) winProb.value = Math.round(clamp(34 + Number(plan.score || 0) * 0.22, 35, 62));
      updateTradeTicket();
    }}

    function updateTradeTicket() {{
      const account = numberValue("accountInput");
      const riskPct = numberValue("riskPctInput");
      const entry = numberValue("entryInput");
      const stop = numberValue("stopInput");
      const target = numberValue("targetInput");
      const winProb = clamp(numberValue("winProbInput") / 100, 0.01, 0.99);
      const debit = numberValue("optionDebitInput");
      const width = numberValue("spreadWidthInput");
      const tradeType = (document.getElementById("tradeType") || {{ value: "" }}).value;
      const maxRisk = account * riskPct / 100;
      let sizeText = "-";
      let rr = 0;
      let breakeven = 0;
      let expectancy = 0;
      let grade = "Missing inputs";

      if (tradeType === "Cash / no trade") {{
        grade = "Wait";
        setText("maxRiskOut", money(maxRisk));
        setText("sizeOut", "0");
        setText("rrOut", "-");
        setText("breakevenOut", "-");
        setText("expectancyOut", "-");
        setText("gradeOut", grade);
        setText("tradeDecision", "Cash");
        return;
      }}

      if (account > 0 && maxRisk > 0) {{
        if (tradeType.includes("spread") && debit > 0 && width > debit) {{
          const riskPerContract = debit * 100;
          const rewardPerContract = (width - debit) * 100;
          const contracts = Math.floor(maxRisk / riskPerContract);
          rr = rewardPerContract / riskPerContract;
          breakeven = 1 / (1 + rr);
          expectancy = contracts * ((winProb * rewardPerContract) - ((1 - winProb) * riskPerContract));
          sizeText = contracts + " contracts";
        }} else if (entry > 0 && stop > 0 && target > 0 && entry !== stop) {{
          const riskPerShare = Math.abs(entry - stop);
          const rewardPerShare = Math.abs(target - entry);
          const shares = Math.floor(maxRisk / riskPerShare);
          rr = rewardPerShare / riskPerShare;
          breakeven = 1 / (1 + rr);
          expectancy = shares * ((winProb * rewardPerShare) - ((1 - winProb) * riskPerShare));
          sizeText = shares + " shares";
        }}
      }}

      if (rr >= 1.8 && latestRegimeScore >= 75 && expectancy > 0) {{
        grade = "A setup";
      }} else if (rr >= 1.5 && latestRegimeScore >= 55 && expectancy > 0) {{
        grade = "B setup";
      }} else if (rr >= 1.2 && expectancy >= 0) {{
        grade = "Watch only";
      }} else if (account > 0) {{
        grade = "Avoid";
      }}

      setText("maxRiskOut", account > 0 ? money(maxRisk) : "-");
      setText("sizeOut", sizeText);
      setText("rrOut", rr > 0 ? rr.toFixed(2) + "R" : "-");
      setText("breakevenOut", breakeven > 0 ? (breakeven * 100).toFixed(1) + "%" : "-");
      setText("expectancyOut", expectancy ? money(expectancy) : "-");
      setText("gradeOut", grade);
      setText("tradeDecision", grade);
    }}

    function loadAuditRows() {{
      try {{
        return JSON.parse(localStorage.getItem("strategyLabAudit") || "[]");
      }} catch (error) {{
        return [];
      }}
    }}

    function saveAuditRows(rows) {{
      localStorage.setItem("strategyLabAudit", JSON.stringify(rows.slice(-30)));
    }}

    function renderAuditRows() {{
      const rows = loadAuditRows();
      const log = document.getElementById("auditLog");
      if (!log) return;
      if (!rows.length) {{
        log.innerHTML = `<article>No completed forecast audits yet. Record one after market close.</article>`;
        setText("auditStats", "No journal yet");
        return;
      }}
      const hitRate = rows.filter((row) => row.hit).length / rows.length * 100;
      const avgBrier = rows.reduce((total, row) => total + row.brier, 0) / rows.length;
      setText("auditStats", `${{rows.length}} audits - ${{hitRate.toFixed(0)}}% hit - Brier ${{avgBrier.toFixed(2)}}`);
      log.innerHTML = rows.slice(-5).reverse().map((row) => `
        <article>
          <strong>${{row.date}} - actual ${{row.actualClass}}</strong>
          Forecast: up ${{row.up}}%, side ${{row.side}}%, down ${{row.down}}%. Move: ${{row.move}}%. Brier: ${{row.brier.toFixed(2)}}.
        </article>
      `).join("");
    }}

    function recordAuditRow() {{
      const up = clamp(numberValue("auditUp"), 0, 100);
      const side = clamp(numberValue("auditSide"), 0, 100);
      const down = clamp(numberValue("auditDown"), 0, 100);
      const move = numberValue("actualMove");
      const actualClass = move > 0.3 ? "up" : move < -0.3 ? "down" : "sideways";
      const predictedClass = up >= side && up >= down ? "up" : down >= up && down >= side ? "down" : "sideways";
      const outcome = {{
        up: actualClass === "up" ? 1 : 0,
        sideways: actualClass === "sideways" ? 1 : 0,
        down: actualClass === "down" ? 1 : 0
      }};
      const brier = Math.pow(up / 100 - outcome.up, 2) + Math.pow(side / 100 - outcome.sideways, 2) + Math.pow(down / 100 - outcome.down, 2);
      const rows = loadAuditRows();
      rows.push({{
        date: new Date().toLocaleString(),
        up,
        side,
        down,
        move,
        actualClass,
        hit: predictedClass === actualClass,
        brier
      }});
      saveAuditRows(rows);
      renderAuditRows();
    }}

    let liveWallsRows = [];
    let liveWallsLoading = false;

    function escapeHtmlText(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\\"": "&quot;",
        "'": "&#39;"
      }}[char]));
    }}

    function fmtWallNumber(value, digits = 2) {{
      if (value === null || value === undefined || value === "") return "-";
      const number = Number(value);
      if (!Number.isFinite(number)) return "-";
      return number.toLocaleString(undefined, {{ maximumFractionDigits: digits, minimumFractionDigits: 0 }});
    }}

    function fmtWallPct(value) {{
      if (value === null || value === undefined || value === "") return "-";
      const number = Number(value);
      if (!Number.isFinite(number)) return "-";
      return number.toFixed(2) + "%";
    }}

    function updateLiveWallsStatus(text, meta) {{
      setText("liveWallsStatus", text);
      if (meta !== undefined) setText("liveWallsMeta", meta);
    }}

    function filteredLiveWallRows() {{
      const query = (document.getElementById("wallSearch")?.value || "").trim().toUpperCase();
      const kind = document.getElementById("wallKindFilter")?.value || "all";
      const availability = document.getElementById("wallAvailabilityFilter")?.value || "all";
      return liveWallsRows.filter((row) => {{
        if (query && !String(row.symbol || "").toUpperCase().includes(query)) return false;
        if (kind !== "all" && row.kind !== kind) return false;
        if (availability === "available" && !row.available) return false;
        if (availability === "missing" && row.available) return false;
        return true;
      }});
    }}

    function renderLiveWallsTable() {{
      const body = document.getElementById("liveWallsBody");
      if (!body) return;
      const rows = filteredLiveWallRows();
      if (liveWallsLoading) {{
        body.innerHTML = `<tr><td colspan="13" class="empty">Refreshing live options walls. This can take a minute for the full watchlist...</td></tr>`;
        return;
      }}
      if (!rows.length) {{
        body.innerHTML = `<tr><td colspan="13" class="empty">No matching options-wall rows.</td></tr>`;
        return;
      }}
      body.innerHTML = rows.map((row) => {{
        if (!row.available) {{
          return `
            <tr>
              <td><strong>${{escapeHtmlText(row.symbol)}}</strong></td>
              <td>${{escapeHtmlText(row.kind || "-")}}</td>
              <td>${{escapeHtmlText(row.expiration_date || "-")}}</td>
              <td colspan="10" class="wall-error">${{escapeHtmlText(row.error || "Unavailable")}}</td>
            </tr>
          `;
        }}
        const putClass = Number(row.put_wall_distance_pct || 0) > -0.4 ? "wall-good" : "";
        const callClass = Number(row.call_wall_distance_pct || 0) < 0.4 ? "wall-error" : "";
        return `
          <tr>
            <td><strong>${{escapeHtmlText(row.symbol)}}</strong></td>
            <td>${{escapeHtmlText(row.kind)}}</td>
            <td>${{escapeHtmlText(row.expiration_date || "-")}}</td>
            <td>${{fmtWallNumber(row.underlying_price)}}</td>
            <td class="${{putClass}}">${{fmtWallNumber(row.put_wall_strike)}}</td>
            <td>${{fmtWallNumber(row.put_wall_oi, 0)}}</td>
            <td>${{fmtWallPct(row.put_wall_distance_pct)}}</td>
            <td class="${{callClass}}">${{fmtWallNumber(row.call_wall_strike)}}</td>
            <td>${{fmtWallNumber(row.call_wall_oi, 0)}}</td>
            <td>${{fmtWallPct(row.call_wall_distance_pct)}}</td>
            <td>${{fmtWallNumber(row.max_pain)}}</td>
            <td>${{fmtWallNumber(row.near_put_call_oi_ratio)}}</td>
            <td>${{escapeHtmlText(row.interpretation || "-")}}</td>
          </tr>
        `;
      }}).join("");
    }}

    async function loadLiveOptionsWalls() {{
      if (liveWallsLoading) return;
      liveWallsLoading = true;
      updateLiveWallsStatus("Refreshing", "Pulling nearest expiry and live option open interest...");
      setText("liveWallsCoverage", "-");
      renderLiveWallsTable();
      try {{
        const response = await fetch("/api/live-options-walls?ts=" + Date.now(), {{ cache: "no-store" }});
        const payload = await response.json();
        if (!response.ok || payload.error) {{
          throw new Error(payload.error || "Options-wall refresh failed");
        }}
        liveWallsRows = payload.rows || [];
        const requestedAt = payload.requested_at ? new Date(payload.requested_at).toLocaleString() : "just now";
        setText("liveWallsTimestamp", "Last refresh: " + requestedAt);
        setText("liveWallsCoverage", `${{payload.available_count || 0}} / ${{payload.symbol_count || 0}}`);
        updateLiveWallsStatus("Live", `Nearest expiry scan from ${{payload.from_date || "-"}}.`);
      }} catch (error) {{
        liveWallsRows = [];
        updateLiveWallsStatus("Error", error.message || String(error));
        setText("liveWallsCoverage", "0");
      }} finally {{
        liveWallsLoading = false;
        renderLiveWallsTable();
      }}
    }}

    candidateCount.textContent = plans.length + " scanned";
    body.innerHTML = plans.length ? plans.map((plan) => `
      <tr>
        <td><strong>${{plan.instrument}}</strong><br><span style="color:var(--muted)">${{plan.date}}</span></td>
        <td>${{plan.kind}}</td>
        <td><span class="tag ${{setupClass(plan.setup)}}">${{plan.setup}}</span></td>
        <td><strong>${{plan.score}}</strong></td>
        <td>${{plan.lane}}</td>
        <td>${{plan.close.toFixed(2)}}</td>
        <td>${{plan.ema20.toFixed(2)}}</td>
        <td>${{plan.sma50.toFixed(2)}}</td>
        <td>${{plan.sma200.toFixed(2)}}</td>
        <td>${{plan.rsi14.toFixed(1)}}</td>
        <td>${{plan.atr_pct.toFixed(2)}}%</td>
        <td>${{plan.relative_strength_20d.toFixed(2)}}%</td>
        <td>${{plan.stop.toFixed(2)}}</td>
        <td>${{plan.target1.toFixed(2)}} / ${{plan.target2.toFixed(2)}}</td>
        ${{includePrivate ? `<td>${{money(plan.max_trade_risk)}} max risk<br>${{money(plan.suggested_cash_position)}} position<br>R/R ${{plan.reward_to_risk.toFixed(2)}}</td>` : ""}}
        <td>${{plan.options_candidate}}</td>
        <td>${{plan.exit_rule}}</td>
      </tr>
    `).join("") : `<tr><td colspan="{empty_colspan}" class="empty">No scan results yet. Add a Massive API key, then refresh.</td></tr>`;

    alertCount.textContent = alerts.length + " recent";
    alertList.innerHTML = alerts.length ? alerts.map((alert) => `
      <article class="alert">
        <strong>${{alert.instrument}} ${{alert.type.replaceAll("_", " ")}}</strong>
        <span>${{alert.created_at}}</span>
        <span>${{alert.message}}</span>
      </article>
    `).join("") : `<div class="empty">No local alerts yet.</div>`;

    populatePlanSelect();
    applySelectedPlan();
    updateStrategyRead();
    updateRegimeScore();
    renderAuditRows();

    document.querySelectorAll(".lab-check").forEach((item) => {{
      item.addEventListener("change", updateRegimeScore);
    }});
    ["accountInput", "riskPctInput", "entryInput", "stopInput", "targetInput", "winProbInput", "optionDebitInput", "spreadWidthInput", "tradeType"].forEach((id) => {{
      const element = document.getElementById(id);
      if (element) element.addEventListener("input", updateTradeTicket);
      if (element) element.addEventListener("change", updateTradeTicket);
    }});
    const planSelect = document.getElementById("planSelect");
    if (planSelect) planSelect.addEventListener("change", applySelectedPlan);
    const strategySelect = document.getElementById("strategySelect");
    if (strategySelect) strategySelect.addEventListener("change", updateStrategyRead);
    const recordAudit = document.getElementById("recordAudit");
    if (recordAudit) recordAudit.addEventListener("click", recordAuditRow);
    ["wallSearch", "wallKindFilter", "wallAvailabilityFilter"].forEach((id) => {{
      const element = document.getElementById(id);
      if (element) element.addEventListener("input", renderLiveWallsTable);
      if (element) element.addEventListener("change", renderLiveWallsTable);
    }});
    const refreshLiveWalls = document.getElementById("refreshLiveWalls");
    if (refreshLiveWalls) refreshLiveWalls.addEventListener("click", loadLiveOptionsWalls);
    loadLiveOptionsWalls();

    tabButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        const target = button.dataset.tab;
        tabButtons.forEach((item) => item.classList.toggle("active", item === button));
        tabPages.forEach((page) => page.classList.toggle("active", page.id === target));
        if (target === "optionsWallsTab" && !liveWallsRows.length && !liveWallsLoading) {{
          loadLiveOptionsWalls();
        }}
      }});
    }});
  </script>
</body>
</html>"""
