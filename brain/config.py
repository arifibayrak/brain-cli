import os
import tomllib
import tomli_w
from pathlib import Path

BRAIN_DIR = Path.home() / ".brain"
CONFIG_PATH = BRAIN_DIR / "config.toml"

DEFAULTS = {
    "anthropic_api_key": "",
    "brain_dir": str(BRAIN_DIR),
    "git_auto_commit": True,
    "haiku_model": "claude-haiku-4-5-20251001",
    "sonnet_model": "claude-sonnet-4-6",
    "chat_model": "claude-haiku-4-5-20251001",  # default to Haiku — 8x cheaper than Sonnet for chat
    "openai_api_key": "",
    "quality_provider": "anthropic",  # "anthropic" or "openai"
    "google_calendar_enabled": False,
    "google_gmail_enabled": False,
    "google_credentials_path": str(BRAIN_DIR / "credentials" / "google_oauth.json"),
    "google_token_path": str(BRAIN_DIR / "credentials" / "google_token.json"),
}


def load() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    # Merge with defaults for any missing keys
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save(cfg: dict) -> None:
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(cfg, f)


def get(key: str, default=None):
    cfg = load()
    return cfg.get(key, default)


def set_key(key: str, value) -> None:
    cfg = load()
    cfg[key] = value
    save(cfg)


def api_key() -> str:
    """Return API key: config file > env var."""
    key = get("anthropic_api_key", "")
    if not key:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    return key


def brain_dir() -> Path:
    return Path(get("brain_dir", str(BRAIN_DIR)))
