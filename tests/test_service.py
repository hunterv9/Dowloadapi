"""Unit tests for core/service.py — downloader/filesystem fully mocked."""

import json
from pathlib import Path
from unittest import mock

import pytest

from core import service
from core.service import friendly_error, _friendly_error, clear_video_info_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_video_info_cache()
    yield
    clear_video_info_cache()


def test_analyze_video_delegates_to_downloader(monkeypatch):
    fake_info = {"id": "123", "title": "Clip", "success": True}
    monkeypatch.setattr(service.downloader, "get_video_info", lambda url: fake_info)
    out = service.analyze_video("https://www.tiktok.com/@u/video/123")
    assert out == fake_info


def test_analyze_video_empty_url_raises():
    with pytest.raises(ValueError, match="không được để trống"):
        service.analyze_video("")
    with pytest.raises(ValueError, match="không được để trống"):
        service.analyze_video("   ")


def test_analyze_video_uses_cache(monkeypatch):
    calls = {"n": 0}

    def _fake(url):
        calls["n"] += 1
        return {"id": "1", "url": url}

    monkeypatch.setattr(service.downloader, "get_video_info", _fake)
    r1 = service.analyze_video("https://www.tiktok.com/@u/video/1")
    r2 = service.analyze_video("https://www.tiktok.com/@u/video/1")
    assert r1 == r2
    assert calls["n"] == 1


def test_analyze_video_cache_disabled_when_ttl_zero(monkeypatch):
    monkeypatch.setenv("VIDEO_INFO_TTL", "0")
    calls = {"n": 0}

    def _fake(url):
        calls["n"] += 1
        return {"id": "1"}

    monkeypatch.setattr(service.downloader, "get_video_info", _fake)
    service.analyze_video("https://www.tiktok.com/@u/video/9")
    service.analyze_video("https://www.tiktok.com/@u/video/9")
    assert calls["n"] == 2


def test_download_single_video_happy_path(monkeypatch):
    expected = {"success": True, "filename": "clip.mp4"}
    monkeypatch.setattr(service.downloader, "download_video", lambda **kw: expected)
    result = service.download_single_video("https://www.tiktok.com/@u/video/123")
    assert result == expected


def test_download_single_video_forwards_custom_dir_and_callback(monkeypatch):
    received = {}

    def _fake(url, custom_output_dir=None, progress_callback=None, with_subtitles=True):
        received["url"] = url
        received["custom_output_dir"] = custom_output_dir
        received["progress_callback"] = progress_callback
        received["with_subtitles"] = with_subtitles
        return {"success": True}

    monkeypatch.setattr(service.downloader, "download_video", _fake)
    cb = mock.Mock()
    service.download_single_video("https://www.tiktok.com/@u/video/1", custom_dir="mydir", progress_callback=cb)
    assert received["custom_output_dir"] == "mydir"
    assert received["progress_callback"] is cb
    assert received["with_subtitles"] is True


# -- friendly_error mappings --------------------------------------------------

@pytest.mark.parametrize("msg,expected_fragment", [
    ("Invalid URL provided", "Link không hợp lệ"),
    ("unsupported url", "Link không hợp lệ"),
    ("video is private", "riêng tư"),
    ("login required", "riêng tư"),
    ("403 Forbidden", "riêng tư"),
    ("not found", "không tồn tại"),
    ("404 error", "không tồn tại"),
    ("timeout connecting", "quá chậm"),
    ("connection refused", "Không thể kết nối mạng"),
    ("network error", "Không thể kết nối mạng"),
    ("rate limit exceeded", "quá nhanh"),
    ("429 Too Many Requests", "quá nhanh"),
    ("geo blocked", "bị chặn theo khu vực"),
    ("region restricted", "bị chặn theo khu vực"),
    ("cookie expired", "Cookie không hợp lệ"),
    ("No space left", "Không đủ dung lượng"),
    ("disk full", "Không đủ dung lượng"),
    ("permission denied", "Không có quyền ghi"),
    ("access denied", "Không có quyền ghi"),
])
def test_friendly_error_maps_known_patterns(msg, expected_fragment):
    out = friendly_error(Exception(msg))
    assert expected_fragment.lower() in out.lower()


def test_friendly_error_unknown_returns_generic():
    out = friendly_error(Exception("something totally unknown xyz 123"))
    assert "không xác định" in out.lower()


def test_friendly_error_alias_is_same():
    assert _friendly_error is friendly_error


# -- list_downloads -----------------------------------------------------------

def test_list_downloads_empty_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_downloads_dir", lambda: tmp_path)
    result = service.list_downloads()
    assert result["count"] == 0
    assert result["files"] == []
    assert result["total_size_mb"] == 0


def test_list_downloads_with_files(monkeypatch, tmp_path):
    # Create fake mp4 + sidecar json
    mp4 = tmp_path / "tiktok_user_123_Title.mp4"
    mp4.write_bytes(b"x" * 1024)
    sidecar = tmp_path / "tiktok_user_123_Title.info.json"
    sidecar.write_text(json.dumps({
        "title": "My Title", "uploader": "creator", "thumbnail": "https://cdn/cover.jpg"
    }), encoding="utf-8")
    # Another file without sidecar
    mp4b = tmp_path / "douyin_456.mp4"
    mp4b.write_bytes(b"y" * 2048)

    monkeypatch.setattr(service, "get_downloads_dir", lambda: tmp_path)
    result = service.list_downloads()
    assert result["count"] == 2
    assert result["total_size_mb"] == round(3072 / (1024 * 1024), 2)
    titles = {f["title"] for f in result["files"]}
    assert "My Title" in titles
    # Platform detection
    platforms = {f["platform"] for f in result["files"]}
    assert "Douyin" in platforms
    assert "TikTok" in platforms
    # stream_url present
    for f in result["files"]:
        assert f["stream_url"].startswith("/downloaded-media/")


def test_list_downloads_ignores_non_mp4(monkeypatch, tmp_path):
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(service, "get_downloads_dir", lambda: tmp_path)
    result = service.list_downloads()
    assert result["count"] == 0


def test_get_downloads_dir_creates_dir(monkeypatch, tmp_path):
    target = tmp_path / "new_downloads"
    monkeypatch.setattr(service.cookie_mgr, "config", {"download_dir": str(target)})
    # Patch Path mkdir via real call — just verify it creates
    result = service.get_downloads_dir()
    assert result.exists()


def test_safe_media_path_traversal_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_downloads_dir", lambda: tmp_path)
    # Attempt to escape
    assert service.safe_media_path("../../etc/passwd") is None
    assert service.safe_media_path(str(tmp_path / ".." / "etc" / "passwd")) is None


def test_safe_media_path_valid_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_downloads_dir", lambda: tmp_path)
    p = service.safe_media_path("subdir/clip.mp4")
    assert p is not None
    assert str(p).startswith(str(tmp_path.resolve()))


def test_delete_download_success(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_downloads_dir", lambda: tmp_path)
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"data")
    jf = tmp_path / "clip.info.json"
    jf.write_text("{}", encoding="utf-8")
    result = service.delete_download("clip.mp4")
    assert result["success"] is True
    assert not f.exists()
    assert not jf.exists()


def test_delete_download_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_downloads_dir", lambda: tmp_path)
    result = service.delete_download("nonexistent.mp4")
    assert result["success"] is False
