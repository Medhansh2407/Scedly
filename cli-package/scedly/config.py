"""Config storage — API key and base URL persisted in ~/.config/scedly/"""

import json
import os
from pathlib import Path

# ─── CHANGE THIS folder name when you pick a name ───
APP_NAME = "scedly"
# ─────────────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_BASE_URL = "http://localhost:8000"


def _load() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def _save(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def get_api_key() -> str | None:
    return _load().get("api_key")


def get_base_url() -> str:
    return _load().get("base_url", DEFAULT_BASE_URL)


def save_config(api_key: str, base_url: str | None = None):
    data = _load()
    data["api_key"] = api_key
    if base_url:
        data["base_url"] = base_url
    _save(data)
