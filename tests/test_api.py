"""Unit tests for the TikTok / Douyin API clients."""

from unittest import mock

from core.tiktok_api import TikTokAPI
from core.douyin_api import DouyinAPI


class _FakeResp:
    def __init__(self, text="", status_code=200, json_data=None, headers=None):
        self.text = text
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json is not None:
            return self._json
        raise ValueError("no json")


def _fake_session(resp):
    s = mock.Mock()
    s.get.return_value = resp
    s.head.return_value = resp
    return s


def test_tiktok_extract_video_id():
    api = TikTokAPI()
    assert api.extract_video_id("https://www.tiktok.com/@x/video/123456") == "123456"
    assert api.extract_video_id("123456") == "123456"
    assert api.extract_video_id("https://x.com/other") is None


def test_douyin_extract_video_id():
    api = DouyinAPI()
    assert api.extract_video_id("https://www.douyin.com/video/98765") == "98765"
    assert api.extract_video_id("https://x.com/video?modal_id=111") == "111"


def test_tiktok_get_video_info_from_api_data():
    api = TikTokAPI()
    html = (
        '<script id="api-data" type="application/json">'
        '{"videoDetail":{"itemInfo":{"itemStruct":{'
        '"desc":"My Clip","video":{"playAddr":"https://cdn/x.mp4",'
        '"cover":"https://cdn/cover.jpg","duration":12},'
        '"author":{"uniqueId":"tony","nickname":"Tony"}}}}}'
        '</script>'
    )
    api.session = _fake_session(_FakeResp(text=html))

    info = api.get_video_info("https://www.tiktok.com/@tony/video/123")
    assert info["title"] == "My Clip"
    assert info["uploader"] == "tony"
    assert info["download_url"] == "https://cdn/x.mp4"


def test_tiktok_scrape_profile_urls():
    api = TikTokAPI()
    html = (
        '<div><a href="/video/1">a</a><a href="/video/2">b</a></div>'
        '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
        '{"__DEFAULT_SCOPE__":{"webapp.user-detail":{'
        '"userInfo":{"user":{"secUid":"S"}},'
        '"itemList":[{"id":"1"},{"id":"2"}]}}}'
        '</script>'
    )
    api.session.get = mock.Mock(return_value=_FakeResp(html))
    urls = api.scrape_profile_urls("https://www.tiktok.com/@tony", max_videos=50)
    ids = [u.rsplit("/", 1)[-1] for u in urls]
    assert "1" in ids and "2" in ids


def test_tiktok_collects_embedded_profile_items():
    ids = []
    TikTokAPI._append_embedded_video_ids(
        {"profile": {"itemList": [{"id": "123"}, {"id": "456"}]}}, ids, 10
    )
    assert ids == ["123", "456"]


def test_tiktok_profile_api_resolves_sec_uid():
    api = TikTokAPI()

    # Mock yt-dlp to return video URLs
    mock_ydl = mock.MagicMock()
    mock_ydl.__enter__ = mock.Mock(return_value=mock_ydl)
    mock_ydl.__exit__ = mock.Mock(return_value=False)
    mock_ydl.extract_info.return_value = {
        "entries": [{"url": "https://www.tiktok.com/@creator/video/789"}]
    }

    with mock.patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        urls = api.scrape_profile_urls("https://www.tiktok.com/@creator", max_videos=5)

    assert urls == ["https://www.tiktok.com/@creator/video/789"]


def test_download_subtitles_writes_srt(tmp_path):
    from core.downloader import TikTokDownloader

    dldr = TikTokDownloader.__new__(TikTokDownloader)
    dldr.cookie_manager = mock.Mock()
    dldr.cookie_manager.config = {"download_dir": str(tmp_path)}
    dldr.is_douyin = mock.Mock(return_value=False)
    dldr.get_api = mock.Mock()
    api = mock.Mock()
    resp = mock.Mock()
    resp.status_code = 200
    resp.headers = {"content-type": "application/x-subrip; charset=utf-8"}
    resp.content = b"1\n00:00:01 --> 00:00:02\nHi\n"
    api.session.get = mock.Mock(return_value=resp)
    api._headers = mock.Mock(return_value={})
    dldr.get_api.return_value = api

    info = {
        "id": "9",
        "uploader": "tony",
        "title": "Clip",
        "captions": [{"lang": "en", "url": "https://cdn/x.srt"}],
    }
    saved = dldr.download_subtitles("https://www.tiktok.com/@tony/video/9", info=info)
    assert len(saved) == 1
    assert (tmp_path / "tiktok_tony_9_Clip.en.srt").exists()


def test_tiktok_download_stream(tmp_path):
    api = TikTokAPI()
    fake_get = mock.Mock()
    fake_get.headers = {"content-length": "11"}
    fake_get.iter_content = mock.Mock(return_value=iter([b"hello", b" world"]))
    api.session.get = mock.Mock(return_value=fake_get)

    out = api.download_stream("https://cdn/x.mp4", str(tmp_path / "clip"))
    assert out.endswith(".mp4")
    assert (tmp_path / "clip.mp4").read_bytes() == b"hello world"