# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TikTok & Douyin video/profile downloader — downloads watermark-free HD videos directly from official APIs (no 3rd-party services). Supports single video, full profile batch, and subtitle extraction. Three interfaces: CLI (Rich), Web (FastAPI), Desktop (Electron).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests -v

# Run a single test file
python -m pytest tests/test_base_api.py -v

# Run a single test
python -m pytest tests/test_base_api.py::test_sanitize_filename_strips_illegal_chars -v

# Web dashboard
python -m uvicorn web.app:app --host 127.0.0.1 --port 8080

# CLI
python cli.py

# Desktop (Electron)
npm start
npm run dist:win   # build installer
```

## Architecture

**Core layer** (`core/`):
- `BasePlatformAPI` — shared HTTP session, streaming download, short-link resolution, JSON extraction from HTML `<script>` blocks, recursive subtitle discovery, retry logic. Both platform clients inherit from this.
- `TikTokAPI` / `DouyinAPI` — platform-specific video info extraction and profile scraping. Each has a 3-tier fallback for profile URLs: Playwright headless browser → yt-dlp → HTML regex + embedded JSON.
- `TikTokDownloader` — unified facade that routes URLs to the correct platform API via `is_douyin()` check. Handles download + metadata + subtitle writing.
- `ProfileScraper` — batch orchestrator. Resolves profiles/file-lists into video URLs, then downloads concurrently (4 workers via `ThreadPoolExecutor`). Maintains a per-profile `download_archive.txt` to skip already-downloaded videos.
- `CookieManager` — loads/saves `config.json` (download dir, cookie string, quality, metadata toggle).
- `BrowserScraper` — optional Playwright-based scraper with persistent browser data in `.browser_data/`. Anti-detection: removes webdriver flag, blocks heavy resources.

**Web layer** (`web/`):
- FastAPI app with background task queue (`download_tasks` dict keyed by UUID). All file management endpoints enforce `safe_media_path()` to prevent path traversal outside the downloads directory.
- CORS locked to localhost origins only.

**Desktop** (`electron/` + `desktop/ws_server.py`):
- Electron shell wrapping the web UI via WebSocket bridge.

## Key Patterns

- **URL routing**: `TikTokDownloader.get_api(url)` returns `TikTokAPI` or `DouyinAPI` based on domain detection. Cookie refresh happens on every call.
- **Profile scraping cascade**: BrowserScraper (Playwright, headless then headed for CAPTCHA) → yt-dlp → HTML fallback. Each tier returns `[]` on failure, falling through silently.
- **Concurrency**: `ProfileScraper.download_video_list` uses `ThreadPoolExecutor(max_workers=4)` with thread-safe archive writes via `threading.Lock`.
- **Path safety**: `web/app.py:safe_media_path()` resolves and validates all user-supplied paths against the downloads base directory.
- **Tests mock at the session level**: tests inject `_fake_session` or `mock.Mock()` onto `api.session` to avoid real HTTP calls. No integration tests hitting real TikTok/Douyin servers.

## Language

UI strings and error messages are in Vietnamese. Code identifiers and docstrings are in English.
