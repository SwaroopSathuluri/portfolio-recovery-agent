from __future__ import annotations

import sys

from app.notifiers.pushover import send_pushover_message


def main() -> int:
    response = send_pushover_message(
        title="Portfolio Recovery Agent",
        message="Test notification: Pushover is connected.",
        priority=0,
        url="http://127.0.0.1:8010/",
    )
    if response.get("status") != 1:
        print(response)
        return 1
    print("Pushover test sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
