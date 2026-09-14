dii# REPO MAP — Dowloadapi (updated: 2026-09-11)

## What this system does
TikTok & Douyin video downloader with three UIs (CLI, Web/FastAPI, Electron Desktop). Core engine extracts direct CDN stream URLs from embedded HTML/JSON payloads, downloads videos, captions, and metadata. Supports single video, batch profile download (via yt-dlp → Playwright → HTML fallback chain), and subtitle extraction.

## Detected stack
| Layer | Technology | Evidence |
|-------|-----------|----------|
| Language | Python 3.10+ | `build.py` uses `list[str]` syntax (PEP 585) |
| Language | JavaScript (ES2022) | `electron/main.js`, `frontend/src/main.jsx` |
| Web framework | FastAPI + Uvicorn | `requirements.txt`, `web/app.py` |
| Desktop runtime | Electron 30 | `package.json` |
| Frontend | React 18 + Vite 5 | `package.json`, `vite.config.js` |
| HTTP client | requests | `requirements.txt`, `core/base_api.py` |
| Profile scraping | yt-dlp (primary), Playwright (fallback), HTML regex (last resort) | `core/base_api.py` `_scrape_via_ytdlp`, `core/browser_scraper.py` |
| CLI UI | Rich | `requirements.txt`, `cli.py` |
| Desktop WS server | Raw asyncio WebSocket (no library) | `desktop/ws_server.py` — hand-rolled handshake + frame parser |
| Build/packaging | PyInstaller + electron-builder | `build.py`, `package.json` |
| Test runner | pytest | `requirements.txt` |
| Config store | JSON file (`config.json`) | `core/cookie_manager.py` |

## Module map

| Directory / File | Owns | Depends on | Depended by |
|------------------|------|------------|-------------|
| `core/base_api.py` | HTTP session, retry, streaming download, JSON extraction, subtitle walker, yt-dlp profile scrape | requests, yt-dlp (optional) | `tiktok_api.py`, `douyin_api.py` |
| `core/tiktok_api.py` | TikTok video info extraction (3 strategies: api-data, UNIVERSAL_DATA, oEmbed), HTML profile fallback | `base_api.py` | `downloader.py` |
| `core/douyin_api.py` | Douyin video info extraction (iesdouyin share endpoint, paginated aweme/v1 API) | `base_api.py` | `downloader.py` |
| `core/browser_scraper.py` | Playwright headless browser profile scraping with anti-detection | playwright (optional) | `base_api.py` (lazy import) |
| `core/downloader.py` | Unified download orchestrator: routes to correct API, saves video + metadata + subtitles | `tiktok_api.py`, `douyin_api.py`, `cookie_manager.py` | `profile_scraper.py`, `service.py` |
| `core/profile_scraper.py` | Profile URL normalization, batch download with ThreadPoolExecutor (4 workers), archive dedup | `downloader.py`, `cookie_manager.py` | `service.py` |
| `core/service.py` | **Shared business logic** — single source of truth for Web + Desktop | `profile_scraper.py`, `downloader.py`, `cookie_manager.py` | `web/app.py`, `desktop/ws_server.py`, `cli.py` |
| `core/cookie_manager.py` | Load/save `config.json`, provide active cookie string | (stdlib only) | everywhere |
| `web/app.py` | FastAPI REST + WebSocket routes, localhost guard, background task tracking | `core/service.py` | browser |
| `desktop/ws_server.py` | Raw asyncio WebSocket server, JSON-RPC dispatch | `core/service.py` | Electron `main.js` |
| `cli.py` | Rich CLI menu: single download, batch, settings, launch web | `core/service.py` (+ direct `CookieManager`, `TikTokDownloader`, `ProfileScraper`) | user |
| `electron/main.js` | Electron window management, spawns Python WS backend, IPC, auto-update | `desktop/ws_server.py` (subprocess) | user |
| `electron/preload.js` | Exposes `electronAPI` to renderer (minimize/maximize/close/openExternal) | Electron IPC | `main.jsx` |
| `frontend/src/main.jsx` | React SPA: 4 views (single, batch, library, settings), WS + REST dual protocol | FastAPI / WS server | user |
| `build.py` | Build orchestration: PyInstaller backend, Vite frontend, electron-builder | all | CI/release |
| `config.json` | Runtime config: cookie, download dir, quality, metadata toggle | — | `cookie_manager.py` |
| `tests/` | Unit tests for base_api, tiktok_api, profile_scraper, subtitle download | core modules | CI |

## Entry points
| Entry | Type | Handler location |
|-------|------|------------------|
| `cli.py` | CLI | `cli.py:main()` → `core/service.py` |
| `web/app.py` | HTTP REST + WebSocket | FastAPI routes → `core/service.py` |
| `desktop/ws_server.py` | Raw WebSocket (port 8765) | `_handle()` → `core/service.py` |
| `electron/main.js` | Desktop GUI | spawns `ws_server.py`, loads `web/static/index.html` |

