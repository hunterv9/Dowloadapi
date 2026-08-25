"""Configuration and cookie management for the downloader engine."""

import json
from pathlib import Path
from typing import Dict, Any

__all__ = ["CookieManager", "CONFIG_FILE"]

CONFIG_FILE = Path(__file__).parent.parent / "config.json"


class CookieManager:
    """Load, persist and query runtime configuration plus active cookies."""

    def __init__(self):
        self.config = self.load_config()

    # -- config persistence -------------------------------------------------
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from *config.json*, falling back to defaults."""
        default_config: Dict[str, Any] = {
            "custom_cookie_string": "",
            "download_dir": str(Path(__file__).parent.parent / "downloads"),
            "video_quality": "hd",
            "save_metadata": True,
        }
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except (json.JSONDecodeError, OSError):
                pass
        return default_config

    def save_config(self, new_config: Dict[str, Any]) -> None:
        """Merge *new_config* into the current config and persist to disk."""
        self.config.update(new_config)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    # -- cookie helpers -----------------------------------------------------
    def get_active_cookie_string(self, domain: str = "tiktok.com") -> str:
        """Return the active cookie string from manual input."""
        return self.config.get("custom_cookie_string", "").strip()
