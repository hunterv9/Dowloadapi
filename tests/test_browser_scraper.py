"""Unit tests for core/browser_scraper.py — no real Playwright launch."""

import sys
import types
from unittest import mock

from core.browser_scraper import BrowserScraper


def test_is_available_false_when_import_fails(monkeypatch):
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    assert BrowserScraper.is_available() is False


def test_is_available_true_when_chromium_installed(monkeypatch):
    fake_pw = types.ModuleType("playwright.sync_api")
    fake_pw.sync_playwright = mock.Mock()  # noqa — only import presence matters here
    fake_pkg = types.ModuleType("playwright")
    fake_pkg.sync_api = fake_pw
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_pw)
    fake_result = mock.Mock(stdout="chromium 124.0 already installed", returncode=0)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake_result)
    assert BrowserScraper.is_available() is True


def test_is_available_falls_back_to_launch(monkeypatch):
    fake_ctx = mock.MagicMock()
    fake_ctx.__enter__.return_value = mock.MagicMock()
    fake_pw = types.ModuleType("playwright.sync_api")
    fake_pw.sync_playwright = mock.Mock(return_value=fake_ctx)
    fake_pkg = types.ModuleType("playwright")
    fake_pkg.sync_api = fake_pw
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_pw)
    fake_result = mock.Mock(stdout="nothing here", returncode=0)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake_result)
    assert BrowserScraper.is_available() is True


def test_is_available_false_when_launch_fails(monkeypatch):
    def _boom():
        raise RuntimeError("no chromium")

    fake_pw = types.ModuleType("playwright.sync_api")
    fake_pw.sync_playwright = _boom
    fake_pkg = types.ModuleType("playwright")
    fake_pkg.sync_api = fake_pw
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_pw)
    fake_result = mock.Mock(stdout="nothing here", returncode=0)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake_result)
    assert BrowserScraper.is_available() is False


def test_scrape_profile_returns_empty_when_no_playwright(monkeypatch):
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    assert BrowserScraper.scrape_profile("https://www.tiktok.com/@u") == []


def test_install_browser_success(monkeypatch):
    fake_result = mock.Mock(returncode=0, stderr="")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake_result)
    assert BrowserScraper.install_browser() is True


def test_install_browser_failure(monkeypatch):
    fake_result = mock.Mock(returncode=1, stderr="boom")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake_result)
    assert BrowserScraper.install_browser() is False


def test_install_browser_exception(monkeypatch):
    monkeypatch.setattr("subprocess.run", mock.Mock(side_effect=OSError("nope")))
    assert BrowserScraper.install_browser() is False


class _FakeLink:
    def __init__(self, href):
        self._href = href

    def get_attribute(self, name):
        return self._href


class _FakePage:
    def __init__(self, links):
        self._links = links

    def route(self, *a, **k):
        pass

    def goto(self, *a, **k):
        pass

    def query_selector(self, sel):
        return None  # no CAPTCHA

    def wait_for_selector(self, *a, **k):
        pass

    def query_selector_all(self, sel):
        return self._links

    def evaluate(self, *a, **k):
        pass

    def wait_for_timeout(self, ms):
        pass


class _FakeContext:
    def __init__(self, links):
        self._page = _FakePage(links)
        self.closed = False

    def add_init_script(self, *a, **k):
        pass

    def new_page(self):
        return self._page

    def new_cdp_session(self, page):
        raise RuntimeError("no cdp")

    def close(self):
        self.closed = True


def _install_fake_browser(monkeypatch, links):
    ctx = _FakeContext(links)
    fake_chromium = mock.Mock()

    def _launch(**kwargs):
        return ctx

    fake_chromium.launch_persistent_context = _launch
    fake_p = mock.Mock()
    fake_p.chromium = fake_chromium

    class _PW:
        def __enter__(self):
            return fake_p

        def __exit__(self, *a):
            return False

    fake_sync = types.ModuleType("playwright.sync_api")
    fake_sync.sync_playwright = mock.Mock(return_value=_PW())
    fake_pkg = types.ModuleType("playwright")
    fake_pkg.sync_api = fake_sync
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync)
    import core.browser_scraper as bs

    fake_dir = mock.Mock()
    fake_dir.mkdir = mock.Mock()
    fake_dir.__str__ = lambda self: "/tmp/fake_browser"
    monkeypatch.setattr(bs, "_BROWSER_DATA_DIR", fake_dir)
    return ctx


def test_scrape_profile_builds_tiktok_urls(monkeypatch):
    links = [
        _FakeLink("https://www.tiktok.com/@u/video/111"),
        _FakeLink("https://www.tiktok.com/@u/video/222"),
        _FakeLink("https://www.tiktok.com/@u/video/111"),  # dup
    ]
    _install_fake_browser(monkeypatch, links)
    urls = BrowserScraper.scrape_profile("https://www.tiktok.com/@u", max_videos=10)
    assert urls == [
        "https://www.tiktok.com/@u/video/111",
        "https://www.tiktok.com/@u/video/222",
    ]


def test_scrape_profile_builds_douyin_base(monkeypatch):
    links = [_FakeLink("https://www.douyin.com/@u/video/555")]
    _install_fake_browser(monkeypatch, links)
    urls = BrowserScraper.scrape_profile("https://www.douyin.com/@u", max_videos=10)
    assert urls == ["https://www.douyin.com/@u/video/555"]


def test_scrape_profile_caps_at_max_videos(monkeypatch):
    links = [_FakeLink(f"https://www.tiktok.com/@u/video/{i}") for i in range(20)]
    _install_fake_browser(monkeypatch, links)
    urls = BrowserScraper.scrape_profile("https://www.tiktok.com/@u", max_videos=5)
    assert len(urls) == 5
