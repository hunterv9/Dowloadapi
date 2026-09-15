"""Stealth + pacing layer for outbound scraping requests.

Two goals that pull in opposite directions:

1. **Throughput** — serve as many requests as possible (keep-alive sessions,
   no wasted retries, cached video-info).
2. **Anti-detection** — don't look like a bot scan (rotated user-agents with
   matching header sets, per-domain token-bucket pacing, jittered backoff,
   ``Retry-After`` compliance, cool-down after repeated 429s).

All behaviour is env-tunable (see README)::

    STEALTH_RPS=3.0            sustained scrape requests/sec per domain
    STEALTH_BURST=6            bucket size (short bursts allowed)
    STEALTH_JITTER_MS=150,700  random pre-request delay range (milliseconds)
    STEALTH_COOLDOWN_S=120     sleep after 3 consecutive 429s on a domain
    STEALTH_ALLOW_HEADED=0     set to 1 to allow visible-browser fallback
"""

import logging
import os
import random
import threading
import time
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

__all__ = [
    "RateLimiter",
    "IPHONE_USER_AGENT",
    "PC_USER_AGENT",
    "get_limiter",
    "reset_limiters",
    "pick_user_agent",
    "browser_like_headers",
    "pace_before_request",
    "backoff_sleep",
    "retry_after_seconds",
    "note_429",
    "headed_allowed",
]

# -- user-agent pool (real, current browser strings) ---------------------------
_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)
_IPHONE_OLD = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)
_PC_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_PC_CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_USER_AGENTS: List[str] = [_IPHONE, _IPHONE_OLD, _ANDROID, _PC_CHROME, _PC_CHROME_MAC]

# Canonical single-source user-agents (newest strings; import these elsewhere).
IPHONE_USER_AGENT = _IPHONE
PC_USER_AGENT = _PC_CHROME

_ACCEPT_LANGUAGES = (
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,vi;q=0.8",
    "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
)


def pick_user_agent(rng: random.Random = random) -> str:
    """Return a random user-agent so traffic isn't one fixed fingerprint."""
    return rng.choice(_USER_AGENTS)


def browser_like_headers(user_agent: Optional[str] = None,
                         referer: str = "https://www.tiktok.com/",
                         rng: random.Random = random) -> Dict[str, str]:
    """Build a full browser-like header set matching *user_agent*.

    Bots typically send only ``User-Agent``; real browsers send the
    ``Sec-Fetch-*`` / ``Sec-Ch-Ua`` family. Missing them is a cheap signal.
    """
    ua = user_agent or pick_user_agent(rng)
    headers: Dict[str, str] = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": rng.choice(_ACCEPT_LANGUAGES),
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if "Chrome/" in ua and "iPhone" not in ua and "Android" not in ua:
        # Desktop Chrome client hints — must match a Chrome UA.
        headers["Sec-Ch-Ua"] = '"Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="99"'
        headers["Sec-Ch-Ua-Mobile"] = "?0"
        headers["Sec-Ch-Ua-Platform"] = '"macOS"' if "Macintosh" in ua else '"Windows"'
    elif "Android" in ua:
        headers["Sec-Ch-Ua-Mobile"] = "?1"
        headers["Sec-Ch-Ua-Platform"] = '"Android"'
    headers["Referer"] = referer
    return headers


# -- per-domain token-bucket rate limiter --------------------------------------
class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, capacity: float):
        self.tokens = capacity
        self.updated = time.monotonic()


