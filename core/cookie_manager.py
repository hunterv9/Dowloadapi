"""Configuration and cookie management for the downloader engine."""

import json
import os
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
            "proxy": "",
        }
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except (json.JSONDecodeError, OSError):
                pass
        default_config["download_dir"] = self._resolve_download_dir(
            default_config.get("download_dir", "./downloads")
        )
        return default_config

    @staticmethod
    def _resolve_download_dir(raw: Any) -> str:
        """Resolve *raw* download dir against config file's parent dir."""
        p = Path(str(raw or "./downloads")).expanduser()
        if not p.is_absolute():
            p = CONFIG_FILE.parent / p
        return str(p.resolve()) if p.exists() else str(p.absolute())

    def get_download_dir(self) -> Path:
        """Return download dir as absolute Path (CWD-independent)."""
        return Path(self._resolve_download_dir(self.config.get("download_dir")))

    def save_config(self, new_config: Dict[str, Any]) -> None:
        """Merge *new_config* into the current config and persist to disk."""
        self.config.update(new_config)
        # ponytail: keep download_dir portable — store relative when inside
        # project root; upgrade path: user-specified absolute paths stay absolute.
        try:
            dd = Path(str(self.config.get("download_dir", "./downloads")))
            if dd.is_absolute():
                self.config["download_dir"] = str(
                    dd.relative_to(CONFIG_FILE.parent.resolve())
                ).replace("\\", "/") if CONFIG_FILE.parent.resolve() in dd.resolve().parents else str(dd)
                if not self.config["download_dir"].startswith("."):
                    self.config["download_dir"] = "./" + self.config["download_dir"]
        except (OSError, ValueError):
            pass
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        try:
            # Cookies stored as plaintext: restrict to owner-only (0600).
            # Note: on Windows chmod has no POSIX effect; ACLs apply instead.
            os.chmod(CONFIG_FILE, 0o600)
        except OSError:
            pass

    # -- cookie helpers -----------------------------------------------------
    def get_active_cookie_string(self, domain: str = "tiktok.com") -> str:
        """Return the active cookie string for *domain*."""
        return self.config.get("custom_cookie_string", "").strip()

    # -- proxy helpers -------------------------------------------------------
    def get_proxy(self) -> str:
        """Return the configured proxy URL, or empty string if not set."""
        return self.config.get("proxy", "").strip()