## Core flows

### 1. Single video download
```
User pastes URL
  → CLI/Web/Desktop sends to service.analyze_video()
    → TikTokDownloader.get_video_info(url)
      → get_api(url) picks TikTokAPI or DouyinAPI
        → resolve_shortlink() follows redirects
        → HTTP GET with iPhone UA → parse embedded JSON
        → TikTok: api-data → UNIVERSAL_DATA → oEmbed
        → Douyin: iesdouyin share → _ROUTER_DATA → aweme/v1/play fallback
  → returns {download_url, title, captions, ...}
  → download_stream() streams CDN to disk (64KB chunks)
  → download_subtitles() saves .srt/.vtt sidecars
```

### 2. Profile / batch download
```
User enters @username or profile URL
  → ProfileScraper.resolve_video_urls()
    → normalize_profile_url()
    → Strategy 1: yt-dlp extract_info() → flat playlist of webpage_urls
    → Strategy 2: Playwright headless Chromium → scroll → extract /video/\d+ links
    → Strategy 3: HTML GET → regex /video/\d+ + embedded JSON itemList
  → returns List[str] of individual video URLs
  → ProfileScraper.download_video_list()
    → ThreadPoolExecutor(4 workers)
    → each worker: get_video_info() → download_video_with_info()
    → archive check skips already-downloaded IDs
```

### 3. Config management
```
config.json ←→ CookieManager.load_config() / save_config()
  → propagated to TikTokAPI/DouyinAPI via set_cookie_string()
  → single source: core/service.py module-level instances
```

## Request flow diagram
```
┌─────────────┐  ┌──────────────┐  ┌──────────────────┐
│   CLI       │  │  Web (REST)  │  │  Desktop (WS:8765)│
│  cli.py     │  │  web/app.py  │  │  desktop/ws_server│
└──────┬──────┘  └──────┬───────┘  └────────┬─────────┘
       │                │                    │
       └────────────────┼────────────────────┘
                        ▼
              ┌──────────────────┐
              │  core/service.py │  ← shared singleton instances
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │ core/downloader  │
              └──┬───────────┬───┘
                 ▼           ▼
          TikTokAPI     DouyinAPI        (both extend BasePlatformAPI)
                 │           │
                 └─────┬─────┘
                       ▼
              ┌──────────────────┐
              │  base_api.py     │  HTTP, retry, download, subtitle
              └──────────────────┘
```

## Profile scraper blocking analysis

### What's failing / likely blocked
1. **TikTok profile scraping (HTML fallback)**: TikTok returns minimal HTML with no embedded video data for unauthenticated requests. `__UNIVERSAL_DATA_FOR_REHYDRATION__` often contains only user metadata, not `itemList`. The `_scrape_via_html` path is nearly useless for TikTok profiles without cookies.

2. **yt-dlp (primary strategy)**: yt-dlp itself gets blocked by TikTok's anti-bot (WAF, rate limiting). With no valid cookies in `http_headers`, `extract_info()` returns empty entries or raises "Unable to extract secondary user ID". The stderr suppression (`os.dup2(os.devnull, 2)`) hides these failures silently.

3. **Playwright (secondary strategy)**: The anti-detection measures are basic:
   - `navigator.webdriver` overridden → but TikTok checks `cdc_` Chrome DevTools Protocol flags
   - No stealth plugin (e.g., `playwright-stealth`) used
   - Persistent context at `.browser_data/` can accumulate stale cookies that trigger detection
   - Resource blocking (`.mp4`, `.png`, etc.) prevents thumbnail loading but doesn't help with bot detection
   - CAPTCHA detection waits 60s then continues — but if CAPTCHA isn't solved, returns empty
   - `headless=True` mode is easily detected by TikTok (missing WebGL, canvas fingerprint)

4. **Douyin profile scraping**: The paginated `aweme/v1/web/aweme/post/` endpoint requires `msToken` and `X-Bogus` anti-bot signatures. Without these, requests return empty `aweme_list`. The HTML fallback extracts `sec_user_id` from `_ROUTER_DATA` but the API call without signing fails silently.

5. **Rate limiting**: No global rate limiter exists. Concurrent profile downloads (4 threads) + retry logic (3 attempts each) = up to 12 simultaneous requests to TikTok, triggering 429 blocks quickly.

### Root causes
- **No cookie = no data**: Both platforms increasingly require authenticated sessions for profile endpoints
- **Missing anti-bot signatures**: Douyin needs `msToken`/`X-Bogus`; TikTok needs valid `ttwid` cookie
- **yt-dlp stderr suppression masks failures**: The `os.dup2(devnull, 2)` hack hides critical error messages
- **No proxy support**: No rotation, no residential proxy → easy IP fingerprinting

