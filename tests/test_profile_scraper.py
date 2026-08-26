"""Unit tests for ProfileScraper URL resolution and batch download."""

from unittest import mock

from core.profile_scraper import ProfileScraper


def _build_scraper() -> ProfileScraper:
    mgr = mock.Mock()
    mgr.config = {"download_dir": "downloads", "save_metadata": True}
    return ProfileScraper(mgr)


def test_normalize_profile_url_bare_handle():
    s = _build_scraper()
    assert s.normalize_profile_url("@user") == "https://www.tiktok.com/@user"


def test_normalize_profile_url_tiktok():
    s = _build_scraper()
    url = "https://www.tiktok.com/@abc/video/123"
    assert s.normalize_profile_url(url) == "https://www.tiktok.com/@abc"


def test_normalize_profile_url_douyin():
    s = _build_scraper()
    url = "https://www.douyin.com/user/@xyz"
    assert s.normalize_profile_url(url) == "https://www.douyin.com/@xyz"


def test_extract_username():
    s = _build_scraper()
    assert s.extract_username("@my_channel") == "my_channel"
    assert s.extract_username("https://www.tiktok.com/@foo/video/9") == "foo"


def test_resolve_profile_handle_uses_profile_scraper():
    s = _build_scraper()
    s.downloader.tiktok_api.scrape_profile_urls = mock.Mock(return_value=["video-url"])

    assert s.resolve_video_urls("@creator") == ["video-url"]
    # Default max_videos=0 means fetch all without an artificial limit.
    s.downloader.tiktok_api.scrape_profile_urls.assert_called_once_with(
        "https://www.tiktok.com/@creator", 0
    )


def test_resolve_profile_url_is_not_treated_as_single_video():
    s = _build_scraper()
    s.downloader.tiktok_api.scrape_profile_urls = mock.Mock(return_value=["video-url"])

    assert s.resolve_video_urls("https://www.tiktok.com/@creator") == ["video-url"]
    s.downloader.tiktok_api.scrape_profile_urls.assert_called_once_with(
        "https://www.tiktok.com/@creator", 0
    )


def test_resolve_profile_with_max_videos():
    s = _build_scraper()
    s.downloader.tiktok_api.scrape_profile_urls = mock.Mock(return_value=["video-url"])

    assert s.resolve_video_urls("@creator", max_videos=10) == ["video-url"]
    s.downloader.tiktok_api.scrape_profile_urls.assert_called_once_with(
        "https://www.tiktok.com/@creator", 10
    )


def test_is_file_input():
    assert ProfileScraper.is_file_input("urls.txt")
    assert ProfileScraper.is_file_input("C:\\tmp\\list.csv")
    assert not ProfileScraper.is_file_input("@user")
    assert not ProfileScraper.is_file_input("https://x.com/a.txt")


def test_download_video_list_honours_archive(tmp_path):
    s = _build_scraper()
    # Pre-seed the archive with id "1" so it should be skipped.
    user_dir = tmp_path / "chan"
    user_dir.mkdir(parents=True)
    (user_dir / "download_archive.txt").write_text("1\n", encoding="utf-8")

    s.downloader.get_video_info = mock.Mock(
        side_effect=[
            {"id": "1", "title": "old"},
            {"id": "2", "title": "new"},
        ]
    )
    s.downloader.download_video_with_info = mock.Mock()
    events = []

    res = s.download_video_list(
        ["1", "2"], username="chan", output_dir=str(tmp_path),
        progress_hook=events.append, workers=1,
    )

    assert res["downloaded"] == 1
    assert res["skipped"] == 1
    assert res["failed"] == 0
    # With concurrent downloads, check counts rather than order
    statuses = [e["status"] for e in events]
    assert "skipped" in statuses
    assert "downloading_item" in statuses
    s.downloader.download_video_with_info.assert_called_once()


def test_download_profile_resolves_then_downloads(tmp_path):
    s = _build_scraper()
    s.resolve_video_urls = mock.Mock(
        return_value=["https://www.tiktok.com/@c/video/77"]
    )
    s.downloader.get_video_info = mock.Mock(
        return_value={"id": "77", "title": "clip"}
    )
    s.downloader.download_video_with_info = mock.Mock()

    res = s.download_profile("@creator", output_dir=str(tmp_path))

    assert res["downloaded"] == 1
    assert (tmp_path / "creator" / "download_archive.txt").exists()


def test_download_video_list_forwards_each_resolved_url(tmp_path):
    s = _build_scraper()
    urls = [
        "https://www.tiktok.com/@creator/video/1",
        "https://www.tiktok.com/@creator/video/2",
    ]
    s.downloader.get_video_info = mock.Mock(
        side_effect=[{"id": "1", "title": "one"}, {"id": "2", "title": "two"}]
    )
    s.downloader.download_video_with_info = mock.Mock()

    result = s.download_video_list(
        urls, username="creator", output_dir=str(tmp_path), workers=1
    )

    assert result["downloaded"] == 2
    assert s.downloader.get_video_info.call_args_list == [
        mock.call(urls[0]),
        mock.call(urls[1]),
    ]
    assert [
        call.args[0]
        for call in s.downloader.download_video_with_info.call_args_list
    ] == urls
