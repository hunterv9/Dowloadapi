"""Hermetic tests for core/stealth.py and the video-info cache."""

import time

import pytest

from core import stealth
from core.stealth import (
    RateLimiter,
    backoff_sleep,
    browser_like_headers,
    get_limiter,
    headed_allowed,
    note_429,
    pace_before_request,
    pick_user_agent,
    reset_limiters,
    retry_after_seconds,
)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    reset_limiters()
    monkeypatch.setenv("STEALTH_JITTER_MS", "0,0")
    monkeypatch.setenv("STEALTH_RPS", "1000")
    monkeypatch.setenv("STEALTH_BURST", "100")
    yield
    reset_limiters()


def test_pick_user_agent_from_pool():
    uas = {pick_user_agent() for _ in range(50)}
    assert uas <= set(stealth._USER_AGENTS)
    assert len(uas) > 1  # actually rotates


def test_browser_like_headers_full_set():
    h = browser_like_headers(user_agent=stealth._PC_CHROME, referer="https://www.tiktok.com/")
    assert h["Sec-Fetch-Dest"] == "document"
    assert h["Sec-Fetch-Mode"] == "navigate"
    assert h["Sec-Ch-Ua-Platform"] == '"Windows"'
    assert h["Referer"] == "https://www.tiktok.com/"
    assert "Cookie" not in h


def test_rate_limiter_burst_then_waits():
    lim = RateLimiter(rps=50, burst=1)
    assert lim.acquire("b") < 0.05
    waited = lim.acquire("b")  # must refill one token: ~1/50s
    assert 0.005 <= waited < 1.0


def test_backoff_sleep_full_jitter(monkeypatch):
    calls = []
    monkeypatch.setattr(time, "sleep", calls.append)
    import random
    rng = random.Random(0)
    slept = backoff_sleep(2, base=1.0, cap=30.0, rng=rng)
    assert calls == [slept]
    assert 0 <= slept <= 4.0


def test_retry_after_seconds():
    assert retry_after_seconds("120") == 120.0
    assert retry_after_seconds(None) is None
    assert retry_after_seconds("garbage") is None
    # HTTP-date in the future → positive delta
    assert retry_after_seconds("Wed, 01 Jan 2042 00:00:00 GMT") > 0


def test_note_429_triggers_cooldown_every_third(monkeypatch):
    monkeypatch.setenv("STEALTH_COOLDOWN_S", "0")
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    assert note_429("d") is False
    assert note_429("d") is False
    assert note_429("d") is True
    assert sleeps  # cool-down sleep happened (0s)


def test_pace_before_request_fast_path():
    t0 = time.monotonic()
    pace_before_request("d", limiter=get_limiter())
    assert time.monotonic() - t0 < 2.0


def test_headed_allowed(monkeypatch):
    monkeypatch.setenv("STEALTH_ALLOW_HEADED", "0")
    assert headed_allowed() is False
    monkeypatch.setenv("STEALTH_ALLOW_HEADED", "1")
    assert headed_allowed() is True


def test_headers_cookie_and_rotation():
    from core.tiktok_api import TikTokAPI
    api = TikTokAPI()
    api.set_cookie_string("ttwid=X")
    seen = {api._headers()["User-Agent"] for _ in range(30)}
    assert len(seen) > 1
    h = api._headers()
    assert h["Cookie"] == "ttwid=X"
    assert h["Sec-Fetch-Dest"] == "document"


def test_retry_honours_retry_after(monkeypatch):
    from core.tiktok_api import TikTokAPI

    class _Resp:
        def __init__(self, status, headers=None):
            self.status_code = status
            self.headers = headers or {}

    calls = {"n": 0}

    def _fake_request(method, url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429, {"Retry-After": "1"})
        return _Resp(200)

    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(stealth, "note_429", lambda bucket: False)

    api = TikTokAPI()
    api.session.request = _fake_request
    resp = api._request_with_retry("GET", "https://www.tiktok.com/x", max_retries=2)
    assert resp.status_code == 200
    assert calls["n"] == 2
    assert 1.0 in sleeps  # Retry-After: 1 was honoured


def test_analyze_video_cache(monkeypatch):
    from core import service

    calls = {"n": 0}

    def _fake_info(url):
        calls["n"] += 1
        return {"id": "1", "url": url}

    monkeypatch.setattr(service.downloader, "get_video_info", _fake_info)
    service.clear_video_info_cache()
    try:
        r1 = service.analyze_video("https://www.tiktok.com/@u/video/1")
        r2 = service.analyze_video("https://www.tiktok.com/@u/video/1")
        assert r1 == r2
        assert calls["n"] == 1  # second hit served from cache
        service.analyze_video("https://www.tiktok.com/@u/video/2")
        assert calls["n"] == 2
    finally:
        service.clear_video_info_cache()
        monkeypatch.setenv("VIDEO_INFO_TTL", "300")


def test_batch_workers_env(monkeypatch):
    from core.profile_scraper import _batch_workers
    monkeypatch.setenv("DOWNLOAD_WORKERS", "12")
    assert _batch_workers() == 12
    monkeypatch.setenv("DOWNLOAD_WORKERS", "999")
    assert _batch_workers() == 16
    monkeypatch.setenv("DOWNLOAD_WORKERS", "bogus")
    assert _batch_workers() == 4
