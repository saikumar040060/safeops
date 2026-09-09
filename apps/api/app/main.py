from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.approvals import router as approvals_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.executions import router as executions_router
from app.api.health import router as health_router
from app.api.integrations import router as integrations_router
from app.api.metrics import router as metrics_router
from app.api.ready import router as ready_router
from app.api.security import router as security_router
from app.core.config import get_settings, validate_production_safety
from app.core.database import SessionLocal
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import LatencyMiddleware
from app.core.request_context import RequestIDMiddleware
from app.core.security import ensure_bootstrap_admin
from app.core.security_headers import SecurityHeadersMiddleware

settings = get_settings()

# Fail fast: a misconfigured production process must never bind a socket
# and start serving traffic. Validated at import time, before the app
# object (and therefore uvicorn's server loop) even exists.
validate_production_safety(settings)

configure_logging("INFO" if settings.is_production else "DEBUG")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db = SessionLocal()
    try:
        ensure_bootstrap_admin(db, settings)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

register_exception_handlers(app)

# Middleware executes in reverse registration order for requests (last
# added runs first) -- request id must be established before anything else
# logs, so it is added last.
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
app.add_middleware(LatencyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

app.include_router(health_router, prefix="/api")
app.include_router(ready_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(approvals_router, prefix="/api")
app.include_router(executions_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(security_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
