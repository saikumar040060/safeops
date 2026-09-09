"""Minimal in-process request-latency + event-counter tracking, in the
same spirit as app/core/rate_limit.py: plain dicts guarded by a lock,
appropriate for the current single-process architecture. Most of
/api/metrics is derived directly from durable state (row counts), which is
naturally correct across restarts and multiple workers -- these two
in-process trackers exist only for events that deliberately never persist
any row (auth failures, idempotency conflicts), so there is nothing
durable to count them from. Same documented limitation as
app/core/rate_limit.py: with >1 worker each process has independent
counts, not a combined total."""

import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_lock = Lock()
_latency: dict[str, dict[str, float]] = {}

_counters_lock = Lock()
_counters: dict[str, int] = defaultdict(int)


def increment_counter(name: str) -> None:
    with _counters_lock:
        _counters[name] += 1


def snapshot_counters() -> dict[str, int]:
    with _counters_lock:
        return dict(_counters)


class LatencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start
        route = request.scope.get("route")
        key = f"{request.method} {route.path if route else request.url.path}"
        with _lock:
            bucket = _latency.setdefault(
                key, {"count": 0, "total_seconds": 0.0, "max_seconds": 0.0}
            )
            bucket["count"] += 1
            bucket["total_seconds"] += elapsed
            bucket["max_seconds"] = max(bucket["max_seconds"], elapsed)
        return response


def snapshot_latency() -> dict[str, dict[str, float]]:
    with _lock:
        return {
            route: {
                "count": b["count"],
                "avg_ms": round((b["total_seconds"] / b["count"]) * 1000, 2) if b["count"] else 0,
                "max_ms": round(b["max_seconds"] * 1000, 2),
            }
            for route, b in _latency.items()
        }
