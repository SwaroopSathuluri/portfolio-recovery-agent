from __future__ import annotations

import argparse
import json
import time

from app.market_monitor import run_monitor_once


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run intraday SPY/QQQ notification monitor.")
    parser.add_argument("--date", help="Market date in YYYY-MM-DD. Defaults to today's New York date.")
    parser.add_argument("--send", action="store_true", help="Send Pushover notifications when credentials exist.")
    parser.add_argument("--dry-run", action="store_true", help="Log alerts without sending phone notifications.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--interval-minutes", type=float, default=5, help="Loop interval in minutes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = args.dry_run or not args.send
    while True:
        status = run_monitor_once(market_date=args.date, dry_run=dry_run)
        print(json.dumps(status, indent=2))
        if not args.loop:
            return 0
        time.sleep(max(30, args.interval_minutes * 60))


if __name__ == "__main__":
    raise SystemExit(main())
