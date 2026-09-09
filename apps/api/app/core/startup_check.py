"""Standalone pre-flight config check for the production Docker entrypoint.

Why this exists (Milestone 10 review finding): `validate_production_safety`
also runs at `app.main` import time, but under `uvicorn --workers N` each
worker process imports `app.main` independently, and uvicorn's
multiprocess supervisor treats a worker that dies on import as a crash to
recover from -- it keeps respawning a new worker forever rather than
letting the failure stop the container. The result was an indefinite
crash loop (confirmed: dozens of repeated tracebacks within seconds, the
container never exits) instead of a clean, single, fast startup failure.

Running this script once, before uvicorn is even invoked (see
infra/docker/api.Dockerfile's production CMD, which `exec`s uvicorn only
after this succeeds), moves the check outside the per-worker respawn loop
entirely: an unsafe configuration now fails the container exactly once,
with a clear message and a non-zero exit code, and uvicorn never starts.
`app.main`'s own import-time check is left in place as defense in depth
for any invocation path that skips this script (e.g. running uvicorn
directly with a single worker, or embedding the app another way).
"""

import sys

from app.core.config import ConfigurationError, get_settings, validate_production_safety


def main() -> int:
    try:
        validate_production_safety(get_settings())
    except ConfigurationError as exc:
        print(f"STARTUP CHECK FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