## Dead code & over-engineering

### Can be removed / simplified

| File | Issue | Recommendation |
|------|-------|----------------|
| `desktop/ws_server.py` | Hand-rolled WebSocket protocol (100+ lines of handshake, frame parsing). Duplication of `web/app.py` routing logic. | **Remove entirely**. Electron can load the FastAPI server directly (like the web UI does). Eliminates an entire transport layer. |
| `cli.py` | Creates its own `CookieManager`, `TikTokDownloader`, `ProfileScraper` instances instead of using `service.py` singletons. Duplicates error message translation. | Use `core/service.py` functions directly (like web/desktop do). Delete `cli.py:_cli_friendly_error()` — reuse `web/app.py:_friendly_error()` from service. |
| `web/app.py:_friendly_error()` | Duplicated in `cli.py` and `desktop/ws_server.py` (3 copies, ~60 lines each). | Move to `core/service.py` as `friendly_error()`. Delete all 3 copies. |
| `core/base_api.py:_scrape_via_ytdlp()` | stderr suppression hack (`os.dup2(devnull, 2)`) is fragile and hides real errors. | Remove stderr redirection. Use yt-dlp's `logger` parameter instead. |
| `core/browser_scraper.py:is_available()` | Runs `playwright install --dry-run` AND launches a real browser to check — slow, spawns subprocesses. | Just catch `ImportError` on `from playwright.sync_api import sync_playwright`. |
| `electron/preload.js` | Exists but not shown — likely just IPC bridge. Check if `window.electronAPI` is used properly. | Verify; may be minimal already. |
| `vite.config.js` | Vite config for frontend build. The frontend is a single `main.jsx` file. | Fine as-is, but consider if Vite is overkill for a single-file React app. |

### Redundant abstractions
- **`BasePlatformAPI` inheritance**: `TikTokAPI` and `DouyinAPI` share ~60% of code via inheritance. The remaining platform-specific code is quite different. Current structure is OK but `_scrape_via_html` being abstract (raises `NotImplementedError`) while also being the last-resort fallback in the parent's `scrape_profile_urls()` is a code smell — if subclass doesn't override, it silently fails.
- **`downloader.py` vs `service.py`**: `TikTokDownloader` wraps API calls + filename generation. `service.py` wraps `TikTokDownloader`. Two layers of delegation for what could be one.
- **Profile scraper creates its own `TikTokDownloader`** inside `__init__` rather than accepting one — creates redundant cookie propagation chains.

## Error handling gaps

1. **Silent failures in profile scraping**: All three strategies (`_scrape_via_ytdlp`, `BrowserScraper.scrape_profile`, `_scrape_via_html`) catch broad `Exception` and return empty lists. User gets "Không tìm thấy video" with no diagnostic info.

