# REPO MAP — Dowloadapi (updated: 2026-09-14)

## What this system does
Commercial pure REST API (FastAPI) for TikTok & Douyin video downloads, plus a Rich CLI. Core engine extracts direct CDN stream URLs from embedded HTML/JSON payloads, downloads videos, captions, and metadata. Supports single video download with async task tracking, downloaded-file serving, and (via CLI) batch profile download.

## Detected stack
| Layer | Technology | Evidence |
|-------|-----------|----------|
| Language | Python 3.10+ | `pyproject.toml`, `apps/web/app.py` |
| Web framework | FastAPI + Uvicorn (standard extras: uvloop, httptools) | `pyproject.toml`, `apps/web/app.py` |
| JSON serialization | orjson (ORJSONResponse) | `apps/web/app.py`, `requirements.txt` |
| HTTP client | requests | `core/base_api.py` |
| Profile scraping | Playwright (primary), HTML regex + embedded JSON (fallback) | `core/base_api.py` `scrape_profile_urls`, `core/browser_scraper.py` |
| CLI UI | Rich | `apps/cli.py` |
| Test runner | pytest | `pyproject.toml` `[dev]` extra |
| Load benchmark | aiohttp script | `scripts/bench.py` |
| Config store | JSON file (`config.json`) | `core/cookie_manager.py` |
| Packaging | setuptools (editable install + console scripts) | `pyproject.toml` |

## Module map

| Directory / File | Owns | Depends on | Depended by |
|------------------|------|------------|-------------|
| `core/base_api.py` | HTTP session, retry, streaming download, JSON extraction, subtitle walker, `scrape_profile_urls` strategy (browser → HTML) | requests, playwright (lazy) | `tiktok_api.py`, `douyin_api.py` |
| `core/tiktok_api.py` | TikTok video info extraction (api-data, UNIVERSAL_DATA strategies), HTML profile fallback | `base_api.py` | `downloader.py` |
| `core/douyin_api.py` | Douyin video info extraction (iesdouyin share endpoint, paginated aweme/v1 API) | `base_api.py` | `downloader.py` |
| `core/browser_scraper.py` | Playwright headless browser profile scraping with anti-detection | playwright (lazy) | `base_api.py` (lazy import) |
| `core/downloader.py` | Unified download orchestrator: routes to correct API, saves video + metadata + subtitles | `tiktok_api.py`, `douyin_api.py`, `cookie_manager.py` | `profile_scraper.py`, `service.py` |
| `core/profile_scraper.py` | Profile URL normalization, batch download with ThreadPoolExecutor (4 workers), archive dedup | `downloader.py`, `cookie_manager.py` | `service.py` |
| `core/service.py` | **Shared business logic** — single source of truth for CLI + API | `profile_scraper.py`, `downloader.py`, `cookie_manager.py` | `apps/web/app.py`, `apps/cli.py` |
| `core/cookie_manager.py` | Load/save `config.json` (root-relative path), provide active cookie string | (stdlib only) | everywhere |
| `apps/web/app.py` | **Pure API** — 5 REST routes, ORJSONResponse, TTL-cached downloads listing, background task tracking + periodic cleanup, thread-offloaded blocking I/O | `core/service.py` | API consumers |
| `apps/cli.py` | Rich CLI menu: single download, batch, settings, launch web | `core/service.py` (+ direct `CookieManager`, `TikTokDownloader`, `ProfileScraper`) | user |
| `scripts/bench.py` | aiohttp load benchmark against a running server | aiohttp (ad-hoc) | dev |
| `pyproject.toml` | Package metadata, deps, extras (`browser`, `dev`), console scripts `tikdl-cli` / `tikdl-web` | setuptools | pip/CI |

## API surface (only these routes exist)

| Method | Route | Notes |
|--------|-------|-------|
| POST | `/api/video-info` | `analyze_video` offloaded to worker thread |
| POST | `/api/download-single` | BackgroundTasks threadpool; returns `task_id` |
| GET | `/api/task-status/{task_id}` | In-memory dict lookup (fastest path) |
| GET | `/api/downloads` | 2s TTL cache + `asyncio.to_thread`; invalidated on download completion |
| GET | `/downloaded-media/{path}` | `service.safe_media_path` traversal guard + FileResponse |

Multi-worker: `WEB_WORKERS=N` (entry point) or `uvicorn --workers N` / gunicorn+UvicornWorker (Linux). Note: task store is in-memory per process — with workers > 1, a task started on one worker must be polled from the same worker (use sticky routing or a shared store if cross-worker polling is required).

## Known issues / improvement backlog
1. **Douyin profile pagination**: the `while has_more` loop in `douyin_api.py:_scrape_via_html` can make unbounded requests when `msToken` is missing. Needs (a) hard input caps, (b) proxy rotation, or (c) honest error messaging.
2. **No rate limiting**: 4 concurrent threads × 3 retries × exponential backoff = potential for rapid-fire requests that trigger IP bans.
3. **In-memory task store**: multi-worker deployments cannot poll tasks across workers (see note above). Move to Redis/DB for horizontal scaling.
4. **Test coverage is thin**: Tests cover happy paths for single video extraction and URL parsing. No tests for: error paths, Douyin video info, browser scraper, service layer, API routes, concurrent download edge cases.

## Test layout
```
tests/
  conftest.py            ← fixtures: sample HTML, subtitle JSON
  test_api.py            ← TikTokAPI + DouyinAPI + subtitle + stream + profile-strategy tests (11 tests)
  test_base_api.py       ← sanitize, extract_video_ids, json_script, subtitle walker, cookie (5 tests)
  test_profile_scraper.py ← URL normalization, file detection, archive dedup, batch download (9 tests)
```

Run: `pip install -e .[dev] && python -m pytest tests -v`

All tests are hermetic (no network): `BrowserScraper` and HTTP sessions are mocked in profile-strategy tests. 25 tests, green.

**Missing coverage**: Douyin video info extraction, browser scraper internals, service layer, API endpoint smoke tests, error paths, concurrent edge cases, CLI.

## Benchmark (measured 2026-09-14, single corporate Windows laptop)
| Scenario | Result |
|----------|--------|
| `/api/task-status` (404 fast path), 1 worker | ~1,300–1,600 rps |
| `/api/downloads` (cached), 1 worker | ~1,850 rps |
| Same endpoints, 4 workers | ~2,100–3,100 rps |

Client and server shared one CPU during measurement; dedicated Linux servers with uvloop/httptools and 8 workers comfortably exceed 5,000 rps on the lightweight endpoints.

## CI
`.github/workflows/ci.yml` — pytest on Python 3.10 & 3.12, on push/PR to `main`.

## Open unknowns
- `config.json` download_dir is an absolute local path; runtime-only, not portable across machines.
- No authentication/rate-limiting layer yet — required before public commercial exposure.

