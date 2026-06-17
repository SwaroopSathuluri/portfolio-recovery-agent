from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_DIR / "config"
DATA_DIR = PROJECT_DIR / "data"


def load_env_files() -> None:
    """Load project-local env values, with a read-only parent fallback."""
    for env_path in (PROJECT_DIR / ".env", PROJECT_DIR.parent / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line or line.startswith("export "):
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_portfolio_config() -> dict[str, Any]:
    return read_json(CONFIG_DIR / "portfolio.json", {})


def load_watchlist_config() -> dict[str, list[str]]:
    payload = read_json(CONFIG_DIR / "watchlist.json", {"etfs": [], "stocks": []})
    return {
        "etfs": [str(item).upper() for item in payload.get("etfs", [])],
        "stocks": [str(item).upper() for item in payload.get("stocks", [])],
    }


def get_massive_api_key() -> str | None:
    load_env_files()
    return os.getenv("MASSIVE_API_KEY")


def get_pushover_credentials() -> tuple[str | None, str | None]:
    load_env_files()
    return os.getenv("PUSHOVER_APP_TOKEN"), os.getenv("PUSHOVER_USER_KEY")


def get_private_dashboard_token() -> str | None:
    load_env_files()
    return os.getenv("PRIVATE_DASHBOARD_TOKEN")
