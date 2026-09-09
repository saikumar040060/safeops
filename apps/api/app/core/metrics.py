"""Minimal in-process request-latency tracking, in the same spirit as
app/core/rate_limit.py: a single dict guarded by a lock, appropriate for
the current single-process architecture. Everything else /api/metrics
reports is derived directly from durable state (row counts), which is
naturally correct across restarts and multiple workers without needing a
shared counter store -- only latency needs live in-process tracking."""

import time
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_lock = Lock()
_latency: dict[str, dict[str, float]] = {}


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
