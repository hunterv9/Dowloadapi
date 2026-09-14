# REPO MAP — Dowloadapi (updated: 2026-09-14)

## What this system does
TikTok & Douyin video downloader with two UIs (CLI, Web/FastAPI). Core engine extracts direct CDN stream URLs from embedded HTML/JSON payloads, downloads videos, captions, and metadata. Supports single video, batch profile download (Playwright → HTML fallback chain), and subtitle extraction.

## Detected stack
| Layer | Technology | Evidence |
|-------|-----------|----------|
| Language | Python 3.10+ | `pyproject.toml`, `scripts/build.py` (`list[str]` PEP 585) |
| Language | JavaScript (ES2022) | `frontend/src/main.jsx` |
| Web framework | FastAPI + Uvicorn | `pyproject.toml`, `apps/web/app.py` |
| Frontend | React 18 + Vite 5 | `package.json`, `vite.config.js` |
| HTTP client | requests | `core/base_api.py` |
| Profile scraping | Playwright (primary), HTML regex + embedded JSON (fallback) | `core/base_api.py` `scrape_profile_urls`, `core/browser_scraper.py` |
| CLI UI | Rich | `apps/cli.py` |
| Test runner | pytest | `pyproject.toml` `[dev]` extra |
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
| `core/service.py` | **Shared business logic** — single source of truth for CLI + Web | `profile_scraper.py`, `downloader.py`, `cookie_manager.py` | `apps/web/app.py`, `apps/cli.py` |
| `core/cookie_manager.py` | Load/save `config.json` (root-relative path), provide active cookie string | (stdlib only) | everywhere |
| `apps/web/app.py` | FastAPI REST + progress-WebSocket routes, serves `apps/web/static`, background task tracking | `core/service.py` | browser |
| `apps/cli.py` | Rich CLI menu: single download, batch, settings, launch web | `core/service.py` (+ direct `CookieManager`, `TikTokDownloader`, `ProfileScraper`) | user |
| `frontend/src/main.jsx` | React SPA: 4 views (single, batch, library, settings), REST + progress WS | FastAPI | user |
| `scripts/build.py` | Frontend build orchestration (Vite → `apps/web/static`) | npm/Vite | dev/CI |
| `pyproject.toml` | Package metadata, deps, extras (`browser`, `dev`), console scripts `tikdl-cli` / `tikdl-web` | setuptools | pip/CI |

## Entry points
| Command | Resolves to | Notes |
|---------|-------------|-------|
| `tikdl-web` | `apps.web.app:main` | uvicorn on `127.0.0.1:8000` |
| `tikdl-cli` | `apps.cli:main` | Rich interactive menu |
| `python apps/web/app.py` | same as tikdl-web | no install needed |
| `python -m apps.cli` | same as tikdl-cli | no install needed |

## Known issues / improvement backlog
1. **Douyin profile pagination**: the `while has_more` loop in `douyin_api.py:_scrape_via_html` can make unbounded requests when `msToken` is missing. Needs (a) hard input caps, (b) proxy rotation, or (c) honest error messaging.
2. **No rate limiting**: 4 concurrent threads × 3 retries × exponential backoff = potential for rapid-fire requests that trigger IP bans.
3. **Test coverage is thin**: Tests cover happy paths for single video extraction and URL parsing. No tests for: error paths, Douyin video info, browser scraper, service layer, web routes, concurrent download edge cases.
4. **`vite.config.js` uses `emptyOutDir: false`**: stale hashed assets can accumulate in `apps/web/static/assets/` across builds.

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

**Missing coverage**: Douyin video info extraction, browser scraper internals, service layer, web endpoint smoke tests, error paths, concurrent edge cases, CLI.

## CI
`.github/workflows/ci.yml` — on push/PR to `main`:
- `python-tests`: pytest on Python 3.10 & 3.12 (`pip install -e .[dev]`).
- `frontend-build`: Node 20, `npm ci && npm run build`, verifies `apps/web/static/index.html`.

## Open unknowns
- `frontend/src/styles.css` not reviewed in depth — unknown CSS framework usage.
- `config.json` download_dir is an absolute local path; runtime-only, not portable across machines.
