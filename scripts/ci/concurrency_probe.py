#!/usr/bin/env python3
"""Opens N chat streams at once and insists every one of them ends in `done`.

Run by .github/workflows/compose-smoke.yml after scripts/smoke.sh, and by hand
against any running API. Depends on: httpx (`uv run --with httpx` or the api
venv) and a stack whose model is scripts/ci/stub_openai.py, so it costs nothing.
Load test, 2026-09-15: the SSE route deadlocks at exactly 20 (pool_size +
max_overflow), which is what this number is.
Usage: python scripts/ci/concurrency_probe.py [--base-url URL] [-n 20]
"""

import argparse
import asyncio
import json
import time

import httpx


async def one_stream(base_url: str, index: int) -> tuple[int, bool, float]:
    """Drive one stream; return (status, saw_done, seconds). Own client per
    stream so a per-session cookie (M20) belongs to exactly one session id."""
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        body = {"session_id": f"probe-{int(started)}-{index:03d}", "message": "Hello there"}
        async with client.stream("POST", f"{base_url}/api/chat/stream", json=body) as response:
            if response.status_code != 200:
                await response.aread()
                return response.status_code, False, time.perf_counter() - started
            done = False
            async for line in response.aiter_lines():
                if line.startswith("data: ") and json.loads(line[6:]).get("type") == "done":
                    done = True
            return 200, done, time.perf_counter() - started


async def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent SSE probe")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("-n", "--concurrency", type=int, default=20)
    # A stream that ends in `done` is not the whole bar: the pool deadlock ends
    # every stream in a `done` too, because the QueuePool timeout is caught and
    # templated into the fallback apology 30 s later. Below the cliff a stream
    # finishes in well under a second, so anything past this ceiling is the
    # failure mode wearing a success's clothes.
    parser.add_argument("--max-seconds", type=float, default=15.0)
    args = parser.parse_args()

    started = time.perf_counter()
    results = await asyncio.gather(
        *(one_stream(args.base_url, i) for i in range(args.concurrency)),
        return_exceptions=True,
    )
    wall = time.perf_counter() - started

    failures = [r for r in results if isinstance(r, Exception)]
    ok = [r for r in results if not isinstance(r, Exception)]
    server_errors = [r for r in ok if r[0] >= 500]
    no_done = [r for r in ok if r[0] == 200 and not r[1]]
    times = sorted(r[2] for r in ok) or [0.0]
    too_slow = [t for t in times if t > args.max_seconds]

    print(f"{args.concurrency} concurrent streams against {args.base_url} in {wall:.1f}s")
    print(f"  status codes : {sorted({r[0] for r in ok})}")
    print(f"  ended in done: {sum(1 for r in ok if r[1])}/{args.concurrency}")
    print(f"  p50 / max    : {times[len(times) // 2]:.1f}s / {times[-1]:.1f}s")
    for exc in failures[:3]:
        print(f"  transport err: {type(exc).__name__}: {exc}")

    if failures or server_errors or no_done or too_slow:
        print(
            f"::error::{len(server_errors)} 5xx, {len(no_done)} streams with no done event, "
            f"{len(too_slow)} over {args.max_seconds}s, {len(failures)} transport failures "
            f"at concurrency {args.concurrency}"
        )
        return 1
    print("  OK: zero 5xx, every stream ended in a done event")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
