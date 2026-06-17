from __future__ import annotations

import json
import sys

from app.config import get_massive_api_key, load_watchlist_config
from app.config import DATA_DIR
from app.market_data import fetch_histories
from app.market_forecast import CORE_SYMBOLS, build_market_forecast
from app.options_walls import fetch_options_walls


def main() -> int:
    api_key = get_massive_api_key()
    if not api_key:
        print("Missing MASSIVE_API_KEY in .env", file=sys.stderr)
        return 1

    watchlist = load_watchlist_config()
    symbols = sorted(set([*CORE_SYMBOLS, *watchlist.get("etfs", []), *watchlist.get("stocks", [])]))
    histories = fetch_histories(symbols, api_key)
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
    rendered = json.dumps(forecast, indent=2)
    (DATA_DIR / "latest_premarket_forecast.json").write_text(rendered, encoding="utf-8")
    forecast_dir = DATA_DIR / "forecasts"
    forecast_dir.mkdir(exist_ok=True)
    (forecast_dir / f"forecast_asof_{forecast.get('as_of')}_for_{forecast.get('next_session')}.json").write_text(
        rendered,
        encoding="utf-8",
    )
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
