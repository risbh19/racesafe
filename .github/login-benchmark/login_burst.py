import asyncio
import json
import math
import os
from collections import Counter
from pathlib import Path
from time import perf_counter

import jwt

COUNT = 10_000
HOST = "127.0.0.1"
PORT = 8000


async def open_client(source):
    return await asyncio.open_connection(HOST, PORT, local_addr=(source, 0))


def login_request(user, password):
    body = json.dumps({
        "email": f"login-{user}@benchmark.racesafe.test",
        "password": password,
    }).encode()
    return (
        f"POST /api/auth/login HTTP/1.1\r\nHost: {HOST}:{PORT}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode() + body


async def read_response(reader, user, secret):
    head = await reader.readuntil(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status = int(lines[0].split()[1])
    headers = dict(line.lower().split(b":", 1) for line in lines[1:] if b":" in line)
    body = await reader.readexactly(int(headers[b"content-length"]))
    if status == 200:
        claims = jwt.decode(json.loads(body)["access_token"], secret, algorithms=["HS256"], issuer="racesafe")
        if claims["sub"] != str(user):
            return "invalid_token"
    return str(status)


def distribution(values):
    if not values:
        return None
    values.sort()
    return {f"p{p}": round(values[math.ceil(len(values) * p / 100) - 1], 2) for p in (50, 95, 99)}


async def benchmark():
    mode = os.environ["LOGIN_BENCH_MODE"]
    password = os.environ["LOGIN_BENCH_PASSWORD"]
    secret = os.environ["JWT_SECRET"]
    reader, writer = await open_client("127.2.0.1")
    try:
        writer.write(login_request(1, password))
        await writer.drain()
        assert await asyncio.wait_for(read_response(reader, 1, secret), timeout=10) == "200"
    finally:
        writer.close()
        await writer.wait_closed()

    gate = asyncio.Event()
    connections = asyncio.Semaphore(200)
    ready = asyncio.Event()
    connected = 0

    async def attempt(user):
        nonlocal connected
        source = "127.0.0.1" if mode == "shared-ip" else f"127.1.{user // 256}.{user % 256}"
        async with connections:
            reader, writer = await asyncio.wait_for(open_client(source), timeout=15)
        connected += 1
        if connected == COUNT:
            ready.set()
        try:
            await gate.wait()
            started = perf_counter()
            try:
                writer.write(login_request(user, password))
                await writer.drain()
                outcome = await asyncio.wait_for(read_response(reader, user, secret), timeout=120)
            except TimeoutError:
                outcome = "client_timeout"
            except (OSError, ValueError, KeyError, IndexError, asyncio.IncompleteReadError, jwt.InvalidTokenError) as exc:
                outcome = type(exc).__name__
            return outcome, started, perf_counter()
        finally:
            writer.close()

    tasks = [asyncio.create_task(attempt(user)) for user in range(1, COUNT + 1)]
    try:
        await asyncio.wait_for(ready.wait(), timeout=60)
        gate.set()
        results = await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    counts = Counter(result for result, _, _ in results)
    by_outcome = {
        status: distribution([(end - start) * 1000 for result, start, end in results if result == status])
        for status in counts
    }
    events = sorted((when, delta) for _, start, end in results for when, delta in ((start, 1), (end, -1)))
    peak = pending = 0
    for _, delta in events:
        pending += delta
        peak = max(peak, pending)
    starts = [start for _, start, _ in results]
    report = {
        "mode": mode,
        "attempts": len(results),
        "source_ips": 1 if mode == "shared-ip" else COUNT,
        "outcomes": dict(sorted(counts.items())),
        "latency_ms_by_outcome": by_outcome,
        "peak_outstanding_requests": peak,
        "dispatch_spread_ms": round((max(starts) - min(starts)) * 1000, 2),
        "burst_completion_s": round(max(end for _, _, end in results) - min(starts), 3),
    }
    formatted = json.dumps(report, indent=2) + "\n"
    Path("login-benchmark.json").write_text(formatted, encoding="utf-8")
    print(formatted)


asyncio.run(benchmark())
