"""Unit tests for core/douyin_api.py — no real network calls."""

from unittest import mock

import pytest

from core.douyin_api import DouyinAPI


class _FakeResp:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


def _api():
    return DouyinAPI()


def test_extract_video_id_full_url():
    api = _api()
    assert api.extract_video_id("https://www.douyin.com/video/123456") == "123456"


def test_extract_video_id_mobile_url():
    api = _api()
    assert api.extract_video_id("https://m.douyin.com/video/654321") == "654321"


def test_extract_video_id_modal_param():
    api = _api()
    assert api.extract_video_id("https://x.com/video?modal_id=111") == "111"


def test_extract_video_id_bare_id():
    api = _api()
    assert api.extract_video_id("98765") == "98765"


def test_extract_video_id_short_link_has_no_id():
    api = _api()
    assert api.extract_video_id("https://v.douyin.com/abcXYZ/") is None


def test_extract_video_id_garbage_returns_none():
    api = _api()
    assert api.extract_video_id("not a video link") is None


def test_resolve_shortlink_strips_query_for_long_url():
    api = _api()
    out = api.resolve_shortlink("https://www.douyin.com/video/123?foo=bar", ("v.douyin.com",))
    assert out == "https://www.douyin.com/video/123"


def test_resolve_shortlink_follows_short_link():
    api = _api()
    head_resp = mock.Mock(url="https://www.douyin.com/video/999?x=1")
    api.session.head = mock.Mock(return_value=head_resp)
    out = api.resolve_shortlink("https://v.douyin.com/abc/", ("v.douyin.com",))
    assert out == "https://www.douyin.com/video/999"


def test_resolve_shortlink_falls_back_when_head_fails():
    api = _api()
    api.session.head = mock.Mock(side_effect=RuntimeError("dns down"))
    out = api.resolve_shortlink("https://v.douyin.com/abc/", ("v.douyin.com",))
    assert out == "https://v.douyin.com/abc/"


def _router_item(desc="Test Clip", play_url="https://cdn/x/playwm/v.mp4"):
    return {
        "loaderData": {
            "key": {
                "videoInfoRes": {
                    "item_list": [
                        {
                            "desc": desc,
                            "author": {"nickname": "Creator", "unique_id": "creator1"},
                            "video": {
                                "cover": {"url_list": ["https://cdn/x/cover.jpg"]},
                                "play_addr": {"url_list": [play_url]},
                            },
                            "duration": 12000,
                        }
                    ]
                }
            }
        }
    }


def test_get_video_info_parses_router_data():
    api = _api()
    api._request_with_retry = mock.Mock(return_value=_FakeResp(text="<html/>"))
    with mock.patch.object(
        DouyinAPI, "extract_json_script", return_value=_router_item()
    ):
        info = api.get_video_info("https://www.douyin.com/video/123456")
    assert info["id"] == "123456"
    assert info["title"] == "Test Clip"
    assert info["uploader"] == "creator1"
    assert info["download_url"] == "https://cdn/x/play/v.mp4"  # playwm -> play
    assert info["thumbnail"] == "https://cdn/x/cover.jpg"
    assert info["duration"] == 12


def test_get_video_info_falls_back_to_play_endpoint():
    # Blind aweme fallback removed (Issue 15) — missing stream now raises NotFoundError
    from core.exceptions import NotFoundError
    api = _api()
    api._request_with_retry = mock.Mock(return_value=_FakeResp(text="<html/>", status_code=404))
    with pytest.raises(NotFoundError, match="Không tìm thấy video"):
        api.get_video_info("https://www.douyin.com/video/777")


def test_get_video_info_bare_id_builds_canonical_url():
    # Bare ID still builds canonical URL but missing stream raises (Issue 15)
    from core.exceptions import NotFoundError
    api = _api()
    api._request_with_retry = mock.Mock(return_value=_FakeResp(text="", status_code=500))
    with pytest.raises(NotFoundError):
        api.get_video_info("555666")


def test_get_video_info_rejects_disallowed_host():
    api = _api()
    with pytest.raises(Exception):
        api.get_video_info("https://evil.com/video/123")


def test_get_video_info_unresolvable_short_link_raises():
    api = _api()
    api.session.head = mock.Mock(side_effect=RuntimeError("no network"))
    with pytest.raises(Exception):
        api.get_video_info("https://v.douyin.com/abcXYZ/")