2. **`_request_with_retry` swallows 5xx**: Returns the response object (doesn't raise) for status < 500, but callers like `get_video_info` only check `status_code != 200` — so 3xx/4xx responses pass through silently.

3. **No timeout on yt-dlp**: `socket_timeout: 30` is set but `extract_info()` can hang indefinitely on playlist extraction. No `max_download_attempts` or global timeout.

4. **Concurrent download race condition**: `ProfileScraper._download_one()` checks archive with lock, but `download_stream()` (in `base_api.py`) has no dedup — if the same URL appears twice in the list before the first download completes, both threads download it.

5. **`download_tasks` dict in `web/app.py`**: In-memory only, lost on restart. No persistence, no limit on concurrent tasks. `_TASK_MAX_AGE_SECONDS = 3600` cleanup only runs on new download requests.

6. **Douyin pagination**: The `while has_more` loop in `douyin_api.py:_scrape_via_html` makes unbounded API requests. If `has_more` stays true, it loops until `max_pages` (50+) — all failing silently without `msToken`.

7. **WebSocket server has no auth**: `desktop/ws_server.py` accepts any connection on `127.0.0.1:8765`. While localhost-only, any local process can send commands (delete files, change config).

## Dependency tree

### Python (`requirements.txt`)
```
fastapi >=0.115.0        ← web server
uvicorn >=0.30.0         ← ASGI server
rich >=13.7.0            ← CLI only
requests >=2.31.0        ← HTTP client (core)
yt-dlp >=2024.1.0        ← profile scraping (optional at runtime)
playwright >=1.40.0      ← browser fallback (optional at runtime)
pyinstaller >=6.0.0      ← build only
pytest >=8.0.0           ← test only
```

### JavaScript (`package.json`)
```
react ^18.3.1            ← frontend
react-dom ^18.3.1        ← frontend
electron-updater ^6.3.9  ← auto-update
electron ^30.0.0         ← desktop (devDep)
electron-builder ^26.15.3← packaging (devDep)
vite ^5.4.8              ← build (devDep)
@vitejs/plugin-react     ← build (devDep)
```

### Can we remove deps?
| Dependency | Can remove? | Why |
|------------|-------------|-----|
| `playwright` | Move to optional/extras | Heavy (~400MB Chromium). Not needed if user has cookies. Make it `pip install .[browser]` |
| `rich` | No | Core CLI experience |
| `yt-dlp` | Move to optional/extras | Only needed for profile scraping. Core single-video download doesn't use it. Make it `pip install .[profile]` |
| `pyinstaller` | Move to dev extras | Not a runtime dep |
| `pytest` | Move to dev extras | Not a runtime dep |
| `electron-updater` | Consider | Only used in packaged Electron builds. Could lazy-load. |

## Structural risks (top 5)

1. **Profile scraping is effectively broken without cookies**: All 3 fallback strategies fail against modern TikTok/Douyin anti-bot. The code creates illusion of functionality but returns empty in practice. Needs either: (a) mandatory cookie input, (b) proxy rotation, or (c) honest error messaging.

2. **3 copies of error translation logic**: `web/app.py`, `desktop/ws_server.py`, `cli.py` each have ~50 lines of identical `_friendly_error()` that will drift.

3. **No rate limiting**: 4 concurrent threads × 3 retries × exponential backoff = potential for rapid-fire requests that trigger IP bans.

4. **WebSocket transport is unnecessary complexity**: `desktop/ws_server.py` reimplements HTTP WebSocket from scratch (~180 lines). Electron could just use the FastAPI server (like the web UI does) or the frontend could use REST polling.

5. **Test coverage is thin**: Tests cover happy paths for single video extraction and URL parsing. No tests for: error paths, Douyin video info, browser scraper, service layer, web routes, concurrent download edge cases.

## Test layout
```
tests/
  conftest.py            ← fixtures: sample HTML, subtitle JSON
  test_api.py            ← TikTokAPI + DouyinAPI + subtitle + stream tests (9 tests)
  test_base_api.py       ← sanitize, extract_video_ids, json_script, subtitle walker, cookie (5 tests)
  test_profile_scraper.py ← URL normalization, file detection, archive dedup, batch download (9 tests)
```

Run: `python -m pytest tests -v`

**Missing coverage**: Douyin video info extraction, browser scraper, service layer, web routes, error paths, concurrent edge cases, CLI.

## Recommended refactoring approach

### Phase 1 — Quick wins (1 day)
1. **Consolidate `_friendly_error()`** into `core/service.py`. Delete 3 copies.
2. **CLI uses service.py** — delete duplicate instance creation in `cli.py`.
3. **Fix `is_available()`** — just check import, skip subprocess.
4. **Remove stderr suppression** in `_scrape_via_ytdlp()` — use yt-dlp logger.
5. **Add `@pytest.mark.skip` for tests that need network** — make `pytest` runnable offline.

### Phase 2 — Profile scraping fix (2-3 days)
1. **Make cookies mandatory for profile scraping** — warn user upfront if no cookie set.
2. **Add rate limiter** — `threading.Semaphore` or `ratelimit` library, max 2 req/s.
3. **Use `playwright-stealth`** for browser scraper.
4. **Add Douyin `msToken` generation** or document that Douyin profile scraping requires cookies.
5. **Replace yt-dlp stderr hack** with proper `logger` callback.

### Phase 3 — Architecture simplification (2-3 days)
1. **Remove `desktop/ws_server.py`** — Electron loads FastAPI directly.
2. **Flatten `downloader.py` into `service.py`** — one delegation layer, not two.
3. **ProfileScraper accepts `TikTokDownloader` as parameter** instead of creating its own.
4. **Move optional deps** to extras: `pip install .[profile]` (yt-dlp), `pip install .[browser]` (playwright).

### Phase 4 — Hardening (1-2 days)
1. **Add request timeout** to yt-dlp (`--socket-timeout`, `--max-download-attempts`).
2. **Dedup download URLs** before submitting to ThreadPoolExecutor.
3. **Persist task state** to disk or use a simple SQLite for web download tasks.
4. **Add tests** for: Douyin info, error paths, service functions, web endpoint smoke tests.
5. **Add proxy support** to `BasePlatformAPI` (accept `http_proxy` in config).

## Open unknowns
- `electron/preload.js` contents not reviewed — may have additional IPC surface.
- `vite.config.js` contents not reviewed — unknown if it has custom plugins or aliases.
- `frontend/src/styles.css` not reviewed — unknown CSS framework usage.
- No `.gitignore` reviewed — unclear what's tracked vs ignored.
- No CI/CD pipeline files found — unclear if GitHub Actions or similar exists.
- `tiktok-backend.spec` (PyInstaller spec file) not reviewed — may have additional bundling config.