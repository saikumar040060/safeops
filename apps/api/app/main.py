from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.approvals import router as approvals_router
from app.api.audit import router as audit_router
from app.api.dashboard import router as dashboard_router
from app.api.executions import router as executions_router
from app.api.health import router as health_router
from app.api.security import router as security_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(approvals_router, prefix="/api")
app.include_router(executions_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(security_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
