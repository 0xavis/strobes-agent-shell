"""Configuration and persistent state for the shell agent.

Loads settings from (in priority order):
1. CLI flags (--url, --api-key, etc.)
2. Environment variables (STROBES_URL, STROBES_API_KEY, etc.)
3. .env file in current directory or ~/.strobes-shell-agent/.env
4. ~/.strobes-shell-agent/config.json (for persistent bridge_id only)
"""

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".strobes-shell-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Load .env from cwd first, then from config dir
load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
load_dotenv(dotenv_path=CONFIG_DIR / ".env", override=False)


def get_or_create_bridge_id() -> str:
    """Get the persistent bridge_id, creating one on first run."""
    # Check env first
    env_id = os.environ.get("STROBES_BRIDGE_ID")
    if env_id:
        return env_id
    # Fall back to config file
    config = _load_config()
    if "bridge_id" not in config:
        config["bridge_id"] = str(uuid.uuid4())
        _save_config(config)
    return config["bridge_id"]


def get_env(key: str, default: str = "") -> str:
    """Get a config value from environment."""
    return os.environ.get(key, default)


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
