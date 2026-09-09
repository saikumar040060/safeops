# Multi-stage: `dev` preserves the existing local docker-compose workflow
# unchanged; `production` is the hardened target (non-root, healthcheck,
# multi-worker ASGI server) used by docker-compose.prod.yml.

FROM python:3.13-slim AS base

WORKDIR /app

RUN groupadd --gid 1000 appuser && useradd --uid 1000 --gid appuser --create-home appuser

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api .
RUN chown -R appuser:appuser /app

EXPOSE 8000


FROM base AS dev

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM base AS production

USER appuser

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=2).status == 200 else 1)"

# Config is validated once here, before uvicorn (and therefore before any
# worker process) ever starts -- see app/core/startup_check.py for why
# this has to happen outside uvicorn's own worker-respawn loop rather than
# only at app.main import time. `exec` replaces this shell with uvicorn on
# success, so uvicorn still ends up as PID 1 and receives SIGTERM directly
# from the container runtime for a graceful shutdown.
#
# Known limitation: app.core.rate_limit and app.core.metrics keep their
# counters in-process (see their docstrings). With >1 worker each worker
# process gets an independent rate-limit bucket and latency snapshot, so
# the effective rate limit is looser than configured and /api/metrics
# reflects only the serving worker, not the whole instance. Acceptable for
# now per the milestone's "do not overengineer distributed rate limiting
# yet" scope; move to a shared store (Redis, or Postgres-backed counters)
# before relying on multi-worker deployments for either guarantee.
CMD ["sh", "-c", "python -m app.core.startup_check && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers"]
