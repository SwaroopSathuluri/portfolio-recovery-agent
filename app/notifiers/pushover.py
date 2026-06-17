from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from ..config import get_pushover_credentials


PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"


def send_pushover_message(title: str, message: str, priority: int = 0, url: str | None = None) -> dict[str, Any]:
    """Disabled-by-default helper for the later mobile-alert phase."""
    token, user_key = get_pushover_credentials()
    if not token or not user_key:
        return {"status": 0, "errors": ["Missing Pushover credentials"]}

    payload: dict[str, Any] = {
        "token": token,
        "user": user_key,
        "title": title,
        "message": message[:1024],
        "priority": str(priority),
    }
    if url:
        payload["url"] = url
        payload["url_title"] = "Open dashboard"
    if priority == 2:
        payload["retry"] = "300"
        payload["expire"] = "1800"

    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(PUSHOVER_ENDPOINT, data=encoded, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))