class RateLimiter:
    """Thread-safe token-bucket limiter with named buckets (one per domain)."""

    def __init__(self, rps: float, burst: int):
        self.rps = max(rps, 0.001)
        self.burst = max(burst, 1)
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def acquire(self, bucket: str) -> float:
        """Block until a token is available. Returns seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                b = self._buckets.get(bucket)
                if b is None:
                    b = self._buckets[bucket] = _Bucket(float(self.burst))
                now = time.monotonic()
                b.tokens = min(float(self.burst), b.tokens + (now - b.updated) * self.rps)
                b.updated = now
                if b.tokens >= 1.0:
                    b.tokens -= 1.0
                    return waited
                deficit = (1.0 - b.tokens) / self.rps
            time.sleep(deficit)
            waited += deficit


_LIMITERS: Dict[Tuple[float, int], RateLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


from .env_utils import _env_float, _env_int


def get_limiter(rps: Optional[float] = None, burst: Optional[int] = None) -> RateLimiter:
    """Shared limiter instance for the given config (env-overridable)."""
    if rps is None:
        rps = _env_float("STEALTH_RPS", 3.0)
    if burst is None:
        burst = _env_int("STEALTH_BURST", 6)
    key = (rps, burst)
    with _LIMITERS_LOCK:
        lim = _LIMITERS.get(key)
        if lim is None:
            lim = _LIMITERS[key] = RateLimiter(rps, burst)
        return lim


def reset_limiters() -> None:
    """Drop cached limiters (used by tests)."""
    with _LIMITERS_LOCK:
        _LIMITERS.clear()


def _jitter_range() -> Tuple[int, int]:
    raw = os.getenv("STEALTH_JITTER_MS", "150,700")
    try:
        lo_s, hi_s = raw.split(",", 1)
        lo, hi = int(lo_s), int(hi_s)
        if lo < 0 or hi < lo:
            raise ValueError
        return lo, hi
    except ValueError:
        return 150, 700


def pace_before_request(bucket: str,
                         limiter: Optional[RateLimiter] = None,
                         rng: random.Random = random) -> None:
    """Pace one outbound scrape request: token-bucket + random jitter.

    The jitter breaks the metronome pattern (fixed-interval requests are a
    classic bot signal) while the bucket caps sustained rate per domain.
    """
    (limiter or get_limiter()).acquire(bucket)
    lo, hi = _jitter_range()
    if hi > 0:
        time.sleep(rng.randint(lo, hi) / 1000.0)


def backoff_sleep(attempt: int, base: float = 1.0, cap: float = 30.0,
                  rng: random.Random = random) -> float:
    """Sleep with full jitter (AWS-style): uniform(0, min(cap, base*2^attempt))."""
    slept = rng.uniform(0, min(cap, base * (2 ** attempt)))
    time.sleep(slept)
    return slept


def retry_after_seconds(value: Optional[str]) -> Optional[float]:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date)."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        return max(0.0, (dt.timestamp() - time.time()))
    except (TypeError, ValueError, OverflowError):
        return None


# -- 429 cool-down tracker ------------------------------------------------------
_429_STATE: Dict[str, Dict] = {}
_429_LOCK = threading.Lock()


def _cooldown_seconds() -> float:
    return _env_float("STEALTH_COOLDOWN_S", 120.0)


def note_429(bucket: str) -> bool:
    """Record a 429 for *bucket*. Every 3rd consecutive 429 triggers cool-down.

    Returns True when the caller should cool down now.
    """
    now = time.monotonic()
    with _429_LOCK:
        st = _429_STATE.get(bucket)
        if st is None or now - st["at"] > 600:
            st = _429_STATE[bucket] = {"count": 0, "at": now}
        st["count"] += 1
        st["at"] = now
        trigger = st["count"] % 3 == 0
    if trigger:
        secs = _cooldown_seconds()
        _log.warning("429 x%d on %s — cooling down %.0fs", st["count"], bucket, secs)
        time.sleep(secs)
    return trigger


def note_success(bucket: str) -> None:
    """Reset the 429 counter for *bucket* after a successful response."""
    with _429_LOCK:
        _429_STATE.pop(bucket, None)


def headed_allowed() -> bool:
    """Visible-browser fallback is only allowed with an explicit opt-in.

    On headless Ubuntu servers a headed Chromium would crash/hang and stall
    API requests — never attempt it there.
    """
    return os.getenv("STEALTH_ALLOW_HEADED", "0") == "1"
