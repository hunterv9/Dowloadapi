"""Unit tests for the shared base platform API helpers."""

from core.base_api import (
    BasePlatformAPI,
    sanitize_filename,
)


class _Concrete(BasePlatformAPI):
    PLATFORM = "tiktok"
    ACCEPT_LANGUAGE = "en-US,en;q=0.9"
    REFERER = "https://www.tiktok.com/"


def test_sanitize_filename_strips_illegal_chars():
    assert sanitize_filename('a<b>:"/\\|?*') == "ab"
    assert sanitize_filename("  hello   world  ") == "hello world"
    assert sanitize_filename("x" * 300) == "x" * 100


def test_extract_video_ids_dedupes_and_caps():
    html = "/video/1 /video/2 /video/2 /video/3"
    assert BasePlatformAPI.extract_video_ids(html, 5) == ["1", "2", "3"]
    assert BasePlatformAPI.extract_video_ids(html, 2) == ["1", "2"]


def test_extract_json_script_quoted_and_unquoted():
    html = '<script id="api-data">{"a":1}</script>'
    assert BasePlatformAPI.extract_json_script(html, "api-data") == {"a": 1}

    html2 = '<script>window._ROUTER_DATA = {"b":2}</script>'
    assert BasePlatformAPI.extract_json_script(html2, "_ROUTER_DATA") == {"b": 2}


def test_find_subtitle_entries_walks_payload(sample_subtitle_json):
    found = BasePlatformAPI.find_subtitle_entries(sample_subtitle_json)
    langs = {entry["lang"] for entry in found}
    assert {"en", "vi", "auto"} <= langs
    urls = [entry["url"] for entry in found]
    assert "https://cdn.example.com/en.srt" in urls


def test_set_cookie_string_clears_header():
    api = _Concrete()
    api.set_cookie_string("a=1")
    assert api.session.headers["Cookie"] == "a=1"
    api.set_cookie_string("")
    assert "Cookie" not in api.session.headers