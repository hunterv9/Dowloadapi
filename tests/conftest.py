"""Pytest configuration — ensures the repo root is importable."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def sample_page_html() -> str:
    """A minimal TikTok-style HTML page with embedded JSON + video IDs."""
    return (
        '<html><head></head><body>'
        '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
        '{"__DEFAULT_SCOPE__":{"webapp.user-detail":{'
        '"userInfo":{"user":{"secUid":"SEC123"}},'
        '"itemList":[{"id":"111"},{"id":"222"},{"id":"333"}]}'
        '}}'
        '</script>'
        '<a href="/@test1/video/111">a</a>'
        '<a href="/@test1/video/222">b</a>'
        '<a href="/@test1/video/333">c</a>'
        '</body></html>'
    )


@pytest.fixture
def sample_subtitle_json() -> dict:
    """A payload exercising the recursive caption walker."""
    return {
        "author": {"nickname": "Maker"},
        "video": {
            "playAddr": "https://cdn.example.com/play.mp4",
            "subtitleInfos": [
                {"LanguageCode": "en", "url": "https://cdn.example.com/en.srt"},
                {"LanguageCode": "vi", "url": "https://cdn.example.com/vi.srt"},
            ],
            "nested": {
                "video_subtitle": [
                    {"lang": "auto", "url_list": ["https://cdn.example.com/auto.vtt"]}
                ]
            },
        },
    }