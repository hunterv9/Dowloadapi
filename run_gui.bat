@echo off
title TikTok Downloader Web Dashboard
echo ========================================================
echo      TIKTOK DOWNLOADER WEB DASHBOARD (http://127.0.0.1:8080)
echo ========================================================
start "" "http://127.0.0.1:8080"
python -m uvicorn web.app:app --host 127.0.0.1 --port 8080
pause
