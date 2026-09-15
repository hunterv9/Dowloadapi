"""Async load benchmark (aiohttp, keep-alive) — measures server throughput."""
import os
import asyncio
import time
from collections import Counter

import aiohttp

BASE = os.getenv("BENCH_BASE", "http://127.0.0.1:8000")
TOTAL = 5000
CONCURRENCY = 200


async def run(label, path, total=TOTAL, conc=CONCURRENCY):
    codes = Counter()
    sem = asyncio.Semaphore(conc)
    connector = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
    timeout = aiohttp.ClientTimeout(total=15)

    async def hit(session):
        async with sem:
            async with session.get(f"{BASE}{path}") as r:
                await r.read()
                codes[str(r.status)] += 1

    t0 = time.perf_counter()
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        await asyncio.gather(*(hit(session) for _ in range(total)))
    dt = time.perf_counter() - t0
    print(f"{label}: {total} req / {dt:.2f}s = {total / dt:,.0f} rps  codes={dict(codes)}")


async def main():
    await run("task-status(404)", "/api/task-status/bench-miss")
    await run("downloads(cached)", "/api/downloads")
    await run("task-status(404) #2", "/api/task-status/bench-miss")


if __name__ == "__main__":
    asyncio.run(main())



