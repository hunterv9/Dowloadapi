"""Unit tests for apps/web/app.py — TestClient, no real network/disk."""

import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from apps.web import app as wapp
from apps.web.app import app


@pytest.fixture(autouse=True)
def _reset_state():
    wapp._rate_buckets.clear()
    wapp.download_tasks.clear()
    wapp._list_cache["at"] = 0.0
    wapp._list_cache["data"] = None
    yield
    wapp._rate_buckets.clear()
    wapp.download_tasks.clear()
    wapp._list_cache["at"] = 0.0
    wapp._list_cache["data"] = None


def _client(**kw):
    return TestClient(app, **kw)


# -- health ------------------------------------------------------------------

def test_health_public_no_auth():
    wapp._API_KEY = ""
    with _client() as c:
        r = c.get("/")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_health_no_api_key_even_when_protected(monkeypatch):
    monkeypatch.setattr(wapp, "_API_KEY", "secret123")
    with _client() as c:
        r = c.get("/")
    assert r.status_code == 200


# -- auth --------------------------------------------------------------------

def test_protected_requires_api_key(monkeypatch):
    monkeypatch.setattr(wapp, "_API_KEY", "secret123")
    with _client() as c:
        r = c.get("/api/downloads")
    assert r.status_code == 401


def test_protected_wrong_key_rejected(monkeypatch):
    monkeypatch.setattr(wapp, "_API_KEY", "secret123")
    with _client() as c:
        r = c.get("/api/downloads", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_protected_correct_key_ok(monkeypatch):
    monkeypatch.setattr(wapp, "_API_KEY", "secret123")
    monkeypatch.setattr(wapp.service, "list_downloads", lambda: {"files": [], "count": 0, "total_size_mb": 0, "download_dir": "/tmp"})
    with _client() as c:
        r = c.get("/api/downloads", headers={"X-API-Key": "secret123"})
    assert r.status_code == 200


def test_no_api_key_env_allows_without_header():
    wapp._API_KEY = ""
    with mock.patch.object(wapp.service, "list_downloads", return_value={"files": [], "count": 0, "total_size_mb": 0, "download_dir": "/tmp"}):
        with _client() as c:
            r = c.get("/api/downloads")
    assert r.status_code == 200


# -- security headers --------------------------------------------------------

def test_security_headers_present():
    wapp._API_KEY = ""
    with _client() as c:
        r = c.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-XSS-Protection") == "1; mode=block"


def test_security_headers_on_protected(monkeypatch):
    monkeypatch.setattr(wapp, "_API_KEY", "secret123")
    with _client() as c:
        r = c.get("/api/downloads")
    # Even 401 responses go through middleware
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


# -- rate limiting -----------------------------------------------------------

def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(wapp, "_RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(wapp, "_RATE_LIMIT_WINDOW", 60)
    wapp._rate_buckets.clear()
    wapp._API_KEY = ""
    with _client() as c:
        assert c.get("/").status_code == 200
        assert c.get("/").status_code == 200
        r = c.get("/")
        assert r.status_code == 429
        assert r.json()["detail"] == "Too many requests"
    # cleanup window reset
    wapp._rate_buckets.clear()


def test_rate_limit_per_ip_isolated(monkeypatch):
    monkeypatch.setattr(wapp, "_RATE_LIMIT_REQUESTS", 1)
    monkeypatch.setattr(wapp, "_RATE_LIMIT_WINDOW", 60)
    wapp._rate_buckets.clear()
    wapp._API_KEY = ""
    # First IP fills bucket
    with _client() as c:
        assert c.get("/").status_code == 200
        assert c.get("/").status_code == 429
    wapp._rate_buckets.clear()


# -- custom_dir validation ---------------------------------------------------

@pytest.mark.parametrize("bad_dir", [
    "/absolute/path",
    "/etc/passwd",
    "../escape",
    "../../etc",
    "a/../../b",
])
def test_custom_dir_rejects_escape(bad_dir):
    wapp._API_KEY = ""
    with _client() as c:
        r = c.post("/api/download-single", json={"url": "https://www.tiktok.com/@u/video/1", "custom_dir": bad_dir})
    assert r.status_code == 400
    assert "custom_dir" in r.json()["detail"].lower()


def test_custom_dir_accepts_relative():
    wapp._API_KEY = ""
    # safe_media_path will be checked; mock it to allow
    with mock.patch.object(wapp.service, "safe_media_path", return_value=mock.Mock()):
        with mock.patch.object(wapp.service, "download_single_video", return_value={"success": True}):
            with _client() as c:
                r = c.post("/api/download-single", json={"url": "https://www.tiktok.com/@u/video/1", "custom_dir": "mydir/sub"})
    assert r.status_code == 200
    assert "task_id" in r.json()


def test_custom_dir_none_ok():
    wapp._API_KEY = ""
    with mock.patch.object(wapp.service, "download_single_video", return_value={"success": True}):
        with _client() as c:
            r = c.post("/api/download-single", json={"url": "https://www.tiktok.com/@u/video/1"})
    assert r.status_code == 200


# -- video-info forwards friendly error -------------------------------------

def test_video_info_returns_400_on_bad_url(monkeypatch):
    wapp._API_KEY = ""
    monkeypatch.setattr(wapp.service, "analyze_video", mock.Mock(side_effect=ValueError("Invalid URL")))
    with _client() as c:
        r = c.post("/api/video-info", json={"url": "bad"})
    assert r.status_code == 400


def test_task_status_404_when_missing():
    wapp._API_KEY = ""
    with _client() as c:
        r = c.get("/api/task-status/does-not-exist")
    assert r.status_code == 404


def test_serve_media_404_when_missing(monkeypatch):
    wapp._API_KEY = ""
    monkeypatch.setattr(wapp.service, "safe_media_path", lambda p: None)
    with _client() as c:
        r = c.get("/downloaded-media/clip.mp4")
    assert r.status_code == 404
