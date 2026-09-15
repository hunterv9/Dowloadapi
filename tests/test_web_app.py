"""Unit tests for apps/web/app.py — TestClient, no real network/disk."""

import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from apps.web import app as wapp
from apps.web.app import app


@pytest.fixture(autouse=True)
def _reset_state():
    wapp.download_tasks.clear()
    wapp._list_cache["at"] = 0.0
    wapp._list_cache["data"] = None
    yield
    wapp.download_tasks.clear()
    wapp._list_cache["at"] = 0.0
    wapp._list_cache["data"] = None


def _client(**kw):
    return TestClient(app, **kw)


# -- health ------------------------------------------------------------------


def test_health_returns_ok():
    with _client() as c:
        r = c.get("/")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# -- custom_dir validation ---------------------------------------------------


@pytest.mark.parametrize("bad_dir", [
    "/absolute/path",
    "/etc/passwd",
    "../escape",
    "../../etc",
    "a/../../b",
])
def test_custom_dir_rejects_escape(bad_dir):
    with _client() as c:
        r = c.post("/api/download-single", json={"url": "https://www.tiktok.com/@u/video/1", "custom_dir": bad_dir})
    assert r.status_code == 400
    assert "custom_dir" in r.json()["detail"].lower()


def test_custom_dir_accepts_relative():
    with mock.patch.object(wapp.service, "safe_media_path", return_value=mock.Mock()):
        with mock.patch.object(wapp.service, "download_single_video", return_value={"success": True}):
            with _client() as c:
                r = c.post("/api/download-single", json={"url": "https://www.tiktok.com/@u/video/1", "custom_dir": "mydir/sub"})
    assert r.status_code == 200
    assert "task_id" in r.json()


def test_custom_dir_none_ok():
    with mock.patch.object(wapp.service, "download_single_video", return_value={"success": True}):
        with _client() as c:
            r = c.post("/api/download-single", json={"url": "https://www.tiktok.com/@u/video/1"})
    assert r.status_code == 200


# -- video-info forwards friendly error -------------------------------------


def test_video_info_returns_400_on_bad_url(monkeypatch):
    monkeypatch.setattr(wapp.service, "analyze_video", mock.Mock(side_effect=ValueError("Invalid URL")))
    with _client() as c:
        r = c.post("/api/video-info", json={"url": "bad"})
    assert r.status_code == 400


def test_task_status_404_when_missing():
    with _client() as c:
        r = c.get("/api/task-status/does-not-exist")
    assert r.status_code == 404


def test_serve_media_404_when_missing(monkeypatch):
    monkeypatch.setattr(wapp.service, "safe_media_path", lambda p: None)
    with _client() as c:
        r = c.get("/downloaded-media/clip.mp4")
    assert r.status_code == 404
