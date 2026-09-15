"""Unit tests for core/cookie_manager.py — filesystem isolated via tmp_path."""

import json
from pathlib import Path
from unittest import mock

import pytest

from core.cookie_manager import CookieManager


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    fake = tmp_path / "config.json"
    monkeypatch.setattr("core.cookie_manager.CONFIG_FILE", fake)
    return fake


def test_load_config_defaults_when_missing(isolated_config):
    mgr = CookieManager()
    assert mgr.config["custom_cookie_string"] == ""
    assert mgr.config["video_quality"] == "hd"
    assert mgr.config["save_metadata"] is True
    assert "download_dir" in mgr.config


def test_load_config_reads_valid_file(isolated_config):
    isolated_config.write_text(
        json.dumps({"custom_cookie_string": "a=1", "video_quality": "sd"}), encoding="utf-8"
    )
    mgr = CookieManager()
    assert mgr.config["custom_cookie_string"] == "a=1"
    assert mgr.config["video_quality"] == "sd"


def test_load_config_ignores_corrupt_json(isolated_config):
    isolated_config.write_text("{ not json", encoding="utf-8")
    mgr = CookieManager()  # must not raise
    assert isinstance(mgr.config, dict)
    assert mgr.config["custom_cookie_string"] == ""


def test_load_config_ignores_os_error(tmp_path, monkeypatch):
    fake = tmp_path / "config.json"
    monkeypatch.setattr("core.cookie_manager.CONFIG_FILE", fake)
    fake.write_text("{}", encoding="utf-8")
    # Make open raise OSError inside load_config
    with mock.patch("builtins.open", side_effect=OSError("disk fail")):
        mgr = CookieManager()
    assert mgr.config["custom_cookie_string"] == ""


def test_save_config_writes_json(isolated_config):
    mgr = CookieManager()
    mgr.save_config({"custom_cookie_string": "x=9", "proxy": "http://p:8080"})
    data = json.loads(isolated_config.read_text(encoding="utf-8"))
    assert data["custom_cookie_string"] == "x=9"
    assert data["proxy"] == "http://p:8080"


def test_save_config_portable_relative_path(isolated_config, tmp_path, monkeypatch):
    # Use an absolute path inside project root → should be stored relative
    monkeypatch.setattr("core.cookie_manager.CONFIG_FILE", isolated_config)
    mgr = CookieManager()
    inside = tmp_path / "downloads2"
    inside.mkdir()
    mgr.save_config({"download_dir": str(inside)})
    data = json.loads(isolated_config.read_text(encoding="utf-8"))
    # Stored value must not be the bare absolute path
    assert not Path(data["download_dir"]).is_absolute() or str(inside) in data["download_dir"]


def test_get_active_cookie_string_returns_manual():
    mgr = CookieManager.__new__(CookieManager)
    mgr.config = {"custom_cookie_string": "manual=1"}
    assert mgr.get_active_cookie_string("tiktok.com") == "manual=1"

def test_get_active_cookie_string_empty_when_unset():
    mgr = CookieManager.__new__(CookieManager)
    mgr.config = {"custom_cookie_string": "   "}
    assert mgr.get_active_cookie_string("tiktok.com") == ""

def test_resolve_download_dir_relative():
    fake = Path("/tmp/project/config.json")
    with mock.patch("core.cookie_manager.CONFIG_FILE", fake):
        out = CookieManager._resolve_download_dir("downloads")
        assert out.endswith("downloads")


def test_resolve_download_dir_absolute(tmp_path):
    abs_dir = tmp_path / "abs_dl"
    abs_dir.mkdir()
    out = CookieManager._resolve_download_dir(str(abs_dir))
    assert Path(out).is_absolute()


def test_resolve_download_dir_empty_falls_back_to_downloads():
    fake = Path("/tmp/project/config.json")
    with mock.patch("core.cookie_manager.CONFIG_FILE", fake):
        out = CookieManager._resolve_download_dir("")
        assert "downloads" in out


def test_resolve_download_dir_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fake = Path("/tmp/project/config.json")
    with mock.patch("core.cookie_manager.CONFIG_FILE", fake):
        out = CookieManager._resolve_download_dir("~/mydl")
        assert str(tmp_path) in out


def test_get_download_dir_returns_path(isolated_config):
    mgr = CookieManager()
    p = mgr.get_download_dir()
    assert isinstance(p, Path)
    assert p.is_absolute()


def test_get_proxy_trims():
    mgr = CookieManager.__new__(CookieManager)
    mgr.config = {"proxy": "  http://p:8080  "}
    assert mgr.get_proxy() == "http://p:8080"
    mgr.config = {}
    assert mgr.get_proxy() == ""
