"""Per-client rate limits for the endpoints that cost money (model calls and speech).

A sliding one-minute window per client IP and bucket, kept in memory (one replica). Limits are
generous for a person using the app, including a highlights reel that asks for every voice line
at once, but stop a script from burning the model and speech budget.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, WebSocket

LIMITS = {"tts": 150, "ai": 40, "ask": 20, "a2a": 30}  # requests per minute per client
WINDOW_S = 60.0

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def client_ip(conn: Request | WebSocket) -> str:
    """The caller's address; behind the Container Apps ingress it is the first X-Forwarded-For entry."""
    forwarded = conn.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return conn.client.host if conn.client else "unknown"


def allow(ip: str, bucket: str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    q = _hits[(ip, bucket)]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= LIMITS[bucket]:
        return False
    q.append(now)
    if len(_hits) > 10_000:  # drop idle clients so memory stays bounded
        for key in [k for k, v in _hits.items() if not v or now - v[-1] > WINDOW_S]:
            del _hits[key]
    return True


def check(request: Request, bucket: str) -> None:
    """FastAPI guard: 429 when the client is over its limit."""
    if not allow(client_ip(request), bucket):
        raise HTTPException(429, "Too many requests, try again in a minute", headers={"Retry-After": "30"})
