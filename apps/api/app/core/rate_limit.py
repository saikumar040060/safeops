"""A simple in-process rate limiter appropriate to the current
architecture: a single Uvicorn worker process, no Redis/external cache.
Deliberately not distributed -- if this ever runs as multiple worker
processes or replicas, each would track its own counters independently.
That is an explicit, documented limitation, not an oversight; wiring up a
shared store (Redis, Postgres-backed counters) is future work once there is
more than one process to coordinate.

Keyed by authenticated operator id wherever one is available (every
endpoint this is applied to already requires authentication), never by a
caller-controlled header -- so a spoofed/malformed header cannot bypass the
limit or evict another operator's bucket. Fails open on any internal error:
this is an abuse/availability control, not the security boundary (RBAC is),
so a bug here must never turn into a full outage.
"""

import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException

_lock = Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(
    bucket: str, identity: uuid.UUID | str, *, max_requests: int, window_seconds: int
) -> None:
    try:
        key = f"{bucket}:{identity}"
        now = time.monotonic()
        with _lock:
            window = _buckets[key]
            while window and now - window[0] > window_seconds:
                window.popleft()
            if len(window) >= max_requests:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Slow down and try again.",
                    },
                )
            window.append(now)
    except HTTPException:
        raise
    except Exception:
        # Fail open: a bug in the limiter must never block legitimate
        # traffic on endpoints whose real security boundary is RBAC.
        return


def reset_all() -> None:
    """Test-only: clears every bucket so rate-limit tests don't leak state
    across test functions sharing this module-level store."""
    with _lock:
        _buckets.clear()
